"""기간별 매수 종목·수익률 추정(period_purchase_service) 테스트."""

from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.period_purchase_service import (
    SOURCE_ESTIMATED,
    SOURCE_MANUAL,
    PosState,
    estimate_lots,
    get_period_purchases,
    lots_from_trades,
    resolve_period,
)

START = date(2026, 10, 1)
END = date(2026, 10, 31)
KEY = ("005930", "KOSPI")
US_KEY = ("AAPL", "NASDAQ")


def _s(qty, avg, cur=None, **kw):
    return PosState(qty=qty, avg_price=avg, current_price=cur, **kw)


class TestResolvePeriod:
    def test_month(self):
        assert resolve_period("month", 2026, 2) == (date(2026, 2, 1), date(2026, 2, 28))

    def test_december(self):
        assert resolve_period("month", 2026, 12) == (date(2026, 12, 1), date(2026, 12, 31))

    def test_year(self):
        assert resolve_period("year", 2026, None) == (date(2026, 1, 1), date(2026, 12, 31))

    def test_month_requires_month(self):
        with pytest.raises(ValueError, match="month is required"):
            resolve_period("month", 2026, None)


class TestEstimateLots:
    def test_new_buy(self):
        series = [
            (date(2026, 9, 30), {}),
            (date(2026, 10, 2), {KEY: _s(10, 70_000, 71_000)}),
        ]
        lot = estimate_lots(series, START, END)[KEY]
        assert lot.bought_qty == 10
        assert lot.bought_cost == pytest.approx(700_000)
        assert lot.first_buy_date == date(2026, 10, 2)
        assert not lot.price_estimated

    def test_additional_buy_back_solves_unit_price(self):
        # 기존 10주@60,000 → 15주 평단 62,000 : 추가 5주 단가 = (15*62000 - 10*60000)/5 = 66,000
        series = [
            (date(2026, 9, 30), {KEY: _s(10, 60_000)}),
            (date(2026, 10, 5), {KEY: _s(15, 62_000, 66_500)}),
        ]
        lot = estimate_lots(series, START, END)[KEY]
        assert lot.bought_qty == 5
        assert lot.bought_cost == pytest.approx(330_000)

    def test_buy_outside_period_ignored(self):
        series = [
            (date(2026, 9, 1), {}),
            (date(2026, 9, 15), {KEY: _s(10, 70_000)}),
            (date(2026, 10, 2), {KEY: _s(10, 70_000)}),
        ]
        assert estimate_lots(series, START, END) == {}

    def test_partial_sell_reduces_pro_rata(self):
        # 기존 10주 + 이번달 10주 → 20주 중 10주 매도: 이번달분은 절반(5주) 차감
        series = [
            (date(2026, 9, 30), {KEY: _s(10, 50_000)}),
            (date(2026, 10, 2), {KEY: _s(20, 55_000, 60_000)}),
            (date(2026, 10, 20), {KEY: _s(10, 55_000, 70_000)}),
        ]
        lot = estimate_lots(series, START, END)[KEY]
        assert lot.bought_qty == 10
        assert lot.qty == pytest.approx(5)
        assert lot.partially_sold
        # 이번달 단가 60,000 → 5주를 70,000에 매도: +50,000
        assert lot.realized_pnl == pytest.approx(50_000)

    def test_full_sell_after_period(self):
        series = [
            (date(2026, 9, 30), {}),
            (date(2026, 10, 2), {KEY: _s(10, 70_000, 70_000)}),
            (date(2026, 11, 3), {}),
        ]
        lot = estimate_lots(series, START, END)[KEY]
        assert lot.qty == 0
        assert lot.partially_sold
        # 매도 단가는 직전 스냅샷 현재가(70,000)로 추정 → 실현손익 0
        assert lot.realized_pnl == pytest.approx(0)

    def test_abnormal_implied_price_falls_back(self):
        # 평단이 사용자가 수정해 크게 바뀐 경우 등: 역산 단가 음수 → 현재가 대체
        series = [
            (date(2026, 9, 30), {KEY: _s(10, 100_000)}),
            (date(2026, 10, 2), {KEY: _s(11, 50_000, 52_000)}),
        ]
        lot = estimate_lots(series, START, END)[KEY]
        assert lot.bought_cost == pytest.approx(52_000)
        assert lot.price_estimated

    def test_overseas_uses_usd_avg_and_buy_day_rate(self):
        # 원화 평단은 환율로 매일 재환산되므로 USD 평단으로 역산해야 한다
        series = [
            (date(2026, 9, 30), {US_KEY: _s(10, 200 * 1300, avg_price_usd=200, usd_rate=1300)}),
            (
                date(2026, 10, 2),
                {US_KEY: _s(20, 210 * 1400, 220 * 1400, avg_price_usd=210, usd_rate=1400)},
            ),
        ]
        lot = estimate_lots(series, START, END)[US_KEY]
        # 추가 10주 USD 단가 = (20*210 - 10*200)/10 = 220 → 220*1400
        assert lot.bought_cost == pytest.approx(10 * 220 * 1400)

    def test_empty_series(self):
        assert estimate_lots([], START, END) == {}


def _trade(side, qty, price, d, fee=0, ticker="005930", market="KOSPI", name="삼성전자"):
    return SimpleNamespace(
        side=side, qty=qty, price_krw=price, fee=fee, trade_date=d, ticker=ticker, market=market, name=name
    )


class TestLotsFromTrades:
    def test_buys_and_sell(self):
        trades = [
            _trade("BUY", 10, 70_000, date(2026, 10, 2), fee=100),
            _trade("BUY", 10, 80_000, date(2026, 10, 10)),
            _trade("SELL", 5, 90_000, date(2026, 10, 20)),
        ]
        lot = lots_from_trades(trades, START, END)[KEY]
        assert lot.bought_qty == 20
        assert lot.bought_cost == pytest.approx(1_500_100)
        assert lot.qty == 15
        # 평균원가 75,005 → 5주 450,000 매도: 450,000 - 375,025
        assert lot.realized_pnl == pytest.approx(450_000 - 1_500_100 / 4)

    def test_buy_outside_period_ignored(self):
        trades = [_trade("BUY", 10, 70_000, date(2026, 9, 2))]
        assert lots_from_trades(trades, START, END) == {}


# ── get_period_purchases (DB mock) ──


def _result(rows=None, scalars=None):
    r = MagicMock()
    r.all.return_value = rows or []
    r.scalars.return_value.all.return_value = scalars or []
    return r


def _pos(snapshot_id, account_id, qty, avg, cur, ticker="005930", market="KOSPI", name="삼성전자"):
    return SimpleNamespace(
        snapshot_id=snapshot_id,
        account_id=account_id,
        ticker=ticker,
        market=market,
        name=name,
        qty=qty,
        avg_price=avg,
        avg_price_usd=None,
        current_price=cur,
        usd_rate=None,
    )


@pytest.fixture
def account():
    return SimpleNamespace(id=uuid.uuid4(), name="키움 일반", asset_type="STOCK_KIWOOM")


async def test_get_period_purchases_estimated(account):
    base_id, s1_id = uuid.uuid4(), uuid.uuid4()
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _result(scalars=[account]),  # 계좌
            _result(rows=[(account.id, date(2026, 9, 30))]),  # 기준 스냅샷 날짜
            _result(rows=[(base_id, account.id, date(2026, 9, 30)), (s1_id, account.id, date(2026, 10, 7))]),
            _result(scalars=[_pos(s1_id, account.id, 10, 70_000, 77_000)]),  # 포지션
            _result(scalars=[]),  # 수기 기록
        ]
    )
    out = await get_period_purchases(db, uuid.uuid4(), START, END, date(2026, 10, 8))
    assert out["end"] == date(2026, 10, 8)
    assert out["tracking_started"] == []
    [item] = out["items"]
    assert item["source"] == SOURCE_ESTIMATED
    assert item["name"] == "삼성전자"
    assert item["bought_amount_krw"] == 700_000
    assert item["value_krw"] == 770_000
    assert item["return_pct"] == 10.0
    assert out["summary"]["total_pnl_krw"] == 70_000


async def test_get_period_purchases_manual_overrides_and_caps(account):
    s1_id = uuid.uuid4()
    trade = SimpleNamespace(
        account_id=account.id,
        side="BUY",
        qty=10,
        price_krw=60_000,
        fee=0,
        trade_date=date(2026, 10, 3),
        ticker="005930",
        market="KOSPI",
        name="삼성전자",
    )
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _result(scalars=[account]),
            _result(rows=[]),  # 기준 스냅샷 없음 → 추적 시작
            _result(rows=[(s1_id, account.id, date(2026, 10, 7))]),
            _result(scalars=[_pos(s1_id, account.id, 4, 60_000, 66_000)]),
            _result(scalars=[trade]),
        ]
    )
    out = await get_period_purchases(db, uuid.uuid4(), START, END, date(2026, 10, 8))
    [item] = out["items"]
    assert item["source"] == SOURCE_MANUAL
    # 기록상 10주지만 현재 4주만 보유 → 4주로 상한
    assert item["held_qty"] == 4
    assert item["partially_sold"]
    assert item["return_pct"] == 10.0
    assert out["tracking_started"][0]["since"] == date(2026, 10, 7)


async def test_get_period_purchases_no_accounts():
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_result(scalars=[]))
    out = await get_period_purchases(db, uuid.uuid4(), START, END, date(2026, 10, 8))
    assert out["items"] == []
    assert out["summary"]["return_pct"] is None


async def test_get_period_purchases_out_of_period_manual_keeps_estimate(account):
    """기간 밖 수기 기록(이후 매도·end 뒤 매수)만 있으면 추정 매수가 사라지면 안 된다."""
    base_id, s1_id = uuid.uuid4(), uuid.uuid4()
    later = [
        _trade("SELL", 5, 80_000, date(2026, 11, 5)),
        _trade("BUY", 3, 75_000, date(2026, 11, 6)),
    ]
    for t in later:
        t.account_id = account.id
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _result(scalars=[account]),
            _result(rows=[(account.id, date(2026, 9, 30))]),
            _result(rows=[(base_id, account.id, date(2026, 9, 30)), (s1_id, account.id, date(2026, 10, 7))]),
            _result(scalars=[_pos(s1_id, account.id, 10, 70_000, 77_000)]),
            _result(scalars=later),
        ]
    )
    out = await get_period_purchases(db, uuid.uuid4(), START, END, date(2026, 11, 10))
    [item] = out["items"]
    assert item["source"] == SOURCE_ESTIMATED
    assert item["bought_amount_krw"] == 700_000


class TestMergeState:
    def test_usd_avg_dropped_when_only_one_row_has_it(self):
        from app.services.period_purchase_service import _merge_state

        states: dict = {}
        a = _pos(None, None, 10, 1_300_000, None, ticker="AAPL", market="NASDAQ")
        a.avg_price_usd, a.usd_rate = 1000.0, 1300.0
        b = _pos(None, None, 10, 1_400_000, None, ticker="AAPL", market="NASDAQ")
        _merge_state(states, a)
        _merge_state(states, b)
        merged = states[US_KEY]
        assert merged.qty == 20
        assert merged.avg_price == 1_350_000
        # 10주분 USD 평단이 20주에 붙으면 역산이 틀어진다 → KRW 폴백
        assert merged.avg_price_usd is None

    def test_usd_avg_weighted_when_both_rows_have_it(self):
        from app.services.period_purchase_service import _merge_state

        states: dict = {}
        for qty, usd in ((10, 100.0), (30, 200.0)):
            p = _pos(None, None, qty, usd * 1300, None, ticker="AAPL", market="NASDAQ")
            p.avg_price_usd, p.usd_rate = usd, 1300.0
            _merge_state(states, p)
        assert states[US_KEY].avg_price_usd == pytest.approx(175.0)


@pytest.mark.parametrize(
    ("trade_market", "pos_market", "ticker"),
    [
        ("KOSDAQ", "KOSPI", "247540"),  # 브로커는 코스닥 종목도 "KOSPI"로 저장
        ("NYSE", "US", "SPY"),  # 토스 해외 센티널
    ],
)
async def test_get_period_purchases_manual_matches_position_market(account, trade_market, pos_market, ticker):
    """검색에서 온 market과 브로커 포지션 market이 달라도 같은 종목으로 매칭한다."""
    base_id, s1_id = uuid.uuid4(), uuid.uuid4()
    trade = _trade("BUY", 10, 60_000, date(2026, 10, 3), ticker=ticker, market=trade_market, name="종목")
    trade.account_id = account.id
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _result(scalars=[account]),
            _result(rows=[(account.id, date(2026, 9, 30))]),
            _result(rows=[(base_id, account.id, date(2026, 9, 30)), (s1_id, account.id, date(2026, 10, 7))]),
            _result(scalars=[_pos(s1_id, account.id, 10, 60_000, 66_000, ticker=ticker, market=pos_market)]),
            _result(scalars=[trade]),
        ]
    )
    out = await get_period_purchases(db, uuid.uuid4(), START, END, date(2026, 10, 8))
    # 추정·기록 이중 집계 없이 기록 1건, 현재 보유(10주)로 평가
    [item] = out["items"]
    assert item["source"] == SOURCE_MANUAL
    assert item["market"] == pos_market
    assert item["held_qty"] == 10
    assert item["return_pct"] == 10.0
