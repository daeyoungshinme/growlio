"""연배당/월배당 계획 및 목표 달성 현황 서비스."""

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import UserSettings
from app.services.dividend.aggregator import get_dividend_summary
from app.services.dividend.orchestrator import get_ticker_dividend_summary

if TYPE_CHECKING:
    from app.core.cache_store import CacheStore

_YEARLY_HISTORY_YEARS = 5


async def get_dividend_plan(
    user_id: uuid.UUID,
    db: AsyncSession,
    cache: CacheStore | None = None,
) -> dict:
    """연배당 목표 달성 현황 및 월별/연도별 배당 분포 반환."""
    settings_row = await db.scalar(select(UserSettings).where(UserSettings.user_id == user_id))
    annual_dividend_goal = (
        float(settings_row.annual_dividend_goal) if settings_row and settings_row.annual_dividend_goal else None
    )

    # 종목별 예상 배당 (캐시 활용)
    ticker_summaries = await get_ticker_dividend_summary(user_id, db)

    estimated_annual_krw = sum(float(item.get("estimated_annual_krw") or 0) for item in ticker_summaries)
    estimated_monthly_krw = estimated_annual_krw / 12 if estimated_annual_krw else 0.0

    goal_achievement_pct: float | None = None
    if annual_dividend_goal and annual_dividend_goal > 0:
        goal_achievement_pct = round(estimated_annual_krw / annual_dividend_goal * 100, 1)

    # 올해 실수령 배당 + 월별 내역 (캐시 활용)
    summary = await get_dividend_summary(user_id, db, cache)
    actual_annual_received_krw = float(summary.get("annual_received") or 0)
    monthly_received = summary.get("monthly_breakdown", [])

    # 월별 예상 배당 분포 (1~12월 버킷)
    monthly_projected = _calc_monthly_projected(ticker_summaries)

    # 최근 N년 연도별 실수령 배당
    yearly_received = await _fetch_yearly_received(user_id, db)

    return {
        "annual_dividend_goal": annual_dividend_goal,
        "estimated_annual_krw": round(estimated_annual_krw),
        "estimated_monthly_krw": round(estimated_monthly_krw),
        "actual_annual_received_krw": round(actual_annual_received_krw),
        "goal_achievement_pct": goal_achievement_pct,
        "monthly_projected": monthly_projected,
        "monthly_received": monthly_received,
        "yearly_received": yearly_received,
    }


def _calc_monthly_projected(ticker_summaries: list[dict]) -> list[dict]:
    """종목별 dividend_months + estimated_annual_krw → 월별 예상 배당 버킷."""
    buckets: dict[int, float] = {m: 0.0 for m in range(1, 13)}
    for item in ticker_summaries:
        annual = float(item.get("estimated_annual_krw") or 0)
        if annual <= 0:
            continue
        months: list[int] = item.get("dividend_months") or []
        if not months:
            continue
        per_month = annual / len(months)
        for m in months:
            if 1 <= m <= 12:
                buckets[m] += per_month

    return [{"month": m, "amount_krw": round(buckets[m])} for m in range(1, 13)]


async def _fetch_yearly_received(user_id: uuid.UUID, db: AsyncSession) -> list[dict]:
    """최근 N년 연도별 실수령 배당금 합계."""
    today = date.today()
    start_year = today.year - _YEARLY_HISTORY_YEARS + 1

    result = await db.execute(
        text("""
            SELECT
                EXTRACT(year FROM transaction_date)::int AS year,
                SUM(amount)::float AS amount_krw
            FROM transactions
            WHERE user_id = :uid
              AND transaction_type = 'DIVIDEND'
              AND EXTRACT(year FROM transaction_date) >= :start_year
            GROUP BY 1
            ORDER BY 1
        """),
        {"uid": str(user_id), "start_year": start_year},
    )
    rows = result.fetchall()
    return [{"year": row.year, "amount_krw": round(row.amount_krw)} for row in rows]
