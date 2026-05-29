"""적립식 투자(DCA) 복리계산 및 월/년 목표달성율 서비스."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any

from dateutil.relativedelta import relativedelta
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import AssetAccount, AssetSnapshot
from app.models.user import UserSettings


async def get_dca_analysis(user_id: uuid.UUID, db: AsyncSession) -> dict[str, Any]:
    """DCA 복리 이론 곡선과 실제 자산을 비교한 분석 결과 반환."""
    settings_row = await db.scalar(select(UserSettings).where(UserSettings.user_id == user_id))

    pmt = float(settings_row.monthly_deposit_amount) if settings_row and settings_row.monthly_deposit_amount else None
    annual_return_pct = float(settings_row.goal_annual_return_pct) if settings_row and settings_row.goal_annual_return_pct else None
    goal_amount = float(settings_row.goal_amount) if settings_row and settings_row.goal_amount else None
    start_dt = settings_row.goal_start_date if settings_row else None
    manual_initial = float(settings_row.goal_initial_amount) if settings_row and settings_row.goal_initial_amount else None

    is_configured = bool(pmt and annual_return_pct and goal_amount and start_dt)

    dca_settings = {
        "monthly_deposit_amount": pmt,
        "goal_annual_return_pct": annual_return_pct,
        "goal_amount": goal_amount,
        "goal_start_date": start_dt.date().isoformat() if start_dt else None,
        "goal_initial_amount": manual_initial,
    }

    if not is_configured:
        return {
            "settings": dca_settings,
            "projection_months": [],
            "yearly_achievements": [],
            "goal_timeline": {
                "months_to_goal": None,
                "expected_goal_date": None,
                "actual_expected_goal_date": None,
                "current_progress_pct": None,
                "on_track": None,
                "lead_lag_months": None,
            },
            "is_configured": False,
        }

    start_date: date = start_dt.date() if isinstance(start_dt, datetime) else start_dt  # type: ignore[assignment]
    today = datetime.now(timezone.utc).date()
    r = annual_return_pct / 12 / 100  # 월 이자율

    if manual_initial is not None:
        initial_value = manual_initial
    else:
        initial_value = await _get_initial_value(user_id, start_date, db)
    monthly_actuals = await _get_monthly_actual_values(user_id, start_date, db)

    # goal_start_date부터 오늘까지 + 향후 미래 예측 (총 목표 달성까지)
    months_to_goal = _calc_months_to_goal(initial_value, pmt, r, goal_amount)  # type: ignore[arg-type]
    total_months = max(
        _elapsed_months(start_date, today) + 1,
        months_to_goal if months_to_goal else _elapsed_months(start_date, today) + 1,
    )

    projection_months = _build_projection_curve(
        initial_value, pmt, r, start_date, total_months, monthly_actuals  # type: ignore[arg-type]
    )
    yearly_achievements = _build_yearly_achievements(projection_months)

    current_actual = monthly_actuals.get(_month_key(today))
    if not current_actual and monthly_actuals:
        # 이번 달 스냅샷이 없으면 최근 월 값 사용
        latest_key = max(monthly_actuals.keys())
        current_actual = monthly_actuals[latest_key]

    goal_timeline = _calc_goal_timeline(
        initial_value, pmt, r, goal_amount, current_actual or 0.0, start_date, months_to_goal  # type: ignore[arg-type]
    )

    return {
        "settings": dca_settings,
        "projection_months": projection_months,
        "yearly_achievements": yearly_achievements,
        "goal_timeline": goal_timeline,
        "is_configured": True,
    }


async def _get_initial_value(user_id: uuid.UUID, start_date: date, db: AsyncSession) -> float:
    """goal_start_date 기준 전후로 가장 가까운 스냅샷 날짜의 전체 계좌 합계 반환."""
    # start_date 이후 첫 번째 유효 날짜 탐색 (없으면 이전 날짜 중 가장 최근)
    result_after = await db.execute(
        select(AssetSnapshot.snapshot_date, func.sum(AssetSnapshot.amount_krw).label("total"))
        .join(AssetAccount, AssetAccount.id == AssetSnapshot.account_id)
        .where(
            AssetSnapshot.user_id == user_id,
            AssetSnapshot.snapshot_date >= start_date,
            AssetAccount.is_active == True,  # noqa: E712
            AssetAccount.include_in_total == True,  # noqa: E712
        )
        .group_by(AssetSnapshot.snapshot_date)
        .order_by(AssetSnapshot.snapshot_date.asc())
        .limit(1)
    )
    row = result_after.first()
    if row:
        return float(row.total)

    result_before = await db.execute(
        select(AssetSnapshot.snapshot_date, func.sum(AssetSnapshot.amount_krw).label("total"))
        .join(AssetAccount, AssetAccount.id == AssetSnapshot.account_id)
        .where(
            AssetSnapshot.user_id == user_id,
            AssetSnapshot.snapshot_date < start_date,
            AssetAccount.is_active == True,  # noqa: E712
            AssetAccount.include_in_total == True,  # noqa: E712
        )
        .group_by(AssetSnapshot.snapshot_date)
        .order_by(AssetSnapshot.snapshot_date.desc())
        .limit(1)
    )
    row = result_before.first()
    return float(row.total) if row else 0.0


async def _get_monthly_actual_values(
    user_id: uuid.UUID, start_date: date, db: AsyncSession
) -> dict[str, float]:
    """start_date부터 현재까지 각 월의 마지막 스냅샷 날짜 기준 전체 계좌 합계 반환.

    반환: {"2024-01": 10500000.0, "2024-02": 11200000.0, ...}
    """
    # 계좌별·월별 마지막 스냅샷을 CTE로 구한 뒤 합산
    # SQLAlchemy ORM subquery 혼합 사용 시 GROUP BY 컬럼 누락 오류가 발생해 text() CTE로 작성
    sql = text("""
        WITH per_account_month AS (
            SELECT
                s.account_id,
                to_char(s.snapshot_date, 'YYYY-MM') AS month,
                max(s.snapshot_date) AS last_date
            FROM asset_snapshots s
            JOIN asset_accounts a ON a.id = s.account_id
            WHERE s.user_id = :user_id
              AND s.snapshot_date >= :start_date
              AND a.is_active = true
              AND a.include_in_total = true
            GROUP BY s.account_id, to_char(s.snapshot_date, 'YYYY-MM')
        )
        SELECT pam.month, sum(s.amount_krw) AS total
        FROM asset_snapshots s
        JOIN asset_accounts a ON a.id = s.account_id
        JOIN per_account_month pam
            ON s.account_id = pam.account_id
           AND s.snapshot_date = pam.last_date
        WHERE s.user_id = :user_id
          AND a.is_active = true
          AND a.include_in_total = true
        GROUP BY pam.month
        ORDER BY pam.month
    """)
    result = await db.execute(sql, {"user_id": str(user_id), "start_date": start_date})
    return {row.month: float(row.total) for row in result.all()}


def _build_projection_curve(
    initial_value: float,
    pmt: float,
    r: float,
    start_date: date,
    total_months: int,
    monthly_actuals: dict[str, float],
) -> list[dict[str, Any]]:
    """월별 이론값과 실제값을 비교한 리스트 생성."""
    result = []
    for n in range(total_months):
        month_date = start_date + relativedelta(months=n)
        month_key = _month_key(month_date)

        if r == 0:
            projected = initial_value + pmt * n
        else:
            projected = initial_value * ((1 + r) ** n) + pmt * (((1 + r) ** n - 1) / r)

        actual = monthly_actuals.get(month_key)
        achievement_pct = round((actual / projected) * 100, 1) if actual and projected > 0 else None

        result.append(
            {
                "month": month_key,
                "projected_krw": round(projected),
                "actual_krw": round(actual) if actual is not None else None,
                "achievement_pct": achievement_pct,
                "has_data": actual is not None,
            }
        )
    return result


def _build_yearly_achievements(projection_months: list[dict]) -> list[dict[str, Any]]:
    """월별 데이터에서 연도별 달성율 계산 (각 연도의 마지막 월 기준)."""
    by_year: dict[int, dict] = {}
    for point in projection_months:
        year = int(point["month"][:4])
        by_year[year] = point  # 같은 연도의 마지막 월로 덮어쓰기

    result = []
    for year in sorted(by_year.keys()):
        point = by_year[year]
        projected = point["projected_krw"]
        actual = point["actual_krw"]
        achievement_pct = round((actual / projected) * 100, 1) if actual and projected > 0 else None
        result.append(
            {
                "year": year,
                "projected_year_end_krw": projected,
                "actual_year_end_krw": actual,
                "achievement_pct": achievement_pct,
                "has_data": point["has_data"],
            }
        )
    return result


def _calc_months_to_goal(initial_value: float, pmt: float, r: float, goal_amount: float) -> int | None:
    """현재 계획 기준 목표 달성까지 남은 개월 수. 최대 600개월(50년) 탐색."""
    for n in range(1, 601):
        if r == 0:
            fv = initial_value + pmt * n
        else:
            fv = initial_value * ((1 + r) ** n) + pmt * (((1 + r) ** n - 1) / r)
        if fv >= goal_amount:
            return n
    return None


def _calc_goal_timeline(
    initial_value: float,
    pmt: float,
    r: float,
    goal_amount: float,
    current_actual: float,
    start_date: date,
    months_to_goal: int | None,
) -> dict[str, Any]:
    today = datetime.now(timezone.utc).date()
    elapsed = _elapsed_months(start_date, today)

    # 이론 곡선에서 현재 월의 이론값
    n = elapsed
    if r == 0:
        projected_now = initial_value + pmt * n
    else:
        projected_now = initial_value * ((1 + r) ** n) + pmt * (((1 + r) ** n - 1) / r)

    on_track = (current_actual >= projected_now) if (current_actual and projected_now > 0) else None
    current_progress_pct = round((current_actual / goal_amount) * 100, 1) if goal_amount > 0 else None

    expected_goal_date: str | None = None
    if months_to_goal:
        expected = start_date + relativedelta(months=months_to_goal)
        expected_goal_date = expected.strftime("%Y-%m")

    # 실제 자산 기준으로 목표 달성까지 남은 개월 탐색 (앞서는/뒤처지는 개월 계산)
    lead_lag_months: int | None = None
    actual_expected_goal_date: str | None = None
    if months_to_goal and current_actual and projected_now > 0:
        actual_months_to_goal = _calc_months_to_goal(current_actual, pmt, r, goal_amount)
        if actual_months_to_goal:
            remaining_planned = months_to_goal - elapsed
            remaining_actual = actual_months_to_goal
            lead_lag_months = remaining_planned - remaining_actual  # 양수=앞서는 개월
            actual_expected = today + relativedelta(months=actual_months_to_goal)
            actual_expected_goal_date = actual_expected.strftime("%Y-%m")

    return {
        "months_to_goal": months_to_goal,
        "expected_goal_date": expected_goal_date,
        "actual_expected_goal_date": actual_expected_goal_date,
        "current_progress_pct": current_progress_pct,
        "on_track": on_track,
        "lead_lag_months": lead_lag_months,
    }


def _elapsed_months(start: date, end: date) -> int:
    delta = relativedelta(end, start)
    return delta.years * 12 + delta.months


def _month_key(d: date) -> str:
    return d.strftime("%Y-%m")
