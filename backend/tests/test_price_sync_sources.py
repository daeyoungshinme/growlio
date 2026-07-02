"""price_sync_sources.py 단위 테스트 — 국내 종목 현재가/종가 폴백 소스."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

# ── yf_symbol_to_krx_ticker (순수 함수) ────────────────────────


class TestYfSymbolToKrxTicker:
    def test_kospi_symbol(self, override_settings):
        from app.services.price_sync_sources import yf_symbol_to_krx_ticker

        assert yf_symbol_to_krx_ticker("005930.KS") == "005930"

    def test_kosdaq_symbol(self, override_settings):
        from app.services.price_sync_sources import yf_symbol_to_krx_ticker

        assert yf_symbol_to_krx_ticker("035720.KQ") == "035720"

    def test_overseas_symbol_returns_none(self, override_settings):
        from app.services.price_sync_sources import yf_symbol_to_krx_ticker

        assert yf_symbol_to_krx_ticker("AAPL") is None

    def test_index_symbol_returns_none(self, override_settings):
        from app.services.price_sync_sources import yf_symbol_to_krx_ticker

        assert yf_symbol_to_krx_ticker("^GSPC") is None


# ── sync_naver_price ────────────────────────────────────────────


class TestSyncNaverPrice:
    def test_success_returns_price(self, override_settings):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"closePrice": "286,000"}

        with patch("requests.get", return_value=mock_resp):
            from app.services.price_sync_sources import sync_naver_price

            result = sync_naver_price("005930")

        assert result == pytest.approx(286000.0)

    def test_missing_close_price_returns_none(self, override_settings):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {}

        with patch("requests.get", return_value=mock_resp):
            from app.services.price_sync_sources import sync_naver_price

            result = sync_naver_price("005930")

        assert result is None

    def test_http_error_returns_none(self, override_settings):
        import requests.exceptions as _req_exc

        with patch("requests.get", side_effect=_req_exc.ConnectionError("network down")):
            from app.services.price_sync_sources import sync_naver_price

            result = sync_naver_price("005930")

        assert result is None

    def test_parse_error_returns_none(self, override_settings):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.side_effect = ValueError("bad json")

        with patch("requests.get", return_value=mock_resp):
            from app.services.price_sync_sources import sync_naver_price

            result = sync_naver_price("005930")

        assert result is None


# ── sync_pykrx_price ─────────────────────────────────────────────


class TestSyncPykrxPrice:
    def test_success_returns_last_close(self, override_settings):
        import pandas as pd

        mock_df = pd.DataFrame({"종가": [284000, 285500, 286000]})

        with patch("pykrx.stock.get_market_ohlcv_by_date", return_value=mock_df):
            from app.services.price_sync_sources import sync_pykrx_price

            result = sync_pykrx_price("005930")

        assert result == pytest.approx(286000.0)

    def test_empty_dataframe_returns_none(self, override_settings):
        import pandas as pd

        with patch("pykrx.stock.get_market_ohlcv_by_date", return_value=pd.DataFrame()):
            from app.services.price_sync_sources import sync_pykrx_price

            result = sync_pykrx_price("005930")

        assert result is None

    def test_exception_returns_none(self, override_settings):
        with patch("pykrx.stock.get_market_ohlcv_by_date", side_effect=Exception("krx down")):
            from app.services.price_sync_sources import sync_pykrx_price

            result = sync_pykrx_price("005930")

        assert result is None


# ── sync_pykrx_close_series ───────────────────────────────────────


class TestSyncPykrxCloseSeries:
    def test_success_returns_series(self, override_settings):
        import pandas as pd

        mock_df = pd.DataFrame({"종가": [100.0, 101.0, 0.0, 103.0]})

        with patch("pykrx.stock.get_market_ohlcv_by_date", return_value=mock_df):
            from app.services.price_sync_sources import sync_pykrx_close_series

            result = sync_pykrx_close_series("005930", date(2024, 1, 1), date(2024, 1, 31))

        assert result is not None
        assert len(result) == 3  # 0.0인 행은 제외

    def test_none_dataframe_returns_none(self, override_settings):
        with patch("pykrx.stock.get_market_ohlcv_by_date", return_value=None):
            from app.services.price_sync_sources import sync_pykrx_close_series

            result = sync_pykrx_close_series("005930", date(2024, 1, 1), date(2024, 1, 31))

        assert result is None

    def test_exception_returns_none(self, override_settings):
        with patch("pykrx.stock.get_market_ohlcv_by_date", side_effect=Exception("krx down")):
            from app.services.price_sync_sources import sync_pykrx_close_series

            result = sync_pykrx_close_series("005930", date(2024, 1, 1), date(2024, 1, 31))

        assert result is None
