"""dividend/drip_service.py 단위 테스트 — 순수 함수."""

from __future__ import annotations

from app.services.dividend.drip_service import calc_monthly_optimization


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
