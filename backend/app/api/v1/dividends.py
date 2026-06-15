"""배당금 현황 API."""

import redis.asyncio as aioredis
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.limiter import limiter
from app.models.user import User
from app.redis_client import get_redis
from app.services.dividend.drip_service import (
    calc_monthly_optimization,
    simulate_drip,
)
from app.services.dividend_aggregator import get_dividend_summary
from app.services.dividend.orchestrator import (
    delete_ticker_settings,
    get_position_dividend_yields,
    get_ticker_dividend_summary,
    get_ticker_settings,
    upsert_ticker_settings,
)

router = APIRouter(prefix="/dividends", tags=["dividends"])
logger = structlog.get_logger()


@router.get("/summary")
@limiter.limit("10/minute")
async def dividend_summary(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    return await get_dividend_summary(current_user.id, db, redis)


@router.get("/positions")
@limiter.limit("5/minute")
async def position_dividend_yields(
    request: Request,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """보유 종목별 배당수익률 및 예상 배당금 (yfinance, 비실시간)."""
    result = await get_position_dividend_yields(current_user.id, db)
    return result[skip : skip + limit]


@router.get("/by-ticker")
@limiter.limit("10/minute")
async def ticker_dividend_summary(
    request: Request,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """종목별 실수령(올해) + 예상 배당금 통합 (Redis 24h 캐시)."""
    result = await get_ticker_dividend_summary(current_user.id, db)
    return result[skip : skip + limit]


class TickerSettingsRequest(BaseModel):
    market: str
    dividend_months: list[int]

    @field_validator("dividend_months")
    @classmethod
    def months_valid(cls, v: list[int]) -> list[int]:
        if not v:
            raise ValueError("배당월을 하나 이상 입력하세요")
        invalid = [m for m in v if not (1 <= m <= 12)]
        if invalid:
            raise ValueError(f"배당월은 1~12 범위여야 합니다: {invalid}")
        return sorted(set(v))


@router.get("/ticker-settings/{ticker}")
async def get_ticker_setting(
    ticker: str,
    market: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """종목 설정 조회 (배당월 override 여부 포함)."""
    result = await get_ticker_settings(current_user.id, ticker, market, db)
    if not result:
        return {"ticker": ticker, "market": market, "dividend_months": [], "is_manual": False}
    return result


@router.put("/ticker-settings/{ticker}")
async def put_ticker_setting(
    ticker: str,
    body: TickerSettingsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """배당월 수동 override 저장."""
    return await upsert_ticker_settings(
        current_user.id, ticker, body.market, body.dividend_months, db
    )


@router.delete("/ticker-settings/{ticker}")
async def del_ticker_setting(
    ticker: str,
    market: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """배당월 override 삭제 (자동 감지로 복구)."""
    deleted = await delete_ticker_settings(current_user.id, ticker, market, db)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="설정이 존재하지 않습니다"
        )
    return {"deleted": True}


# ---------------------------------------------------------------------------
# DRIP 시뮬레이션
# ---------------------------------------------------------------------------

class DRIPSimulationRequest(BaseModel):
    n_years: int = 10
    annual_dividend_yield_pct: float | None = None

    @field_validator("n_years")
    @classmethod
    def years_valid(cls, v: int) -> int:
        if not (1 <= v <= 50):
            raise ValueError("시뮬레이션 기간은 1~50년 범위여야 합니다")
        return v


@router.post("/drip-simulation")
@limiter.limit("10/minute")
async def drip_simulation(
    request: Request,
    body: DRIPSimulationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """DRIP(배당 재투자) vs 현금수령 비교 투영."""
    from sqlalchemy import select

    from app.models.user import UserSettings

    settings_row = await db.scalar(
        select(UserSettings).where(UserSettings.user_id == current_user.id)
    )
    div_summary = await get_dividend_summary(current_user.id, db, redis)
    dashboard_data = {}
    try:
        from app.services.asset_aggregator import get_dashboard_summary
        dashboard_data = await get_dashboard_summary(current_user.id, db, redis)
    except Exception as e:
        logger.warning("drip_dashboard_summary_failed", user_id=str(current_user.id), error=str(e))

    initial_value = float(dashboard_data.get("total_assets_krw") or 0)
    monthly_contribution = float(
        (settings_row.monthly_deposit_amount if settings_row and settings_row.monthly_deposit_amount else None) or 0
    )
    annual_return_pct = float(
        (settings_row.goal_annual_return_pct if settings_row and settings_row.goal_annual_return_pct else None) or 6.0
    )
    estimated_annual = float(div_summary.get("estimated_annual", 0) or 0)

    if body.annual_dividend_yield_pct is not None:
        annual_div_yield = body.annual_dividend_yield_pct
    elif initial_value > 0 and estimated_annual > 0:
        annual_div_yield = estimated_annual / initial_value * 100
    else:
        annual_div_yield = 2.0

    return simulate_drip(
        initial_portfolio_value=initial_value,
        monthly_contribution=monthly_contribution,
        annual_return_pct=annual_return_pct,
        annual_dividend_yield_pct=annual_div_yield,
        n_years=body.n_years,
        drip=True,
    )


# ---------------------------------------------------------------------------
# 월별 균등화 제안
# ---------------------------------------------------------------------------

@router.get("/monthly-optimization")
@limiter.limit("10/minute")
async def monthly_optimization(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """배당 약한 달 추가 매수 종목 제안."""
    ticker_summaries = await get_ticker_dividend_summary(current_user.id, db)
    return calc_monthly_optimization(ticker_summaries)
