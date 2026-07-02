"""_kis_order_executor._execute_two_phase_orders Phase 2(매도) clamp 통합 테스트."""

from unittest.mock import AsyncMock, patch

import pytest

from app.schemas.rebalancing import ExecutionOrderItem, OrderResult
from app.services import _kis_order_executor


def _make_order(
    ticker: str = "005930",
    market: str = "KOSPI",
    side: str = "SELL",
    quantity: int = 10,
) -> ExecutionOrderItem:
    return ExecutionOrderItem(ticker=ticker, name="삼성전자", market=market, side=side, quantity=quantity)


class TestExecuteTwoPhaseOrdersSellClamp:
    """TWO_PHASE Phase 2(매도)도 실행 계좌 실제 보유수량으로 clamp되어야 한다."""

    @pytest.mark.asyncio
    async def test_phase2_sell_clamped_to_actual_holdings(self, override_settings):
        sell_order = _make_order(ticker="005930", side="SELL", quantity=10)

        captured_quantity: int | None = None

        async def mock_execute_single(order, app_key, app_secret, access_token, account_no, is_mock):
            nonlocal captured_quantity
            if order.side == "SELL":
                captured_quantity = order.quantity
            return OrderResult(
                ticker=order.ticker,
                name=order.name,
                market=order.market,
                side=order.side,
                quantity=order.quantity,
                status="SUCCESS",
            )

        with (
            patch.object(_kis_order_executor, "get_orderable_cash", AsyncMock(return_value=0.0)),
            patch.object(
                _kis_order_executor,
                "get_domestic_balance",
                AsyncMock(return_value={"positions": [{"ticker": "005930", "qty": 3}]}),
            ),
            patch.object(_kis_order_executor, "_execute_single_order", side_effect=mock_execute_single),
        ):
            results = await _kis_order_executor._execute_two_phase_orders(
                [sell_order], "key", "secret", "token", "12345678-01", True
            )

        assert captured_quantity == 3
        assert any(r.status == "SUCCESS" for r in results)

    @pytest.mark.asyncio
    async def test_overseas_fallback_also_clamps_sells(self, override_settings):
        """buys에 해외종목이 섞이면 FULL 방식으로 폴백하는데, 이 경로의 매도도 clamp되어야 한다."""
        sell_order = _make_order(ticker="005930", market="KOSPI", side="SELL", quantity=10)
        buy_order = _make_order(ticker="AAPL", market="NASDAQ", side="BUY", quantity=1)

        captured_quantity: int | None = None

        async def mock_execute_single(order, app_key, app_secret, access_token, account_no, is_mock):
            nonlocal captured_quantity
            if order.side == "SELL":
                captured_quantity = order.quantity
            return OrderResult(
                ticker=order.ticker,
                name=order.name,
                market=order.market,
                side=order.side,
                quantity=order.quantity,
                status="SUCCESS",
            )

        with (
            patch.object(
                _kis_order_executor,
                "get_domestic_balance",
                AsyncMock(return_value={"positions": [{"ticker": "005930", "qty": 2}]}),
            ),
            patch.object(_kis_order_executor, "_execute_single_order", side_effect=mock_execute_single),
        ):
            results = await _kis_order_executor._execute_two_phase_orders(
                [sell_order, buy_order], "key", "secret", "token", "12345678-01", True
            )

        assert captured_quantity == 2
        assert len(results) == 2
