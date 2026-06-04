"""backtest_service 단위 테스트 — 순수 계산 함수 검증."""

import math

import pytest


class TestToYfSymbol:
    """_to_yf_symbol: Yahoo Finance 심볼 변환."""

    def test_kospi_appends_ks(self):
        from app.services.backtest_service import _to_yf_symbol
        assert _to_yf_symbol("005930", "KOSPI") == "005930.KS"

    def test_krx_appends_ks(self):
        from app.services.backtest_service import _to_yf_symbol
        assert _to_yf_symbol("069500", "KRX") == "069500.KS"

    def test_kosdaq_appends_kq(self):
        from app.services.backtest_service import _to_yf_symbol
        assert _to_yf_symbol("035720", "KOSDAQ") == "035720.KQ"

    def test_overseas_no_suffix(self):
        from app.services.backtest_service import _to_yf_symbol
        assert _to_yf_symbol("AAPL", "NASDAQ") == "AAPL"

    def test_short_ticker_zero_padded(self):
        from app.services.backtest_service import _to_yf_symbol
        assert _to_yf_symbol("5930", "KOSPI") == "005930.KS"


class TestComputeMetrics:
    """_compute_metrics: Sharpe, MDD, CAGR 지표 계산."""

    def test_returns_zeros_for_single_value(self):
        from app.services.backtest_service import _compute_metrics
        m = _compute_metrics("test", [100.0])
        assert m.sharpe_ratio == 0
        assert m.mdd_pct == 0
        assert m.cagr_pct == 0

    def test_returns_zeros_for_empty_values(self):
        from app.services.backtest_service import _compute_metrics
        m = _compute_metrics("test", [])
        assert m.total_return_pct == 0

    def test_monotone_increase_has_positive_total_return(self):
        from app.services.backtest_service import _compute_metrics
        # 100 → 200: 100% 수익
        values = [100.0 + i for i in range(253)]
        m = _compute_metrics("test", values)
        assert m.total_return_pct > 0

    def test_monotone_decrease_has_positive_mdd(self):
        from app.services.backtest_service import _compute_metrics
        # 100 → 50: MDD 50%
        values = [100.0 - i * 0.2 for i in range(251)]
        m = _compute_metrics("test", values)
        assert m.mdd_pct > 0

    def test_mdd_correct_on_simple_drawdown(self):
        from app.services.backtest_service import _compute_metrics
        # [100, 150, 75] → peak=150, trough=75, MDD = (150-75)/150 = 50%
        m = _compute_metrics("test", [100.0, 150.0, 75.0])
        assert abs(m.mdd_pct - 50.0) < 0.01

    def test_sharpe_positive_for_trending_up(self):
        from app.services.backtest_service import _compute_metrics
        # 꾸준히 오르는 시리즈 → 양의 Sharpe
        values = [100.0 * (1.001 ** i) for i in range(300)]
        m = _compute_metrics("test", values)
        assert m.sharpe_ratio > 0

    def test_volatility_zero_for_flat_series(self):
        from app.services.backtest_service import _compute_metrics
        # 완전히 평평한 시리즈 → 변동성 0
        values = [100.0] * 300
        m = _compute_metrics("test", values)
        assert m.volatility_pct == 0
        assert m.sharpe_ratio == 0

    def test_total_return_matches_expected(self):
        from app.services.backtest_service import _compute_metrics
        # 100 기준 시작, 200 기준 끝 → 총수익률 100%
        # values는 지수 기준 (100 = 시작)
        # values[-1] = 200 → (200/100 - 1)*100 = 100%
        values = [100.0, 200.0]
        m = _compute_metrics("test", values)
        assert abs(m.total_return_pct - 100.0) < 0.01

    def test_metrics_are_rounded(self):
        from app.services.backtest_service import _compute_metrics
        values = [100.0 * (1.001 ** i) for i in range(300)]
        m = _compute_metrics("test", values)
        # 소수점 2~3자리까지만 반환
        assert m.sharpe_ratio == round(m.sharpe_ratio, 3)
        assert m.volatility_pct == round(m.volatility_pct, 2)


class TestComputePortfolioSeries:
    """_compute_portfolio_series: 단순 Buy & Hold 시리즈 계산."""

    def test_returns_flat_series_when_no_price_data(self):
        from app.services.backtest_service import _compute_portfolio_series

        holdings = [{"ticker": "AAPL", "market": "NASDAQ", "weight": 100}]
        price_data: dict = {}  # 가격 데이터 없음
        dates = ["2024-01-02", "2024-01-03", "2024-01-04"]

        series, metrics = _compute_portfolio_series("test", holdings, price_data, dates)

        assert all(v == 100.0 for v in series.values)
        assert metrics.total_return_pct == 0

    def test_single_asset_tracks_price(self):
        from app.services.backtest_service import _compute_portfolio_series

        holdings = [{"ticker": "AAPL", "market": "NASDAQ", "weight": 100}]
        dates = ["2024-01-02", "2024-01-03", "2024-01-04"]
        price_data = {"AAPL": [("2024-01-02", 150.0), ("2024-01-03", 165.0), ("2024-01-04", 180.0)]}

        series, metrics = _compute_portfolio_series("test", holdings, price_data, dates)

        # 150 → 180: +20%
        assert series.values[-1] > series.values[0]
        assert metrics.total_return_pct > 0

    def test_empty_holdings_returns_flat(self):
        from app.services.backtest_service import _compute_portfolio_series

        dates = ["2024-01-02", "2024-01-03"]
        series, metrics = _compute_portfolio_series("empty", [], {}, dates)

        assert all(v == 100.0 for v in series.values)
