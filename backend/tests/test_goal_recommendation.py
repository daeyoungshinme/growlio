"""goal_return_solver.py / goal_recommendation_service.py 단위 테스트."""

from __future__ import annotations

import random
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.goal_recommendation_service import (
    _months_until_year_end,
    _optimize_goal_portfolio,
    get_goal_recommendation,
)
from app.services.goal_return_solver import solve_required_annual_return_pct


class TestSolveRequiredAnnualReturnPct:
    def test_low_return_sufficient_when_deposits_dominate(self):
        r = solve_required_annual_return_pct(pv=0, pmt=1000, n_months=100, goal_amount=90_000)
        assert r is not None
        assert r < 5

    def test_known_case_matches_fv_formula(self):
        pv, pmt, n = 10_000_000.0, 500_000.0, 120
        annual_r = 0.06
        r_m = annual_r / 12
        fv = pv * (1 + r_m) ** n + pmt * (((1 + r_m) ** n - 1) / r_m)

        solved = solve_required_annual_return_pct(pv, pmt, n, fv)

        assert solved is not None
        assert solved == pytest.approx(6.0, abs=0.05)

    def test_unreachable_goal_returns_none(self):
        r = solve_required_annual_return_pct(pv=1.0, pmt=0.0, n_months=1, goal_amount=1_000_000_000.0)
        assert r is None


class TestMonthsUntilYearEnd:
    def test_future_year_is_positive(self):
        from datetime import date

        assert _months_until_year_end(date.today().year + 5) > 0

    def test_past_year_is_non_positive(self):
        from datetime import date

        assert _months_until_year_end(date.today().year - 5) <= 0


class TestOptimizeGoalPortfolio:
    def test_insufficient_candidates_returns_note(self):
        items, expected, note = _optimize_goal_portfolio(
            symbols=["A"],
            tickers=[("A", "A Inc", "NASDAQ")],
            cagr_pct=[10.0],
            returns_map={"A": [0.001] * 252},
            required_return_pct=5.0,
        )
        assert items == []
        assert expected is None
        assert note is not None

    def test_unreachable_required_return_returns_note(self):
        items, expected, note = _optimize_goal_portfolio(
            symbols=["A", "B"],
            tickers=[("A", "A Inc", "NASDAQ"), ("B", "B Inc", "NASDAQ")],
            cagr_pct=[5.0, 6.0],
            returns_map={"A": [0.001] * 252, "B": [0.0012] * 252},
            required_return_pct=50.0,
        )
        assert items == []
        assert expected is None
        assert "달성하기 어렵습니다" in note

    def test_feasible_case_produces_weights_summing_to_100(self):
        random.seed(1)
        r_a = [random.gauss(0.0006, 0.008) for _ in range(252)]
        r_b = [random.gauss(0.0003, 0.004) for _ in range(252)]

        items, expected, note = _optimize_goal_portfolio(
            symbols=["A", "B"],
            tickers=[("A", "고성장 ETF", "NASDAQ"), ("B", "저변동 ETF", "NASDAQ")],
            cagr_pct=[15.0, 4.0],
            returns_map={"A": r_a, "B": r_b},
            required_return_pct=8.0,
        )

        assert note is None
        assert items
        assert sum(i["weight"] for i in items) == pytest.approx(100.0, abs=0.1)
        assert expected >= 8.0 - 0.01


@pytest.mark.asyncio
class TestGetGoalRecommendation:
    async def test_not_configured_without_goal_amount(self):
        settings_row = SimpleNamespace(goal_amount=None, retirement_target_year=None)
        portfolio = SimpleNamespace(items=[], base_type="TOTAL_ASSETS")
        overview = {"total_assets_krw": 0}

        result = await get_goal_recommendation(None, portfolio, overview, settings_row)

        assert result.is_configured is False

    async def test_already_achieved_goal(self):
        settings_row = SimpleNamespace(
            goal_amount=1_000_000.0,
            retirement_target_year=9999,
            monthly_deposit_amount=100_000.0,
            annual_deposit_goal=None,
            annual_dividend_goal=None,
        )
        portfolio = SimpleNamespace(items=[], base_type="TOTAL_ASSETS")
        overview = {"total_assets_krw": 2_000_000.0}

        result = await get_goal_recommendation(None, portfolio, overview, settings_row)

        assert result.is_configured is True
        assert "이미" in result.note

    async def test_target_year_already_passed(self):
        settings_row = SimpleNamespace(
            goal_amount=1_000_000_000.0,
            retirement_target_year=2000,
            monthly_deposit_amount=100_000.0,
            annual_deposit_goal=None,
            annual_dividend_goal=None,
        )
        portfolio = SimpleNamespace(items=[], base_type="TOTAL_ASSETS")
        overview = {"total_assets_krw": 0.0}

        result = await get_goal_recommendation(None, portfolio, overview, settings_row)

        assert result.is_configured is True
        assert "지났습니다" in result.note

    async def test_full_happy_path_returns_recommended_items(self):
        settings_row = SimpleNamespace(
            goal_amount=100_000_000.0,
            retirement_target_year=9999,
            monthly_deposit_amount=1_000_000.0,
            annual_deposit_goal=None,
            annual_dividend_goal=2_000_000.0,
        )
        portfolio = SimpleNamespace(items=[], base_type="TOTAL_ASSETS")
        overview = {"total_assets_krw": 10_000_000.0}

        cagr_map = {
            ("SPY", "NYSE"): {"cagr_pct": 10.0},
            ("QQQ", "NASDAQ"): {"cagr_pct": 15.0},
            ("VOO", "NYSE"): {"cagr_pct": 9.0},
            ("VTI", "NYSE"): {"cagr_pct": 9.5},
            ("SCHD", "NYSE"): {"cagr_pct": 8.0},
            ("VYM", "NYSE"): {"cagr_pct": 7.0},
            ("069500", "KOSPI"): {"cagr_pct": 6.0},
            ("360750", "KOSPI"): {"cagr_pct": 9.0},
            ("133690", "KOSPI"): {"cagr_pct": 14.0},
            ("458730", "KOSPI"): {"cagr_pct": 5.0},
        }
        random.seed(7)
        returns_map = {
            sym: [random.gauss(0.0005, 0.01) for _ in range(252)]
            for sym in ["SPY", "QQQ", "VOO", "VTI", "SCHD", "VYM", "069500.KS", "360750.KS", "133690.KS", "458730.KS"]
        }
        dividend_map = {("SCHD", "NYSE"): 3.5, ("VYM", "NYSE"): 2.9}

        with (
            patch(
                "app.services.goal_recommendation_service.get_historical_returns",
                AsyncMock(return_value=cagr_map),
            ),
            patch(
                "app.services.goal_recommendation_service._fetch_dividend_yields",
                AsyncMock(return_value=dividend_map),
            ),
            patch(
                "app.services.goal_recommendation_service.fetch_yf_daily_returns",
                return_value=returns_map,
            ),
        ):
            result = await get_goal_recommendation(None, portfolio, overview, settings_row)

        assert result.is_configured is True
        assert result.required_return_pct is not None
        assert result.recommended_items
        assert sum(i.weight for i in result.recommended_items) == pytest.approx(100.0, abs=0.5)

    async def test_infeasible_required_return_reports_note(self):
        """필요수익률(연 60%)이 해석 가능한 범위 내지만 모든 후보 CAGR을 초과하면 추천 없이 note만 채워진다."""
        from datetime import date

        settings_row = SimpleNamespace(
            goal_amount=1_600_000.0,  # pv 100만원, 무적립, 1년 내 60% 수익률 필요
            retirement_target_year=date.today().year + 1,
            monthly_deposit_amount=0.0,
            annual_deposit_goal=None,
            annual_dividend_goal=None,
        )
        portfolio = SimpleNamespace(items=[], base_type="TOTAL_ASSETS")
        overview = {"total_assets_krw": 1_000_000.0}

        cagr_map = {("SPY", "NYSE"): {"cagr_pct": 10.0}, ("QQQ", "NASDAQ"): {"cagr_pct": 12.0}}
        returns_map = {"SPY": [0.0005] * 252, "QQQ": [0.0006] * 252}

        with (
            patch(
                "app.services.goal_recommendation_service.get_historical_returns",
                AsyncMock(return_value=cagr_map),
            ),
            patch(
                "app.services.goal_recommendation_service._fetch_dividend_yields",
                AsyncMock(return_value={}),
            ),
            patch(
                "app.services.goal_recommendation_service.fetch_yf_daily_returns",
                return_value=returns_map,
            ),
        ):
            result = await get_goal_recommendation(None, portfolio, overview, settings_row)

        assert result.is_configured is True
        assert result.recommended_items == []
        assert result.note is not None
