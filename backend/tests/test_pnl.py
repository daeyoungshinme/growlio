"""utils/pnl.py 단위 테스트."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.utils.pnl import calc_net_asset_amount, calc_position_pnl, eval_value, invested_value, pnl_pct


def _pos(avg_price=1000.0, qty=10.0, current_price=None):
    return SimpleNamespace(avg_price=avg_price, qty=qty, current_price=current_price)


class TestEvalValue:
    def test_uses_current_price_when_available(self):
        positions = [_pos(avg_price=1000.0, qty=10.0, current_price=1200.0)]
        assert eval_value(positions) == pytest.approx(12000.0)

    def test_falls_back_to_avg_price_when_no_current(self):
        positions = [_pos(avg_price=1000.0, qty=5.0, current_price=None)]
        assert eval_value(positions) == pytest.approx(5000.0)

    def test_multiple_positions_summed(self):
        positions = [
            _pos(avg_price=1000.0, qty=10.0, current_price=1100.0),
            _pos(avg_price=2000.0, qty=5.0, current_price=2200.0),
        ]
        assert eval_value(positions) == pytest.approx(11000.0 + 11000.0)

    def test_empty_positions_returns_zero(self):
        assert eval_value([]) == pytest.approx(0.0)

    def test_zero_qty_contributes_nothing(self):
        positions = [_pos(avg_price=5000.0, qty=0.0, current_price=6000.0)]
        assert eval_value(positions) == pytest.approx(0.0)

    def test_none_avg_and_current_price_treated_as_zero(self):
        pos = SimpleNamespace(avg_price=None, qty=10.0, current_price=None)
        assert eval_value([pos]) == pytest.approx(0.0)

    def test_handles_float_strings_via_float_cast(self):
        positions = [SimpleNamespace(current_price="12000", avg_price="10000", qty="4")]
        assert eval_value(positions) == pytest.approx(12_000 * 4)


class TestInvestedValue:
    def test_basic_calculation(self):
        positions = [_pos(avg_price=1000.0, qty=10.0)]
        assert invested_value(positions) == pytest.approx(10000.0)

    def test_multiple_positions(self):
        positions = [
            _pos(avg_price=500.0, qty=4.0),
            _pos(avg_price=2000.0, qty=3.0),
        ]
        assert invested_value(positions) == pytest.approx(2000.0 + 6000.0)

    def test_empty_positions_returns_zero(self):
        assert invested_value([]) == pytest.approx(0.0)

    def test_none_avg_price_treated_as_zero(self):
        pos = SimpleNamespace(avg_price=None, qty=5.0, current_price=None)
        assert invested_value([pos]) == pytest.approx(0.0)


class TestPnlPct:
    def test_profit(self):
        assert pnl_pct(11000.0, 10000.0) == pytest.approx(10.0)

    def test_loss(self):
        assert pnl_pct(9000.0, 10000.0) == pytest.approx(-10.0)

    def test_zero_invested_returns_zero(self):
        assert pnl_pct(5000.0, 0.0) == pytest.approx(0.0)

    def test_breakeven(self):
        assert pnl_pct(10000.0, 10000.0) == pytest.approx(0.0)


class TestCalcPositionPnl:
    def test_profit_scenario(self):
        invested, value, pnl, rate = calc_position_pnl(qty=10.0, avg_price=1000.0, current_price=1200.0)
        assert invested == pytest.approx(10000.0)
        assert value == pytest.approx(12000.0)
        assert pnl == pytest.approx(2000.0)
        assert rate == pytest.approx(20.0)

    def test_loss_scenario(self):
        invested, value, pnl, rate = calc_position_pnl(qty=5.0, avg_price=2000.0, current_price=1500.0)
        assert pnl == pytest.approx(-2500.0)
        assert rate == pytest.approx(-25.0)

    def test_zero_avg_price_returns_zero_rate(self):
        invested, value, pnl, rate = calc_position_pnl(qty=10.0, avg_price=0.0, current_price=500.0)
        assert invested == pytest.approx(0.0)
        assert rate == pytest.approx(0.0)

    def test_zero_qty_returns_zero_values(self):
        invested, value, pnl, rate = calc_position_pnl(qty=0, avg_price=5_000, current_price=6_000)
        assert invested == 0.0
        assert value == 0.0
        assert rate == 0.0

    def test_breakeven(self):
        _, _, pnl, rate = calc_position_pnl(qty=10.0, avg_price=1000.0, current_price=1000.0)
        assert pnl == pytest.approx(0.0)
        assert rate == pytest.approx(0.0)


class TestCalcNetAssetAmount:
    def test_non_real_estate_returns_manual_amount(self):
        assert calc_net_asset_amount(5_000_000.0, "CASH_OTHER", None) == pytest.approx(5_000_000.0)

    def test_real_estate_deducts_mortgage(self):
        details = {"mortgage_balance_krw": 100_000_000}
        result = calc_net_asset_amount(500_000_000.0, "REAL_ESTATE", details)
        assert result == pytest.approx(400_000_000.0)

    def test_none_manual_amount_treated_as_zero(self):
        assert calc_net_asset_amount(None, "CASH_OTHER", None) == pytest.approx(0.0)

    def test_none_real_estate_details_no_deduction(self):
        assert calc_net_asset_amount(300_000_000.0, "REAL_ESTATE", None) == pytest.approx(300_000_000.0)
