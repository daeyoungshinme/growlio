"""트랜잭션 기반 배당금 집계 서비스."""

from __future__ import annotations

import contextlib
import json
import uuid
from datetime import date

import structlog
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.dividend.orchestrator import get_ticker_dividend_summary
from app.utils.cache_keys import TTL_DIVIDEND_SUMMARY, dividend_summary_key

logger = structlog.get_logger()


async def get_dividend_summary(user_id: uuid.UUID, db: AsyncSession, redis: Redis | None = None) -> dict:
    if redis:
        try:
            cached = await redis.get(dividend_summary_key(user_id))
            if cached:
                return json.loads(cached)
        except RedisError:
            logger.warning("dividend_cache_read_error", user_id=str(user_id))

    current_year = date.today().year

    annual_received, monthly_breakdown, monthly_ticker_breakdown = await _fetch_dividend_aggregates(
        user_id, db, current_year
    )

    ticker_summaries = await get_ticker_dividend_summary(user_id, db)
    estimated_annual = sum(
        item["estimated_annual_krw"]
        for item in ticker_summaries
        if item.get("estimated_annual_krw", 0) > 0
    )

    result = {
        "annual_received": annual_received,
        "monthly_breakdown": monthly_breakdown,
        "monthly_ticker_breakdown": monthly_ticker_breakdown,
        "estimated_annual": estimated_annual,
    }

    if redis:
        with contextlib.suppress(RedisError):
            await redis.setex(
                dividend_summary_key(user_id), TTL_DIVIDEND_SUMMARY, json.dumps(result)
            )

    return result


async def _fetch_dividend_aggregates(
    user_id: uuid.UUID, db: AsyncSession, year: int
) -> tuple[float, list[dict], list[dict]]:
    """연간 배당 합계·월별 내역·월별 종목 내역을 단일 DB 왕복으로 조회한다."""
    result = await db.execute(
        text("""
            WITH base AS (
                SELECT
                    to_char(transaction_date, 'YYYY-MM') AS month,
                    ticker,
                    amount
                FROM transactions
                WHERE user_id = :uid
                  AND transaction_type = 'DIVIDEND'
                  AND EXTRACT(year FROM transaction_date) = :yr
            ),
            annual AS (
                SELECT SUM(amount) AS total FROM base
            ),
            monthly AS (
                SELECT month, SUM(amount) AS total
                FROM base
                GROUP BY month
                ORDER BY month
            ),
            monthly_ticker AS (
                SELECT month, ticker, SUM(amount) AS total
                FROM base
                GROUP BY month, ticker
                ORDER BY month, ticker
            )
            SELECT 'annual'         AS kind, NULL  AS month, NULL   AS ticker, total FROM annual
            UNION ALL
            SELECT 'monthly',                month,           NULL,            total FROM monthly
            UNION ALL
            SELECT 'monthly_ticker',         month,           ticker,          total FROM monthly_ticker
        """),
        {"uid": str(user_id), "yr": year},
    )
    rows = result.all()

    annual_received = 0.0
    monthly_breakdown: list[dict] = []
    monthly_ticker_breakdown: list[dict] = []

    for row in rows:
        if row.kind == "annual":
            annual_received = float(row.total or 0)
        elif row.kind == "monthly":
            monthly_breakdown.append({"month": row.month, "amount": float(row.total)})
        else:
            monthly_ticker_breakdown.append(
                {"month": row.month, "ticker": row.ticker, "amount": float(row.total)}
            )

    return annual_received, monthly_breakdown, monthly_ticker_breakdown
