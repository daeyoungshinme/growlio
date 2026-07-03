"""리밸런싱 분석 및 브로커 잔고 API."""

import asyncio
import uuid
from functools import partial
from typing import cast

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db
from app.constants import DOMESTIC_MARKETS
from app.kis.auth import get_access_token
from app.kis.balance import get_domestic_balance, get_orderable_cash
from app.kis.client import KisApiError
from app.kiwoom.auth import get_access_token as kiwoom_get_access_token
from app.kiwoom.balance import get_domestic_balance as kiwoom_get_domestic_balance
from app.limiter import limiter
from app.models.asset import AssetAccount
from app.models.portfolio import Portfolio
from app.models.user import User
from app.redis_client import get_redis
from app.schemas.rebalancing import (
    KisBalancePosition,
    KisBalanceResponse,
    PortfolioDriftSummary,
    RebalancingAnalysis,
)
from app.schemas.service_dtypes import DividendMapEntry, ReturnsMapEntry
from app.services._account_queries import active_broker_accounts_stmt, get_account_including_inactive
from app.services._portfolio_queries import get_active_alert_thresholds, get_linked_portfolios
from app.services.credential_service import decrypt
from app.services.dividend.orchestrator import get_ticker_dividend_summary
from app.services.dividend_constants import is_korean_etf
from app.services.dividend_sync_sources import (
    sync_naver_etf_dividend_info,
    sync_naver_stock_dividend_info,
    sync_yahoo_dividend_info,
)
from app.services.portfolio_service import build_portfolio_overview
from app.services.price_service import fetch_prices_batch, get_historical_returns
from app.services.rebalancing_diagnosis_service import (
    build_diagnosis_context,
    check_composite_signal,
    fetch_market_and_risk_signal,
)
from app.services.rebalancing_service import _item_attr, analyze_rebalancing, compute_portfolio_drift_summary
from app.services.yahoo_price import to_yf_symbol as _to_yahoo_symbol
from app.utils.currency import get_usd_krw_rate

router = APIRouter(prefix="/rebalancing", tags=["rebalancing"])
logger = structlog.get_logger()


async def _collect_dividend_map(
    portfolio: Portfolio,
    base_dividend_map: dict,
) -> dict:
    """목표 포트폴리오 중 미보유 종목의 배당수익률을 Naver/Yahoo에서 보완한다.

    배당 fetcher는 yfinance 가격 조회와 별개 I/O이므로 Semaphore(8)로 더 높은 동시성을 허용한다.
    """
    dividend_map = dict(base_dividend_map)
    loop = asyncio.get_running_loop()
    sem = asyncio.Semaphore(8)

    async def _fetch_one(raw_item) -> None:
        ticker = str(_item_attr(raw_item, "ticker"))
        market = str(_item_attr(raw_item, "market"))
        if ticker == "CASH" or market == "KR_PROPERTY":
            return
        key = (ticker, market)
        if key in dividend_map:
            return
        is_korean = market.upper() in DOMESTIC_MARKETS
        try:
            async with sem:
                if is_korean:
                    is_etf = is_korean_etf(ticker, market)
                    fn = sync_naver_etf_dividend_info if is_etf else sync_naver_stock_dividend_info
                    info = await loop.run_in_executor(None, partial(fn, ticker))
                    if info["dividend_yield"] > 0:
                        dividend_map[key] = {
                            "ticker": ticker,
                            "market": market,
                            "dividend_yield": info["dividend_yield"] * 100,
                            "estimated_annual_krw": 0.0,
                        }
                else:
                    yahoo_sym = _to_yahoo_symbol(ticker, market)
                    info = await loop.run_in_executor(None, partial(sync_yahoo_dividend_info, yahoo_sym))
                    if info["dividend_yield"] > 0:
                        dividend_map[key] = {
                            "ticker": ticker,
                            "market": market,
                            "dividend_yield": info["dividend_yield"] * 100,
                            "estimated_annual_krw": 0.0,
                        }
        except Exception as e:
            logger.warning("dividend_fetch_failed", ticker=ticker, market=market, error=str(e))

    await asyncio.gather(*[_fetch_one(item) for item in portfolio.items])
    return dividend_map


async def _enrich_overview_with_prices(
    portfolio: Portfolio,
    overview: dict,
    user_id: uuid.UUID,
    db,
    redis,
) -> dict:
    """목표 포트폴리오 중 미보유 종목의 현재가를 조회해 overview에 보완한다."""
    existing_price_keys: set[tuple[str, str]] = {
        (pos["ticker"], pos["market"]) for pos in overview.get("all_positions", []) if pos.get("current_price")
    }
    unpriced: list[tuple[str, str]] = [
        (str(_item_attr(raw_item, "ticker")), str(_item_attr(raw_item, "market")))
        for raw_item in portfolio.items
        if str(_item_attr(raw_item, "ticker")) != "CASH"
        and str(_item_attr(raw_item, "market")) != "KR_PROPERTY"
        and (str(_item_attr(raw_item, "ticker")), str(_item_attr(raw_item, "market"))) not in existing_price_keys
    ]
    if not unpriced:
        return overview

    fetched_prices = await fetch_prices_batch(user_id, unpriced, db, redis)
    extra_positions = [
        {
            "ticker": ticker,
            "market": market,
            "name": next(
                (
                    str(_item_attr(raw_item, "name"))
                    for raw_item in portfolio.items
                    if str(_item_attr(raw_item, "ticker")) == ticker
                ),
                ticker,
            ),
            "value_krw": 0.0,
            "current_price": fetched_prices[ticker],
            "qty": 0.0,
        }
        for ticker, market in unpriced
        if ticker in fetched_prices and fetched_prices[ticker] > 0
    ]
    if not extra_positions:
        return overview
    return {**overview, "all_positions": list(overview.get("all_positions", [])) + extra_positions}


@router.get("/portfolios/{portfolio_id}/analyze", response_model=RebalancingAnalysis)
@limiter.limit("5/minute")
async def analyze_portfolio(
    request: Request,
    portfolio_id: uuid.UUID,
    account_ids: list[uuid.UUID] | None = Query(default=None),
    deposit_krw_override: float | None = Query(default=None, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """현재 자산과 목표 포트폴리오를 비교해 리밸런싱 제안을 반환한다."""
    portfolio = await db.scalar(
        select(Portfolio)
        .options(
            selectinload(Portfolio.linked_accounts),
            selectinload(Portfolio.items),
        )
        .where(
            Portfolio.id == portfolio_id,
            Portfolio.user_id == current_user.id,
        )
    )
    if not portfolio:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="포트폴리오를 찾을 수 없습니다")

    portfolio_acct_ids = [uuid.UUID(aid) for aid in portfolio.account_ids] if portfolio.account_ids else None
    effective_ids = account_ids if account_ids is not None else portfolio_acct_ids
    overview = await build_portfolio_overview(current_user.id, db, account_ids=effective_ids)

    base_dividend_items = await get_ticker_dividend_summary(current_user.id, db)
    base_dividend_map = {(item["ticker"], item["market"]): item for item in base_dividend_items if item.get("ticker")}
    dividend_map = await _collect_dividend_map(portfolio, base_dividend_map)

    target_tickers = [
        (str(_item_attr(raw_item, "ticker")), str(_item_attr(raw_item, "market")))
        for raw_item in portfolio.items
        if str(_item_attr(raw_item, "ticker")) != "CASH" and str(_item_attr(raw_item, "market")) != "KR_PROPERTY"
    ]
    current_tickers = [
        (p["ticker"], p["market"])
        for p in overview.get("all_positions", [])
        if p.get("ticker") and p.get("ticker") != "CASH"
    ]
    returns_map = await get_historical_returns(list(set(target_tickers) | set(current_tickers)), redis=redis)

    overview = await _enrich_overview_with_prices(portfolio, overview, current_user.id, db, redis)

    if deposit_krw_override is not None:
        old_deposit = float(overview.get("total_deposit_krw") or 0)
        delta = deposit_krw_override - old_deposit
        overview = {
            **overview,
            "total_deposit_krw": deposit_krw_override,
            "total_assets_krw": float(overview.get("total_assets_krw", 0)) + delta,
        }

    analysis = analyze_rebalancing(
        portfolio,
        overview,
        cast(dict[tuple[str, str], DividendMapEntry], dividend_map),
        cast(dict[tuple[str, str], ReturnsMapEntry], returns_map),
    )

    try:
        analysis.diagnosis_context = await build_diagnosis_context(current_user.id, db, redis, analysis, overview)
    except Exception as e:
        logger.warning("diagnosis_context_build_failed", portfolio_id=str(portfolio_id), error=str(e))
        analysis.diagnosis_context = None

    return analysis


async def _fetch_broker_balance(
    account: AssetAccount,
    db: AsyncSession,
    redis,
    usd_rate: float | None = None,
) -> KisBalanceResponse:
    """KIS 또는 키움 계좌 실시간 잔고를 조회해 KisBalanceResponse로 반환한다. 실패 시 예외 발생."""
    if account.asset_type == "STOCK_KIS":
        if not account.kis_account_no:
            raise ValueError("계좌번호가 설정되지 않았습니다.")
        if not account.kis_app_key or not account.kis_app_secret:
            raise ValueError("KIS 자격증명이 설정되지 않았습니다. 계좌 설정에서 App Key와 App Secret을 입력해주세요.")

        app_key = decrypt(account.kis_app_key)
        app_secret = decrypt(account.kis_app_secret)
        is_mock = account.is_mock_mode
        access_token = await get_access_token(
            app_key,
            app_secret,
            is_mock=is_mock,
            redis=redis,
            db=db,
            user_id=str(account.user_id),
            account_id=str(account.id),
        )
        domestic = await get_domestic_balance(
            app_key, app_secret, access_token, account.kis_account_no, is_mock=is_mock
        )
        try:
            orderable = await get_orderable_cash(
                app_key, app_secret, access_token, account.kis_account_no, is_mock=is_mock
            )
        except Exception as e:
            logger.warning("orderable_cash_fetch_failed", account_id=str(account.id), error=str(e))
            orderable = None
        positions: list[KisBalancePosition] = [
            KisBalancePosition(
                ticker=p["ticker"],
                name=p["name"],
                market=p["market"],
                quantity=int(p["qty"]),
                avg_price=float(p["avg_price"]),
                current_price=float(p["current_price"]),
                value_krw=float(p["value_krw"]),
            )
            for p in domestic.get("positions", [])
        ]
        return KisBalanceResponse(
            account_id=str(account.id),
            account_name=account.name,
            is_mock=is_mock,
            positions=positions,
            deposit_krw=float(domestic.get("deposit_krw", 0)),
            orderable_krw=orderable,
        )

    if account.asset_type == "STOCK_KIWOOM":
        if not account.kiwoom_app_key or not account.kiwoom_app_secret:
            raise ValueError("키움 API 자격증명이 설정되지 않았습니다.")
        if not account.kiwoom_account_no:
            raise ValueError("키움 계좌번호가 설정되지 않았습니다.")

        app_key = decrypt(account.kiwoom_app_key)
        app_secret = decrypt(account.kiwoom_app_secret)
        is_mock = account.is_mock_mode
        access_token = await kiwoom_get_access_token(
            app_key,
            app_secret,
            is_mock=is_mock,
            redis=redis,
            db=db,
            user_id=str(account.user_id),
            account_id=str(account.id),
        )
        domestic = await kiwoom_get_domestic_balance(
            access_token,
            account.kiwoom_account_no,
            is_mock=is_mock,
        )
        positions = [
            KisBalancePosition(
                ticker=p["ticker"],
                name=p["name"],
                market=p["market"],
                quantity=int(p["qty"]),
                avg_price=float(p["avg_price"]),
                current_price=float(p["current_price"]),
                value_krw=float(p["value_krw"]),
            )
            for p in domestic.get("positions", [])
        ]
        return KisBalanceResponse(
            account_id=str(account.id),
            account_name=account.name,
            is_mock=is_mock,
            positions=positions,
            deposit_krw=float(domestic.get("deposit_krw", 0)),
        )

    raise ValueError(f"지원하지 않는 계좌 유형: {account.asset_type}")


@router.get("/broker-balance/{account_id}", response_model=KisBalanceResponse)
@limiter.limit("10/minute")
async def get_broker_account_balance(
    request: Request,
    account_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """KIS 또는 키움 계좌의 실시간 보유 종목 잔고를 조회한다 (비활성 계좌 포함)."""
    account = await get_account_including_inactive(db, account_id, current_user.id)
    if not account:
        logger.warning(
            "broker_balance_account_not_found",
            account_id=str(account_id),
            user_id=str(current_user.id),
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="계좌를 찾을 수 없습니다")
    if account.asset_type not in ("STOCK_KIS", "STOCK_KIWOOM"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="KIS 또는 키움 계좌만 잔고 조회가 가능합니다",
        )

    usd_rate = await get_usd_krw_rate(redis)
    try:
        return await _fetch_broker_balance(account, db, redis, usd_rate)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except KisApiError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"KIS API 응답 오류 (코드: {e.rt_cd}). 잠시 후 다시 시도해주세요.",
        ) from e


@router.get("/broker-balance-all", response_model=list[KisBalanceResponse])
@limiter.limit("5/minute")
async def get_all_broker_balances(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """연동된 모든 활성 KIS/키움 계좌의 실시간 잔고를 병렬로 조회한다."""
    acc_result = await db.execute(active_broker_accounts_stmt(current_user.id))
    accounts = acc_result.scalars().all()

    if not accounts:
        return []

    usd_rate = await get_usd_krw_rate(redis)
    tasks = [_fetch_broker_balance(acc, db, redis, usd_rate) for acc in accounts]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    return [
        r
        if not isinstance(r, Exception)
        else KisBalanceResponse(
            account_id=str(acc.id),
            account_name=acc.name,
            is_mock=acc.is_mock_mode,
            positions=[],
            deposit_krw=0.0,
            error=str(r),
        )
        for acc, r in zip(accounts, results, strict=False)
    ]


@router.get("/drift-summary", response_model=list[PortfolioDriftSummary])
@limiter.limit("10/minute")
async def get_drift_summary(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """모든 포트폴리오의 비중 이탈 현황을 빠르게 반환한다 (배당·수익률 외부 API 미사용)."""
    portfolios = await get_linked_portfolios(db, current_user.id)
    if not portfolios:
        return []

    alert_by_portfolio = await get_active_alert_thresholds(db, current_user.id)

    # 시장상황/리스크는 유저 단위 신호이므로 포트폴리오 루프 밖에서 1회만 조회한다.
    has_composite_signal = False
    composite_reason: str | None = None
    try:
        market_level, risk = await fetch_market_and_risk_signal(current_user.id, db, redis)
        has_composite_signal, composite_reason = check_composite_signal(
            market_level,
            bool(risk.get("data_available")),
            risk.get("diversification_score"),
            risk.get("top_holding_weight_pct"),
            risk.get("annualized_volatility_pct"),
        )
    except Exception as e:
        logger.warning("drift_summary_composite_signal_failed", error=str(e))

    summaries: list[PortfolioDriftSummary] = []
    for portfolio in portfolios:
        try:
            portfolio_account_ids = getattr(portfolio, "account_ids", None)
            effective_ids = [uuid.UUID(aid) for aid in portfolio_account_ids] if portfolio_account_ids else None
            overview = await build_portfolio_overview(current_user.id, db, account_ids=effective_ids)
            threshold = alert_by_portfolio.get(str(portfolio.id), 5.0)
            summary = compute_portfolio_drift_summary(portfolio, overview, threshold)
            summary.has_composite_signal = has_composite_signal
            summary.composite_reason = composite_reason
            summary.has_alert_configured = str(portfolio.id) in alert_by_portfolio
            summaries.append(summary)
        except Exception as e:
            logger.error(
                "drift_summary_failed",
                portfolio_id=str(portfolio.id),
                error=str(e),
                exc_type=type(e).__name__,
            )

    return summaries
