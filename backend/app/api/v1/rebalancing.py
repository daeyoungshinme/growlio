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
from app.kis.balance import get_orderable_cash
from app.limiter import limiter
from app.models.asset import AssetAccount
from app.models.portfolio import Portfolio
from app.models.user import User
from app.providers.base import BrokerProvider
from app.providers.kis_provider import KISProvider
from app.providers.kiwoom_provider import KiwoomProvider
from app.redis_client import get_redis
from app.schemas.rebalancing import (
    CompositeSignalStatus,
    GoalRecommendation,
    HorizonRecommendationResponse,
    KisBalancePosition,
    KisBalanceResponse,
    PortfolioDriftSummary,
    RebalancingAnalysis,
)
from app.schemas.service_dtypes import DividendMapEntry, ReturnsMapEntry
from app.services._account_queries import active_broker_accounts_stmt, get_account_including_inactive
from app.services._portfolio_queries import get_active_alert_thresholds, get_linked_portfolios
from app.services._settings_queries import get_or_create_settings, get_settings_row
from app.services.credential_service import decrypt
from app.services.dividend.orchestrator import get_ticker_dividend_summary
from app.services.dividend_constants import is_korean_etf
from app.services.dividend_sync_sources import (
    sync_naver_etf_dividend_info,
    sync_naver_stock_dividend_info,
    sync_yahoo_dividend_info,
)
from app.services.goal_recommendation_service import (
    existing_items_from_positions,
    get_goal_recommendation,
    get_horizon_recommendations,
)
from app.services.portfolio_service import build_portfolio_overview
from app.services.position_aggregator import query_latest_position_map
from app.services.price_service import fetch_prices_batch, get_historical_returns
from app.services.rebalancing.diagnosis_service import (
    build_diagnosis_context,
    check_composite_signal,
    fetch_market_and_risk_signal,
)
from app.services.rebalancing.service import (
    _item_attr,
    analyze_rebalancing,
    compute_portfolio_drift_summary,
)
from app.services.yahoo_price import to_yf_symbol as _to_yahoo_symbol

router = APIRouter(prefix="/rebalancing", tags=["rebalancing"])
logger = structlog.get_logger()

_DIVIDEND_FETCH_CONCURRENCY = 8  # yfinance 가격 조회와 별개 I/O이므로 더 높은 동시성 허용


async def _collect_dividend_map(
    portfolio: Portfolio,
    base_dividend_map: dict,
) -> dict:
    """목표 포트폴리오 중 미보유 종목의 배당수익률을 Naver/Yahoo에서 보완한다."""
    dividend_map = dict(base_dividend_map)
    loop = asyncio.get_running_loop()
    sem = asyncio.Semaphore(_DIVIDEND_FETCH_CONCURRENCY)

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
        settings_row = await get_settings_row(db, current_user.id)
        enable_composite_signals = settings_row.composite_signal_alerts_enabled if settings_row else True
        analysis.diagnosis_context = await build_diagnosis_context(
            current_user.id,
            db,
            redis,
            analysis,
            overview,
            enable_composite_signals=enable_composite_signals,
            settings_row=settings_row,
        )
    except Exception as e:
        logger.warning("diagnosis_context_build_failed", portfolio_id=str(portfolio_id), error=str(e))
        analysis.diagnosis_context = None

    return analysis


@router.get("/goal-recommendation", response_model=GoalRecommendation)
@limiter.limit("5/minute")
async def get_overall_goal_recommendation_endpoint(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """전체 계좌(전체 투자현황) 기준으로 목표 역산 추천을 반환한다 (자동 적용 아님)."""
    overview = await build_portfolio_overview(current_user.id, db, redis=redis)
    settings_row = await get_settings_row(db, current_user.id)

    base_krw = float(overview.get("total_assets_krw", 0))
    pos_map = await query_latest_position_map(current_user.id, db, include_name=True)
    existing_items = existing_items_from_positions(pos_map)
    return await get_goal_recommendation(redis, base_krw, existing_items, settings_row, db)


@router.get("/goal-recommendation/by-horizon", response_model=HorizonRecommendationResponse)
@limiter.limit("5/minute")
async def get_horizon_goal_recommendation_endpoint(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """계좌에 태그된 투자기간(단기/중기/장기)별로 리스크 성향이 다른 추천을 반환한다 (자동 적용 아님).

    목표금액/목표연도 설정과 무관하게 동작한다 — `/goal-recommendation`(전체 자산 기준 목표 역산)과는
    별개의 기능이며, 두 엔드포인트 모두 그대로 유지된다.
    """
    settings_row = await get_or_create_settings(db, current_user.id)
    return await get_horizon_recommendations(redis, db, current_user.id, settings_row)


async def _fetch_broker_balance(
    account: AssetAccount,
    db: AsyncSession,
    redis,
) -> KisBalanceResponse:
    """KIS 또는 키움 계좌 실시간 잔고를 조회해 KisBalanceResponse로 반환한다.

    실제 조회는 BrokerProvider(KISProvider/KiwoomProvider)에 위임한다 — 자격증명 검증,
    토큰 갱신-재시도, 원화 포지션 변환은 sync_account()가 쓰는 것과 동일한 provider
    경로를 공유한다. 실패 시 SyncError 계층 예외(ProviderCredentialError 등)가 그대로
    전파되며 main.py 전역 핸들러가 HTTP 응답으로 변환한다.
    """
    if account.asset_type == "STOCK_KIS":
        provider: BrokerProvider = KISProvider()
    elif account.asset_type == "STOCK_KIWOOM":
        provider = KiwoomProvider()
    else:
        raise ValueError(f"지원하지 않는 계좌 유형: {account.asset_type}")

    result = await provider.sync(account, db, redis)

    orderable_krw: float | None = None
    if account.asset_type == "STOCK_KIS" and account.kis_app_key and account.kis_app_secret and account.kis_account_no:
        try:
            app_key = decrypt(account.kis_app_key)
            app_secret = decrypt(account.kis_app_secret)
            access_token = await get_access_token(
                app_key,
                app_secret,
                is_mock=account.is_mock_mode,
                redis=redis,
                db=db,
                user_id=str(account.user_id),
                account_id=str(account.id),
            )
            orderable_krw = await get_orderable_cash(
                app_key, app_secret, access_token, account.kis_account_no, is_mock=account.is_mock_mode
            )
        except Exception as e:
            logger.warning("orderable_cash_fetch_failed", account_id=str(account.id), error=str(e))

    positions = [
        KisBalancePosition(
            ticker=p.ticker,
            name=p.name,
            market=p.market,
            quantity=p.qty,
            avg_price=p.avg_price,
            current_price=p.current_price,
            value_krw=p.value_krw,
        )
        for p in result.positions
    ]
    return KisBalanceResponse(
        account_id=str(account.id),
        account_name=account.name,
        is_mock=account.is_mock_mode,
        positions=positions,
        deposit_krw=result.deposit_krw,
        orderable_krw=orderable_krw,
    )


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

    try:
        return await _fetch_broker_balance(account, db, redis)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


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

    tasks = [_fetch_broker_balance(acc, db, redis) for acc in accounts]
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
        settings_row = await get_settings_row(db, current_user.id)
        enable_composite_signals = settings_row.composite_signal_alerts_enabled if settings_row else True
        if enable_composite_signals:
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


@router.get("/composite-signal", response_model=CompositeSignalStatus)
@limiter.limit("30/minute")
async def get_composite_signal_status(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """진단탭 상단 배너 전용 — 포트폴리오 컨텍스트 없이 유저 단위 복합신호(시장/리스크) 상태만 반환."""
    settings_row = await get_settings_row(db, current_user.id)
    enabled = settings_row.composite_signal_alerts_enabled if settings_row else True

    alert_by_portfolio = await get_active_alert_thresholds(db, current_user.id)
    has_active_alert = bool(alert_by_portfolio)

    triggered = False
    reason: str | None = None
    if enabled:
        try:
            market_level, risk = await fetch_market_and_risk_signal(current_user.id, db, redis)
            triggered, reason = check_composite_signal(
                market_level,
                bool(risk.get("data_available")),
                risk.get("diversification_score"),
                risk.get("top_holding_weight_pct"),
                risk.get("annualized_volatility_pct"),
            )
        except Exception as e:
            logger.warning("composite_signal_status_failed", error=str(e))

    return CompositeSignalStatus(enabled=enabled, triggered=triggered, reason=reason, has_active_alert=has_active_alert)
