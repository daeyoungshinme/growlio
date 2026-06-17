"""utils/pnl.py 및 공통 유틸리티 단위 테스트."""

from types import SimpleNamespace

import pytest

from app.utils.pnl import calc_position_pnl, eval_value, invested_value, pnl_pct

# ── eval_value ──────────────────────────────────────────────


class TestEvalValue:
    """현재가 기준 평가금액 합계."""

    def test_sums_current_price_times_qty(self, override_settings):
        positions = [
            SimpleNamespace(current_price=10_000, avg_price=9_000, qty=5),
            SimpleNamespace(current_price=50_000, avg_price=48_000, qty=2),
        ]
        assert eval_value(positions) == 10_000 * 5 + 50_000 * 2

    def test_uses_avg_price_when_no_current_price(self, override_settings):
        positions = [SimpleNamespace(current_price=None, avg_price=8_000, qty=3)]
        assert eval_value(positions) == 8_000 * 3

    def test_falls_back_to_zero_when_both_prices_none(self, override_settings):
        positions = [SimpleNamespace(current_price=None, avg_price=None, qty=5)]
        assert eval_value(positions) == 0.0

    def test_empty_list_returns_zero(self, override_settings):
        assert eval_value([]) == 0.0

    def test_handles_float_strings_via_float_cast(self, override_settings):
        positions = [SimpleNamespace(current_price="12000", avg_price="10000", qty="4")]
        assert eval_value(positions) == pytest.approx(12_000 * 4)


# ── invested_value ──────────────────────────────────────────


class TestInvestedValue:
    """매수가 기준 투자금액 합계."""

    def test_sums_avg_price_times_qty(self, override_settings):
        positions = [
            SimpleNamespace(avg_price=9_000, qty=5),
            SimpleNamespace(avg_price=48_000, qty=2),
        ]
        assert invested_value(positions) == 9_000 * 5 + 48_000 * 2

    def test_empty_list_returns_zero(self, override_settings):
        assert invested_value([]) == 0.0

    def test_none_avg_price_treated_as_zero(self, override_settings):
        positions = [SimpleNamespace(avg_price=None, qty=10)]
        assert invested_value(positions) == 0.0


# ── pnl_pct ─────────────────────────────────────────────────


class TestPnlPct:
    """수익률(%) 계산."""

    def test_positive_return(self, override_settings):
        assert pnl_pct(110.0, 100.0) == pytest.approx(10.0)

    def test_negative_return(self, override_settings):
        assert pnl_pct(90.0, 100.0) == pytest.approx(-10.0)

    def test_zero_invested_returns_zero(self, override_settings):
        assert pnl_pct(100.0, 0.0) == 0.0

    def test_even_returns_zero_pct(self, override_settings):
        assert pnl_pct(100.0, 100.0) == pytest.approx(0.0)


# ── calc_position_pnl ────────────────────────────────────────


class TestCalcPositionPnl:
    """단일 포지션의 투자금/평가금/손익/수익률 반환."""

    def test_profit_position(self, override_settings):
        invested, value, pnl, rate = calc_position_pnl(qty=10, avg_price=5_000, current_price=6_000)
        assert invested == 50_000
        assert value == 60_000
        assert pnl == 10_000
        assert rate == pytest.approx(20.0)

    def test_loss_position(self, override_settings):
        invested, value, pnl, rate = calc_position_pnl(qty=5, avg_price=10_000, current_price=8_000)
        assert invested == 50_000
        assert value == 40_000
        assert pnl == -10_000
        assert rate == pytest.approx(-20.0)

    def test_breakeven_position(self, override_settings):
        invested, value, pnl, rate = calc_position_pnl(qty=3, avg_price=7_000, current_price=7_000)
        assert pnl == pytest.approx(0.0)
        assert rate == pytest.approx(0.0)

    def test_zero_qty_returns_zero_rate(self, override_settings):
        invested, value, pnl, rate = calc_position_pnl(qty=0, avg_price=5_000, current_price=6_000)
        assert invested == 0.0
        assert value == 0.0
        assert rate == 0.0

    def test_zero_avg_price_returns_zero_rate(self, override_settings):
        _, _, _, rate = calc_position_pnl(qty=10, avg_price=0, current_price=5_000)
        assert rate == 0.0
