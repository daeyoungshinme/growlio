"""yahoo_price.py 단위 테스트 (yfinance mocked)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd

# ── _to_yahoo_symbol (순수 함수) ──────────────────────────────


class TestToYahooSymbol:
    def test_kospi(self, override_settings):
        from app.services.yahoo_price import to_yf_symbol as _to_yahoo_symbol

        assert _to_yahoo_symbol("005930", "KOSPI") == "005930.KS"

    def test_krx(self, override_settings):
        from app.services.yahoo_price import to_yf_symbol as _to_yahoo_symbol

        assert _to_yahoo_symbol("069500", "KRX") == "069500.KS"

    def test_kosdaq(self, override_settings):
        from app.services.yahoo_price import to_yf_symbol as _to_yahoo_symbol

        assert _to_yahoo_symbol("035720", "KOSDAQ") == "035720.KQ"

    def test_nasdaq_unchanged(self, override_settings):
        from app.services.yahoo_price import to_yf_symbol as _to_yahoo_symbol

        assert _to_yahoo_symbol("AAPL", "NASDAQ") == "AAPL"

    def test_short_kospi_padded(self, override_settings):
        from app.services.yahoo_price import to_yf_symbol as _to_yahoo_symbol

        assert _to_yahoo_symbol("5930", "KOSPI") == "005930.KS"

    def test_case_insensitive(self, override_settings):
        from app.services.yahoo_price import to_yf_symbol as _to_yahoo_symbol

        assert _to_yahoo_symbol("005930", "kospi") == "005930.KS"


# ── _sync_usdkrw (yfinance mocked) ───────────────────────────


class TestSyncUsdkrw:
    def test_returns_rate_from_yfinance(self, override_settings):
        from app.services.yahoo_price import _sync_usdkrw

        hist_df = pd.DataFrame({"Close": [1320.0]})
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = hist_df

        with patch("yfinance.Ticker", return_value=mock_ticker):
            result = _sync_usdkrw()

        assert result == 1320.0

    def test_returns_zero_on_empty_hist(self, override_settings):
        from app.services.yahoo_price import _sync_usdkrw

        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame()

        with patch("yfinance.Ticker", return_value=mock_ticker):
            result = _sync_usdkrw()

        assert result == 0.0

    def test_returns_zero_on_exception(self, override_settings):
        from app.services.yahoo_price import _sync_usdkrw

        mock_ticker = MagicMock()
        mock_ticker.history.side_effect = Exception("network error")

        with patch("yfinance.Ticker", return_value=mock_ticker):
            result = _sync_usdkrw()

        assert result == 0.0


# ── _sync_yahoo_price (yfinance mocked) ──────────────────────


class TestSyncYahooPrice:
    def test_returns_price_from_history(self, override_settings):
        from app.services.yahoo_price import _sync_yahoo_price

        hist_df = pd.DataFrame({"Close": [185.0, 187.0]})
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = hist_df

        with patch("yfinance.Ticker", return_value=mock_ticker):
            result = _sync_yahoo_price("AAPL", "NASDAQ")

        assert result == 187.0

    def test_returns_none_on_empty(self, override_settings):
        from app.services.yahoo_price import _sync_yahoo_price

        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame()

        with patch("yfinance.Ticker", return_value=mock_ticker):
            result = _sync_yahoo_price("INVALID", "NASDAQ")

        assert result is None

    def test_returns_none_on_exception(self, override_settings):
        from app.services.yahoo_price import _sync_yahoo_price

        mock_ticker = MagicMock()
        mock_ticker.history.side_effect = Exception("timeout")

        with patch("yfinance.Ticker", return_value=mock_ticker):
            result = _sync_yahoo_price("AAPL", "NASDAQ")

        assert result is None


# ── _sync_yahoo_batch (yfinance mocked) ──────────────────────


class TestSyncYahooBatch:
    def test_empty_items_returns_empty(self, override_settings):
        from app.services.yahoo_price import _sync_yahoo_batch

        result = _sync_yahoo_batch([])
        assert result == {}

    def test_returns_prices_from_download(self, override_settings):
        from app.services.yahoo_price import _sync_yahoo_batch

        close_df = pd.DataFrame({"AAPL": [180.0, 185.0]})
        download_data = MagicMock()
        download_data.get.return_value = close_df
        download_data.columns = pd.MultiIndex.from_tuples([("Close", "AAPL")])

        with patch("yfinance.download", return_value=download_data):
            result = _sync_yahoo_batch([("AAPL", "NASDAQ")])

        assert "AAPL" in result

    def test_returns_empty_on_exception(self, override_settings):
        from app.services.yahoo_price import _sync_yahoo_batch

        with patch("yfinance.download", side_effect=Exception("rate limit")):
            result = _sync_yahoo_batch([("AAPL", "NASDAQ")])

        assert result == {}

    def test_close_none_returns_empty_after_all_retries(self, override_settings):
        from app.services.yahoo_price import _sync_yahoo_batch

        download_data = MagicMock()
        download_data.get.return_value = None  # close is None → triggers retry path

        with (
            patch("yfinance.download", return_value=download_data),
            patch("time.sleep"),  # suppress actual sleeps
        ):
            result = _sync_yahoo_batch([("AAPL", "NASDAQ")])

        assert result == {}

    def test_key_error_in_price_parse_skipped(self, override_settings):
        from app.services.yahoo_price import _sync_yahoo_batch

        close_df = MagicMock(spec=pd.DataFrame)
        close_df.empty = False
        close_df.__getitem__ = MagicMock(side_effect=KeyError("AAPL"))

        download_data = MagicMock()
        download_data.get.return_value = close_df

        with patch("yfinance.download", return_value=download_data):
            result = _sync_yahoo_batch([("AAPL", "NASDAQ")])

        assert result == {}


# ── _cagr_from_prices (순수 함수) ─────────────────────────────


class TestCagrFromPrices:
    def test_returns_none_when_start_price_zero(self, override_settings):
        from datetime import date

        from app.services.yahoo_price import _cagr_from_prices

        result = _cagr_from_prices(0.0, 100.0, date(2015, 1, 1), date(2025, 1, 1))
        assert result is None

    def test_returns_none_when_actual_years_too_short(self, override_settings):
        from datetime import date

        from app.services.yahoo_price import _cagr_from_prices

        # 1일 차이 → ~1/365 years < 0.1
        result = _cagr_from_prices(100.0, 105.0, date(2025, 1, 1), date(2025, 1, 2))
        assert result is None

    def test_returns_dict_on_valid_range(self, override_settings):
        from datetime import date

        from app.services.yahoo_price import _cagr_from_prices

        result = _cagr_from_prices(100.0, 200.0, date(2015, 1, 1), date(2025, 1, 1))

        assert result is not None
        assert "cumulative_return_pct" in result
        assert "cagr_pct" in result
        assert "actual_years" in result
        assert result["cumulative_return_pct"] == 100.0


# ── _pykrx_calc_return (pykrx mocked) ─────────────────────────


class TestPykrxCalcReturn:
    def test_returns_none_for_overseas_market(self, override_settings):
        from datetime import date

        from app.services.yahoo_price import _pykrx_calc_return

        result = _pykrx_calc_return("AAPL", "NASDAQ", date(2015, 1, 1), date(2025, 1, 1))
        assert result is None

    def test_returns_none_when_series_missing(self, override_settings):
        from datetime import date

        from app.services.yahoo_price import _pykrx_calc_return

        with patch("app.services.yahoo_price.sync_pykrx_close_series", return_value=None):
            result = _pykrx_calc_return("005930", "KOSPI", date(2015, 1, 1), date(2025, 1, 1))

        assert result is None

    def test_returns_dict_for_domestic_ticker(self, override_settings):
        from datetime import date

        from app.services.yahoo_price import _pykrx_calc_return

        dates = pd.date_range("2015-01-01", periods=300, freq="B")
        series = pd.Series([50000.0 + i * 10 for i in range(300)], index=dates)

        with patch("app.services.yahoo_price.sync_pykrx_close_series", return_value=series):
            result = _pykrx_calc_return("5930", "KOSPI", date(2015, 1, 1), date(2025, 1, 1))

        assert result is not None
        assert "cagr_pct" in result


# ── _sync_calc_returns_batch (yfinance mocked) ────────────────


class TestSyncCalcReturnsBatch:
    def test_empty_items_returns_empty(self, override_settings):
        from app.services.yahoo_price import _sync_calc_returns_batch

        result = _sync_calc_returns_batch([])
        assert result == {}

    def test_returns_dict_on_valid_download(self, override_settings):
        from datetime import date

        from app.services.yahoo_price import _sync_calc_returns_batch

        dates = pd.date_range(end=date.today().isoformat(), periods=300, freq="B", tz="UTC")
        close_df = pd.DataFrame({"AAPL": [100.0 + i * 0.05 for i in range(300)]}, index=dates)
        download_data = MagicMock()
        download_data.get.return_value = close_df

        with patch("yfinance.download", return_value=download_data):
            result = _sync_calc_returns_batch([("AAPL", "NASDAQ")], years=10)

        assert ("AAPL", "NASDAQ") in result
        assert "cagr_pct" in result[("AAPL", "NASDAQ")]

    def test_returns_empty_on_exception(self, override_settings):
        from app.services.yahoo_price import _sync_calc_returns_batch

        with patch("yfinance.download", side_effect=Exception("rate limit")):
            result = _sync_calc_returns_batch([("AAPL", "NASDAQ")])

        assert result == {}

    def test_close_none_returns_empty_after_all_retries(self, override_settings):
        from app.services.yahoo_price import _sync_calc_returns_batch

        download_data = MagicMock()
        download_data.get.return_value = None

        with (
            patch("yfinance.download", return_value=download_data),
            patch("time.sleep"),
        ):
            result = _sync_calc_returns_batch([("AAPL", "NASDAQ")])

        assert result == {}

    def test_key_error_in_parse_skipped(self, override_settings):
        from app.services.yahoo_price import _sync_calc_returns_batch

        close_df = MagicMock(spec=pd.DataFrame)
        close_df.empty = False
        close_df.__getitem__ = MagicMock(side_effect=KeyError("AAPL"))

        download_data = MagicMock()
        download_data.get.return_value = close_df

        with patch("yfinance.download", return_value=download_data):
            result = _sync_calc_returns_batch([("AAPL", "NASDAQ")])

        assert result == {}


# ── _sync_pykrx_returns_batch (pykrx mocked) ──────────────────


class TestSyncPykrxReturnsBatch:
    def test_empty_items_returns_empty(self, override_settings):
        from app.services.yahoo_price import _sync_pykrx_returns_batch

        result = _sync_pykrx_returns_batch([])
        assert result == {}

    def test_skips_overseas_and_fills_domestic(self, override_settings):
        from app.services.yahoo_price import _sync_pykrx_returns_batch

        dates = pd.date_range("2015-01-01", periods=300, freq="B")
        series = pd.Series([50000.0 + i * 10 for i in range(300)], index=dates)

        with patch("app.services.yahoo_price.sync_pykrx_close_series", return_value=series):
            result = _sync_pykrx_returns_batch([("005930", "KOSPI"), ("AAPL", "NASDAQ")], years=10)

        assert ("005930", "KOSPI") in result
        assert ("AAPL", "NASDAQ") not in result
