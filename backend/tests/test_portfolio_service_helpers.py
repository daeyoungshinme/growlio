"""portfolio_service.py 순수 헬퍼 함수 단위 테스트."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.portfolio_service import (
    _build_position_details,
    _build_stock_allocation,
    _calc_account_amounts,
)

# ── _calc_account_amounts ────────────────────────────────────────────────────


def _pos(qty=10, avg=50_000, cur=60_000, value_krw=None):
    return SimpleNamespace(qty=qty, avg_price=avg, current_price=cur, value_krw=value_krw)


def _snap(amount=10_000_000.0, invested=None, pnl=None):
    return SimpleNamespace(
        amount_krw=amount,
        invested_amount=invested,
        unrealized_pnl=pnl,
    )


def _acc(asset_type="STOCK_KIS", manual_amount=None, real_estate_details=None):
    return SimpleNamespace(
        asset_type=asset_type,
        manual_amount=manual_amount,
        real_estate_details=real_estate_details,
    )


class TestCalcAccountAmounts:
    def test_snap_with_invested_amount_returns_stored_values(self, override_settings):
        snap = _snap(amount=10_000_000, invested=9_000_000, pnl=1_000_000)
        acc = _acc()
        positions = [_pos()]
        amount, invested, pnl, pos = _calc_account_amounts(acc, snap, positions)
        assert amount == 10_000_000
        assert invested == 9_000_000
        assert pnl == 1_000_000
        assert pos is positions

    def test_snap_without_invested_calculates_from_positions(self, override_settings):
        snap = _snap(amount=10_000_000, invested=None, pnl=None)
        acc = _acc()
        positions = [_pos(qty=10, avg=50_000, cur=60_000)]
        amount, invested, pnl, _ = _calc_account_amounts(acc, snap, positions)
        assert amount == 10_000_000
        assert invested == pytest.approx(500_000)  # 10 * 50_000
        assert pnl == pytest.approx(100_000)        # (600_000 - 500_000)

    def test_snap_without_invested_no_positions(self, override_settings):
        snap = _snap(amount=5_000_000, invested=None, pnl=None)
        acc = _acc()
        amount, invested, pnl, pos = _calc_account_amounts(acc, snap, [])
        assert amount == 5_000_000
        assert invested == 0.0
        assert pnl == 0.0
        assert pos == []

    def test_manual_amount_no_snap(self, override_settings):
        acc = _acc(manual_amount=3_000_000)
        positions = [_pos(qty=5, avg=100_000, cur=120_000)]
        amount, invested, pnl, _ = _calc_account_amounts(acc, None, positions)
        assert amount == 3_000_000
        assert invested == pytest.approx(500_000)
        assert pnl == pytest.approx(100_000)

    def test_real_estate_subtracts_mortgage(self, override_settings):
        acc = _acc(
            asset_type="REAL_ESTATE",
            manual_amount=500_000_000,
            real_estate_details={"mortgage_balance_krw": 200_000_000},
        )
        amount, *_ = _calc_account_amounts(acc, None, [])
        assert amount == pytest.approx(300_000_000)

    def test_no_snap_no_manual_returns_zeros(self, override_settings):
        acc = _acc()
        amount, invested, pnl, pos = _calc_account_amounts(acc, None, [])
        assert amount == 0.0
        assert invested == 0.0
        assert pnl == 0.0
        assert pos == []

    def test_snap_with_none_unrealized_pnl(self, override_settings):
        snap = _snap(amount=10_000_000, invested=9_000_000, pnl=None)
        acc = _acc()
        _, _, pnl, _ = _calc_account_amounts(acc, snap, [])
        assert pnl == 0.0


# ── _build_position_details ──────────────────────────────────────────────────


def _raw_pos(ticker="005930", name="삼성전자", market="KOSPI", qty=10,
             avg=70_000, cur=80_000, value_krw=None, currency="KRW"):
    return SimpleNamespace(
        ticker=ticker, name=name, market=market,
        qty=qty, avg_price=avg, current_price=cur,
        value_krw=value_krw, currency=currency,
    )


def _stock_acc(asset_type="STOCK_KIS"):
    return SimpleNamespace(
        id=__import__("uuid").uuid4(),
        name="테스트계좌",
        asset_type=asset_type,
    )


class TestBuildPositionDetails:
    def test_non_stock_account_returns_empty(self, override_settings):
        acc = _stock_acc(asset_type="BANK_ACCOUNT")
        result = _build_position_details(acc, [_raw_pos()], None)
        assert result == []

    def test_empty_positions_returns_empty(self, override_settings):
        acc = _stock_acc()
        result = _build_position_details(acc, [], None)
        assert result == []

    def test_returns_correct_fields(self, override_settings):
        acc = _stock_acc()
        pos = _raw_pos(qty=10, avg=70_000, cur=80_000)
        result = _build_position_details(acc, [pos], None)
        assert len(result) == 1
        item = result[0]
        assert item["ticker"] == "005930"
        assert item["qty"] == pytest.approx(10.0)
        assert item["avg_price"] == pytest.approx(70_000.0)
        assert item["current_price"] == pytest.approx(80_000.0)
        assert item["value_krw"] == pytest.approx(800_000.0)
        assert item["invested_krw"] == pytest.approx(700_000.0)

    def test_uses_avg_price_when_no_current(self, override_settings):
        acc = _stock_acc()
        pos = _raw_pos(cur=None, avg=50_000, qty=5)
        result = _build_position_details(acc, [pos], None)
        assert result[0]["current_price"] == pytest.approx(50_000.0)

    def test_uses_value_krw_when_provided(self, override_settings):
        acc = _stock_acc()
        pos = _raw_pos(qty=10, avg=70_000, cur=80_000, value_krw=850_000)
        result = _build_position_details(acc, [pos], None)
        assert result[0]["value_krw"] == pytest.approx(850_000.0)

    def test_none_name_becomes_empty_string(self, override_settings):
        acc = _stock_acc()
        pos = _raw_pos(name=None)
        result = _build_position_details(acc, [pos], None)
        assert result[0]["name"] == ""

    def test_stock_other_account_included(self, override_settings):
        acc = _stock_acc(asset_type="STOCK_OTHER")
        pos = _raw_pos()
        result = _build_position_details(acc, [pos], None)
        assert len(result) == 1


# ── _build_stock_allocation ──────────────────────────────────────────────────


class TestBuildStockAllocation:
    def _make_pos(self, ticker, market="KOSPI", value_krw=1_000_000, name=None):
        return {"ticker": ticker, "name": name or ticker, "market": market, "value_krw": value_krw}

    def test_empty_positions_returns_empty(self, override_settings):
        result = _build_stock_allocation([], 0)
        assert result == []

    def test_single_position_returned_correctly(self, override_settings):
        positions = [self._make_pos("005930", value_krw=5_000_000)]
        result = _build_stock_allocation(positions, 5_000_000)
        assert len(result) == 1
        assert result[0]["ticker"] == "005930"
        assert result[0]["pct"] == pytest.approx(100.0)

    def test_merges_same_ticker_across_markets(self, override_settings):
        positions = [
            self._make_pos("AAPL", market="NASDAQ", value_krw=2_000_000),
            self._make_pos("AAPL", market="NASDAQ", value_krw=3_000_000),
        ]
        result = _build_stock_allocation(positions, 5_000_000)
        assert len(result) == 1
        assert result[0]["value_krw"] == pytest.approx(5_000_000)

    def test_more_than_10_generates_etc(self, override_settings):
        positions = [self._make_pos(f"T{i}", value_krw=1_000_000) for i in range(12)]
        total = 12_000_000
        result = _build_stock_allocation(positions, total)
        tickers = [r["ticker"] for r in result]
        assert "ETC" in tickers
        assert len(result) == 11  # top 10 + ETC

    def test_zero_total_gives_zero_pct(self, override_settings):
        positions = [self._make_pos("AAPL", value_krw=1_000_000)]
        result = _build_stock_allocation(positions, 0)
        assert result[0]["pct"] == 0

    def test_sorted_by_value_desc(self, override_settings):
        positions = [
            self._make_pos("A", value_krw=1_000_000),
            self._make_pos("B", value_krw=5_000_000),
            self._make_pos("C", value_krw=3_000_000),
        ]
        result = _build_stock_allocation(positions, 9_000_000)
        assert result[0]["ticker"] == "B"
        assert result[1]["ticker"] == "C"
        assert result[2]["ticker"] == "A"
