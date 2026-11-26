"""적립식 투자(DCA) 복리계산 및 월/년 목표달성율 서비스."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

from dateutil.relativedelta import relativedelta
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import AssetType
from app.models.asset import AssetAccount, AssetSnapshot
from app.models.user import UserSettings
from app.services._settings_queries import get_settings_row
from app.services.goal.goal_return_solver import (
    future_value_monthly,
    monthly_rate,
    solve_required_annual_return_pct,
    solve_required_monthly_deposit,
)
from app.services.portfolio.composition_calculator import build_asset_totals, exclude_real_estate
from app.utils.cache_keys import (
    TTL_DCA_ANALYSIS,
    CacheStoreType,
    dca_analysis_key,
    get_cached_json,
    set_cached_json,
)
from app.utils.kst import month_key as _month_key
from app.utils.kst import today_kst

_DCA_MAX_MONTHS = 600  # 목표 달성까지 탐색하는 최대 개월 수 (50년)

# 가속 시나리오("N년 더 빨리 달성하려면 월 적립액을 얼마로 늘려야 하는지") 프리셋
_ACCELERATION_YEARS_PRESETS: tuple[int, ...] = (1, 2, 3)


def _number(value: Any) -> float | None:
    """0은 유효한 값이다(수익률 0%, 거치식 적립 0원, 시작 금액 0원) — 비운 값은 None으로 저장된다."""
    return float(value) if value is not None else None


def _dca_params(
    settings_row: UserSettings | None,
) -> tuple[float | None, float | None, float | None, date | None, float | None]:
    """(월 적립액, 목표 연수익률%, 목표 금액, 시작일, 직접 입력한 시작 금액)."""
    if settings_row is None:
        return None, None, None, None, None
    return (
        _number(settings_row.monthly_deposit_amount),
        _number(settings_row.goal_annual_return_pct),
        _number(settings_row.goal_amount),
        settings_row.goal_start_date,
        _number(settings_row.goal_initial_amount),
    )


async def compute_goal_expected_month(
    user_id: uuid.UUID, db: AsyncSession, settings_row: UserSettings | None, investable_assets_krw: float
) -> str | None:
    """홈 목표 카드의 "YYYY-MM 달성 예상"(실적 기준 우선, 없으면 계획 기준).

    `get_dca_analysis`의 goal_timeline과 같은 계산을 투영 곡선·월별 실적 없이 한다 — 대시보드가 이 값만 받으려고
    적립 분석 전체를 부르지 않게(plans/151 B1)."""
    pmt, annual_return_pct, goal_amount, start_dt, manual_initial = _dca_params(settings_row)
    if pmt is None or annual_return_pct is None or not goal_amount or start_dt is None:
        return None
    r = monthly_rate(annual_return_pct / 100)
    initial_value = manual_initial if manual_initial is not None else await _get_initial_value(user_id, start_dt, db)
    months_to_goal = _calc_months_to_goal(initial_value, pmt, r, goal_amount)
    timeline = _calc_goal_timeline(
        initial_value,
        pmt,
        r,
        goal_amount,
        investable_assets_krw,
        start_dt,
        months_to_goal,
        annual_return_pct,
        with_scenarios=False,
    )
    expected: str | None = timeline["actual_expected_goal_date"] or timeline["expected_goal_date"]
    return expected


async def get_dca_analysis(user_id: uuid.UUID, db: AsyncSession, cache: CacheStoreType = None) -> dict[str, Any]:
    """DCA 복리 이론 곡선과 실제 자산을 비교한 분석 결과 반환."""
    cached = await get_cached_json(cache, dca_analysis_key(user_id))
    if cached is not None:
        return cached

    settings_row = await get_settings_row(db, user_id)
    pmt, annual_return_pct, goal_amount, start_dt, manual_initial = _dca_params(settings_row)

    is_configured = pmt is not None and annual_return_pct is not None and bool(goal_amount) and bool(start_dt)

    dca_settings = {
        "monthly_deposit_amount": pmt,
        "goal_annual_return_pct": annual_return_pct,
        "goal_amount": goal_amount,
        "goal_start_date": start_dt.isoformat() if start_dt else None,
        "goal_initial_amount": manual_initial,
    }

    if not is_configured:
        result = {
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
        await set_cached_json(cache, dca_analysis_key(user_id), result, TTL_DCA_ANALYSIS)
        return result

    if pmt is None or annual_return_pct is None or goal_amount is None or start_dt is None:
        raise ValueError("DCA 목표 설정값이 누락되었습니다.")

    start_date: date = start_dt  # Date 컬럼(plans/114 B2) — tz 변환 없음
    today = today_kst()
    r = monthly_rate(annual_return_pct / 100)

    if manual_initial is not None:
        initial_value = manual_initial
    else:
        initial_value = await _get_initial_value(user_id, start_date, db)
    monthly_actuals = await _get_monthly_actual_values(user_id, start_date, db)

    # goal_start_date부터 오늘까지 + 향후 미래 예측 (총 목표 달성까지)
    months_to_goal = _calc_months_to_goal(initial_value, pmt, r, goal_amount)
    total_months = max(
        _elapsed_months(start_date, today) + 1,
        months_to_goal if months_to_goal else _elapsed_months(start_date, today) + 1,
    )

    projection_months = _build_projection_curve(initial_value, pmt, r, start_date, total_months, monthly_actuals)
    yearly_achievements = _build_yearly_achievements(projection_months)

    # 대시보드 "자산 목표 달성률"과 동일한 소스(build_asset_totals)를 사용해
    # 두 화면의 진행율이 항상 일치하도록 함 — 월별 스냅샷 CTE와는 별도 계산.
    # 부동산은 목표 역산 추천/DCA 복리 곡선 어느 쪽도 성장을 모델링하지 않으므로 제외
    # (부동산 추가만으로 진행율이 왜곡되는 것을 방지 — investable_assets_krw).
    total_assets_krw, _, _, by_type = await build_asset_totals(user_id, db, cache)
    investable_assets_krw = exclude_real_estate(total_assets_krw, by_type)

    goal_timeline = _calc_goal_timeline(
        initial_value, pmt, r, goal_amount, investable_assets_krw, start_date, months_to_goal, annual_return_pct
    )

    result = {
        "settings": dca_settings,
        "projection_months": projection_months,
        "yearly_achievements": yearly_achievements,
        "goal_timeline": goal_timeline,
        "is_configured": True,
    }
    await set_cached_json(cache, dca_analysis_key(user_id), result, TTL_DCA_ANALYSIS)
    return result


_INITIAL_SNAPSHOT_WINDOW_DAYS = 31


async def _get_initial_value(user_id: uuid.UUID, start_date: date, db: AsyncSession) -> float:
    """목표 시작 시점의 투자자산 합계(부동산·비활성·합산 제외 계좌 제외).

    계좌마다 시작일 이후 31일 안의 첫 스냅샷, 없으면 시작일 전 마지막 스냅샷을 골라 더한다 — 계좌별 동기화
    날짜가 달라도 "그날 스냅샷이 있는 계좌만" 더해 과소 추정되지 않게. 시작 무렵 스냅샷이 하나도 없으면
    (앱 사용 전 시작일) 시작일 이후 첫 스냅샷 날짜의 합계를 쓴다.
    """
    sql = text("""
        WITH eligible AS (
            SELECT s.account_id, s.snapshot_date, s.amount_krw
            FROM asset_snapshots s
            JOIN asset_accounts a ON a.id = s.account_id
            WHERE s.user_id = :user_id
              AND a.is_active = true
              AND a.include_in_total = true
              AND a.asset_type != 'REAL_ESTATE'
        ),
        after_start AS (
            SELECT account_id, min(snapshot_date) AS d FROM eligible
            WHERE snapshot_date >= :start_date AND snapshot_date <= :window_end
            GROUP BY account_id
        ),
        before_start AS (
            SELECT account_id, max(snapshot_date) AS d FROM eligible
            WHERE snapshot_date < :start_date
            GROUP BY account_id
        ),
        chosen AS (
            SELECT coalesce(a.account_id, b.account_id) AS account_id, coalesce(a.d, b.d) AS d
            FROM after_start a FULL OUTER JOIN before_start b ON a.account_id = b.account_id
        )
        SELECT sum(e.amount_krw) AS total
        FROM eligible e
        JOIN chosen c ON e.account_id = c.account_id AND e.snapshot_date = c.d
    """)
    window_end = start_date + timedelta(days=_INITIAL_SNAPSHOT_WINDOW_DAYS)
    result = await db.execute(sql, {"user_id": str(user_id), "start_date": start_date, "window_end": window_end})
    row = result.first()
    if row is not None and row.total is not None:
        return float(row.total)

    result_after = await db.execute(
        select(AssetSnapshot.snapshot_date, func.sum(AssetSnapshot.amount_krw).label("total"))
        .join(AssetAccount, AssetAccount.id == AssetSnapshot.account_id)
        .where(
            AssetSnapshot.user_id == user_id,
            AssetSnapshot.snapshot_date >= start_date,
            AssetAccount.is_active == True,
            AssetAccount.include_in_total == True,
            AssetAccount.asset_type != AssetType.REAL_ESTATE,
        )
        .group_by(AssetSnapshot.snapshot_date)
        .order_by(AssetSnapshot.snapshot_date.asc())
        .limit(1)
    )
    row = result_after.first()
    return float(row.total) if row else 0.0


async def _get_monthly_actual_values(user_id: uuid.UUID, start_date: date, db: AsyncSession) -> dict[str, float]:
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
              AND a.asset_type != 'REAL_ESTATE'
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
          AND a.asset_type != 'REAL_ESTATE'
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

        projected = future_value_monthly(initial_value, pmt, r, n)

        actual = monthly_actuals.get(month_key)
        # 실적 0원도 0% 달성으로 보인다(None이면 데이터 없음과 구분되지 않는다)
        achievement_pct = round((actual / projected) * 100, 1) if actual is not None and projected > 0 else None

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
        # 실적 0원도 0% 달성으로 보인다(None이면 데이터 없음과 구분되지 않는다)
        achievement_pct = round((actual / projected) * 100, 1) if actual is not None and projected > 0 else None
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
    """initial_value에서 출발해 목표에 닿기까지 걸리는 개월 수. 이미 달성했으면 0.

    초기 투자금을 넘기면 시작일부터의 총 기간이고, 현재 자산을 넘겨야 오늘부터 남은 기간이다.
    """
    if initial_value >= goal_amount:
        return 0
    for n in range(1, _DCA_MAX_MONTHS + 1):
        if future_value_monthly(initial_value, pmt, r, n) >= goal_amount:
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
    annual_return_pct: float,
    *,
    with_scenarios: bool = True,
) -> dict[str, Any]:
    """`with_scenarios=False`면 "더 빨리 달성하려면?" 시나리오를 건너뛴다(달성 예상월만 필요한 홈)."""
    today = today_kst()
    elapsed = _elapsed_months(start_date, today)

    # 이론 곡선에서 현재 월의 이론값
    projected_now = future_value_monthly(initial_value, pmt, r, elapsed)

    not_started = start_date > today
    # 시작 전에는 비교 대상이 없다 — 예전에는 경과 개월이 음수라 이론값이 초기금액보다 낮아져 "순항"으로 나왔다
    on_track = (current_actual >= projected_now) if (current_actual and projected_now > 0 and not not_started) else None
    current_progress_pct = round((current_actual / goal_amount) * 100, 1) if goal_amount > 0 else None

    expected_goal_date: str | None = None
    if months_to_goal is not None:
        expected = start_date + relativedelta(months=months_to_goal)
        expected_goal_date = expected.strftime("%Y-%m")

    # 실제 자산 기준으로 목표 달성까지 남은 개월 탐색 (앞서는/뒤처지는 개월 계산)
    lead_lag_months: int | None = None
    actual_expected_goal_date: str | None = None
    acceleration_scenarios: list[dict[str, Any]] = []
    if months_to_goal is not None and current_actual and projected_now > 0 and not not_started:
        actual_months_to_goal = _calc_months_to_goal(current_actual, pmt, r, goal_amount)
        if actual_months_to_goal is not None:
            remaining_planned = months_to_goal - elapsed
            remaining_actual = actual_months_to_goal
            lead_lag_months = remaining_planned - remaining_actual  # 양수=앞서는 개월
            actual_expected = today + relativedelta(months=actual_months_to_goal)
            actual_expected_goal_date = actual_expected.strftime("%Y-%m")

            if with_scenarios and current_actual < goal_amount:
                acceleration_scenarios = _calc_acceleration_scenarios(
                    current_actual, pmt, annual_return_pct, goal_amount, actual_months_to_goal, today
                )

    return {
        "months_to_goal": months_to_goal,
        "expected_goal_date": expected_goal_date,
        "actual_expected_goal_date": actual_expected_goal_date,
        "current_progress_pct": current_progress_pct,
        "on_track": on_track,
        "lead_lag_months": lead_lag_months,
        "acceleration_scenarios": acceleration_scenarios,
    }


def _calc_acceleration_scenarios(
    pv: float,
    pmt: float,
    annual_return_pct: float,
    goal_amount: float,
    actual_months_to_goal: int,
    today: date,
) -> list[dict[str, Any]]:
    """현재 페이스보다 N년 더 빨리 목표를 달성하려면 월 적립액(또는 수익률)을 얼마로 늘려야 하는지 역산."""
    scenarios = []
    for years in _ACCELERATION_YEARS_PRESETS:
        target_n_months = actual_months_to_goal - years * 12
        if target_n_months <= 0:
            continue
        required_monthly_deposit = solve_required_monthly_deposit(pv, annual_return_pct, target_n_months, goal_amount)
        # 적립액은 현재(pmt) 그대로 두고 수익률만 높인다면 필요한 연수익률 — 탐색범위 밖이면 None
        required_return_pct = solve_required_annual_return_pct(pv, pmt, target_n_months, goal_amount)
        extra_return_pct = (
            round(required_return_pct - annual_return_pct, 2) if required_return_pct is not None else None
        )
        new_expected = today + relativedelta(months=target_n_months)
        scenarios.append(
            {
                "years_earlier": years,
                "new_expected_goal_date": new_expected.strftime("%Y-%m"),
                "required_monthly_deposit": required_monthly_deposit,
                "required_annual_deposit": round(required_monthly_deposit * 12, 2),
                "extra_monthly_deposit": round(max(required_monthly_deposit - pmt, 0.0), 2),
                "required_return_pct": required_return_pct,
                "extra_return_pct": extra_return_pct,
            }
        )
    return scenarios


def _elapsed_months(start: date, end: date) -> int:
    """경과 개월 수. 시작일이 미래면 0."""
    delta = relativedelta(end, start)
    return max(delta.years * 12 + delta.months, 0)
