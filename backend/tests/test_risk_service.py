"""risk_service.py 단위 테스트 (plans/137 A)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from app.services.risk_service import (
    SP500_SYMBOL,
    USDKRW_SYMBOL,
    _calc_beta,
    _calc_max_drawdown,
    _calc_var,
    _concentration,
    _to_yf_symbol,
    build_krw_close_frame,
    compute_risk_result,
)

# ── 헬퍼 ──────────────────────────────────────────────────────


def _wave(n: int, amp: float = 0.01, period: int = 5) -> list[float]:
    return [amp * ((i % period) - period // 2) for i in range(n)]


def _prices_from_returns(returns: list[float], start: float = 100.0) -> list[float]:
    out = [start]
    for r in returns:
        out.append(out[-1] * (1 + r))
    return out


def _series(values: list[float], dates: pd.DatetimeIndex) -> pd.Series:
    return pd.Series(values, index=dates[: len(values)])


# ── 순수 함수 ──────────────────────────────────────────────────


class TestToYfSymbol:
    def test_kospi(self, override_settings):
        assert _to_yf_symbol("005930", "KOSPI") == "005930.KS"

    def test_nasdaq_unchanged(self, override_settings):
        assert _to_yf_symbol("AAPL", "NASDAQ") == "AAPL"


class TestCalcVar:
    def test_empty_returns_zero(self):
        assert _calc_var([], 0.95) == 0.0

    def test_loss_quantile(self):
        returns = [r / 100.0 for r in range(-20, 20)]
        assert _calc_var(returns, 0.95) == pytest.approx(19.0)

    def test_all_positive_returns_no_loss(self):
        assert _calc_var([0.01, 0.02, 0.03], 0.95) == 0.0


class TestCalcMaxDrawdown:
    def test_peak_to_trough(self):
        # 100 → 120 → 90 → 110: 고점 120 대비 90은 -25%
        returns = [0.2, -0.25, 110 / 90 - 1]
        assert _calc_max_drawdown(returns) == pytest.approx(25.0)

    def test_monotonic_rise_zero(self):
        assert _calc_max_drawdown([0.01] * 10) == 0.0


class TestCalcBeta:
    def test_insufficient_data_returns_none(self):
        assert _calc_beta([0.01, 0.02], [0.01, 0.02]) is None

    def test_double_returns_beta_two(self):
        bench = _wave(50)
        assert _calc_beta([2 * r for r in bench], bench) == pytest.approx(2.0)

    def test_zero_variance_bench_returns_none(self):
        assert _calc_beta([0.01] * 30, [0.0] * 30) is None


class TestBuildKrwCloseFrame:
    def test_aligns_by_date_across_holidays(self):
        """한국 휴장일(미국 거래일)이 끼어도 같은 날짜끼리 맞춘다 — 순번 정렬이면 이후 모든 날이 하루씩 밀린다."""
        us_dates = pd.bdate_range("2026-01-05", periods=6)
        kr_dates = us_dates.delete(2)  # 한국만 쉬는 날
        closes = {
            "AAPL": pd.Series([100, 101, 102, 103, 104, 105], index=us_dates, dtype=float),
            "005930.KS": pd.Series([10, 11, 12, 13, 14], index=kr_dates, dtype=float),
            USDKRW_SYMBOL: pd.Series([1000.0] * 6, index=us_dates),
        }
        frame, no_fx = build_krw_close_frame(closes, {"AAPL"}, ["AAPL", "005930.KS"])
        assert no_fx == []
        # 휴장일은 직전 값으로 메운다
        assert frame.loc[us_dates[2], "005930.KS"] == 11
        assert frame.loc[us_dates[3], "005930.KS"] == 12
        assert frame.loc[us_dates[3], "AAPL"] == pytest.approx(103_000)

    def test_usd_converted_with_fx(self):
        dates = pd.bdate_range("2026-01-05", periods=3)
        closes = {
            "SPY": pd.Series([100.0, 100.0, 100.0], index=dates),
            USDKRW_SYMBOL: pd.Series([1000.0, 1100.0, 1100.0], index=dates),
        }
        frame, _ = build_krw_close_frame(closes, {"SPY"}, ["SPY"])
        returns = frame["SPY"].pct_change().dropna().tolist()
        # 달러 가격은 그대로여도 환율 +10%만큼 원화 수익
        assert returns[0] == pytest.approx(0.1)

    def test_usd_without_fx_reported(self):
        dates = pd.bdate_range("2026-01-05", periods=3)
        frame, no_fx = build_krw_close_frame({"SPY": pd.Series([1.0, 2.0, 3.0], index=dates)}, {"SPY"}, ["SPY"])
        assert no_fx == ["SPY"]
        assert frame.empty

    def test_timezone_index_normalized(self):
        dates = pd.date_range("2026-01-05 09:30", periods=3, freq="B", tz="America/New_York")
        frame, _ = build_krw_close_frame({"A.KS": pd.Series([1.0, 2.0, 3.0], index=dates)}, set(), ["A.KS"])
        assert frame.index.tz is None
        assert frame.index[0] == pd.Timestamp("2026-01-05")


class TestComputeRiskResult:
    def _closes(self, n: int = 300) -> tuple[dict[str, pd.Series], list[float]]:
        dates = pd.bdate_range("2025-01-01", periods=n + 1)
        rets = _wave(n)
        prices = _prices_from_returns(rets)
        closes = {
            "A.KS": _series(prices, dates),
            SP500_SYMBOL: _series(prices, dates),
            USDKRW_SYMBOL: pd.Series([1000.0] * (n + 1), index=dates),
        }
        return closes, rets

    def test_cash_halves_volatility(self):
        closes, _ = self._closes()
        holdings = [{"symbol": "A.KS", "value_krw": 1_000_000, "usd": False}]
        no_cash = compute_risk_result(holdings, 0.0, closes)
        half_cash = compute_risk_result(holdings, 1_000_000, closes)
        assert no_cash["data_available"] is True
        expected = no_cash["annualized_volatility_pct"] / 2
        assert half_cash["annualized_volatility_pct"] == pytest.approx(expected, rel=1e-3)
        assert half_cash["cash_weight_pct"] == pytest.approx(50.0)
        assert half_cash["total_value_krw"] == 2_000_000

    def test_missing_symbol_reweighted_and_coverage(self):
        """가격이 없는 종목은 빼고 나머지 가중치를 다시 맞춘다 — 합이 1보다 작아 위험이 줄어 보이면 안 된다."""
        closes, _ = self._closes()
        alone = compute_risk_result([{"symbol": "A.KS", "value_krw": 500_000, "usd": False}], 0.0, closes)
        with_missing = compute_risk_result(
            [
                {"symbol": "A.KS", "value_krw": 500_000, "usd": False},
                {"symbol": "MISSING.KS", "value_krw": 500_000, "usd": False},
            ],
            0.0,
            closes,
        )
        assert with_missing["annualized_volatility_pct"] == pytest.approx(alone["annualized_volatility_pct"])
        assert with_missing["coverage_pct"] == pytest.approx(50.0)

    def test_short_history_symbol_excluded(self):
        closes, _ = self._closes()
        dates = closes["A.KS"].index
        closes["NEW.KS"] = pd.Series([100.0 + i for i in range(50)], index=dates[-50:])
        result = compute_risk_result(
            [
                {"symbol": "A.KS", "value_krw": 500_000, "usd": False},
                {"symbol": "NEW.KS", "value_krw": 500_000, "usd": False},
            ],
            0.0,
            closes,
        )
        assert result["coverage_pct"] == pytest.approx(50.0)

    def test_same_as_benchmark_beta_one_ratio_one(self):
        closes, _ = self._closes()
        result = compute_risk_result([{"symbol": "A.KS", "value_krw": 1_000_000, "usd": False}], 0.0, closes)
        assert result["beta_sp500"] == pytest.approx(1.0, abs=1e-6)
        assert result["vol_ratio_vs_sp500"] == pytest.approx(1.0, abs=0.01)
        assert result["sp500_10pct_drop_krw"] == pytest.approx(100_000, rel=1e-3)

    def test_var_krw_matches_pct(self):
        closes, _ = self._closes()
        result = compute_risk_result([{"symbol": "A.KS", "value_krw": 1_000_000, "usd": False}], 0.0, closes)
        assert result["var_95_krw"] == pytest.approx(result["var_95_pct"] / 100 * 1_000_000, abs=1)

    def test_insufficient_data(self):
        dates = pd.bdate_range("2026-01-05", periods=5)
        closes = {"A.KS": pd.Series([1.0, 2.0, 3.0, 4.0, 5.0], index=dates)}
        result = compute_risk_result([{"symbol": "A.KS", "value_krw": 1.0, "usd": False}], 0.0, closes)
        assert result["data_available"] is False
        assert result["vol_ratio_vs_sp500"] is None
        assert result["sp500_10pct_drop_krw"] is None


class TestConcentration:
    def test_index_exposure_top3_and_top_holding(self):
        pos_map = {
            "QQQ-NASDAQ": {"ticker": "QQQ", "market": "NASDAQ", "name": "QQQ", "value_krw": 600.0},
            "133690-KOSPI": {"ticker": "133690", "market": "KOSPI", "name": "TIGER 나스닥100", "value_krw": 400.0},
        }
        group = SimpleNamespace(key="NASDAQ100", label="나스닥100", kind="INDEX", value_krw=1000.0, pct_of_stock=100.0)
        other = SimpleNamespace(key="STOCK", label="개별주", kind="STOCK", value_krw=10.0, pct_of_stock=1.0)
        result = _concentration(pos_map, SimpleNamespace(groups=[other, group]))
        assert result["top_holding_weight_pct"] == pytest.approx(60.0)
        assert result["top_holding_name"] == "QQQ"
        assert result["top_index_exposures"] == [{"key": "NASDAQ100", "label": "나스닥100", "pct_of_stock": 100.0}]

    def test_no_exposure(self):
        pos_map = {"A-KOSPI": {"ticker": "A", "market": "KOSPI", "name": "A", "value_krw": 1.0}}
        assert _concentration(pos_map, None)["top_index_exposures"] == []


# ── get_portfolio_risk_metrics (DB mock) ──────────────────────


def _snapshot_rows(positions: list[SimpleNamespace], amount_krw: float, asset_type: str = "STOCK_KIS"):
    snap = SimpleNamespace(id=uuid.uuid4(), position_items=positions, amount_krw=amount_krw)
    acc = SimpleNamespace(id=uuid.uuid4(), is_active=True, asset_type=asset_type)
    return [(snap, acc)]


class TestGetPortfolioRiskMetrics:
    @pytest.mark.asyncio
    async def test_no_positions_returns_empty(self, mock_db, override_settings):
        from app.services.risk_service import get_portfolio_risk_metrics

        with patch("app.services.risk_service.latest_snapshot_rows", new=AsyncMock(return_value=[])):
            result = await get_portfolio_risk_metrics(uuid.uuid4(), mock_db)

        assert result["data_available"] is False
        assert result["position_count"] == 0

    @pytest.mark.asyncio
    async def test_cache_hit_skips_db(self, mock_db, override_settings):
        import json

        from app.services.risk_service import get_portfolio_risk_metrics

        cache = AsyncMock()
        cache.get = AsyncMock(return_value=json.dumps({"var_95_pct": 1.5, "data_available": True}).encode())
        result = await get_portfolio_risk_metrics(uuid.uuid4(), mock_db, cache=cache)

        assert result["var_95_pct"] == 1.5
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_cash_and_non_tradable_handling(self, mock_db, override_settings):
        """증권 계좌 평가액 − 종목 합 = 예수금. 합성 항목(예수금 티커 등)은 종목에서 빼고 예수금 계산에만 쓴다."""
        from app.services.risk_service import get_portfolio_risk_metrics

        positions = [SimpleNamespace(ticker="AAPL", market="NASDAQ", name="Apple", value_krw=1_000_000)]
        rows = _snapshot_rows(positions, amount_krw=1_500_000)
        n = 300
        dates = pd.bdate_range("2025-01-01", periods=n + 1)
        prices = _prices_from_returns(_wave(n))
        closes = {
            "AAPL": _series(prices, dates),
            SP500_SYMBOL: _series(prices, dates),
            USDKRW_SYMBOL: pd.Series([1000.0] * (n + 1), index=dates),
        }

        with (
            patch("app.services.risk_service.latest_snapshot_rows", new=AsyncMock(return_value=rows)),
            patch("app.services.risk_service.get_index_exposure", new=AsyncMock(side_effect=RuntimeError("x"))),
            patch("app.services.risk_service.run_yf_bounded", new=AsyncMock(return_value=closes)),
        ):
            result = await get_portfolio_risk_metrics(uuid.uuid4(), mock_db)

        assert result["position_count"] == 1
        assert result["data_available"] is True
        assert result["cash_weight_pct"] == pytest.approx(100 / 3, rel=1e-3)
        assert result["top_index_exposures"] == []
        assert result["top_holding_name"] == "Apple"

    @pytest.mark.asyncio
    async def test_non_stock_account_has_no_cash(self, mock_db, override_settings):
        from app.services.risk_service import _load_positions_and_cash

        rows = _snapshot_rows([], amount_krw=5_000_000, asset_type="BANK_ACCOUNT")
        with patch("app.services.risk_service.latest_snapshot_rows", new=AsyncMock(return_value=rows)):
            pos_map, cash = await _load_positions_and_cash(uuid.uuid4(), MagicMock())
        assert pos_map == {}
        assert cash == 0.0
