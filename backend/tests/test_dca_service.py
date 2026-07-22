"""dca_service.py 순수 함수 단위 테스트."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.services.dca_service import (
    _build_projection_curve,
    _build_yearly_achievements,
    _calc_acceleration_scenarios,
    _calc_goal_timeline,
    _calc_months_to_goal,
    _elapsed_months,
    _month_key,
    get_dca_analysis,
)

# ── _elapsed_months ──────────────────────────────────────────


class TestElapsedMonths:
    def test_same_date_is_zero(self, override_settings):
        d = date(2024, 1, 1)
        assert _elapsed_months(d, d) == 0

    def test_one_month_apart(self, override_settings):
        assert _elapsed_months(date(2024, 1, 1), date(2024, 2, 1)) == 1

    def test_one_year_apart(self, override_settings):
        assert _elapsed_months(date(2023, 1, 1), date(2024, 1, 1)) == 12

    def test_partial_month_counts_completed(self, override_settings):
        # 2024-01-01 → 2024-03-15 = 2 full months + some days
        assert _elapsed_months(date(2024, 1, 1), date(2024, 3, 15)) == 2


# ── _month_key ───────────────────────────────────────────────


class TestMonthKey:
    def test_format_yyyy_mm(self, override_settings):
        assert _month_key(date(2024, 3, 15)) == "2024-03"

    def test_december(self, override_settings):
        assert _month_key(date(2025, 12, 31)) == "2025-12"

    def test_january(self, override_settings):
        assert _month_key(date(2024, 1, 1)) == "2024-01"


# ── _calc_months_to_goal ─────────────────────────────────────


class TestCalcMonthsToGoal:
    def test_zero_return_rate_linear_growth(self, override_settings):
        """r=0이면 (goal - initial) / pmt 개월 후 목표 달성."""
        result = _calc_months_to_goal(
            initial_value=0.0,
            pmt=1_000_000.0,
            r=0.0,
            goal_amount=12_000_000.0,
        )
        assert result == 12

    def test_with_return_rate_faster(self, override_settings):
        """수익률이 있으면 순수 적립보다 빨리 목표 달성."""
        months_no_return = _calc_months_to_goal(0.0, 1_000_000.0, 0.0, 50_000_000.0)
        months_with_return = _calc_months_to_goal(0.0, 1_000_000.0, 0.05 / 12, 50_000_000.0)
        assert months_with_return < months_no_return  # type: ignore[operator]

    def test_unreachable_goal_returns_none(self, override_settings):
        """600개월 내 달성 불가능하면 None 반환."""
        result = _calc_months_to_goal(0.0, 1.0, 0.0, 10_000_000_000.0)
        assert result is None

    def test_already_at_goal_returns_early(self, override_settings):
        """이미 목표 달성 시 1 반환."""
        result = _calc_months_to_goal(
            initial_value=100_000_000.0,
            pmt=1_000_000.0,
            r=0.0,
            goal_amount=100_000_000.0,
        )
        assert result == 1


# ── _build_projection_curve ──────────────────────────────────


class TestBuildProjectionCurve:
    def test_length_matches_total_months(self, override_settings):
        curve = _build_projection_curve(
            initial_value=10_000_000.0,
            pmt=500_000.0,
            r=0.0,
            start_date=date(2024, 1, 1),
            total_months=12,
            monthly_actuals={},
        )
        assert len(curve) == 12

    def test_month_keys_are_sequential(self, override_settings):
        curve = _build_projection_curve(
            initial_value=0.0,
            pmt=1_000_000.0,
            r=0.0,
            start_date=date(2024, 1, 1),
            total_months=3,
            monthly_actuals={},
        )
        assert curve[0]["month"] == "2024-01"
        assert curve[1]["month"] == "2024-02"
        assert curve[2]["month"] == "2024-03"

    def test_actual_value_included_when_available(self, override_settings):
        actuals = {"2024-01": 10_500_000.0}
        curve = _build_projection_curve(
            initial_value=10_000_000.0,
            pmt=500_000.0,
            r=0.0,
            start_date=date(2024, 1, 1),
            total_months=2,
            monthly_actuals=actuals,
        )
        assert curve[0]["actual_krw"] == round(10_500_000.0)
        assert curve[0]["has_data"] is True
        assert curve[1]["actual_krw"] is None
        assert curve[1]["has_data"] is False

    def test_zero_return_linear_projection(self, override_settings):
        """r=0이면 projected_krw = initial + pmt * n (선형 증가)."""
        curve = _build_projection_curve(
            initial_value=0.0,
            pmt=1_000_000.0,
            r=0.0,
            start_date=date(2024, 1, 1),
            total_months=3,
            monthly_actuals={},
        )
        assert curve[0]["projected_krw"] == 0  # n=0: 0 + 1M*0 = 0
        assert curve[1]["projected_krw"] == 1_000_000  # n=1: 0 + 1M*1
        assert curve[2]["projected_krw"] == 2_000_000  # n=2: 0 + 1M*2

    def test_achievement_pct_calculated_correctly(self, override_settings):
        actuals = {"2024-01": 10_500_000.0}
        curve = _build_projection_curve(
            initial_value=10_000_000.0,
            pmt=0.0,
            r=0.0,
            start_date=date(2024, 1, 1),
            total_months=1,
            monthly_actuals=actuals,
        )
        # projected=10_000_000, actual=10_500_000 → 105.0%
        assert curve[0]["achievement_pct"] == 105.0


# ── _build_yearly_achievements ───────────────────────────────


class TestBuildYearlyAchievements:
    def test_extracts_last_month_per_year(self, override_settings):
        """각 연도의 마지막 월 데이터를 연간 대표값으로 사용."""
        months = [
            {"month": "2024-01", "projected_krw": 11_000_000, "actual_krw": 10_500_000, "has_data": True},
            {"month": "2024-12", "projected_krw": 22_000_000, "actual_krw": 21_000_000, "has_data": True},
            {"month": "2025-06", "projected_krw": 30_000_000, "actual_krw": None, "has_data": False},
        ]
        result = _build_yearly_achievements(months)
        # 2024: 12월이 대표값
        yr2024 = next(r for r in result if r["year"] == 2024)
        assert yr2024["projected_year_end_krw"] == 22_000_000

    def test_achievement_pct_for_year(self, override_settings):
        months = [
            {"month": "2024-12", "projected_krw": 20_000_000, "actual_krw": 21_000_000, "has_data": True},
        ]
        result = _build_yearly_achievements(months)
        assert result[0]["achievement_pct"] == round(21_000_000 / 20_000_000 * 100, 1)

    def test_no_actual_means_none_achievement(self, override_settings):
        months = [
            {"month": "2025-12", "projected_krw": 30_000_000, "actual_krw": None, "has_data": False},
        ]
        result = _build_yearly_achievements(months)
        assert result[0]["achievement_pct"] is None
        assert result[0]["actual_year_end_krw"] is None

    def test_years_sorted_ascending(self, override_settings):
        months = [
            {"month": "2025-06", "projected_krw": 30_000_000, "actual_krw": None, "has_data": False},
            {"month": "2024-12", "projected_krw": 20_000_000, "actual_krw": 20_000_000, "has_data": True},
        ]
        result = _build_yearly_achievements(months)
        years = [r["year"] for r in result]
        assert years == sorted(years)


# ── get_dca_analysis (미설정 케이스) ─────────────────────────


class TestGetDcaAnalysis:
    @pytest.mark.asyncio
    async def test_returns_not_configured_when_no_settings(self, mock_db, override_settings):
        """UserSettings 없으면 is_configured=False 반환."""
        from app.services.dca_service import get_dca_analysis

        mock_db.scalar = AsyncMock(return_value=None)
        result = await get_dca_analysis(uuid.uuid4(), mock_db)

        assert result["is_configured"] is False
        assert result["projection_months"] == []
        assert result["yearly_achievements"] == []

    @pytest.mark.asyncio
    async def test_returns_not_configured_when_missing_goal(self, mock_db, override_settings):
        """goal_amount 없으면 is_configured=False."""
        from types import SimpleNamespace

        from app.services.dca_service import get_dca_analysis

        settings = SimpleNamespace(
            monthly_deposit_amount=1_000_000,
            goal_annual_return_pct=7.0,
            goal_amount=None,  # 미설정
            goal_start_date=None,
            goal_initial_amount=None,
        )
        mock_db.scalar = AsyncMock(return_value=settings)
        result = await get_dca_analysis(uuid.uuid4(), mock_db)

        assert result["is_configured"] is False


# ── _calc_goal_timeline ──────────────────────────────────────


class TestCalcGoalTimeline:
    def test_returns_required_keys(self, override_settings):
        result = _calc_goal_timeline(0.0, 1_000_000.0, 0.0, 50_000_000.0, 0.0, date(2024, 1, 1), 50, 0.0)
        for key in (
            "months_to_goal",
            "expected_goal_date",
            "actual_expected_goal_date",
            "current_progress_pct",
            "on_track",
            "lead_lag_months",
            "acceleration_scenarios",
        ):
            assert key in result

    def test_none_months_to_goal_gives_no_expected_date(self, override_settings):
        result = _calc_goal_timeline(0.0, 1.0, 0.0, 1e15, 0.0, date(2024, 1, 1), None, 0.0)
        assert result["months_to_goal"] is None
        assert result["expected_goal_date"] is None

    def test_expected_goal_date_set_when_months_given(self, override_settings):
        result = _calc_goal_timeline(0.0, 1_000_000.0, 0.0, 12_000_000.0, 0.0, date(2024, 1, 1), 12, 0.0)
        assert result["months_to_goal"] == 12
        assert result["expected_goal_date"] is not None

    def test_progress_pct_half_goal(self, override_settings):
        result = _calc_goal_timeline(0.0, 1_000_000.0, 0.0, 10_000_000.0, 5_000_000.0, date(2024, 1, 1), None, 0.0)
        assert result["current_progress_pct"] == 50.0

    def test_zero_goal_amount_gives_none_progress(self, override_settings):
        result = _calc_goal_timeline(0.0, 1_000_000.0, 0.0, 0.0, 1_000_000.0, date(2024, 1, 1), None, 0.0)
        assert result["current_progress_pct"] is None

    def test_with_return_rate(self, override_settings):
        result = _calc_goal_timeline(
            initial_value=10_000_000.0,
            pmt=500_000.0,
            r=0.005,
            goal_amount=100_000_000.0,
            current_actual=12_000_000.0,
            start_date=date(2020, 1, 1),
            months_to_goal=120,
            annual_return_pct=6.0,
        )
        assert result["months_to_goal"] == 120
        assert result["on_track"] is not None

    def test_lead_lag_computed_when_near_goal(self, override_settings):
        result = _calc_goal_timeline(
            initial_value=0.0,
            pmt=1_000_000.0,
            r=0.0,
            goal_amount=10_000_000.0,
            current_actual=9_000_000.0,
            start_date=date(2024, 1, 1),
            months_to_goal=10,
            annual_return_pct=0.0,
        )
        assert result["lead_lag_months"] is not None or result["actual_expected_goal_date"] is not None

    def test_no_lead_lag_when_zero_current_actual(self, override_settings):
        result = _calc_goal_timeline(
            initial_value=0.0,
            pmt=1_000_000.0,
            r=0.0,
            goal_amount=50_000_000.0,
            current_actual=0.0,
            start_date=date(2024, 1, 1),
            months_to_goal=50,
            annual_return_pct=0.0,
        )
        assert result["lead_lag_months"] is None


# ── acceleration_scenarios ("N년 더 빨리 달성하려면?" 역산) ─────


class TestAccelerationScenarios:
    def test_monotonic_increase_with_years_earlier(self, override_settings):
        """더 많이 앞당길수록(years_earlier가 클수록) 필요 월 적립액도 커져야 한다."""
        result = _calc_goal_timeline(
            initial_value=0.0,
            pmt=1_000_000.0,
            r=0.0,
            goal_amount=60_000_000.0,
            current_actual=1_000.0,
            start_date=date(2020, 1, 1),
            months_to_goal=60,
            annual_return_pct=0.0,
        )
        scenarios = result["acceleration_scenarios"]
        assert len(scenarios) == 3
        years = [s["years_earlier"] for s in scenarios]
        assert years == sorted(years)
        deposits = [s["required_monthly_deposit"] for s in scenarios]
        assert deposits == sorted(deposits)
        extras = [s["extra_monthly_deposit"] for s in scenarios]
        assert extras == sorted(extras)
        assert all(e > 0 for e in extras)
        assert all(s["required_annual_deposit"] == round(s["required_monthly_deposit"] * 12, 2) for s in scenarios)
        # 더 많이 앞당길수록(짧은 기간) 적립액 고정 시 필요한 수익률도 커져야 한다
        returns = [s["required_return_pct"] for s in scenarios]
        assert all(r is not None for r in returns)
        assert returns == sorted(returns)
        assert all(s["extra_return_pct"] == round(s["required_return_pct"] - 0.0, 2) for s in scenarios)

    def test_empty_when_goal_already_achieved(self, override_settings):
        result = _calc_goal_timeline(
            initial_value=0.0,
            pmt=1_000_000.0,
            r=0.0,
            goal_amount=60_000_000.0,
            current_actual=100_000_000.0,
            start_date=date(2020, 1, 1),
            months_to_goal=60,
            annual_return_pct=0.0,
        )
        assert result["acceleration_scenarios"] == []

    def test_excludes_presets_with_non_positive_target_months(self, override_settings):
        """실제 페이스가 이미 12개월 이내면 1년 이상 앞당기는 프리셋은 의미가 없으므로 제외된다."""
        result = _calc_goal_timeline(
            initial_value=0.0,
            pmt=1_000_000.0,
            r=0.0,
            goal_amount=10_000_000.0,
            current_actual=1_000.0,
            start_date=date(2020, 1, 1),
            months_to_goal=10,
            annual_return_pct=0.0,
        )
        assert result["acceleration_scenarios"] == []

    def test_required_return_pct_none_when_unreachable(self, override_settings):
        """적립액 고정 시 탐색범위(연 -90%~500%) 안에서 해가 없으면 None(이 방법으론 달성 어려움)."""
        scenarios = _calc_acceleration_scenarios(
            pv=0.0,
            pmt=1.0,
            annual_return_pct=0.0,
            goal_amount=1e15,
            actual_months_to_goal=13,  # years=1 → target_n_months=1만 포함
            today=date(2024, 1, 1),
        )
        assert len(scenarios) == 1
        assert scenarios[0]["required_return_pct"] is None
        assert scenarios[0]["extra_return_pct"] is None
        # 적립액 쪽 역산(solve_required_monthly_deposit)은 대수적 계산이라 극단값에서도 None이 아니어야 함
        assert scenarios[0]["required_monthly_deposit"] is not None


# ── get_dca_analysis (설정된 케이스) ─────────────────────────


class TestGetDcaAnalysisConfigured:
    @pytest.mark.asyncio
    async def test_configured_returns_projection(self, mock_db, override_settings):
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        settings_obj = SimpleNamespace(
            monthly_deposit_amount=1_000_000,
            goal_annual_return_pct=7.0,
            goal_amount=50_000_000.0,
            goal_start_date=datetime(2020, 1, 1),
            goal_initial_amount=None,
        )
        mock_db.scalar = AsyncMock(return_value=settings_obj)

        execute_result = MagicMock()
        execute_result.first.return_value = None
        execute_result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=execute_result)

        result = await get_dca_analysis(uuid.uuid4(), mock_db)

        assert result["is_configured"] is True
        assert isinstance(result["projection_months"], list)
        assert len(result["projection_months"]) > 0
        assert "goal_timeline" in result

    @pytest.mark.asyncio
    async def test_configured_with_initial_value_from_db(self, mock_db, override_settings):
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        settings_obj = SimpleNamespace(
            monthly_deposit_amount=500_000,
            goal_annual_return_pct=5.0,
            goal_amount=10_000_000.0,
            goal_start_date=datetime(2023, 1, 1),
            goal_initial_amount=None,
        )
        mock_db.scalar = AsyncMock(return_value=settings_obj)

        snap_row = SimpleNamespace(total=5_000_000.0)
        execute_result = MagicMock()
        execute_result.first.return_value = snap_row
        execute_result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=execute_result)

        result = await get_dca_analysis(uuid.uuid4(), mock_db)

        assert result["is_configured"] is True

    @pytest.mark.asyncio
    async def test_configured_with_manual_initial_amount(self, mock_db, override_settings):
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        settings_obj = SimpleNamespace(
            monthly_deposit_amount=1_000_000,
            goal_annual_return_pct=5.0,
            goal_amount=50_000_000.0,
            goal_start_date=datetime(2024, 1, 1),
            goal_initial_amount=10_000_000,
        )
        mock_db.scalar = AsyncMock(return_value=settings_obj)

        execute_result = MagicMock()
        execute_result.first.return_value = None
        execute_result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=execute_result)

        result = await get_dca_analysis(uuid.uuid4(), mock_db)

        assert result["is_configured"] is True

    @pytest.mark.asyncio
    async def test_configured_zero_return_rate(self, mock_db, override_settings):
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        settings_obj = SimpleNamespace(
            monthly_deposit_amount=1_000_000,
            goal_annual_return_pct=0.0,
            goal_amount=12_000_000.0,
            goal_start_date=datetime(2024, 1, 1),
            goal_initial_amount=0,
        )
        mock_db.scalar = AsyncMock(return_value=settings_obj)

        execute_result = MagicMock()
        execute_result.first.return_value = None
        execute_result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=execute_result)

        result = await get_dca_analysis(uuid.uuid4(), mock_db)

        # goal_annual_return_pct=0.0 is falsy → is_configured=False (no projection)
        assert result["is_configured"] is False
        assert result["projection_months"] == []

    @pytest.mark.asyncio
    async def test_current_progress_pct_uses_unified_asset_total(self, mock_db, override_settings):
        """current_progress_pct는 월별 스냅샷 CTE가 아니라 대시보드와 동일한
        build_asset_totals(총자산) 값을 사용해야 두 화면의 진행율이 일치한다."""
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        settings_obj = SimpleNamespace(
            monthly_deposit_amount=1_000_000,
            goal_annual_return_pct=7.0,
            goal_amount=50_000_000.0,
            goal_start_date=datetime(2020, 1, 1),
            goal_initial_amount=10_000_000,
        )
        mock_db.scalar = AsyncMock(return_value=settings_obj)

        # 월별 스냅샷 CTE 쪽 데이터는 일부러 비워도(이번 달 미동기화 등) current_progress_pct에는
        # 영향을 주지 않아야 함 — build_asset_totals가 유일한 소스여야 함.
        execute_result = MagicMock()
        execute_result.first.return_value = None
        execute_result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=execute_result)

        with patch(
            "app.services.dca_service.build_asset_totals",
            AsyncMock(return_value=(25_000_000.0, 0.0, 0.0, {})),
        ):
            result = await get_dca_analysis(uuid.uuid4(), mock_db)

        assert result["is_configured"] is True
        assert result["goal_timeline"]["current_progress_pct"] == 50.0

    @pytest.mark.asyncio
    async def test_current_progress_pct_excludes_real_estate(self, mock_db, override_settings):
        """부동산 계좌 순자산은 목표 진행율 계산에서 제외되어야 한다 — 부동산은 목표 역산
        추천/DCA 복리 곡선 어느 쪽도 성장을 모델링하지 않으므로, 부동산을 추가/편집한다고
        해서 진행율이 왜곡되어서는 안 된다."""
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        settings_obj = SimpleNamespace(
            monthly_deposit_amount=1_000_000,
            goal_annual_return_pct=7.0,
            goal_amount=50_000_000.0,
            goal_start_date=datetime(2020, 1, 1),
            goal_initial_amount=10_000_000,
        )
        mock_db.scalar = AsyncMock(return_value=settings_obj)

        execute_result = MagicMock()
        execute_result.first.return_value = None
        execute_result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=execute_result)

        # 총자산 45M 중 20M이 부동산 순자산 → 투자자산 기준 25M/50M = 50%
        with patch(
            "app.services.dca_service.build_asset_totals",
            AsyncMock(return_value=(45_000_000.0, 0.0, 0.0, {"REAL_ESTATE": 20_000_000.0})),
        ):
            result = await get_dca_analysis(uuid.uuid4(), mock_db)

        assert result["is_configured"] is True
        assert result["goal_timeline"]["current_progress_pct"] == 50.0
