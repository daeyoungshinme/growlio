"""_order_quantity_guard.clamp_sell_orders 단위 테스트."""

from app.schemas.rebalancing import ExecutionOrderItem
from app.services._order_quantity_guard import clamp_sell_orders


def _make_order(ticker: str = "005930", market: str = "KOSPI", quantity: int = 10) -> ExecutionOrderItem:
    return ExecutionOrderItem(ticker=ticker, name="삼성전자", market=market, side="SELL", quantity=quantity)


class TestClampSellOrders:
    """포트폴리오 합산 기준 매도 수량을 실제 보유수량으로 clamp."""

    def test_quantity_within_holdings_is_unchanged(self):
        order = _make_order(quantity=5)
        adjusted, skipped = clamp_sell_orders([order], {"005930": 10})

        assert skipped == []
        assert len(adjusted) == 1
        assert adjusted[0].quantity == 5

    def test_quantity_exceeding_holdings_is_clamped(self):
        order = _make_order(quantity=10)
        adjusted, skipped = clamp_sell_orders([order], {"005930": 3})

        assert skipped == []
        assert len(adjusted) == 1
        assert adjusted[0].quantity == 3

    def test_zero_holdings_skips_order(self):
        order = _make_order(quantity=10)
        adjusted, skipped = clamp_sell_orders([order], {})

        assert adjusted == []
        assert len(skipped) == 1
        assert skipped[0].status == "SKIPPED"
        assert skipped[0].quantity == 10  # 원래 요청 수량 유지 (이력 표시용)

    def test_custom_key_fn_for_overseas_market_matching(self):
        order = _make_order(ticker="AAPL", market="NASDAQ", quantity=10)
        held = {"AAPL:NASDAQ": 4}

        adjusted, skipped = clamp_sell_orders([order], held, key_fn=lambda o: f"{o.ticker}:{o.market.upper()}")

        assert skipped == []
        assert adjusted[0].quantity == 4

    def test_multiple_orders_mixed_results(self):
        orders = [
            _make_order(ticker="A", quantity=10),
            _make_order(ticker="B", quantity=5),
            _make_order(ticker="C", quantity=3),
        ]
        held = {"A": 20, "B": 0, "C": 2}

        adjusted, skipped = clamp_sell_orders(orders, held)

        assert {o.ticker: o.quantity for o in adjusted} == {"A": 10, "C": 2}
        assert [s.ticker for s in skipped] == ["B"]
