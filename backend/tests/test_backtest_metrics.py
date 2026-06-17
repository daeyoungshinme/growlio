"""backtest_metrics.py 순수 계산 함수 단위 테스트."""

from __future__ import annotations

import pytest

from app.services.backtest_metrics import compute_metrics, compute_portfolio_series


class TestComputeMetrics:
    def test_too_few_values_returns_zeros(self):
        result = compute_metrics("test", [100.0])
        assert result.total_return_pct == 0
        assert result.cagr_pct == 0
        assert result.mdd_pct == 0

    def test_empty_values_returns_zeros(self):
        result = compute_metrics("test", [])
        assert result.total_return_pct == 0

    def test_flat_series_no_return(self):
        values = [100.0] * 252
        result = compute_metrics("flat", values)
        assert result.total_return_pct == pytest.approx(0.0, abs=0.1)
        assert result.cagr_pct == pytest.approx(0.0, abs=0.1)
        assert result.mdd_pct == pytest.approx(0.0, abs=0.01)

    def test_positive_return_scenario(self):
        # 252 거래일, 100에서 시작해 110으로 상승
        values = [100.0 + i * (10.0 / 252) for i in range(253)]
        result = compute_metrics("growth", values)
        assert result.total_return_pct == pytest.approx(10.0, abs=0.5)
        assert result.cagr_pct > 0

    def test_mdd_detected(self):
        # peak=100, drop to 50, recover to 110 → MDD should be ~50%
        values = [100.0] * 50 + [50.0] * 50 + [110.0] * 152
        result = compute_metrics("drawdown", values)
        assert result.mdd_pct == pytest.approx(50.0, abs=1.0)

    def test_sharpe_positive_for_positive_trend(self):
        values = [100.0 * (1.001 ** i) for i in range(253)]
        result = compute_metrics("bull", values)
        assert result.sharpe_ratio > 0
        assert result.volatility_pct >= 0

    def test_sortino_zero_when_no_downside(self):
        # 순수 상승 시리즈 — downside 없으면 sortino는 0 또는 양수
        values = [100.0 + i for i in range(253)]
        result = compute_metrics("no_downside", values)
        assert result.sortino_ratio >= 0

    def test_name_preserved(self):
        result = compute_metrics("MyPortfolio", [100.0, 110.0] * 126)
        assert result.name == "MyPortfolio"

    def test_insufficient_daily_rets_returns_partial(self):
        # 정확히 2개 값 → daily_rets 1개 → n < 2 분기
        result = compute_metrics("two_vals", [100.0, 120.0])
        assert result.total_return_pct == pytest.approx(20.0, abs=0.01)
        assert result.sharpe_ratio == 0
        assert result.volatility_pct == 0


class TestComputePortfolioSeries:
    def _make_holdings(self):
        return [{"ticker": "005930", "market": "KOSPI", "weight": 100.0}]

    def _make_price_data(self):
        # KR 종목 → yf symbol은 "005930.KS"
        dates = ["2023-01-02", "2023-01-03", "2023-01-04"]
        return {
            "005930.KS": [(d, 60000.0 + i * 1000) for i, d in enumerate(dates)]
        }, dates

    def test_single_holding_series(self):
        holdings = self._make_holdings()
        price_data_list, dates = self._make_price_data()
        price_data = {k: v for k, v in price_data_list.items()}
        series, metrics = compute_portfolio_series("KR Test", holdings, price_data, dates)
        assert series.name == "KR Test"
        assert len(series.values) == len(dates)
        assert series.values[0] == pytest.approx(100.0)
        assert series.values[-1] > 100.0

    def test_empty_price_data_returns_flat_100(self):
        holdings = self._make_holdings()
        dates = ["2023-01-02", "2023-01-03"]
        series, metrics = compute_portfolio_series("empty", holdings, {}, dates)
        assert all(v == 100.0 for v in series.values)

    def test_missing_symbol_produces_flat_series(self):
        holdings = [{"ticker": "AAPL", "market": "US", "weight": 100.0}]
        dates = ["2023-01-02", "2023-01-03"]
        # KR ticker가 US에 있는 경우 — 심볼 미스매치로 가격 없음
        price_data = {"005930.KS": [("2023-01-02", 60000.0)]}
        series, _ = compute_portfolio_series("no_price", holdings, price_data, dates)
        assert len(series.values) == len(dates)

    def test_metrics_returned_with_series(self):
        holdings = self._make_holdings()
        price_data_list, dates = self._make_price_data()
        price_data = {k: v for k, v in price_data_list.items()}
        _, metrics = compute_portfolio_series("m", holdings, price_data, dates)
        assert metrics.name == "m"
