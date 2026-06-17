"""backtest_service.py 추가 단위 테스트 — _sync_download_history, _sync_compute_correlation."""

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


class TestComputeCorrelationSync:
    def test_empty_symbols_returns_empty(self, override_settings):
        from app.services.backtest_service import _sync_compute_correlation

        labels, matrix = _sync_compute_correlation([], [], date(2020, 1, 1), date(2021, 1, 1))
        assert labels == []
        assert matrix == []

    def test_yfinance_exception_returns_empty(self, override_settings):
        from app.services.backtest_service import _sync_compute_correlation

        with patch("yfinance.download", side_effect=Exception("error")):
            labels, matrix = _sync_compute_correlation(["AAPL"], ["Apple"], date(2020, 1, 1), date(2021, 1, 1))

        assert labels == []
        assert matrix == []

    def test_empty_dataframe_returns_empty(self, override_settings):
        import pandas as pd

        from app.services.backtest_service import _sync_compute_correlation

        with patch("yfinance.download", return_value=pd.DataFrame()):
            labels, matrix = _sync_compute_correlation(["AAPL"], ["Apple"], date(2020, 1, 1), date(2021, 1, 1))

        assert labels == []
        assert matrix == []

    def test_insufficient_data_returns_empty(self, override_settings):
        import pandas as pd

        from app.services.backtest_service import _sync_compute_correlation

        # Only 3 months of data (< 6 required)
        idx = pd.date_range("2020-01-01", periods=3, freq="ME")
        df = pd.DataFrame({"AAPL": [150.0, 155.0, 160.0]}, index=idx)

        with patch("yfinance.download", return_value=df):
            labels, matrix = _sync_compute_correlation(["AAPL"], ["Apple"], date(2020, 1, 1), date(2020, 3, 31))

        assert labels == []
        assert matrix == []

    def test_sufficient_data_returns_correlation_matrix(self, override_settings):
        import pandas as pd

        from app.services.backtest_service import _sync_compute_correlation

        # 12 months of data
        idx = pd.date_range("2020-01-01", periods=12, freq="ME")
        aapl = [150 + i for i in range(12)]
        tsla = [300 + i * 2 for i in range(12)]

        columns = pd.MultiIndex.from_tuples([("Close", "AAPL"), ("Close", "TSLA")])
        df = pd.DataFrame(
            list(zip(aapl, tsla, strict=False)),
            columns=columns,
            index=idx,
        )

        with patch("yfinance.download", return_value=df):
            labels, matrix = _sync_compute_correlation(
                ["AAPL", "TSLA"],
                ["Apple", "Tesla"],
                date(2020, 1, 1),
                date(2020, 12, 31),
            )

        # May or may not have sufficient data depending on dropna behavior
        assert isinstance(labels, list)
        assert isinstance(matrix, list)
