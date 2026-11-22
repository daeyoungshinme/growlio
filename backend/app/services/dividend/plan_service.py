"""연배당/월배당 계획 및 목표 달성 현황 서비스."""

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import OVERSEAS_MARKETS
from app.services._settings_queries import get_settings_row
from app.services.dividend.aggregator import get_dividend_summary
from app.services.dividend.orchestrator import get_ticker_dividend_summary
from app.services.portfolio.portfolio_service import build_portfolio_overview
from app.services.tax.tax_service import get_tax_rates
from app.utils.kst import today_kst

if TYPE_CHECKING:
    from app.core.cache_store import CacheStore

_YEARLY_HISTORY_YEARS = 5
# 해외 배당은 현지 원천징수(미국 15%)로 끝나고 국내 추가 과세가 없다(외국납부세액 공제) — 미국 기준 근사
_OVERSEAS_DIVIDEND_WITHHOLDING_RATE = 0.15
AFTER_TAX_NOTE = (
    "세후는 일반계좌 원천징수(국내 15.4%, 해외 15%·미국 기준)를 뺀 추정이에요. ISA·연금 계좌 보유분은 "
    "배당 시점에 떼지 않아 세전과 같게 봤고, 금융소득 2,000만원 초과 종합과세는 반영하지 않았어요."
)


def _after_tax_annual(ticker_summaries: list[dict], domestic_rate: float) -> float:
    """종목별 예상 배당에서 일반계좌 몫의 원천징수를 뺀 연 합계(ISA·연금 보유 비율은 비과세로 본다)."""
    total = 0.0
    for item in ticker_summaries:
        annual = float(item.get("estimated_annual_krw") or 0)
        if annual <= 0:
            continue
        market = (item.get("market") or "").upper()
        rate = _OVERSEAS_DIVIDEND_WITHHOLDING_RATE if market in OVERSEAS_MARKETS else domestic_rate
        sheltered = min(1.0, max(0.0, float(item.get("tax_sheltered_ratio") or 0)))
        total += annual * (1 - (1 - sheltered) * rate)
    return total


async def get_dividend_plan(
    user_id: uuid.UUID,
    db: AsyncSession,
    cache: CacheStore | None = None,
) -> dict:
    """연배당 목표 달성 현황 및 월별/연도별 배당 분포 반환."""
    settings_row = await get_settings_row(db, user_id)
    annual_dividend_goal = (
        float(settings_row.annual_dividend_goal) if settings_row and settings_row.annual_dividend_goal else None
    )

    # 종목별 예상 배당 (캐시 활용)
    ticker_summaries = await get_ticker_dividend_summary(user_id, db)

    estimated_annual_krw = sum(float(item.get("estimated_annual_krw") or 0) for item in ticker_summaries)
    estimated_monthly_krw = estimated_annual_krw / 12 if estimated_annual_krw else 0.0
    after_tax_annual_krw = _after_tax_annual(ticker_summaries, get_tax_rates(today_kst().year)["dividend"])

    goal_achievement_pct: float | None = None
    if annual_dividend_goal and annual_dividend_goal > 0:
        goal_achievement_pct = round(estimated_annual_krw / annual_dividend_goal * 100, 1)

    # 목표 달성에 필요한 배당수익률 (목표 연배당 ÷ 부동산 뺀 투자자산) — 목표 역산 추천의
    # required_dividend_yield_pct와 같은 분모(`investable_assets_krw`)라 두 화면의 수치가 일치한다.
    required_dividend_yield_pct: float | None = None
    current_dividend_yield_pct: float | None = None
    total_assets_krw = 0.0
    if annual_dividend_goal and annual_dividend_goal > 0:
        # 지연 import — goal 패키지는 무거운 추천 모듈을 끌어온다
        from app.services.goal._goal_recommendation_common import investable_assets_krw

        overview = await build_portfolio_overview(user_id, db, account_ids=None, cache=cache)
        total_assets_krw = max(0.0, investable_assets_krw(overview))
        if total_assets_krw > 0:
            required_dividend_yield_pct = round(annual_dividend_goal / total_assets_krw * 100, 2)
            current_dividend_yield_pct = round(estimated_annual_krw / total_assets_krw * 100, 2)

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
        "estimated_annual_after_tax_krw": round(after_tax_annual_krw),
        "estimated_monthly_after_tax_krw": round(after_tax_annual_krw / 12),
        "after_tax_note": AFTER_TAX_NOTE,
        "actual_annual_received_krw": round(actual_annual_received_krw),
        "goal_achievement_pct": goal_achievement_pct,
        "required_dividend_yield_pct": required_dividend_yield_pct,
        "current_dividend_yield_pct": current_dividend_yield_pct,
        "total_assets_krw": round(total_assets_krw),
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
    today = today_kst()
    start_year = today.year - _YEARLY_HISTORY_YEARS + 1

    result = await db.execute(
        text("""
            SELECT
                EXTRACT(year FROM t.transaction_date)::int AS year,
                SUM(t.amount)::float AS amount_krw
            FROM transactions t
            LEFT JOIN asset_accounts a ON a.id = t.account_id
            WHERE t.user_id = :uid
              AND t.transaction_type = 'DIVIDEND'
              -- 범위 조건 — EXTRACT(year)는 transaction_date 인덱스를 타지 못한다(plans/129 B4)
              AND t.transaction_date >= :start_date
              -- 삭제(soft) 계좌 배당 제외 — 입출금 집계와 같은 기준(plans/95 A4), 세금 집계는 유지
              AND (t.account_id IS NULL OR a.is_active = TRUE)
            GROUP BY 1
            ORDER BY 1
        """),
        {"uid": str(user_id), "start_date": date(start_year, 1, 1)},
    )
    rows = result.fetchall()
    return [{"year": row.year, "amount_krw": round(row.amount_krw)} for row in rows]
