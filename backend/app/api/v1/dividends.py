"""배당금 현황 API."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.limiter import limiter
from app.models.user import User
from app.redis_client import get_redis
from app.services.dividend_aggregator import get_dividend_summary
from app.services.dividend_service import (
    delete_ticker_settings,
    get_position_dividend_yields,
    get_ticker_dividend_summary,
    get_ticker_settings,
    upsert_ticker_settings,
)

router = APIRouter(prefix="/dividends", tags=["dividends"])


@router.get("/summary")
@limiter.limit("10/minute")
async def dividend_summary(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
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
