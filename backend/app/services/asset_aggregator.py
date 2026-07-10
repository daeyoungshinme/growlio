"""자산 집계 대시보드 오케스트레이터."""

from __future__ import annotations

import asyncio
import uuid
from datetime import date
from typing import Any

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import UserSettings
from app.services.composition_calculator import (
    build_asset_totals,
    fetch_position_maps,
    get_latest_snapshot_rows,
    get_no_snap_accounts,
)
from app.services.dividend_aggregator import get_dividend_summary
from app.services.returns_calculator import calc_returns
from app.services.returns_calculator import calc_xirr as _calc_xirr
from app.services.trend_calculator import get_monthly_trend
from app.utils.cache_keys import (
    TTL_DASHBOARD_SUMMARY,
    RedisType,
    dashboard_summary_key,
    get_cached_json,
    set_cached_json,
)

# 기존 테스트 임포트 호환 별칭
_get_latest_snapshot_rows = get_latest_snapshot_rows
_get_no_snap_accounts = get_no_snap_accounts
_fetch_position_maps = fetch_position_maps
_build_asset_totals = build_asset_totals
_get_monthly_trend = get_monthly_trend

logger = structlog.get_logger()


async def _get_scalar_init_data(user_id: uuid.UUID, db: AsyncSession) -> tuple[date | None, float, float, float]:
    """first_snap_date + net_deposits_ytd + non_stock_first_total +
    non_stock_net_flows_after를 CTE 단일 쿼리로 조회.

    non_stock_first_total/non_stock_net_flows_after: 주식 계좌(STOCK_KIS/STOCK_KIWOOM/STOCK_OTHER)를
    제외한 계좌만의 첫 스냅샷 합계·순입금 — 주식은 매입원가(avg_price 기반 total_invested)로 별도
    계산하므로(get_dashboard_summary 참고) 여기서는 이중계산 방지를 위해 제외한다.
    first_snap_date는 연환산 기간 계산용으로 전체 계좌 기준을 유지한다.
    """
    year = date.today().year
    row = (
        await db.execute(
            text("""
                WITH
                  paf AS (
                    SELECT s.account_id, MIN(s.snapshot_date) AS first_date
                    FROM asset_snapshots s
                    JOIN asset_accounts a ON a.id = s.account_id
                    WHERE s.user_id = :uid
                      AND a.is_active = TRUE
                      AND a.include_in_total = TRUE
                    GROUP BY s.account_id
                  ),
                  fs AS (
                    SELECT MIN(paf.first_date) AS first_date
                    FROM paf
                  ),
                  paf_ns AS (
                    SELECT s.account_id, MIN(s.snapshot_date) AS first_date
                    FROM asset_snapshots s
                    JOIN asset_accounts a ON a.id = s.account_id
                    WHERE s.user_id = :uid
                      AND a.is_active = TRUE
                      AND a.include_in_total = TRUE
                      AND a.asset_type NOT IN ('STOCK_KIS', 'STOCK_KIWOOM', 'STOCK_OTHER')
                    GROUP BY s.account_id
                  ),
                  fs_ns AS (
                    SELECT COALESCE(SUM(s.amount_krw), 0) AS non_stock_first_total
                    FROM paf_ns
                    JOIN asset_snapshots s ON s.account_id = paf_ns.account_id
                      AND s.snapshot_date = paf_ns.first_date
                  ),
                  nd AS (
                    SELECT COALESCE(
                      SUM(CASE WHEN transaction_type = 'DEPOSIT' THEN amount ELSE -amount END), 0
                    ) AS net
                    FROM transactions
                    WHERE user_id = :uid
                      AND EXTRACT(YEAR FROM transaction_date) = :year
                      AND transaction_type IN ('DEPOSIT', 'WITHDRAWAL')
                  ),
                  net_after_ns AS (
                    SELECT COALESCE(
                      SUM(CASE WHEN t.transaction_type = 'DEPOSIT' THEN t.amount ELSE -t.amount END), 0
                    ) AS non_stock_net_flows_after
                    FROM transactions t
                    JOIN paf_ns ON paf_ns.account_id = t.account_id
                    WHERE t.user_id = :uid
                      AND t.transaction_type IN ('DEPOSIT', 'WITHDRAWAL')
                      AND t.transaction_date > paf_ns.first_date
                  )
                SELECT fs.first_date, nd.net,
                       fs_ns.non_stock_first_total, net_after_ns.non_stock_net_flows_after
                FROM fs, nd, fs_ns, net_after_ns
            """),
            {"uid": str(user_id), "year": year},
        )
    ).first()
    first_snap = row.first_date if row else None
    net_deposits = float(row.net) if row else 0.0
    non_stock_first_total = float(row.non_stock_first_total) if row else 0.0
    non_stock_net_flows_after = float(row.non_stock_net_flows_after) if row else 0.0
    return (
        first_snap,
        net_deposits,
        non_stock_first_total,
        non_stock_net_flows_after,
    )


async def get_dashboard_summary(user_id: uuid.UUID, db: AsyncSession, redis: RedisType = None) -> dict[str, Any]:
    """전체 자산 집계 + 목표 달성률 + 수익률 계산."""
    cached = await get_cached_json(redis, dashboard_summary_key(user_id))
    if cached is not None:
        return cached

    # 1단계: 서로 독립적인 쿼리들을 병렬 실행
    (
        (
            first_snap_date,
            net_deposits_ytd,
            non_stock_first_total,
            non_stock_net_flows_after,
        ),
        settings_row,
        monthly_trend,
        div_summary,
    ) = await asyncio.gather(
        _get_scalar_init_data(user_id, db),
        db.scalar(select(UserSettings).where(UserSettings.user_id == user_id)),
        _get_monthly_trend(user_id, db, redis),
        get_dividend_summary(user_id, db, redis),
    )

    # 2단계: 내부에서 4개 쿼리를 실행하므로 1단계와 분리해 session 충돌 방지
    total_assets_krw, total_invested, stock_value, by_type = await _build_asset_totals(user_id, db, redis)

    # 3단계: total_assets_krw에 의존
    xirr_pct, xirr_is_estimated = await _calc_xirr(user_id, total_assets_krw, db)

    if (total_invested > 0 or non_stock_first_total > 0) and first_snap_date:
        # 혼합 수익률: 주식은 매입원가(avg_price 기반 total_invested) 기준 실제 손익을,
        # 현금성/부동산 등 나머지는 Growlio 추적 시작 시점 기준 Modified Dietz를 각각 계산해 합산.
        # base = total_invested + non_stock_first_total, net_flows는 비-주식 계좌 거래만 반영
        # (주식 계좌는 거래 기록이 거의 없어 total_invested와 겹치지 않음 — 이중계산 없음).
        annualized_return, cumulative_return = calc_returns(
            total_assets_krw,
            total_invested + non_stock_first_total,
            first_snap_date,
            non_stock_net_flows_after,
        )
    else:
        annualized_return, cumulative_return = None, None
    stock_return_pct = ((stock_value / total_invested) - 1) * 100 if total_invested > 0 else 0.0

    goal = float(settings_row.goal_amount) if settings_row and settings_row.goal_amount else None
    goal_pct = (total_assets_krw / goal * 100) if goal else None
    annual_deposit_goal = (
        float(settings_row.annual_deposit_goal) if settings_row and settings_row.annual_deposit_goal else None
    )
    deposit_achievement_pct = (net_deposits_ytd / annual_deposit_goal * 100) if annual_deposit_goal else None
    goal_annual_return_pct = (
        float(settings_row.goal_annual_return_pct) if settings_row and settings_row.goal_annual_return_pct else None
    )
    actual_return_for_goal = xirr_pct if xirr_pct is not None else annualized_return
    return_goal_gap_pct = (
        round(actual_return_for_goal - goal_annual_return_pct, 2)
        if goal_annual_return_pct is not None and actual_return_for_goal is not None
        else None
    )
    retirement_target_year = settings_row.retirement_target_year if settings_row else None
    annual_dividend_goal = (
        float(settings_row.annual_dividend_goal) if settings_row and settings_row.annual_dividend_goal else None
    )
    estimated_annual = div_summary.get("estimated_annual")
    dividend_goal_achievement_pct = (
        round(estimated_annual / annual_dividend_goal * 100, 1) if annual_dividend_goal and estimated_annual else None
    )

    result: dict[str, Any] = {
        "total_assets_krw": total_assets_krw,
        "asset_allocation": [
            {"type": k, "amount_krw": v, "pct": v / total_assets_krw * 100 if total_assets_krw else 0}
            for k, v in by_type.items()
        ],
        "goal_amount": goal,
        "goal_achievement_pct": goal_pct,
        "stock_return_pct": stock_return_pct,
        "annual_return_pct": annualized_return,
        "cumulative_return_pct": cumulative_return,
        "xirr_pct": xirr_pct,
        "xirr_is_estimated": xirr_is_estimated,
        "goal_annual_return_pct": goal_annual_return_pct,
        "return_goal_gap_pct": return_goal_gap_pct,
        "retirement_target_year": retirement_target_year,
        "monthly_trend": monthly_trend,
        "annual_deposit_goal": annual_deposit_goal,
        "deposit_achievement_pct": deposit_achievement_pct,
        "annual_dividends_received": div_summary["annual_received"],
        "estimated_annual_dividends": div_summary["estimated_annual"],
        "dividend_monthly_breakdown": div_summary["monthly_breakdown"],
        "annual_dividend_goal": annual_dividend_goal,
        "dividend_goal_achievement_pct": dividend_goal_achievement_pct,
    }
    await set_cached_json(redis, dashboard_summary_key(user_id), result, TTL_DASHBOARD_SUMMARY)
    return result
