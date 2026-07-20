"""_kiwoom_order_executor 단위 테스트 — 국내/해외 단건 주문 실행 및 매도 clamp."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.schemas.rebalancing import ExecutionOrderItem
from app.services.rebalancing import _kiwoom_order_executor


def _make_order(
    ticker: str = "005930",
    market: str = "KOSPI",
    side: str = "SELL",
    quantity: int = 10,
    order_type: str = "MARKET",
    limit_price: float | None = None,
    reference_price: float | None = None,
) -> ExecutionOrderItem:
    return ExecutionOrderItem(
        ticker=ticker,
        name="삼성전자",
        market=market,
        side=side,
        quantity=quantity,
        order_type=order_type,
        limit_price=limit_price,
        reference_price=reference_price,
    )


class TestExecuteKiwoomSingleOrder:
    @pytest.mark.asyncio
    async def test_zero_quantity_returns_skipped(self):
        order = _make_order(quantity=0)
        with patch.object(_kiwoom_order_executor, "place_domestic_order", AsyncMock()) as place_fn:
            result = await _kiwoom_order_executor._execute_kiwoom_single_order(order, "token", "1234567890", True)

        assert result.status == "SKIPPED"
        assert result.error_msg == "주문 수량이 0 이하입니다."
        place_fn.assert_not_called()

    @pytest.mark.asyncio
    async def test_domestic_order_calls_place_domestic_order(self):
        order = _make_order(quantity=1, order_type="LIMIT", limit_price=71000.0)
        with patch.object(
            _kiwoom_order_executor, "place_domestic_order", AsyncMock(return_value={"order_no": "123"})
        ) as place_fn:
            result = await _kiwoom_order_executor._execute_kiwoom_single_order(order, "token", "1234567890", True)

        assert result.status == "SUCCESS"
        assert result.order_no == "123"
        assert result.price == 71000.0
        place_fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_overseas_order_calls_place_overseas_order(self):
        order = _make_order(market="NASDAQ", ticker="AAPL", quantity=1, order_type="LIMIT", limit_price=190.0)
        with (
            patch.object(_kiwoom_order_executor, "place_domestic_order", AsyncMock()) as domestic_fn,
            patch.object(
                _kiwoom_order_executor, "place_overseas_order", AsyncMock(return_value={"order_no": "456"})
            ) as overseas_fn,
        ):
            result = await _kiwoom_order_executor._execute_kiwoom_single_order(order, "token", "1234567890", True)

        assert result.status == "SUCCESS"
        assert result.order_no == "456"
        domestic_fn.assert_not_called()
        overseas_fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_market_order_falls_back_to_reference_price(self):
        order = _make_order(quantity=1, order_type="MARKET", reference_price=70000.0)
        with patch.object(_kiwoom_order_executor, "place_domestic_order", AsyncMock(return_value={"order_no": "123"})):
            result = await _kiwoom_order_executor._execute_kiwoom_single_order(order, "token", "1234567890", True)

        assert result.status == "SUCCESS"
        assert result.price == 70000.0

    @pytest.mark.asyncio
    async def test_place_order_exception_returns_failed(self):
        order = _make_order(quantity=1)
        with patch.object(
            _kiwoom_order_executor, "place_domestic_order", AsyncMock(side_effect=RuntimeError("주문 거부"))
        ):
            result = await _kiwoom_order_executor._execute_kiwoom_single_order(order, "token", "1234567890", True)

        assert result.status == "FAILED"
        assert result.error_msg == "주문 거부"


class TestExecuteKiwoomSellsWithClamp:
    @pytest.mark.asyncio
    async def test_domestic_sells_clamped_to_actual_holdings(self, override_settings):
        sell_order = _make_order(ticker="005930", side="SELL", quantity=10)

        captured_quantity: int | None = None
        original = _kiwoom_order_executor._execute_kiwoom_single_order

        async def _spy(order, access_token, account_no, is_mock):
            nonlocal captured_quantity
            captured_quantity = order.quantity
            return await original(order, access_token, account_no, is_mock)

        with (
            patch.object(
                _kiwoom_order_executor,
                "kiwoom_get_domestic_balance",
                AsyncMock(return_value={"positions": [{"ticker": "005930", "qty": 3}]}),
            ),
            patch.object(_kiwoom_order_executor, "place_domestic_order", AsyncMock(return_value={"order_no": "1"})),
            patch.object(_kiwoom_order_executor, "_execute_kiwoom_single_order", side_effect=_spy),
        ):
            results = await _kiwoom_order_executor._execute_kiwoom_sells_with_clamp(
                [sell_order], "token", "1234567890", True
            )

        assert captured_quantity == 3
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_overseas_sells_clamped_to_actual_holdings(self, override_settings):
        sell_order = _make_order(ticker="AAPL", market="NASDAQ", side="SELL", quantity=10)

        captured_quantity: int | None = None
        original = _kiwoom_order_executor._execute_kiwoom_single_order

        async def _spy(order, access_token, account_no, is_mock):
            nonlocal captured_quantity
            captured_quantity = order.quantity
            return await original(order, access_token, account_no, is_mock)

        with (
            patch.object(
                _kiwoom_order_executor,
                "kiwoom_get_overseas_balance",
                AsyncMock(return_value={"positions": [{"ticker": "AAPL", "market": "NASDAQ", "qty": 4}]}),
            ),
            patch.object(_kiwoom_order_executor, "place_overseas_order", AsyncMock(return_value={"order_no": "1"})),
            patch.object(_kiwoom_order_executor, "_execute_kiwoom_single_order", side_effect=_spy),
        ):
            results = await _kiwoom_order_executor._execute_kiwoom_sells_with_clamp(
                [sell_order], "token", "1234567890", True
            )

        assert captured_quantity == 4
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_mixed_domestic_and_overseas_sells_both_clamped(self, override_settings):
        domestic_sell = _make_order(ticker="005930", market="KOSPI", side="SELL", quantity=10)
        overseas_sell = _make_order(ticker="AAPL", market="NASDAQ", side="SELL", quantity=10)

        with (
            patch.object(
                _kiwoom_order_executor,
                "kiwoom_get_domestic_balance",
                AsyncMock(return_value={"positions": [{"ticker": "005930", "qty": 3}]}),
            ),
            patch.object(
                _kiwoom_order_executor,
                "kiwoom_get_overseas_balance",
                AsyncMock(return_value={"positions": [{"ticker": "AAPL", "market": "NASDAQ", "qty": 4}]}),
            ),
            patch.object(_kiwoom_order_executor, "place_domestic_order", AsyncMock(return_value={"order_no": "1"})),
            patch.object(_kiwoom_order_executor, "place_overseas_order", AsyncMock(return_value={"order_no": "2"})),
        ):
            results = await _kiwoom_order_executor._execute_kiwoom_sells_with_clamp(
                [domestic_sell, overseas_sell], "token", "1234567890", True
            )

        assert len(results) == 2
        assert {r.quantity for r in results} == {3, 4}

    @pytest.mark.asyncio
    async def test_empty_sells_returns_empty(self):
        results = await _kiwoom_order_executor._execute_kiwoom_sells_with_clamp([], "token", "1234567890", True)
        assert results == []

    @pytest.mark.asyncio
    async def test_domestic_balance_fetch_failure_falls_back_to_original_quantity(self, override_settings):
        sell_order = _make_order(ticker="005930", side="SELL", quantity=10)

        with (
            patch.object(
                _kiwoom_order_executor,
                "kiwoom_get_domestic_balance",
                AsyncMock(side_effect=RuntimeError("network")),
            ),
            patch.object(_kiwoom_order_executor, "place_domestic_order", AsyncMock(return_value={"order_no": "1"})),
        ):
            results = await _kiwoom_order_executor._execute_kiwoom_sells_with_clamp(
                [sell_order], "token", "1234567890", True
            )

        assert len(results) == 1
        assert results[0].quantity == 10
        assert results[0].status == "SUCCESS"

    @pytest.mark.asyncio
    async def test_overseas_balance_fetch_failure_falls_back_to_original_quantity(self, override_settings):
        sell_order = _make_order(ticker="AAPL", market="NASDAQ", side="SELL", quantity=10)

        with (
            patch.object(
                _kiwoom_order_executor,
                "kiwoom_get_overseas_balance",
                AsyncMock(side_effect=RuntimeError("network")),
            ),
            patch.object(_kiwoom_order_executor, "place_overseas_order", AsyncMock(return_value={"order_no": "1"})),
        ):
            results = await _kiwoom_order_executor._execute_kiwoom_sells_with_clamp(
                [sell_order], "token", "1234567890", True
            )

        assert len(results) == 1
        assert results[0].quantity == 10
        assert results[0].status == "SUCCESS"
