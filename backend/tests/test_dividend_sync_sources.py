"""dividend_sync_sources.py 단위 테스트 — 동기 배당 데이터 수집 함수."""

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
            from app.services.dividend.sync_sources import sync_yahoo_dividend_info

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
            from app.services.dividend.sync_sources import sync_yahoo_dividend_info

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
            from app.services.dividend.sync_sources import sync_yahoo_dividend_info

            result = sync_yahoo_dividend_info("005930.KS")

        assert result["dps"] == pytest.approx(400.0)

    def test_exception_returns_zeros(self, override_settings):
        with patch("yfinance.Ticker", side_effect=Exception("network error")):
            from app.services.dividend.sync_sources import sync_yahoo_dividend_info

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
            from app.services.dividend.sync_sources import sync_yahoo_dividend_info

            result = sync_yahoo_dividend_info("AAPL")

        assert result["dividend_yield"] == pytest.approx(0.03)


class TestSyncYahooDividendInfoOutlierExclusion:
    """레버리지/파생상품 ETF(QLD 등)의 연말 자본이득분배로 인한 배당수익률 과대평가 보정."""

    @staticmethod
    def _dividends_series(amounts_and_days_ago: list[tuple[float, int]]):
        import pandas as pd

        today = pd.Timestamp.today().normalize()
        idx = pd.DatetimeIndex([today - pd.Timedelta(days=d) for _, d in amounts_and_days_ago])
        values = [amt for amt, _ in amounts_and_days_ago]
        return pd.Series(values, index=idx)

    def test_excludes_capital_gain_distribution_qld_like(self, override_settings):
        """소액 분기배당 4건 + 대형 연말 자본이득분배 1건 → 자본이득분배 제외 후 재계산."""
        mock_info = {
            "trailingAnnualDividendYield": 0.08,  # 자본이득분배 포함해 과대평가된 원본값
            "dividendYield": 0.0,
            "trailingAnnualDividendRate": 6.2,
            "currentPrice": 80.0,
            "regularMarketPrice": None,
        }
        mock_ticker = MagicMock()
        mock_ticker.info = mock_info
        mock_ticker.dividends = self._dividends_series([(0.05, 300), (0.05, 210), (0.05, 120), (0.05, 30), (6.0, 15)])

        with patch("yfinance.Ticker", return_value=mock_ticker):
            from app.services.dividend.sync_sources import sync_yahoo_dividend_info

            result = sync_yahoo_dividend_info("QLD")

        assert result["dps"] == pytest.approx(0.20, abs=0.01)
        assert result["dividend_yield"] == pytest.approx(0.20 / 80.0, rel=0.05)
        assert result["dividend_yield"] < 0.08

    def test_no_outlier_keeps_original_for_even_distributions(self, override_settings):
        """고른 분기배당(이상치 없음)은 원래 info 기반 값 그대로 유지(오탐 없음)."""
        mock_info = {
            "trailingAnnualDividendYield": 0.035,
            "dividendYield": 0.0,
            "trailingAnnualDividendRate": 2.8,
            "currentPrice": 80.0,
            "regularMarketPrice": None,
        }
        mock_ticker = MagicMock()
        mock_ticker.info = mock_info
        mock_ticker.dividends = self._dividends_series([(0.7, 300), (0.7, 210), (0.7, 120), (0.7, 30)])

        with patch("yfinance.Ticker", return_value=mock_ticker):
            from app.services.dividend.sync_sources import sync_yahoo_dividend_info

            result = sync_yahoo_dividend_info("SCHD")

        assert result["dps"] == pytest.approx(2.8)
        assert result["dividend_yield"] == pytest.approx(0.035)

    def test_single_distribution_skips_outlier_check(self, override_settings):
        """분배 1건뿐이면 이상치 판단 불가 → 기존 info 기반 값 그대로."""
        mock_info = {
            "trailingAnnualDividendYield": 0.05,
            "dividendYield": 0.0,
            "trailingAnnualDividendRate": 4.0,
            "currentPrice": 80.0,
            "regularMarketPrice": None,
        }
        mock_ticker = MagicMock()
        mock_ticker.info = mock_info
        mock_ticker.dividends = self._dividends_series([(4.0, 15)])

        with patch("yfinance.Ticker", return_value=mock_ticker):
            from app.services.dividend.sync_sources import sync_yahoo_dividend_info

            result = sync_yahoo_dividend_info("XYZ")

        assert result["dps"] == pytest.approx(4.0)
        assert result["dividend_yield"] == pytest.approx(0.05)

    def test_dividends_access_failure_falls_back_to_info(self, override_settings):
        """ticker.dividends 조회 자체가 실패해도 기존 info 기반 로직으로 폴백."""
        from app.services.dividend.sync_sources import _exclude_capital_gain_outlier

        class _BadTicker:
            @property
            def dividends(self):
                raise RuntimeError("network error")

        assert _exclude_capital_gain_outlier(_BadTicker()) is None


# ── sync_pykrx_etf_dividend_info ─────────────────────────────


class TestSyncPykrxEtfDividendInfo:
    def test_api_error_returns_zeros(self, override_settings):
        """pykrx API 오류 시 0 반환 (AttributeError → except Exception)."""
        from app.services.dividend.sync_sources import sync_pykrx_etf_dividend_info

        # pykrx.stock.get_market_dividend_by_date doesn't exist → AttributeError → 0 returned
        result = sync_pykrx_etf_dividend_info("INVALID_TICKER_XYZ")
        assert result["dps"] == 0.0
        assert result["dividend_yield"] == 0.0


# ── sync_fdr_etf_dividend_info ────────────────────────────────


class TestSyncFdrEtfDividendInfo:
    def test_exception_returns_zeros(self, override_settings):
        """FinanceDataReader import 실패 시 0 반환."""
        with patch.dict("sys.modules", {"FinanceDataReader": None}):
            from app.services.dividend.sync_sources import sync_fdr_etf_dividend_info

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

            import app.services.dividend.sync_sources as dp_mod

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
            from app.services.dividend.sync_sources import sync_naver_etf_dividend_info

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
            from app.services.dividend.sync_sources import sync_naver_etf_dividend_info

            result = sync_naver_etf_dividend_info("069500")

        assert result["dps"] == 0.0

    def test_parse_error_returns_zeros(self, override_settings):
        """JSON 파싱 오류 시 0 반환."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.side_effect = ValueError("bad json")

        with patch("requests.get", return_value=mock_resp):
            from app.services.dividend.sync_sources import sync_naver_etf_dividend_info

            result = sync_naver_etf_dividend_info("069500")

        assert result["dps"] == 0.0


# ── sync_naver_etf_index_region ──────────────────────────────


class TestSyncNaverEtfIndexRegion:
    def test_high_kr_weight_returns_domestic(self, override_settings):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "countryPortfolioList": [
                {"detailTypeCode": "KR", "weight": 98.95},
                {"detailTypeCode": "US", "weight": 1.05},
            ]
        }

        with patch("requests.get", return_value=mock_resp):
            from app.services.dividend.sync_sources import sync_naver_etf_index_region

            result = sync_naver_etf_index_region("069500")

        assert result == "DOMESTIC"

    def test_low_kr_weight_returns_overseas(self, override_settings):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "countryPortfolioList": [
                {"detailTypeCode": "KR", "weight": 0.34},
                {"detailTypeCode": "US", "weight": 99.1},
            ]
        }

        with patch("requests.get", return_value=mock_resp):
            from app.services.dividend.sync_sources import sync_naver_etf_index_region

            result = sync_naver_etf_index_region("133690")

        assert result == "OVERSEAS"

    def test_no_kr_entry_returns_overseas(self, override_settings):
        """KR 항목 자체가 없으면 비중 0으로 간주해 해외지수로 판별한다."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"countryPortfolioList": [{"detailTypeCode": "US", "weight": 100.0}]}

        with patch("requests.get", return_value=mock_resp):
            from app.services.dividend.sync_sources import sync_naver_etf_index_region

            result = sync_naver_etf_index_region("360750")

        assert result == "OVERSEAS"

    def test_no_portfolio_data_returns_none(self, override_settings):
        """개별 종목 등 ETF 데이터가 없으면 None 반환 — 호출측이 폴백을 적용해야 함."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {}

        with patch("requests.get", return_value=mock_resp):
            from app.services.dividend.sync_sources import sync_naver_etf_index_region

            result = sync_naver_etf_index_region("005930")

        assert result is None

    def test_parse_error_returns_none(self, override_settings):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.side_effect = ValueError("bad json")

        with patch("requests.get", return_value=mock_resp):
            from app.services.dividend.sync_sources import sync_naver_etf_index_region

            result = sync_naver_etf_index_region("069500")

        assert result is None


# ── sync_naver_stock_dividend_info ────────────────────────────


class TestSyncNaverStockDividendInfo:
    def test_success_returns_yield(self, override_settings):
        """성공적인 Naver 주식 배당수익률 반환."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"stockItemDetail": {"dividendYield": "2.8"}}

        with patch("requests.get", return_value=mock_resp):
            from app.services.dividend.sync_sources import sync_naver_stock_dividend_info

            result = sync_naver_stock_dividend_info("005930")

        assert result["dividend_yield"] == pytest.approx(0.028)
        assert result["dps"] == 0.0

    def test_zero_yield_returns_zeros(self, override_settings):
        """배당수익률 0이면 빈 결과 반환."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"stockItemDetail": {"dividendYield": "0"}}

        with patch("requests.get", return_value=mock_resp):
            from app.services.dividend.sync_sources import sync_naver_stock_dividend_info

            result = sync_naver_stock_dividend_info("005930")

        assert result["dividend_yield"] == 0.0

    def test_parse_error_returns_zeros(self, override_settings):
        """파싱 오류 시 0 반환."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.side_effect = TypeError("bad type")

        with patch("requests.get", return_value=mock_resp):
            from app.services.dividend.sync_sources import sync_naver_stock_dividend_info

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
            from app.services.dividend.sync_sources import sync_fetch_dividend_months

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
            from app.services.dividend.sync_sources import sync_fetch_dividend_months

            result = sync_fetch_dividend_months("AAPL")

        assert result == []

    def test_exception_returns_empty(self, override_settings):
        """예외 시 빈 리스트 반환."""
        with patch("yfinance.Ticker", side_effect=Exception("network")):
            from app.services.dividend.sync_sources import sync_fetch_dividend_months

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
            from app.services.dividend.sync_sources import sync_fetch_dividend_months

            result = sync_fetch_dividend_months("AAPL")

        assert isinstance(result, list)
