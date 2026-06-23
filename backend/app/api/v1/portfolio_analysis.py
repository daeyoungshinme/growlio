"""포트폴리오 API — 전체 계좌 통합 조회."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.enums import DataSource
from app.kis.balance import get_domestic_balance, get_overseas_balance
from app.limiter import limiter
from app.models.asset import AssetAccount
from app.models.user import User
from app.redis_client import get_redis
from app.schemas.portfolio import PortfolioSummaryResponse
from app.services.credential_service import get_kis_user_credentials
from app.services.factor_service import get_factor_analysis, get_factor_analysis_for_portfolio
from app.services.portfolio_history_service import get_allocation_history
from app.services.portfolio_optimizer import get_efficient_frontier
from app.services.portfolio_service import build_portfolio_overview
from app.services.rebalancing_strategy_service import get_rebalancing_strategy
from app.services.risk_service import (
    get_currency_exposure,
    get_portfolio_risk_metrics,
)
from app.utils.cache_keys import TTL_PORTFOLIO_SUMMARY, get_cached_json, portfolio_summary_key, set_cached_json

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("/allocation-history")
@limiter.limit("20/minute")
async def portfolio_allocation_history(
    request: Request,
    months: int = Query(default=12, ge=3, le=36),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """월별 자산 유형별 배분 이력 — 최근 N개월."""
    redis = await get_redis()
    return await get_allocation_history(current_user.id, db, months=months, redis=redis)


@router.get("/overview")
@limiter.limit("10/minute")
async def portfolio_overview(
    request: Request,
    lite: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """모든 계좌 자산을 통합해 포트폴리오 전체 현황을 반환한다."""
    redis = await get_redis()
    return await build_portfolio_overview(current_user.id, db, redis=redis, lite=lite)


@router.get("/summary", response_model=PortfolioSummaryResponse)
@limiter.limit("5/minute")
async def portfolio_summary(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """KIS 등록 계좌 전체 실시간 포트폴리오 집계."""
    redis = await get_redis()
    cache_key = portfolio_summary_key(current_user.id)
    cached = await get_cached_json(redis, cache_key)
    if cached is not None:
        return cached

    kis_creds = await get_kis_user_credentials(current_user.id, db)
    if not kis_creds:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="KIS 설정이 필요합니다")

    kis_result = await db.execute(
        select(AssetAccount).where(
            AssetAccount.user_id == current_user.id,
            AssetAccount.data_source == DataSource.KIS_API,
            AssetAccount.is_active == True,  # noqa: E712
        )
    )
    kis_accounts = kis_result.scalars().all()
    if not kis_accounts:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="등록된 KIS 계좌가 없습니다")

    app_key = kis_creds["app_key"]
    app_secret = kis_creds["app_secret"]
    is_mock = kis_creds["is_mock"]
    access_token = kis_creds["access_token"]

    async def _fetch(account_no: str) -> tuple[str, dict, dict]:
        d = await get_domestic_balance(app_key, app_secret, access_token, account_no, is_mock=is_mock)
        o = await get_overseas_balance(app_key, app_secret, access_token, account_no, is_mock=is_mock)
        return account_no, d, o

    raw_results = await asyncio.gather(
        *[_fetch(acc.kis_account_no) for acc in kis_accounts if acc.kis_account_no],
        return_exceptions=True,
    )

    merged_domestic: dict = {
        "total_value_krw": 0.0,
        "invested_krw": 0.0,
        "pnl_krw": 0.0,
        "deposit_krw": 0.0,
        "positions": [],
    }
    merged_overseas: dict = {"total_value_usd": 0.0, "deposit_usd": 0.0, "positions": []}
    account_details = []
    results = [r for r in raw_results if not isinstance(r, BaseException)]
    failed_count = len(raw_results) - len(results)
    if failed_count:
        import structlog as _sl

        _sl.get_logger().warning("kis_account_fetch_partial_failure", failed=failed_count)
    for account_no, d, o in results:
        merged_domestic["total_value_krw"] += d.get("total_value_krw", 0.0)
        merged_domestic["invested_krw"] += d.get("invested_krw", 0.0)
        merged_domestic["pnl_krw"] += d.get("pnl_krw", 0.0)
        merged_domestic["deposit_krw"] += d.get("deposit_krw", 0.0)
        merged_domestic["positions"].extend(d.get("positions", []))
        merged_overseas["total_value_usd"] += o.get("total_value_usd", 0.0)
        merged_overseas["deposit_usd"] += o.get("deposit_usd", 0.0)
        merged_overseas["positions"].extend(o.get("positions", []))
        account_details.append({"account_no": account_no, "domestic": d, "overseas": o})

    stock_return_pct = 0.0
    if merged_domestic["invested_krw"] > 0:
        stock_return_pct = (merged_domestic["total_value_krw"] / merged_domestic["invested_krw"] - 1) * 100

    result = {
        "domestic": merged_domestic,
        "overseas": merged_overseas,
        "total_value_krw": merged_domestic["total_value_krw"],
        "total_invested_krw": merged_domestic["invested_krw"],
        "unrealized_pnl_krw": merged_domestic["pnl_krw"],
        "stock_return_pct": stock_return_pct,
        "is_mock": is_mock,
        "accounts": account_details,
    }
    await set_cached_json(redis, cache_key, result, TTL_PORTFOLIO_SUMMARY)
    return result


# ---------------------------------------------------------------------------
# 위험 분석
# ---------------------------------------------------------------------------


@router.get("/risk")
@limiter.limit("5/minute")
async def portfolio_risk(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """전체 포트폴리오 위험 지표 — VaR, 베타, 변동성, 분산도."""
    redis = await get_redis()
    return await get_portfolio_risk_metrics(current_user.id, db, redis)


@router.get("/risk/{portfolio_id}")
@limiter.limit("5/minute")
async def portfolio_risk_by_id(
    request: Request,
    portfolio_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """특정 포트폴리오 위험 지표."""
    redis = await get_redis()
    return await get_portfolio_risk_metrics(current_user.id, db, redis, portfolio_id=portfolio_id)


@router.get("/factor-analysis")
@limiter.limit("5/minute")
async def portfolio_factor_analysis(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """팩터 분석 — Value/Size/Momentum/Growth 팩터 노출도 (Fama-French 기반)."""
    redis = await get_redis()
    return await get_factor_analysis(current_user.id, db, redis)


@router.get("/factor-analysis/{portfolio_id}")
@limiter.limit("5/minute")
async def portfolio_factor_analysis_by_id(
    request: Request,
    portfolio_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """저장된 포트폴리오의 팩터 분석 — 비교 목적."""
    redis = await get_redis()
    return await get_factor_analysis_for_portfolio(portfolio_id, db, redis)


@router.get("/efficient-frontier")
@limiter.limit("3/minute")
async def portfolio_efficient_frontier(
    request: Request,
    compare_portfolio_id: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """효율적 프론티어 — MVO (scipy SLSQP). compare_portfolio_id 지정 시 목표 포트폴리오 위치도 반환."""
    redis = await get_redis()
    return await get_efficient_frontier(current_user.id, db, redis, compare_portfolio_id=compare_portfolio_id)


@router.get("/rebalancing-strategy")
@limiter.limit("3/minute")
async def portfolio_rebalancing_strategy(
    request: Request,
    portfolio_id: str = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """팩터·프론티어 분석 기반 리밸런싱 전략 제시."""
    redis = await get_redis()
    result = await get_rebalancing_strategy(current_user.id, portfolio_id, db, redis)
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["error"])
    return result


@router.get("/currency-exposure")
@limiter.limit("10/minute")
async def portfolio_currency_exposure(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """KRW/USD/기타 통화 비중 분석."""
    redis = await get_redis()
    return await get_currency_exposure(current_user.id, db, redis)
