"""배당금 현황 API."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.services.dividend_service import (
    delete_ticker_settings,
    get_dividend_summary,
    get_position_dividend_yields,
    get_ticker_dividend_summary,
    get_ticker_settings,
    upsert_ticker_settings,
)

router = APIRouter(prefix="/dividends", tags=["dividends"])


@router.get("/summary")
async def dividend_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_dividend_summary(current_user.id, db)


@router.get("/positions")
async def position_dividend_yields(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """보유 종목별 배당수익률 및 예상 배당금 (yfinance, 비실시간)."""
    return await get_position_dividend_yields(current_user.id, db)


@router.get("/by-ticker")
async def ticker_dividend_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """종목별 실수령(올해) + 예상 배당금 통합 (Redis 24h 캐시)."""
    return await get_ticker_dividend_summary(current_user.id, db)


class TickerSettingsRequest(BaseModel):
    market: str
    dividend_months: list[int]


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
    return await upsert_ticker_settings(current_user.id, ticker, body.market, body.dividend_months, db)


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
        raise HTTPException(status_code=404, detail="설정이 존재하지 않습니다")
    return {"deleted": True}
