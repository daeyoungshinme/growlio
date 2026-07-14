"""market_data_fetcher 단위 테스트."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch


class TestFetchYfDailyReturns:
    def test_returns_daily_returns_for_symbols(self):
        """정상 다운로드 시 일별 수익률 dict를 반환한다."""
        import pandas as pd

        mock_df = pd.DataFrame({"AAPL": [100.0, 102.0, 101.0, 103.0]})
        mock_raw = MagicMock()
        mock_raw.columns = mock_df.columns
        mock_raw.get.return_value = mock_df
        mock_raw.__class__ = pd.DataFrame

        with patch("yfinance.download", return_value=mock_df):
            from app.services.market_data_fetcher import fetch_yf_daily_returns

            result = fetch_yf_daily_returns(["AAPL"])

        assert "AAPL" in result
        assert len(result["AAPL"]) == 3  # pct_change → N-1 values

    def test_empty_symbols_returns_empty(self):
        """빈 심볼 목록은 빈 dict를 반환한다."""
        from app.services.market_data_fetcher import fetch_yf_daily_returns

        result = fetch_yf_daily_returns([])
        assert result == {}

    def test_download_exception_returns_empty(self):
        """다운로드 실패 시 빈 dict를 반환하고 예외가 전파되지 않는다."""
        with patch("yfinance.download", side_effect=Exception("network error")):
            from app.services.market_data_fetcher import fetch_yf_daily_returns

            result = fetch_yf_daily_returns(["AAPL"])

        assert result == {}

    def test_nan_values_filtered_out(self):
        """NaN 수익률 값은 결과에서 제거된다."""
        import math

        import pandas as pd

        # 중간에 NaN이 있는 시리즈
        mock_df = pd.DataFrame({"AAPL": [100.0, float("nan"), 102.0, 104.0]})

        with patch("yfinance.download", return_value=mock_df):
            from app.services.market_data_fetcher import fetch_yf_daily_returns

            result = fetch_yf_daily_returns(["AAPL"])

        if "AAPL" in result:
            assert all(math.isfinite(r) for r in result["AAPL"])

    def test_extra_symbols_included_in_result(self):
        """extra_symbols도 결과에 포함된다."""
        import pandas as pd

        mock_df = pd.DataFrame({"AAPL": [100.0, 101.0, 102.0], "^GSPC": [4000.0, 4020.0, 4010.0]})

        with patch("yfinance.download", return_value=mock_df):
            from app.services.market_data_fetcher import fetch_yf_daily_returns

            result = fetch_yf_daily_returns(["AAPL"], extra_symbols=["^GSPC"])

        assert "AAPL" in result
        assert "^GSPC" in result

    def test_multiindex_close_extraction(self):
        """MultiIndex DataFrame에서 'Close' 레벨을 올바르게 추출한다."""
        import pandas as pd

        close_df = pd.DataFrame({"AAPL": [100.0, 102.0, 104.0]})
        columns = pd.MultiIndex.from_tuples([("Close", "AAPL"), ("Open", "AAPL")])
        multi_raw = MagicMock()
        multi_raw.columns = columns
        multi_raw.get.return_value = close_df

        with patch("yfinance.download", return_value=multi_raw):
            from app.services.market_data_fetcher import fetch_yf_daily_returns

            result = fetch_yf_daily_returns(["AAPL"])

        # MultiIndex 경로 실행 — 예외 없이 dict 반환
        assert isinstance(result, dict)

    def test_domestic_symbol_falls_back_to_pykrx_when_yahoo_fails(self):
        """Yahoo가 실패해도 국내(.KS) 심볼은 pykrx로 보완된다."""
        import pandas as pd

        pykrx_df = pd.DataFrame({"종가": [70000.0, 71000.0, 69000.0, 72000.0]})

        with (
            patch("yfinance.download", side_effect=Exception("401 Unauthorized")),
            patch("pykrx.stock.get_market_ohlcv_by_date", return_value=pykrx_df),
        ):
            from app.services.market_data_fetcher import fetch_yf_daily_returns

            result = fetch_yf_daily_returns(["005930.KS"])

        assert "005930.KS" in result
        assert len(result["005930.KS"]) == 3

    def test_overseas_symbol_stays_empty_when_yahoo_fails(self):
        """해외 심볼은 대체 소스가 없어 Yahoo 실패 시 빈 결과를 유지한다."""
        with patch("yfinance.download", side_effect=Exception("401 Unauthorized")):
            from app.services.market_data_fetcher import fetch_yf_daily_returns

            result = fetch_yf_daily_returns(["AAPL"])

        assert result == {}

    def test_yf_download_called_with_threads_false(self):
        """yf.download은 반드시 threads=False로 호출돼야 한다 — threads=True는 이 함수가
        run_in_executor로 동시 호출될 때(예: 목표 역산 기간별 추천의 조합별 병렬 계산) yfinance
        내부 스레드풀이 추가로 생겨 프로세스 크래시를 일으키는 것이 확인됐다."""
        import pandas as pd

        mock_df = pd.DataFrame({"AAPL": [100.0, 102.0, 101.0]})

        with patch("yfinance.download", return_value=mock_df) as mock_download:
            from app.services.market_data_fetcher import fetch_yf_daily_returns

            fetch_yf_daily_returns(["AAPL"])

        assert mock_download.call_args.kwargs["threads"] is False

    def test_circuit_open_still_tries_pykrx_for_domestic(self):
        """yahoo_circuit이 OPEN이어도 국내 심볼은 pykrx 경로로 조회된다."""
        import pandas as pd

        pykrx_df = pd.DataFrame({"종가": [70000.0, 71000.0, 69000.0]})

        with (
            patch("app.services.market_data_fetcher.yahoo_circuit") as mock_circuit,
            patch("pykrx.stock.get_market_ohlcv_by_date", return_value=pykrx_df),
        ):
            mock_circuit.is_available.return_value = False

            from app.services.market_data_fetcher import fetch_yf_daily_returns

            result = fetch_yf_daily_returns(["005930.KS"])

        assert "005930.KS" in result


class TestFetchYfCloseSeries:
    def test_returns_series_for_symbols(self):
        """정상 다운로드 시 종목별 종가 Series를 반환한다."""
        import pandas as pd

        mock_df = pd.DataFrame({"AAPL": [100.0, 102.0, 104.0]})

        with patch("yfinance.download", return_value=mock_df):
            from app.services.market_data_fetcher import fetch_yf_close_series

            result = fetch_yf_close_series(["AAPL"], date(2024, 1, 1), date(2024, 1, 31))

        assert "AAPL" in result
        assert len(result["AAPL"]) == 3

    def test_empty_symbols_returns_empty(self):
        from app.services.market_data_fetcher import fetch_yf_close_series

        result = fetch_yf_close_series([], date(2024, 1, 1), date(2024, 1, 31))
        assert result == {}

    def test_download_exception_returns_empty(self):
        with patch("yfinance.download", side_effect=RuntimeError("timeout")):
            from app.services.market_data_fetcher import fetch_yf_close_series

            result = fetch_yf_close_series(["AAPL"], date(2024, 1, 1), date(2024, 1, 31))

        assert result == {}

    def test_domestic_symbol_falls_back_to_pykrx_when_yahoo_fails(self):
        """Yahoo가 실패해도 국내(.KS) 심볼은 pykrx 종가 Series로 보완된다."""
        import pandas as pd

        pykrx_df = pd.DataFrame({"종가": [70000.0, 71000.0, 69000.0]})

        with (
            patch("yfinance.download", side_effect=Exception("401 Unauthorized")),
            patch("pykrx.stock.get_market_ohlcv_by_date", return_value=pykrx_df),
        ):
            from app.services.market_data_fetcher import fetch_yf_close_series

            result = fetch_yf_close_series(["005930.KS"], date(2024, 1, 1), date(2024, 1, 31))

        assert "005930.KS" in result
        assert len(result["005930.KS"]) == 3

    def test_yf_download_called_with_threads_false(self):
        """`fetch_yf_daily_returns`와 동일한 이유로 threads=False가 유지돼야 한다."""
        import pandas as pd

        mock_df = pd.DataFrame({"AAPL": [100.0, 102.0, 104.0]})

        with patch("yfinance.download", return_value=mock_df) as mock_download:
            from app.services.market_data_fetcher import fetch_yf_close_series

            fetch_yf_close_series(["AAPL"], date(2024, 1, 1), date(2024, 1, 31))

        assert mock_download.call_args.kwargs["threads"] is False


class TestFetchYfInfo:
    def test_returns_info_for_symbols(self):
        """정상 조회 시 종목별 info dict를 반환한다."""
        mock_ticker = MagicMock()
        mock_ticker.info = {"trailingPE": 28.5, "marketCap": 3_000_000_000_000}

        with patch("yfinance.Ticker", return_value=mock_ticker):
            from app.services.market_data_fetcher import fetch_yf_info

            result = fetch_yf_info(["AAPL"])

        assert "AAPL" in result
        assert result["AAPL"].get("trailingPE") == 28.5

    def test_exception_per_ticker_returns_empty_dict(self):
        """개별 종목 조회 실패 시 빈 dict로 폴백한다."""
        mock_ticker = MagicMock()
        mock_ticker.info = None
        type(mock_ticker).info = property(lambda self: (_ for _ in ()).throw(Exception("fail")))

        with patch("yfinance.Ticker", return_value=mock_ticker):
            from app.services.market_data_fetcher import fetch_yf_info

            result = fetch_yf_info(["AAPL"])

        assert result.get("AAPL") == {}
