"""사용자별 배당월 수동 설정(UserTickerSettings) CRUD — orchestrator.py의 배당 집계 로직과 무관한 별도 관심사."""

from __future__ import annotations

import uuid
from datetime import date

import structlog
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import get_redis
from app.models.asset import UserTickerSettings
from app.utils.cache_keys import dividend_info_key, dividend_months_key, invalidate_dividend_caches

logger = structlog.get_logger()


async def get_ticker_settings(user_id: uuid.UUID, ticker: str, market: str, db: AsyncSession) -> dict | None:
    row = await db.scalar(
        select(UserTickerSettings).where(
            UserTickerSettings.user_id == user_id,
            UserTickerSettings.ticker == ticker,
            UserTickerSettings.market == market,
        )
    )
    if not row:
        return None
    return {
        "ticker": row.ticker,
        "market": row.market,
        "dividend_months": list(row.dividend_months or []),
        "is_manual": True,
    }


async def upsert_ticker_settings(
    user_id: uuid.UUID, ticker: str, market: str, dividend_months: list[int], db: AsyncSession
) -> dict:
    stmt = (
        pg_insert(UserTickerSettings)
        .values(user_id=user_id, ticker=ticker, market=market, dividend_months=dividend_months)
        .on_conflict_do_update(
            constraint="uq_user_ticker_settings",
            set_={"dividend_months": dividend_months, "updated_at": func.now()},
        )
    )
    await db.execute(stmt)
    await db.commit()

    redis = await get_redis()
    current_year = date.today().year
    await invalidate_dividend_caches(redis, user_id, current_year)
    await redis.delete(dividend_info_key(ticker, market))
    logger.info("ticker_settings_upserted", user_id=str(user_id), ticker=ticker, market=market)

    return {
        "ticker": ticker,
        "market": market,
        "dividend_months": dividend_months,
        "is_manual": True,
    }


async def delete_ticker_settings(user_id: uuid.UUID, ticker: str, market: str, db: AsyncSession) -> bool:
    row = await db.scalar(
        select(UserTickerSettings).where(
            UserTickerSettings.user_id == user_id,
            UserTickerSettings.ticker == ticker,
            UserTickerSettings.market == market,
        )
    )
    if not row:
        return False
    await db.delete(row)
    await db.commit()

    redis = await get_redis()
    current_year = date.today().year
    await invalidate_dividend_caches(redis, user_id, current_year)
    await redis.delete(dividend_months_key(ticker, market))
    await redis.delete(dividend_info_key(ticker, market))
    logger.info("ticker_settings_deleted", user_id=str(user_id), ticker=ticker, market=market)

    return True
