"""dca_service.py 순수 함수 단위 테스트."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from unittest.mock import AsyncMock

import pytest

from app.services.dca_service import (
    _build_projection_curve,
    _build_yearly_achievements,
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
        assert curve[0]["projected_krw"] == 0          # n=0: 0 + 1M*0 = 0
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
        result = _calc_goal_timeline(0.0, 1_000_000.0, 0.0, 50_000_000.0, 0.0, date(2024, 1, 1), 50)
        for key in ("months_to_goal", "expected_goal_date", "actual_expected_goal_date",
                    "current_progress_pct", "on_track", "lead_lag_months"):
            assert key in result

    def test_none_months_to_goal_gives_no_expected_date(self, override_settings):
        result = _calc_goal_timeline(0.0, 1.0, 0.0, 1e15, 0.0, date(2024, 1, 1), None)
        assert result["months_to_goal"] is None
        assert result["expected_goal_date"] is None

    def test_expected_goal_date_set_when_months_given(self, override_settings):
        result = _calc_goal_timeline(0.0, 1_000_000.0, 0.0, 12_000_000.0, 0.0, date(2024, 1, 1), 12)
        assert result["months_to_goal"] == 12
        assert result["expected_goal_date"] is not None

    def test_progress_pct_half_goal(self, override_settings):
        result = _calc_goal_timeline(0.0, 1_000_000.0, 0.0, 10_000_000.0, 5_000_000.0, date(2024, 1, 1), None)
        assert result["current_progress_pct"] == 50.0

    def test_zero_goal_amount_gives_none_progress(self, override_settings):
        result = _calc_goal_timeline(0.0, 1_000_000.0, 0.0, 0.0, 1_000_000.0, date(2024, 1, 1), None)
        assert result["current_progress_pct"] is None

    def test_with_return_rate(self, override_settings):
        result = _calc_goal_timeline(
            initial_value=10_000_000.0, pmt=500_000.0, r=0.005,
            goal_amount=100_000_000.0, current_actual=12_000_000.0,
            start_date=date(2020, 1, 1), months_to_goal=120,
        )
        assert result["months_to_goal"] == 120
        assert result["on_track"] is not None

    def test_lead_lag_computed_when_near_goal(self, override_settings):
        result = _calc_goal_timeline(
            initial_value=0.0, pmt=1_000_000.0, r=0.0,
            goal_amount=10_000_000.0, current_actual=9_000_000.0,
            start_date=date(2024, 1, 1), months_to_goal=10,
        )
        assert result["lead_lag_months"] is not None or result["actual_expected_goal_date"] is not None

    def test_no_lead_lag_when_zero_current_actual(self, override_settings):
        result = _calc_goal_timeline(
            initial_value=0.0, pmt=1_000_000.0, r=0.0,
            goal_amount=50_000_000.0, current_actual=0.0,
            start_date=date(2024, 1, 1), months_to_goal=50,
        )
        assert result["lead_lag_months"] is None


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
    async def test_configured_with_historical_actuals_no_current_month(
        self, mock_db, override_settings
    ):
        """이번 달 스냅샷 없고 과거 월 데이터 있을 때 최근 월 값 사용 (lines 78-79)."""
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

        past_row = SimpleNamespace(month="2024-01", total=12_000_000.0)
        execute_result = MagicMock()
        execute_result.first.return_value = None
        execute_result.all.return_value = [past_row]
        mock_db.execute = AsyncMock(return_value=execute_result)

        result = await get_dca_analysis(uuid.uuid4(), mock_db)

        assert result["is_configured"] is True
        assert isinstance(result["goal_timeline"], dict)
