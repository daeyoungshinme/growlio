"""월별 자산 추이 계산 — DB·Redis 의존, 비즈니스 로직 없음."""

from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.cache_keys import TTL_MONTHLY_TREND, RedisType, get_cached_json, monthly_trend_key, set_cached_json


async def get_monthly_trend(user_id: uuid.UUID, db: AsyncSession, redis: RedisType = None) -> list[dict]:
    """최근 12개월 월별 총자산 추이. is_active/include_in_total 계좌만 집계."""
    cache_key = monthly_trend_key(user_id)
    cached = await get_cached_json(redis, cache_key)
    if cached is not None:
        return cached

    result = await db.execute(
        text("""
            WITH ranked AS (
                SELECT
                    date_trunc('month', s.snapshot_date)::date AS month,
                    s.amount_krw,
                    ROW_NUMBER() OVER (
                        PARTITION BY s.account_id, date_trunc('month', s.snapshot_date)
                        ORDER BY s.snapshot_date DESC
                    ) AS rn
                FROM asset_snapshots s
                JOIN asset_accounts a ON a.id = s.account_id
                WHERE s.user_id = :uid
                    AND a.is_active = TRUE
                    AND a.include_in_total = TRUE
                    AND s.snapshot_date >= (date_trunc('month', CURRENT_DATE) - INTERVAL '11 months')
            )
            SELECT month, SUM(amount_krw) AS total_krw
            FROM ranked
            WHERE rn = 1
            GROUP BY month
            ORDER BY month
        """),
        {"uid": str(user_id)},
    )
    data = [{"month": str(row.month), "total_krw": float(row.total_krw)} for row in result]

    await set_cached_json(redis, cache_key, data, TTL_MONTHLY_TREND)
    return data
