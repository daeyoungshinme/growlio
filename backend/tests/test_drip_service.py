"""dividend/drip_service.py 단위 테스트 — 순수 함수."""
from __future__ import annotations

import pytest

from app.services.dividend.drip_service import (
    calc_monthly_optimization,
    simulate_drip,
)


class TestSimulateDrip:
    def test_basic_drip_returns_expected_structure(self, override_settings):
        result = simulate_drip(
            initial_portfolio_value=10_000_000.0,
            monthly_contribution=500_000.0,
            annual_return_pct=8.0,
            annual_dividend_yield_pct=3.0,
            n_years=5,
            drip=True,
        )

        assert result["n_years"] == 5
        assert result["annual_return_pct"] == 8.0
        assert result["annual_dividend_yield_pct"] == 3.0
        assert result["initial_portfolio_value"] == 10_000_000.0
        assert "final_value_drip" in result
        assert "final_value_cash" in result
        assert "drip_advantage_pct" in result
        assert "total_dividend_received_krw" in result
        assert "yearly_points" in result
        assert len(result["yearly_points"]) >= 5  # year-end points + i==0

    def test_drip_value_exceeds_cash_value(self, override_settings):
        result = simulate_drip(
            initial_portfolio_value=10_000_000.0,
            monthly_contribution=0.0,
            annual_return_pct=8.0,
            annual_dividend_yield_pct=5.0,
            n_years=10,
            drip=True,
        )

        assert result["final_value_drip"] >= result["final_value_cash"]
        assert result["drip_advantage_pct"] >= 0

    def test_zero_dividend_yield_no_advantage(self, override_settings):
        result = simulate_drip(
            initial_portfolio_value=10_000_000.0,
            monthly_contribution=0.0,
            annual_return_pct=8.0,
            annual_dividend_yield_pct=0.0,
            n_years=5,
            drip=True,
        )

        assert result["drip_advantage_pct"] == 0.0
        assert result["total_dividend_received_krw"] == 0.0

    def test_n_years_capped_at_50(self, override_settings):
        result = simulate_drip(
            initial_portfolio_value=1_000_000.0,
            monthly_contribution=0.0,
            annual_return_pct=5.0,
            annual_dividend_yield_pct=2.0,
            n_years=100,  # Should be capped
            drip=True,
        )

        assert result["n_years"] == 50

    def test_n_years_minimum_1(self, override_settings):
        result = simulate_drip(
            initial_portfolio_value=1_000_000.0,
            monthly_contribution=0.0,
            annual_return_pct=5.0,
            annual_dividend_yield_pct=2.0,
            n_years=0,  # Should be minimum 1
            drip=True,
        )

        assert result["n_years"] == 1

    def test_yearly_points_have_expected_fields(self, override_settings):
        result = simulate_drip(
            initial_portfolio_value=5_000_000.0,
            monthly_contribution=100_000.0,
            annual_return_pct=7.0,
            annual_dividend_yield_pct=2.5,
            n_years=3,
            drip=False,
        )

        for point in result["yearly_points"]:
            assert "year" in point
            assert "portfolio_value_drip" in point
            assert "portfolio_value_cash" in point
            assert "cumulative_dividend_krw" in point

    def test_positive_contribution_grows_portfolio(self, override_settings):
        result_with = simulate_drip(
            initial_portfolio_value=5_000_000.0,
            monthly_contribution=500_000.0,
            annual_return_pct=7.0,
            annual_dividend_yield_pct=2.0,
            n_years=5,
            drip=False,
        )
        result_without = simulate_drip(
            initial_portfolio_value=5_000_000.0,
            monthly_contribution=0.0,
            annual_return_pct=7.0,
            annual_dividend_yield_pct=2.0,
            n_years=5,
            drip=False,
        )

        assert result_with["final_value_cash"] > result_without["final_value_cash"]


class TestCalcMonthlyOptimization:
    def test_empty_input_returns_empty(self, override_settings):
        result = calc_monthly_optimization([])
        assert result == []

    def test_all_months_covered_returns_empty(self, override_settings):
        # When all 12 months have dividends above threshold
        summaries = [
            {
                "ticker": f"STOCK{m}",
                "name": f"Stock {m}",
                "market": "NASDAQ",
                "estimated_annual_krw": 120_000.0,
                "dividend_months": [m],
            }
            for m in range(1, 13)
        ]
        result = calc_monthly_optimization(summaries)
        # All months should be above threshold
        assert result == []

    def test_weak_months_get_suggestions(self, override_settings):
        # Stock A dominates months 1,4,7,10; Stock B is weak in months 2,5,8,11
        # Stock B's months are below threshold → B is suggested for those weak months
        summaries = [
            {
                "ticker": "STRONG",
                "name": "Strong Stock",
                "market": "KOSPI",
                "estimated_annual_krw": 1_200_000.0,
                "dividend_months": [1, 4, 7, 10],
            },
            {
                "ticker": "WEAK",
                "name": "Weak Stock",
                "market": "KOSPI",
                "estimated_annual_krw": 120_000.0,
                "dividend_months": [2, 5, 8, 11],
            },
        ]
        result = calc_monthly_optimization(summaries)
        # Months 2, 5, 8, 11 (WEAK pays) and 3, 6, 9, 12 (nobody pays) are weak
        # WEAK stock pays in [2, 5, 8, 11] → should appear in suggestions
        assert len(result) > 0
        assert all(s["ticker"] == "WEAK" for s in result)

    def test_max_3_suggestions_per_month(self, override_settings):
        summaries = [
            {
                "ticker": f"STOCK{i}",
                "name": f"Stock {i}",
                "market": "NASDAQ",
                "estimated_annual_krw": 12_000.0,
                "dividend_months": [1],  # All pay in month 1, weak for others
            }
            for i in range(10)
        ]
        result = calc_monthly_optimization(summaries)
        for month in range(1, 13):
            month_suggestions = [s for s in result if s["month"] == month]
            assert len(month_suggestions) <= 3

    def test_no_estimated_annual_skipped(self, override_settings):
        summaries = [
            {
                "ticker": "AAPL",
                "name": "Apple",
                "market": "NASDAQ",
                "estimated_annual_krw": 0.0,
                "dividend_months": [3, 6, 9, 12],
            }
        ]
        result = calc_monthly_optimization(summaries)
        assert result == []

    def test_no_dividend_months_skipped(self, override_settings):
        summaries = [
            {
                "ticker": "AAPL",
                "name": "Apple",
                "market": "NASDAQ",
                "estimated_annual_krw": 100_000.0,
                "dividend_months": [],
            }
        ]
        result = calc_monthly_optimization(summaries)
        assert result == []
