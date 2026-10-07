"""backtest_service.py 추가 단위 테스트 — _sync_download_history."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch


class TestFetchPricesSync:
    def test_empty_symbols_returns_empty_dict(self, override_settings):
        from app.services.backtest_service import _sync_download_history

        result = _sync_download_history([], date(2020, 1, 1), date(2021, 1, 1))
        assert result == {}

    def test_yfinance_download_exception_returns_empty(self, override_settings):
        from app.services.backtest_service import _sync_download_history

        with patch("yfinance.download", side_effect=Exception("network error")):
            result = _sync_download_history(["AAPL"], date(2020, 1, 1), date(2021, 1, 1))

        assert result == {}

    def test_returns_empty_on_empty_dataframe(self, override_settings):
        import pandas as pd

        from app.services.backtest_service import _sync_download_history

        empty_df = pd.DataFrame()
        with patch("yfinance.download", return_value=empty_df):
            result = _sync_download_history(["AAPL"], date(2020, 1, 1), date(2021, 1, 1))

        assert result == {}

    def test_single_symbol_returns_price_series(self, override_settings):
        import pandas as pd

        from app.services.backtest_service import _sync_download_history

        idx = pd.date_range("2020-01-01", periods=5)
        prices = [150.0, 155.0, 153.0, 157.0, 160.0]
        df = pd.DataFrame({"AAPL": prices}, index=idx)

        with patch("yfinance.download", return_value=df):
            result = _sync_download_history(["AAPL"], date(2020, 1, 1), date(2020, 1, 5))

        assert "AAPL" in result
        assert len(result["AAPL"]) == 5
        assert all(isinstance(d, str) and isinstance(p, float) for d, p in result["AAPL"])

    def test_multi_symbol_returns_multiindex_df(self, override_settings):
        import pandas as pd

        from app.services.backtest_service import _sync_download_history

        idx = pd.date_range("2020-01-01", periods=3)
        columns = pd.MultiIndex.from_tuples([("Close", "AAPL"), ("Close", "TSLA")])
        data = [[150.0, 300.0], [155.0, 310.0], [160.0, 320.0]]
        df = pd.DataFrame(data, columns=columns, index=idx)

        with patch("yfinance.download", return_value=df):
            result = _sync_download_history(["AAPL", "TSLA"], date(2020, 1, 1), date(2020, 1, 3))

        assert "AAPL" in result
        assert "TSLA" in result

    def test_domestic_symbol_falls_back_to_pykrx_when_yahoo_fails(self, override_settings):
        """Yahoo가 실패해도 국내(.KS) 심볼은 pykrx로 보완된다."""
        import pandas as pd

        from app.services.backtest_service import _sync_download_history

        idx = pd.date_range("2020-01-01", periods=3)
        pykrx_df = pd.DataFrame({"종가": [70000.0, 71000.0, 69000.0]}, index=idx)

        with (
            patch("yfinance.download", side_effect=Exception("401 Unauthorized")),
            patch("pykrx.stock.get_market_ohlcv_by_date", return_value=pykrx_df),
        ):
            result = _sync_download_history(["005930.KS"], date(2020, 1, 1), date(2020, 1, 3))

        assert "005930.KS" in result
        assert len(result["005930.KS"]) == 3
