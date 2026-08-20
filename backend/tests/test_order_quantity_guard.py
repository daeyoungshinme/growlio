"""_order_quantity_guard.clamp_sell_orders/clamp_buy_orders_to_budget 단위 테스트."""

from app.schemas.rebalancing import ExecutionOrderItem
from app.services.rebalancing._order_quantity_guard import clamp_buy_orders_to_budget, clamp_sell_orders


def _make_order(ticker: str = "005930", market: str = "KOSPI", quantity: int = 10) -> ExecutionOrderItem:
    return ExecutionOrderItem(ticker=ticker, name="삼성전자", market=market, side="SELL", quantity=quantity)


def _make_buy_order(
    ticker: str = "005930",
    market: str = "KOSPI",
    quantity: int = 10,
    limit_price: float | None = None,
) -> ExecutionOrderItem:
    return ExecutionOrderItem(
        ticker=ticker,
        name="삼성전자",
        market=market,
        side="BUY",
        quantity=quantity,
        order_type="LIMIT" if limit_price else "MARKET",
        limit_price=limit_price,
    )


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


class TestClampBuyOrdersToBudget:
    """매수 주문을 실행 직전 조회한 예산(주문가능금액/예수금)으로 clamp."""

    def test_within_budget_is_unchanged(self):
        order = _make_buy_order(quantity=10, limit_price=1000.0)
        adjusted, skipped = clamp_buy_orders_to_budget([order], budget=20000.0)

        assert skipped == []
        assert len(adjusted) == 1
        assert adjusted[0].quantity == 10

    def test_exceeding_budget_clamps_quantity(self):
        order = _make_buy_order(quantity=10, limit_price=1000.0)
        adjusted, skipped = clamp_buy_orders_to_budget([order], budget=4500.0)

        assert skipped == []
        assert len(adjusted) == 1
        assert adjusted[0].quantity == 4  # 4500 // 1000

    def test_zero_budget_skips_order(self):
        order = _make_buy_order(quantity=10, limit_price=1000.0)
        adjusted, skipped = clamp_buy_orders_to_budget([order], budget=0.0)

        assert adjusted == []
        assert len(skipped) == 1
        assert skipped[0].status == "SKIPPED"
        assert skipped[0].quantity == 10  # 원래 요청 수량 유지 (이력 표시용)

    def test_market_order_without_price_is_not_clamped(self):
        """시장가 주문은 체결가를 미리 알 수 없어 clamp 대상에서 제외한다."""
        order = _make_buy_order(quantity=10, limit_price=None)
        adjusted, skipped = clamp_buy_orders_to_budget([order], budget=0.0)

        assert skipped == []
        assert len(adjusted) == 1
        assert adjusted[0].quantity == 10

    def test_multiple_orders_share_budget_sequentially(self):
        orders = [
            _make_buy_order(ticker="A", quantity=5, limit_price=1000.0),
            _make_buy_order(ticker="B", quantity=5, limit_price=1000.0),
        ]
        # A가 5000 전부 소모 → B는 예산 0으로 SKIPPED
        adjusted, skipped = clamp_buy_orders_to_budget(orders, budget=5000.0)

        assert {o.ticker: o.quantity for o in adjusted} == {"A": 5}
        assert [s.ticker for s in skipped] == ["B"]
