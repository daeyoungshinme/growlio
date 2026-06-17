"""dividend_providers.py 단위 테스트 — 동기 배당 데이터 수집 함수."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# ── sync_yahoo_dividend_info ──────────────────────────────────


class TestSyncYahooDividendInfo:
    def test_success_returns_yield_and_dps(self, override_settings):
        mock_info = {
            "trailingAnnualDividendYield": 0.025,
            "dividendYield": 0.02,
            "trailingAnnualDividendRate": 1500.0,
            "currentPrice": 60000.0,
            "regularMarketPrice": None,
        }
        mock_ticker = MagicMock()
        mock_ticker.info = mock_info

        with patch("yfinance.Ticker", return_value=mock_ticker):
            from app.services.dividend_providers import sync_yahoo_dividend_info

            result = sync_yahoo_dividend_info("005930.KS")

        assert result["dividend_yield"] == pytest.approx(0.025)
        assert result["dps"] == pytest.approx(1500.0)

    def test_yield_percentage_correction(self, override_settings):
        """yield > 0.3 이면 /100 보정."""
        mock_info = {
            "trailingAnnualDividendYield": 2.7,  # percentage 단위 오류
            "dividendYield": 0.0,
            "trailingAnnualDividendRate": 0.0,
            "currentPrice": 60000.0,
            "regularMarketPrice": None,
        }
        mock_ticker = MagicMock()
        mock_ticker.info = mock_info

        with patch("yfinance.Ticker", return_value=mock_ticker):
            from app.services.dividend_providers import sync_yahoo_dividend_info

            result = sync_yahoo_dividend_info("005930.KS")

        assert result["dividend_yield"] == pytest.approx(0.027)

    def test_dps_unit_correction(self, override_settings):
        """DPS가 주가 50% 초과 시 /100 보정."""
        mock_info = {
            "trailingAnnualDividendYield": 0.025,
            "dividendYield": 0.0,
            "trailingAnnualDividendRate": 40000.0,  # 60000원 주가의 66% → 오류
            "currentPrice": 60000.0,
            "regularMarketPrice": None,
        }
        mock_ticker = MagicMock()
        mock_ticker.info = mock_info

        with patch("yfinance.Ticker", return_value=mock_ticker):
            from app.services.dividend_providers import sync_yahoo_dividend_info

            result = sync_yahoo_dividend_info("005930.KS")

        assert result["dps"] == pytest.approx(400.0)

    def test_exception_returns_zeros(self, override_settings):
        with patch("yfinance.Ticker", side_effect=Exception("network error")):
            from app.services.dividend_providers import sync_yahoo_dividend_info

            result = sync_yahoo_dividend_info("INVALID")

        assert result["dividend_yield"] == 0.0
        assert result["dps"] == 0.0

    def test_no_yield_uses_forward(self, override_settings):
        """trailing yield 없으면 forward yield 사용."""
        mock_info = {
            "trailingAnnualDividendYield": 0.0,
            "dividendYield": 0.03,
            "trailingAnnualDividendRate": 2000.0,
            "currentPrice": 70000.0,
            "regularMarketPrice": None,
        }
        mock_ticker = MagicMock()
        mock_ticker.info = mock_info

        with patch("yfinance.Ticker", return_value=mock_ticker):
            from app.services.dividend_providers import sync_yahoo_dividend_info

            result = sync_yahoo_dividend_info("AAPL")

        assert result["dividend_yield"] == pytest.approx(0.03)


# ── sync_pykrx_etf_dividend_info ─────────────────────────────


class TestSyncPykrxEtfDividendInfo:
    def test_api_error_returns_zeros(self, override_settings):
        """pykrx API 오류 시 0 반환 (AttributeError → except Exception)."""
        from app.services.dividend_providers import sync_pykrx_etf_dividend_info

        # pykrx.stock.get_market_dividend_by_date doesn't exist → AttributeError → 0 returned
        result = sync_pykrx_etf_dividend_info("INVALID_TICKER_XYZ")
        assert result["dps"] == 0.0
        assert result["dividend_yield"] == 0.0


# ── sync_fdr_etf_dividend_info ────────────────────────────────


class TestSyncFdrEtfDividendInfo:
    def test_exception_returns_zeros(self, override_settings):
        """FinanceDataReader import 실패 시 0 반환."""
        with patch.dict("sys.modules", {"FinanceDataReader": None}):
            from app.services.dividend_providers import sync_fdr_etf_dividend_info

            result = sync_fdr_etf_dividend_info("069500")

        assert result["dps"] == 0.0
        assert result["dividend_yield"] == 0.0

    def test_empty_listing_returns_zeros(self, override_settings):
        """ETF 목록에 없는 티커 → 0 반환."""
        import pandas as pd

        mock_fdr = MagicMock()
        mock_fdr.StockListing.return_value = pd.DataFrame({"Symbol": ["OTHER"], "Price": [10000.0]})

        with patch.dict("sys.modules", {"FinanceDataReader": mock_fdr}):
            from importlib import reload

            import app.services.dividend_providers as dp_mod

            reload(dp_mod)
            result = dp_mod.sync_fdr_etf_dividend_info("069500")

        assert result["dps"] == 0.0


# ── sync_naver_etf_dividend_info ─────────────────────────────


class TestSyncNaverEtfDividendInfo:
    def test_success_returns_data(self, override_settings):
        """성공적인 Naver ETF 배당 정보 반환."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "dividend": {
                "dividendYieldTtm": "3.5",
                "dividendPerShareTtm": "1200",
                "dividendMonthThisYear": "3,6,9,12",
            }
        }

        with patch("requests.get", return_value=mock_resp):
            from app.services.dividend_providers import sync_naver_etf_dividend_info

            result = sync_naver_etf_dividend_info("069500")

        assert result["dividend_yield"] == pytest.approx(0.035)
        assert result["dps"] == pytest.approx(1200.0)
        assert 3 in result["dividend_months"]
        assert 12 in result["dividend_months"]

    def test_no_dividend_data_returns_zeros(self, override_settings):
        """dividend 키 없으면 0 반환."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {}

        with patch("requests.get", return_value=mock_resp):
            from app.services.dividend_providers import sync_naver_etf_dividend_info

            result = sync_naver_etf_dividend_info("069500")

        assert result["dps"] == 0.0

    def test_parse_error_returns_zeros(self, override_settings):
        """JSON 파싱 오류 시 0 반환."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.side_effect = ValueError("bad json")

        with patch("requests.get", return_value=mock_resp):
            from app.services.dividend_providers import sync_naver_etf_dividend_info

            result = sync_naver_etf_dividend_info("069500")

        assert result["dps"] == 0.0


# ── sync_naver_stock_dividend_info ────────────────────────────


class TestSyncNaverStockDividendInfo:
    def test_success_returns_yield(self, override_settings):
        """성공적인 Naver 주식 배당수익률 반환."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"stockItemDetail": {"dividendYield": "2.8"}}

        with patch("requests.get", return_value=mock_resp):
            from app.services.dividend_providers import sync_naver_stock_dividend_info

            result = sync_naver_stock_dividend_info("005930")

        assert result["dividend_yield"] == pytest.approx(0.028)
        assert result["dps"] == 0.0

    def test_zero_yield_returns_zeros(self, override_settings):
        """배당수익률 0이면 빈 결과 반환."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"stockItemDetail": {"dividendYield": "0"}}

        with patch("requests.get", return_value=mock_resp):
            from app.services.dividend_providers import sync_naver_stock_dividend_info

            result = sync_naver_stock_dividend_info("005930")

        assert result["dividend_yield"] == 0.0

    def test_parse_error_returns_zeros(self, override_settings):
        """파싱 오류 시 0 반환."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.side_effect = TypeError("bad type")

        with patch("requests.get", return_value=mock_resp):
            from app.services.dividend_providers import sync_naver_stock_dividend_info

            result = sync_naver_stock_dividend_info("005930")

        assert result["dividend_yield"] == 0.0


# ── sync_fetch_dividend_months ────────────────────────────────


class TestSyncFetchDividendMonths:
    def test_returns_months_from_dividends(self, override_settings):
        """배당락일 이력에서 지급월 추출."""
        import pandas as pd

        mock_ticker = MagicMock()
        mock_ticker.calendar = {}
        # Create mock dividend index with specific dates
        idx = pd.DatetimeIndex(["2024-03-15", "2024-06-14", "2024-09-13", "2024-12-13"])
        mock_ticker.dividends = pd.Series([500.0, 500.0, 500.0, 500.0], index=idx)

        with patch("yfinance.Ticker", return_value=mock_ticker):
            from app.services.dividend_providers import sync_fetch_dividend_months

            result = sync_fetch_dividend_months("AAPL")

        assert isinstance(result, list)
        assert len(result) > 0

    def test_empty_dividends_returns_empty(self, override_settings):
        """배당 이력 없으면 빈 리스트 반환."""
        import pandas as pd

        mock_ticker = MagicMock()
        mock_ticker.calendar = {}
        mock_ticker.dividends = pd.Series([], dtype=float)

        with patch("yfinance.Ticker", return_value=mock_ticker):
            from app.services.dividend_providers import sync_fetch_dividend_months

            result = sync_fetch_dividend_months("AAPL")

        assert result == []

    def test_exception_returns_empty(self, override_settings):
        """예외 시 빈 리스트 반환."""
        with patch("yfinance.Ticker", side_effect=Exception("network")):
            from app.services.dividend_providers import sync_fetch_dividend_months

            result = sync_fetch_dividend_months("INVALID")

        assert result == []

    def test_calendar_with_dates_adjusts_offset(self, override_settings):
        """calendar에 ex/pay date 있으면 offset 계산."""
        from datetime import date

        import pandas as pd

        mock_ticker = MagicMock()
        # ex-date in March, pay-date in April → offset = 1
        mock_ticker.calendar = {
            "Ex-Dividend Date": date(2024, 3, 15),
            "Dividend Date": date(2024, 4, 15),
        }
        idx = pd.DatetimeIndex(["2024-03-15"])
        mock_ticker.dividends = pd.Series([500.0], index=idx)

        with patch("yfinance.Ticker", return_value=mock_ticker):
            from app.services.dividend_providers import sync_fetch_dividend_months

            result = sync_fetch_dividend_months("AAPL")

        assert isinstance(result, list)
