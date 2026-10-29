"""KIS·키움 공용 매도 clamp의 해외 보유수량 키 고정 (plans/91 B3).

KIS 해외잔고는 실제 거래소명을 주므로 거래소까지 키에 넣고, 키움은 잔고 market이 "US" 센티널이라
ticker 단독으로 비교한다(계획 55 A1). 공용화로 두 규칙이 섞이면 한쪽이 전부 보유 0(SKIPPED)으로 오판한다.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.schemas.rebalancing import ExecutionOrderItem, OrderResult
from app.services.rebalancing import _kis_order_executor, _kiwoom_order_executor


def _sell(market: str, quantity: int = 10) -> ExecutionOrderItem:
    return ExecutionOrderItem(
        ticker="ABC", name="ABC", market=market, side="SELL", quantity=quantity, order_type="MARKET"
    )


def _ok(order: ExecutionOrderItem) -> OrderResult:
    return OrderResult(
        ticker=order.ticker,
        name=order.name,
        market=order.market,
        side=order.side,
        quantity=order.quantity,
        status="SUCCESS",
    )


@pytest.mark.asyncio
async def test_kis_overseas_clamp_keys_by_exchange():
    placed: list[tuple[str, int]] = []

    async def _place(order, *args):
        placed.append((order.market, order.quantity))
        return _ok(order)

    balance = {
        "positions": [{"ticker": "ABC", "market": "NYSE", "qty": 3}, {"ticker": "ABC", "market": "nasdaq", "qty": 5}]
    }
    with (
        patch.object(_kis_order_executor, "get_overseas_balance", AsyncMock(return_value=balance)),
        patch.object(_kis_order_executor, "_execute_single_order", side_effect=_place),
    ):
        await _kis_order_executor._execute_sells_with_clamp(
            [_sell("NYSE"), _sell("NASDAQ"), _sell("AMEX")], "k", "s", "t", "12345678-01", True
        )

    # AMEX엔 보유가 없어 SKIPPED — 브로커 호출 없음
    assert placed == [("NYSE", 3), ("NASDAQ", 5)]


@pytest.mark.asyncio
async def test_kiwoom_overseas_clamp_ignores_us_sentinel_market():
    placed: list[tuple[str, int]] = []

    async def _place(order, *args):
        placed.append((order.market, order.quantity))
        return _ok(order)

    balance = {"positions": [{"ticker": "ABC", "market": "US", "qty": 4}]}
    with (
        patch.object(_kiwoom_order_executor, "kiwoom_get_overseas_balance", AsyncMock(return_value=balance)),
        patch.object(_kiwoom_order_executor, "_execute_kiwoom_single_order", side_effect=_place),
    ):
        await _kiwoom_order_executor._execute_kiwoom_sells_with_clamp([_sell("NASDAQ")], "t", "1234567890", True)

    assert placed == [("NASDAQ", 4)]
