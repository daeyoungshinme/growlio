"""자산 집계 대시보드 오케스트레이터."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

import structlog
from sqlalchemy import bindparam, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import POSITION_STOCK_ASSET_TYPES
from app.models.user import UserSettings
from app.services.dividend.aggregator import get_dividend_summary
from app.services.portfolio.composition_calculator import (
    build_asset_totals,
    exclude_real_estate,
)
from app.services.portfolio.returns_calculator import calc_returns
from app.services.portfolio.returns_calculator import calc_xirr as _calc_xirr
from app.utils.cache_keys import (
    TTL_DASHBOARD_SUMMARY,
    TTL_MONTHLY_TREND,
    CacheStoreType,
    dashboard_summary_key,
    get_cached_json,
    monthly_trend_key,
    set_cached_json,
)
from app.utils.inproc_lock import single_flight_fetch
from app.utils.kst import today_kst

logger = structlog.get_logger()


def _trend_window_start(today: date) -> date:
    """12개월 창의 시작(11개월 전 월 1일). DB CURRENT_DATE는 UTC라 KST 1일 새벽에 한 달 밀린다."""
    months = today.year * 12 + today.month - 1 - 11
    return date(months // 12, months % 12 + 1, 1)


async def get_monthly_trend(user_id: uuid.UUID, db: AsyncSession, cache: CacheStoreType = None) -> list[dict]:
    """최근 12개월 월별 총자산 추이. is_active/include_in_total 계좌만 집계."""
    cache_key = monthly_trend_key(user_id)
    cached = await get_cached_json(cache, cache_key)
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
                    AND s.snapshot_date >= :start_date
            )
            SELECT month, SUM(amount_krw) AS total_krw
            FROM ranked
            WHERE rn = 1
            GROUP BY month
            ORDER BY month
        """),
        {"uid": str(user_id), "start_date": _trend_window_start(today_kst())},
    )
    data = [{"month": str(row.month), "total_krw": float(row.total_krw)} for row in result]

    await set_cached_json(cache, cache_key, data, TTL_MONTHLY_TREND)
    return data


async def _get_scalar_init_data(user_id: uuid.UUID, db: AsyncSession) -> tuple[date | None, float, float, float]:
    """first_snap_date + net_deposits_ytd + non_stock_first_total +
    non_stock_net_flows_after를 CTE 단일 쿼리로 조회.

    non_stock_first_total/non_stock_net_flows_after: 주식 계좌(constants.POSITION_STOCK_ASSET_TYPES)를
    제외한 계좌만의 첫 스냅샷 합계·순입금 — 주식은 매입원가(avg_price 기반 total_invested)로 별도
    계산하므로(get_dashboard_summary 참고) 여기서는 이중계산 방지를 위해 제외한다.
    first_snap_date는 연환산 기간 계산용으로 전체 계좌 기준을 유지한다.
    """
    year = today_kst().year
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
                      AND a.asset_type NOT IN :stock_types
                    GROUP BY s.account_id
                  ),
                  fs_ns AS (
                    SELECT COALESCE(SUM(s.amount_krw), 0) AS non_stock_first_total
                    FROM paf_ns
                    JOIN asset_snapshots s ON s.account_id = paf_ns.account_id
                      AND s.snapshot_date = paf_ns.first_date
                  ),
                  nd AS (
                    -- 계좌 미지정 입출금(account_id NULL)은 유지하고, 삭제(soft)·합산 제외 계좌는 뺀다
                    SELECT COALESCE(
                      SUM(CASE WHEN t.transaction_type = 'DEPOSIT' THEN t.amount ELSE -t.amount END), 0
                    ) AS net
                    FROM transactions t
                    LEFT JOIN asset_accounts a ON a.id = t.account_id
                    WHERE t.user_id = :uid
                      AND EXTRACT(YEAR FROM t.transaction_date) = :year
                      AND t.transaction_type IN ('DEPOSIT', 'WITHDRAWAL')
                      AND (t.account_id IS NULL OR (a.is_active = TRUE AND a.include_in_total = TRUE))
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
            """).bindparams(bindparam("stock_types", expanding=True)),
            {"uid": str(user_id), "year": year, "stock_types": sorted(POSITION_STOCK_ASSET_TYPES)},
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


async def get_dashboard_summary(user_id: uuid.UUID, db: AsyncSession, cache: CacheStoreType = None) -> dict[str, Any]:
    """전체 자산 집계 + 목표 달성률 + 수익률 계산.

    `/dashboard`·`/insights`·`/challenges`가 앱 시작 시 동시에 이 함수를 부른다 — 콜드 캐시에서 셋이
    각자 계산하면 종목별 배당 외부 API 체인이 최대 3중으로 돌았으므로 single-flight로 한 건만 계산한다.
    """
    cache_key = dashboard_summary_key(user_id)

    async def _read_cache() -> dict[str, Any] | None:
        return await get_cached_json(cache, cache_key)

    cached = await _read_cache()
    if cached is not None:
        return cached
    if cache is None:
        return await _compute_dashboard_summary(user_id, db, cache)

    async def _fetch_and_cache() -> dict[str, Any]:
        return await _compute_dashboard_summary(user_id, db, cache)

    result: dict[str, Any] = await single_flight_fetch(cache, cache_key, _read_cache, _fetch_and_cache)
    return result


async def _compute_dashboard_summary(user_id: uuid.UUID, db: AsyncSession, cache: CacheStoreType) -> dict[str, Any]:
    # 1단계: 서로 논리적으로는 독립적이지만 같은 AsyncSession을 쓰므로 순차 실행
    # (asyncpg/SQLAlchemy AsyncSession은 하나의 커넥션에서 동시 쿼리 실행을 지원하지
    # 않음 — asyncio.gather로 묶으면 병렬화 이득 없이 간헐적 InterfaceError 위험만 생김)
    (
        first_snap_date,
        net_deposits_ytd,
        non_stock_first_total,
        non_stock_net_flows_after,
    ) = await _get_scalar_init_data(user_id, db)
    settings_row = await db.scalar(select(UserSettings).where(UserSettings.user_id == user_id))
    monthly_trend = await get_monthly_trend(user_id, db, cache)
    div_summary = await get_dividend_summary(user_id, db, cache)

    # 2단계: 내부에서 4개 쿼리를 실행하므로 1단계와 분리해 session 충돌 방지
    total_assets_krw, total_invested, stock_value, by_type = await build_asset_totals(user_id, db, cache)

    # 3단계: total_assets_krw에 의존
    xirr_pct, xirr_is_estimated = await _calc_xirr(user_id, total_assets_krw, db)

    if (total_invested > 0 or non_stock_first_total > 0) and first_snap_date:
        # 혼합 수익률: 주식은 매입원가(avg_price 기반 total_invested) 기준 실제 손익을,
        # 현금성/부동산 등 나머지는 Growlio 추적 시작 시점 기준 Modified Dietz를 각각 계산해 합산.
        # base = total_invested + non_stock_first_total, net_flows는 비-주식 계좌 거래만 반영
        # (주식 계좌는 거래 기록이 거의 없어 total_invested와 겹치지 않음 — 이중계산 없음).
        # 주식 계좌 예수금(CASH_STOCK)은 total_assets_krw에는 포함되지만 total_invested에는
        # 매입원가만 반영돼 빠져 있으므로, base와 기준을 맞추기 위해 current 쪽에서도 제외한다
        # — 그렇지 않으면 미투자 예수금만큼 대응 원금 없는 가짜 이익이 발생해 누적/연환산
        # 수익률이 폭주한다(현금이 많을수록, 추적 기간이 90일에 가까울수록 심함).
        cash_in_stock_accounts = by_type.get("CASH_STOCK", 0.0)
        annualized_return, cumulative_return = calc_returns(
            total_assets_krw - cash_in_stock_accounts,
            total_invested + non_stock_first_total,
            first_snap_date,
            non_stock_net_flows_after,
        )
    else:
        annualized_return, cumulative_return = None, None
    stock_return_pct = ((stock_value / total_invested) - 1) * 100 if total_invested > 0 else 0.0

    # 부동산은 목표 역산 추천/DCA 복리 곡선 어느 쪽도 성장을 모델링하지 않으므로 목표
    # 달성률 계산에서는 제외한다(부동산 추가만으로 % 왜곡 방지) — total_assets_krw
    # 필드 자체(자산배분 차트 등)는 그대로 부동산을 포함해 반환한다.
    goal = float(settings_row.goal_amount) if settings_row and settings_row.goal_amount else None
    investable_assets_krw = exclude_real_estate(total_assets_krw, by_type)
    goal_pct = (investable_assets_krw / goal * 100) if goal else None
    annual_deposit_goal = (
        float(settings_row.annual_deposit_goal) if settings_row and settings_row.annual_deposit_goal else None
    )
    deposit_achievement_pct = (net_deposits_ytd / annual_deposit_goal * 100) if annual_deposit_goal else None
    goal_annual_return_pct = (
        float(settings_row.goal_annual_return_pct) if settings_row and settings_row.goal_annual_return_pct else None
    )
    actual_return_for_goal = (
        xirr_pct if xirr_pct is not None else annualized_return if annualized_return is not None else cumulative_return
    )
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
        "annual_deposit_current": net_deposits_ytd,
        "deposit_achievement_pct": deposit_achievement_pct,
        "annual_dividends_received": div_summary["annual_received"],
        "estimated_annual_dividends": div_summary["estimated_annual"],
        "dividend_monthly_breakdown": div_summary["monthly_breakdown"],
        "annual_dividend_goal": annual_dividend_goal,
        "dividend_goal_achievement_pct": dividend_goal_achievement_pct,
    }
    await set_cached_json(cache, dashboard_summary_key(user_id), result, TTL_DASHBOARD_SUMMARY)
    return result
