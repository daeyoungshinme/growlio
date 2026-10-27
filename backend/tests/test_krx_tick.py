"""국내 지정가 호가단위 보정 (plans/61 C2)."""

from __future__ import annotations

import pytest

from app.services.rebalancing.krx_tick import (
    domestic_limit_price,
    is_etf_or_etn_name,
    round_to_tick,
    stock_tick_size,
)


@pytest.mark.parametrize(
    ("price", "tick"),
    [
        (1_999, 1),
        (2_000, 5),
        (4_995, 5),
        (5_000, 10),
        (19_990, 10),
        (20_000, 50),
        (49_950, 50),
        (50_000, 100),
        (199_900, 100),
        (200_000, 500),
        (499_500, 500),
        (500_000, 1_000),
    ],
)
def test_stock_tick_table(price, tick):
    assert stock_tick_size(price) == tick


def test_buy_rounds_down_and_sell_rounds_up():
    assert round_to_tick(51_230, "BUY", is_etf=False) == 51_200
    assert round_to_tick(51_230, "SELL", is_etf=False) == 51_300


def test_on_grid_price_is_unchanged():
    # 실시간 현재가(체결가)는 이미 격자 위 — AUTO 경로에서도 값이 바뀌지 않아야 한다
    for price in (1_234, 4_995, 51_200, 498_500, 1_234_000):
        assert round_to_tick(price, "BUY", is_etf=False) == price
        assert round_to_tick(price, "SELL", is_etf=False) == price


def test_sell_crossing_band_boundary_stays_valid():
    rounded = round_to_tick(49_990, "SELL", is_etf=False)
    assert rounded == 50_000
    assert rounded % stock_tick_size(rounded) == 0


def test_etf_uses_five_won_grid():
    assert round_to_tick(51_233, "BUY", is_etf=True) == 51_230
    assert round_to_tick(51_233, "SELL", is_etf=True) == 51_235


def test_never_rounds_to_zero():
    assert round_to_tick(0.5, "BUY", is_etf=False) == 1


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("KODEX 200", True),
        ("TIGER 미국S&P500", True),
        ("삼성 레버리지 WTI원유 선물 ETN", True),
        ("BNK금융지주", False),  # 브랜드 접두어 "BNK"에 공백 없이 붙은 일반주
        ("삼성전자", False),
        (None, False),
    ],
)
def test_etf_name_detection(name, expected):
    assert is_etf_or_etn_name(name) is expected


def test_domestic_limit_price_passes_market_orders_through():
    assert domestic_limit_price(None, "BUY", "삼성전자") is None
    assert domestic_limit_price(51_230.7, "BUY", "삼성전자") == 51_200.0
