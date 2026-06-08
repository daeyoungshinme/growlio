"""dividend/calculator.py 순수 함수 단위 테스트."""

import pytest

from app.services.dividend.calculator import calculate_position_dividend


class TestCalculatePositionDividend:
    """calculate_position_dividend: 종목별 배당 수익률/예상 배당금 계산."""

    def test_korean_stock_dps_based(self, override_settings):
        """국내 일반주식(KOSPI)은 DPS × 수량 기반으로 계산."""
        result = calculate_position_dividend(
            ticker="005930",
            market="KOSPI",
            yield_decimal=0.02,
            dps=1416.0,
            months=[4],
            value_krw=1_000_000.0,
            invested_krw=900_000.0,
            qty=100.0,
            override_months=None,
        )
        assert result["estimated_annual_krw"] == round(1416.0 * 100)
        assert result["currency"] == "KRW"
        assert result["estimated_monthly_usd"] is None  # usd_krw_rate=0

    def test_us_stock_yield_based(self, override_settings):
        """해외 주식은 yield × 평가금액 기반으로 계산."""
        result = calculate_position_dividend(
            ticker="AAPL",
            market="NASDAQ",
            yield_decimal=0.005,
            dps=1.0,
            months=[2, 5, 8, 11],
            value_krw=2_000_000.0,
            invested_krw=1_800_000.0,
            qty=10.0,
            override_months=None,
            usd_krw_rate=1300.0,
        )
        annual = 2_000_000.0 * 0.005
        assert result["estimated_annual_krw"] == round(annual)
        assert result["currency"] == "USD"
        assert result["estimated_monthly_usd"] == round(annual / 12 / 1300.0, 2)

    def test_us_stock_no_usd_rate_returns_none_monthly_usd(self, override_settings):
        """usd_krw_rate=0이면 estimated_monthly_usd=None."""
        result = calculate_position_dividend(
            ticker="MSFT",
            market="NYSE",
            yield_decimal=0.007,
            dps=0.0,
            months=[3, 6, 9, 12],
            value_krw=1_500_000.0,
            invested_krw=1_400_000.0,
            qty=5.0,
            override_months=None,
            usd_krw_rate=0.0,
        )
        assert result["estimated_monthly_usd"] is None

    def test_override_months_sets_is_manual_true(self, override_settings):
        """override_months 지정 시 dividend_months_is_manual=True."""
        result = calculate_position_dividend(
            ticker="005930",
            market="KOSPI",
            yield_decimal=0.02,
            dps=0.0,
            months=[4],
            value_krw=500_000.0,
            invested_krw=450_000.0,
            qty=50.0,
            override_months=[3, 6, 9, 12],
        )
        assert result["dividend_months_is_manual"] is True

    def test_no_override_months_sets_is_manual_false(self, override_settings):
        """override_months=None이면 dividend_months_is_manual=False."""
        result = calculate_position_dividend(
            ticker="AAPL",
            market="NASDAQ",
            yield_decimal=0.01,
            dps=0.5,
            months=[2, 8],
            value_krw=500_000.0,
            invested_krw=450_000.0,
            qty=5.0,
            override_months=None,
        )
        assert result["dividend_months_is_manual"] is False

    def test_zero_yield_and_dps_returns_zero_estimated(self, override_settings):
        """yield_decimal=0, dps=0이면 예상 배당금 0."""
        result = calculate_position_dividend(
            ticker="AAPL",
            market="NYSE",
            yield_decimal=0.0,
            dps=0.0,
            months=[],
            value_krw=1_000_000.0,
            invested_krw=900_000.0,
            qty=10.0,
            override_months=None,
        )
        assert result["estimated_annual_krw"] == 0
        assert result["estimated_monthly_krw"] == 0

    def test_abnormal_investment_yield_falls_back_to_yield_decimal(self, override_settings):
        """투자수익률이 50% 초과(비정상)면 yield_decimal 기반으로 폴백."""
        result = calculate_position_dividend(
            ticker="005935",
            market="KOSPI",
            yield_decimal=0.05,
            dps=10000.0,  # 비정상적으로 높은 DPS
            months=[4],
            value_krw=100_000.0,
            invested_krw=10_000.0,  # cost_per_share=10000, dps/cost_per_share=100% > 50%
            qty=1.0,
            override_months=None,
        )
        assert result["investment_yield"] == round(0.05 * 100, 2)

    def test_ticker_and_market_included_in_result(self, override_settings):
        """결과 dict에 ticker, market 포함."""
        result = calculate_position_dividend(
            ticker="MSFT",
            market="NASDAQ",
            yield_decimal=0.008,
            dps=2.0,
            months=[3, 6, 9, 12],
            value_krw=1_500_000.0,
            invested_krw=1_400_000.0,
            qty=5.0,
            override_months=None,
        )
        assert result["ticker"] == "MSFT"
        assert result["market"] == "NASDAQ"

    def test_korean_etf_uses_yield_not_dps(self, override_settings):
        """국내 ETF(코드 069xxx)는 yield × 평가금액 기반 계산."""
        result = calculate_position_dividend(
            ticker="069500",  # KODEX 200 — ETF prefix 069
            market="KOSPI",
            yield_decimal=0.03,
            dps=500.0,
            months=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
            value_krw=1_000_000.0,
            invested_krw=950_000.0,
            qty=10.0,
            override_months=None,
        )
        # ETF는 yield 기반: 1_000_000 * 0.03 = 30_000
        assert result["estimated_annual_krw"] == round(1_000_000.0 * 0.03)

    def test_dividend_yield_field_is_percent(self, override_settings):
        """dividend_yield 필드는 yield_decimal * 100 값."""
        result = calculate_position_dividend(
            ticker="AAPL",
            market="NASDAQ",
            yield_decimal=0.0075,
            dps=0.96,
            months=[2, 5, 8, 11],
            value_krw=1_000_000.0,
            invested_krw=900_000.0,
            qty=5.0,
            override_months=None,
        )
        assert result["dividend_yield"] == round(0.0075 * 100, 2)

    def test_estimated_monthly_is_annual_divided_by_12(self, override_settings):
        """estimated_monthly_krw는 annual // 12."""
        result = calculate_position_dividend(
            ticker="AAPL",
            market="NYSE",
            yield_decimal=0.02,
            dps=0.0,
            months=[3, 6, 9, 12],
            value_krw=1_200_000.0,
            invested_krw=1_000_000.0,
            qty=10.0,
            override_months=None,
        )
        annual = round(1_200_000.0 * 0.02)
        assert result["estimated_monthly_krw"] == round(annual / 12)
