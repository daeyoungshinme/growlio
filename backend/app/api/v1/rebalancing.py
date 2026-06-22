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

from app.api.deps import get_current_user
from app.database import get_db
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
    RebalancingAnalysis,
)
from app.schemas.service_dtypes import DividendMapEntry, ReturnsMapEntry
from app.services.credential_service import decrypt
from app.services.dividend.orchestrator import get_ticker_dividend_summary
from app.services.dividend_constants import is_korean_etf
from app.services.dividend_providers import (
    sync_naver_etf_dividend_info,
    sync_naver_stock_dividend_info,
    sync_yahoo_dividend_info,
)
from app.services.portfolio_service import build_portfolio_overview
from app.services.price_service import fetch_prices_batch, get_historical_returns
from app.services.rebalancing_service import analyze_rebalancing
from app.services.yahoo_price import to_yf_symbol as _to_yahoo_symbol
from app.utils.currency import get_usd_krw_rate

router = APIRouter(prefix="/rebalancing", tags=["rebalancing"])
logger = structlog.get_logger()


@router.get("/portfolios/{portfolio_id}/analyze", response_model=RebalancingAnalysis)
@limiter.limit("5/minute")
async def analyze_portfolio(
    request: Request,
    portfolio_id: uuid.UUID,
    account_ids: list[uuid.UUID] | None = Query(default=None),
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

    # query param 우선, 없으면 portfolio에 저장된 account_ids 사용, 그것도 없으면 전체 계좌
    saved_ids = getattr(portfolio, "account_ids", None)
    effective_account_ids = account_ids or ([uuid.UUID(aid) for aid in saved_ids] if saved_ids else None)
    overview = await build_portfolio_overview(current_user.id, db, account_ids=effective_account_ids)

    dividend_items = await get_ticker_dividend_summary(current_user.id, db)
    dividend_map = {(item["ticker"], item["market"]): item for item in dividend_items if item.get("ticker")}

    # 목표 포트폴리오 종목 중 현재 미보유(dividend_map에 없음)인 종목 배당수익률 보완
    loop = asyncio.get_running_loop()
    _sem = asyncio.Semaphore(3)

    async def _fetch_dividend(raw_item) -> None:
        ticker = raw_item["ticker"] if isinstance(raw_item, dict) else raw_item.ticker
        market = raw_item["market"] if isinstance(raw_item, dict) else raw_item.market
        if ticker == "CASH" or market == "KR_PROPERTY":
            return
        key = (ticker, market)
        if key in dividend_map:
            return
        is_korean = market.upper() in ("KOSPI", "KOSDAQ", "KRX")
        try:
            async with _sem:
                if is_korean:
                    is_etf = is_korean_etf(ticker, market)
                    fn = sync_naver_etf_dividend_info if is_etf else sync_naver_stock_dividend_info
                    naver_info = await loop.run_in_executor(None, partial(fn, ticker))
                    if naver_info["dividend_yield"] > 0:
                        dividend_map[key] = {
                            "ticker": ticker,
                            "market": market,
                            "dividend_yield": naver_info["dividend_yield"] * 100,
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

    await asyncio.gather(*[_fetch_dividend(item) for item in portfolio.items])

    # 목표 포트폴리오 종목 10년 수익률 수집 (CASH 제외)
    target_tickers = [
        (
            raw_item["ticker"] if isinstance(raw_item, dict) else raw_item.ticker,
            raw_item["market"] if isinstance(raw_item, dict) else raw_item.market,
        )
        for raw_item in portfolio.items
        if (raw_item["ticker"] if isinstance(raw_item, dict) else raw_item.ticker) != "CASH"
        and (raw_item["market"] if isinstance(raw_item, dict) else raw_item.market) != "KR_PROPERTY"
    ]
    # 현재 보유 종목도 포함 (배당 포트폴리오처럼 목표와 현재 보유가 다를 경우 current CAGR 계산을 위해)
    current_tickers = [
        (p["ticker"], p["market"])
        for p in overview.get("all_positions", [])
        if p.get("ticker") and p.get("ticker") != "CASH"
    ]
    all_return_tickers = list(set(target_tickers) | set(current_tickers))
    returns_map = await get_historical_returns(all_return_tickers, redis=redis)

    # 미보유 목표 종목 현재가 보완: all_positions에 없는 종목은 current_price=None → shares=None
    existing_price_keys: set[tuple[str, str]] = {
        (pos["ticker"], pos["market"]) for pos in overview.get("all_positions", []) if pos.get("current_price")
    }
    unpriced: list[tuple[str, str]] = [
        (
            raw_item["ticker"] if isinstance(raw_item, dict) else raw_item.ticker,
            raw_item["market"] if isinstance(raw_item, dict) else raw_item.market,
        )
        for raw_item in portfolio.items
        if (raw_item["ticker"] if isinstance(raw_item, dict) else raw_item.ticker) != "CASH"
        and (raw_item["market"] if isinstance(raw_item, dict) else raw_item.market) != "KR_PROPERTY"
        and (
            raw_item["ticker"] if isinstance(raw_item, dict) else raw_item.ticker,
            raw_item["market"] if isinstance(raw_item, dict) else raw_item.market,
        )
        not in existing_price_keys
    ]
    if unpriced:
        fetched_prices = await fetch_prices_batch(current_user.id, unpriced, db, redis)
        extra_positions = [
            {
                "ticker": ticker,
                "market": market,
                "name": next(
                    (
                        raw_item["name"] if isinstance(raw_item, dict) else raw_item.name
                        for raw_item in portfolio.items
                        if (raw_item["ticker"] if isinstance(raw_item, dict) else raw_item.ticker) == ticker
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
        if extra_positions:
            overview = {**overview, "all_positions": list(overview.get("all_positions", [])) + extra_positions}

    return analyze_rebalancing(
        portfolio,
        overview,
        cast(dict[tuple[str, str], DividendMapEntry], dividend_map),
        cast(dict[tuple[str, str], ReturnsMapEntry], returns_map),
    )


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
            account.kiwoom_account_no,  # type: ignore[arg-type]
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
    account = await db.scalar(
        select(AssetAccount).where(
            AssetAccount.id == account_id,
            AssetAccount.user_id == current_user.id,
        )
    )
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
    acc_result = await db.execute(
        select(AssetAccount).where(
            AssetAccount.user_id == current_user.id,
            AssetAccount.asset_type.in_(["STOCK_KIS", "STOCK_KIWOOM"]),
            AssetAccount.is_active == True,  # noqa: E712
        )
    )
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
