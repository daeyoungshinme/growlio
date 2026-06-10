"""yahoo_price.py 단위 테스트 (yfinance mocked)."""
from __future__ import annotations

import pandas as pd
import pytest
from unittest.mock import MagicMock, patch


# ── _to_yahoo_symbol (순수 함수) ──────────────────────────────

class TestToYahooSymbol:
    def test_kospi(self, override_settings):
        from app.services.yahoo_price import _to_yahoo_symbol
        assert _to_yahoo_symbol("005930", "KOSPI") == "005930.KS"

    def test_krx(self, override_settings):
        from app.services.yahoo_price import _to_yahoo_symbol
        assert _to_yahoo_symbol("069500", "KRX") == "069500.KS"

    def test_kosdaq(self, override_settings):
        from app.services.yahoo_price import _to_yahoo_symbol
        assert _to_yahoo_symbol("035720", "KOSDAQ") == "035720.KQ"

    def test_nasdaq_unchanged(self, override_settings):
        from app.services.yahoo_price import _to_yahoo_symbol
        assert _to_yahoo_symbol("AAPL", "NASDAQ") == "AAPL"

    def test_short_kospi_padded(self, override_settings):
        from app.services.yahoo_price import _to_yahoo_symbol
        assert _to_yahoo_symbol("5930", "KOSPI") == "005930.KS"

    def test_case_insensitive(self, override_settings):
        from app.services.yahoo_price import _to_yahoo_symbol
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


# ── _sync_calc_return (yfinance mocked) ──────────────────────

class TestSyncCalcReturn:
    def test_returns_none_on_empty_hist(self, override_settings):
        from app.services.yahoo_price import _sync_calc_return

        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame()

        with patch("yfinance.Ticker", return_value=mock_ticker):
            result = _sync_calc_return("AAPL", "NASDAQ", years=10)

        assert result is None

    def test_returns_dict_on_valid_hist(self, override_settings):
        from app.services.yahoo_price import _sync_calc_return
        import numpy as np
        from datetime import date, timedelta

        dates = pd.date_range(
            end=date.today().isoformat(), periods=300, freq="B", tz="UTC"
        )
        prices = [100.0 + i * 0.05 for i in range(300)]
        hist_df = pd.DataFrame({"Close": prices}, index=dates)
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = hist_df

        with patch("yfinance.Ticker", return_value=mock_ticker):
            result = _sync_calc_return("AAPL", "NASDAQ", years=10)

        assert result is not None
        assert "cumulative_return_pct" in result
        assert "cagr_pct" in result
        assert "actual_years" in result

    def test_returns_none_on_exception(self, override_settings):
        from app.services.yahoo_price import _sync_calc_return

        mock_ticker = MagicMock()
        mock_ticker.history.side_effect = Exception("fetch error")

        with patch("yfinance.Ticker", return_value=mock_ticker):
            result = _sync_calc_return("AAPL", "NASDAQ")

        assert result is None
