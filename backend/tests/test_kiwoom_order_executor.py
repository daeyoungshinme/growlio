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
    async def test_place_order_rejection_returns_broker_reason(self):
        from app.exceptions import BrokerOrderRejectedError

        order = _make_order(quantity=1)
        with patch.object(
            _kiwoom_order_executor,
            "place_domestic_order",
            AsyncMock(side_effect=BrokerOrderRejectedError("주문가능금액이 부족합니다")),
        ):
            result = await _kiwoom_order_executor._execute_kiwoom_single_order(order, "token", "1234567890", True)

        assert result.status == "FAILED"
        assert result.error_msg == "주문가능금액이 부족합니다"

    @pytest.mark.asyncio
    async def test_unexpected_exception_text_is_not_exposed(self):
        # SQL 바인드 파라미터·URL이 섞일 수 있는 원문은 응답·실행 이력에 남기지 않는다(계획 57 D1)
        order = _make_order(quantity=1)
        with patch.object(
            _kiwoom_order_executor,
            "place_domestic_order",
            AsyncMock(side_effect=RuntimeError("(psycopg) INSERT ... access_token='secret-token'")),
        ):
            result = await _kiwoom_order_executor._execute_kiwoom_single_order(order, "token", "1234567890", True)

        assert result.status == "FAILED"
        assert "secret-token" not in (result.error_msg or "")
        assert "RuntimeError" in (result.error_msg or "")


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
                AsyncMock(
                    return_value={"positions": [{"ticker": "AAPL", "market": "US", "qty": 4}]}
                ),  # 실제 잔고 응답은 "US" 센티널
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
    async def test_overseas_sell_matches_unresolved_us_market_from_balance(self, override_settings):
        """키움 해외잔고(ust21070)는 거래소를 주지 않아 market이 "US" 센티널이다(kiwoom/balance.py).
        주문은 NASDAQ/NYSE/AMEX라 market까지 키에 넣으면 보유 0으로 오판해 매도가 전부 SKIPPED됐다."""
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
                AsyncMock(return_value={"positions": [{"ticker": "AAPL", "market": "US", "qty": 4}]}),
            ),
            patch.object(_kiwoom_order_executor, "place_overseas_order", AsyncMock(return_value={"order_no": "1"})),
            patch.object(_kiwoom_order_executor, "_execute_kiwoom_single_order", side_effect=_spy),
        ):
            results = await _kiwoom_order_executor._execute_kiwoom_sells_with_clamp(
                [sell_order], "token", "1234567890", True
            )

        assert captured_quantity == 4
        assert [r.status for r in results] != ["SKIPPED"]

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
                AsyncMock(return_value={"positions": [{"ticker": "AAPL", "market": "US", "qty": 4}]}),
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


class TestExecuteKiwoomBuysWithCashCheck:
    """FULL 전략 매수 실행 — 실행 직전 국내 예수금으로 clamp(_execute_kiwoom_buys_with_cash_check)."""

    @pytest.mark.asyncio
    async def test_clamps_buy_quantity_to_deposit(self, override_settings):
        buy_order = _make_order(ticker="005930", side="BUY", quantity=10, order_type="LIMIT", limit_price=1000.0)

        with (
            patch.object(
                _kiwoom_order_executor,
                "kiwoom_get_domestic_balance",
                AsyncMock(return_value={"positions": [], "deposit_krw": 4500.0}),
            ),
            patch.object(_kiwoom_order_executor, "place_domestic_order", AsyncMock(return_value={"order_no": "1"})),
        ):
            results = await _kiwoom_order_executor._execute_kiwoom_buys_with_cash_check(
                [buy_order], "token", "1234567890", True
            )

        assert len(results) == 1
        assert results[0].quantity == 4  # 4500 // 1000
        assert results[0].status == "SUCCESS"

    @pytest.mark.asyncio
    async def test_orderable_krw_takes_precedence_over_deposit_krw(self, override_settings):
        """orderable_krw(미수없는 매수여력)가 있으면 그것으로 clamp, deposit_krw는 폴백."""
        buy_order = _make_order(ticker="005930", side="BUY", quantity=10, order_type="LIMIT", limit_price=1000.0)

        with (
            patch.object(
                _kiwoom_order_executor,
                "kiwoom_get_domestic_balance",
                AsyncMock(return_value={"positions": [], "deposit_krw": 9000.0, "orderable_krw": 3000.0}),
            ),
            patch.object(_kiwoom_order_executor, "place_domestic_order", AsyncMock(return_value={"order_no": "1"})),
        ):
            results = await _kiwoom_order_executor._execute_kiwoom_buys_with_cash_check(
                [buy_order], "token", "1234567890", True
            )

        assert results[0].quantity == 3  # 3000 // 1000, not 9

    @pytest.mark.asyncio
    async def test_zero_deposit_skips_buy_without_calling_broker(self, override_settings):
        buy_order = _make_order(ticker="005930", side="BUY", quantity=10, order_type="LIMIT", limit_price=1000.0)

        with (
            patch.object(
                _kiwoom_order_executor,
                "kiwoom_get_domestic_balance",
                AsyncMock(return_value={"positions": [], "deposit_krw": 0.0}),
            ),
            patch.object(_kiwoom_order_executor, "place_domestic_order", AsyncMock()) as place_fn,
        ):
            results = await _kiwoom_order_executor._execute_kiwoom_buys_with_cash_check(
                [buy_order], "token", "1234567890", True
            )

        place_fn.assert_not_called()
        assert results[0].status == "SKIPPED"

    @pytest.mark.asyncio
    async def test_overseas_buy_skips_clamp_entirely(self, override_settings):
        buy_order = _make_order(ticker="AAPL", market="NASDAQ", side="BUY", quantity=5)

        with (
            patch.object(_kiwoom_order_executor, "kiwoom_get_domestic_balance", AsyncMock()) as balance_fn,
            patch.object(_kiwoom_order_executor, "place_overseas_order", AsyncMock(return_value={"order_no": "1"})),
        ):
            results = await _kiwoom_order_executor._execute_kiwoom_buys_with_cash_check(
                [buy_order], "token", "1234567890", True
            )

        balance_fn.assert_not_called()
        assert results[0].quantity == 5

    @pytest.mark.asyncio
    async def test_deposit_lookup_failure_skips_buys(self, override_settings):
        """plans/119 B4: 예산 조회가 실패하면 실자금 매수를 발주하지 않는다(KIS FULL·TWO_PHASE와 같은 예산 0 취급)."""
        buy_order = _make_order(ticker="005930", side="BUY", quantity=10, order_type="LIMIT", limit_price=1000.0)

        with (
            patch.object(
                _kiwoom_order_executor,
                "kiwoom_get_domestic_balance",
                AsyncMock(side_effect=RuntimeError("network")),
            ),
            patch.object(
                _kiwoom_order_executor, "place_domestic_order", AsyncMock(return_value={"order_no": "1"})
            ) as mock_place,
        ):
            results = await _kiwoom_order_executor._execute_kiwoom_buys_with_cash_check(
                [buy_order], "token", "1234567890", True
            )

        mock_place.assert_not_called()
        assert results[0].status == "SKIPPED"

    @pytest.mark.asyncio
    async def test_empty_buys_returns_empty(self):
        results = await _kiwoom_order_executor._execute_kiwoom_buys_with_cash_check([], "token", "1234567890", True)
        assert results == []


def _us_buy(ticker: str = "AAPL", quantity: int = 1, limit_price: float = 100.0) -> ExecutionOrderItem:
    return _make_order(
        ticker=ticker, market="NASDAQ", side="BUY", quantity=quantity, order_type="LIMIT", limit_price=limit_price
    )


def _patch_funding(usd: float, orderable_krw: float = 0.0, rate: float = 1000.0, is_live: bool = True):
    return (
        patch.object(_kiwoom_order_executor, "kiwoom_get_overseas_deposit_usd", AsyncMock(return_value=usd)),
        patch.object(_kiwoom_order_executor, "kiwoom_get_orderable_krw", AsyncMock(return_value=orderable_krw)),
        patch.object(_kiwoom_order_executor, "get_live_or_cached_usd_krw", AsyncMock(return_value=(rate, is_live))),
    )


async def _run_buys(buys, *, krw_order: bool):
    return await _kiwoom_order_executor._execute_kiwoom_buys_with_cash_check(
        buys, "token", "1234567890", True, krw_order=krw_order, cache=None
    )


class TestKiwoomOverseasBuyFunding:
    """plans/140: 해외 매수는 달러 우선 → 원화주문 계좌만 원화, 일반 계좌 달러 부족은 건너뛴다."""

    @pytest.mark.asyncio
    async def test_enough_usd_places_as_usd(self, override_settings):
        usd, krw, rate = _patch_funding(usd=500.0)
        with (
            usd,
            krw as krw_fn,
            rate,
            patch.object(_kiwoom_order_executor, "place_overseas_order", AsyncMock(return_value={"order_no": "1"})),
        ):
            results = await _run_buys([_us_buy(quantity=2, limit_price=100.0)], krw_order=True)

        assert results[0].status == "SUCCESS"
        assert results[0].settlement_currency == "USD"
        krw_fn.assert_awaited_once()  # 원화주문 계좌는 원화 여력도 미리 받는다

    @pytest.mark.asyncio
    async def test_usd_short_regular_account_skips(self, override_settings):
        usd, krw, rate = _patch_funding(usd=50.0, orderable_krw=10_000_000.0)
        with (
            usd,
            krw as krw_fn,
            rate,
            patch.object(_kiwoom_order_executor, "place_overseas_order", AsyncMock()) as place_fn,
        ):
            results = await _run_buys([_us_buy(quantity=1, limit_price=100.0)], krw_order=False)

        place_fn.assert_not_called()
        krw_fn.assert_not_called()
        assert results[0].status == "SKIPPED"
        assert "달러 예수금이 부족" in (results[0].error_msg or "")
        assert "원화주문" in (results[0].error_msg or "")

    @pytest.mark.asyncio
    async def test_usd_short_krw_order_account_places_as_krw(self, override_settings):
        # 달러 $50 + 원화 1,030,000 ÷ (1000 × 1.03) = $1000 여력 → $100.3 주문은 부족분을 원화로
        usd, krw, rate = _patch_funding(usd=50.0, orderable_krw=1_030_000.0)
        with (
            usd,
            krw,
            rate,
            patch.object(
                _kiwoom_order_executor, "place_overseas_order", AsyncMock(return_value={"order_no": "1"})
            ) as place_fn,
        ):
            results = await _run_buys([_us_buy(quantity=1, limit_price=100.0)], krw_order=True)

        place_fn.assert_awaited_once()
        assert results[0].status == "SUCCESS"
        assert results[0].settlement_currency == "KRW"

    @pytest.mark.asyncio
    async def test_krw_order_account_short_on_both_skips(self, override_settings):
        usd, krw, rate = _patch_funding(usd=10.0, orderable_krw=10_300.0)  # 원화 환산 $10
        with (
            usd,
            krw,
            rate,
            patch.object(_kiwoom_order_executor, "place_overseas_order", AsyncMock()) as place_fn,
        ):
            results = await _run_buys([_us_buy(quantity=1, limit_price=100.0)], krw_order=True)

        place_fn.assert_not_called()
        assert results[0].status == "SKIPPED"
        assert "달러·원화" in (results[0].error_msg or "")

    @pytest.mark.asyncio
    async def test_usd_consumed_in_order_then_krw(self, override_settings):
        # 첫 주문이 달러 $150 중 $100.3을 쓰고, 둘째 주문은 남은 달러 + 원화로
        usd, krw, rate = _patch_funding(usd=150.0, orderable_krw=1_030_000.0)
        with (
            usd,
            krw,
            rate,
            patch.object(_kiwoom_order_executor, "place_overseas_order", AsyncMock(return_value={"order_no": "1"})),
        ):
            results = await _run_buys([_us_buy("AAPL"), _us_buy("MSFT")], krw_order=True)

        assert [r.settlement_currency for r in results] == ["USD", "KRW"]

    @pytest.mark.asyncio
    async def test_failed_order_does_not_consume_usd(self, override_settings):
        usd, krw, rate = _patch_funding(usd=150.0)
        place = AsyncMock(side_effect=[RuntimeError("rejected"), {"order_no": "2"}])
        with usd, krw, rate, patch.object(_kiwoom_order_executor, "place_overseas_order", place):
            results = await _run_buys([_us_buy("AAPL"), _us_buy("MSFT")], krw_order=False)

        assert results[0].status == "FAILED"
        assert results[1].status == "SUCCESS"
        assert results[1].settlement_currency == "USD"

    @pytest.mark.asyncio
    async def test_no_live_rate_krw_order_places_unchecked(self, override_settings):
        usd, krw, rate = _patch_funding(usd=0.0, is_live=False)
        with (
            usd,
            krw as krw_fn,
            rate,
            patch.object(
                _kiwoom_order_executor, "place_overseas_order", AsyncMock(return_value={"order_no": "1"})
            ) as place_fn,
        ):
            results = await _run_buys([_us_buy()], krw_order=True)

        krw_fn.assert_not_called()
        place_fn.assert_awaited_once()
        assert results[0].settlement_currency is None

    @pytest.mark.asyncio
    async def test_funding_lookup_failure_places_unchecked(self, override_settings):
        with (
            patch.object(
                _kiwoom_order_executor,
                "kiwoom_get_overseas_deposit_usd",
                AsyncMock(side_effect=RuntimeError("network")),
            ),
            patch.object(
                _kiwoom_order_executor, "place_overseas_order", AsyncMock(return_value={"order_no": "1"})
            ) as place_fn,
        ):
            results = await _run_buys([_us_buy()], krw_order=False)

        place_fn.assert_awaited_once()
        assert results[0].status == "SUCCESS"

    @pytest.mark.asyncio
    async def test_mixed_buys_clamp_domestic_and_judge_overseas(self, override_settings):
        domestic = _make_order(ticker="005930", side="BUY", quantity=10, order_type="LIMIT", limit_price=1000.0)
        usd, krw, rate = _patch_funding(usd=0.0)
        with (
            patch.object(
                _kiwoom_order_executor,
                "kiwoom_get_domestic_balance",
                AsyncMock(return_value={"positions": [], "deposit_krw": 3000.0}),
            ),
            patch.object(_kiwoom_order_executor, "place_domestic_order", AsyncMock(return_value={"order_no": "1"})),
            usd,
            krw,
            rate,
            patch.object(_kiwoom_order_executor, "place_overseas_order", AsyncMock()) as place_overseas,
        ):
            results = await _run_buys([_us_buy(), domestic], krw_order=False)

        assert results[0].ticker == "005930"
        assert results[0].quantity == 3  # 해외가 섞여도 국내는 원화 매수여력으로 clamp
        assert results[1].status == "SKIPPED"
        place_overseas.assert_not_called()


class TestKiwoomDomesticLimitTickRounding:
    """키움 경로도 같은 호가 보정을 거친다 (plans/61 C2)."""

    @pytest.mark.asyncio
    async def test_etf_uses_five_won_grid(self):
        order = ExecutionOrderItem(
            ticker="069500",
            name="KODEX 200",
            market="KOSPI",
            side="BUY",
            quantity=1,
            order_type="LIMIT",
            limit_price=38_233.0,
        )
        place = AsyncMock(return_value={"order_no": "1"})
        with patch.object(_kiwoom_order_executor, "place_domestic_order", place):
            await _kiwoom_order_executor._execute_kiwoom_single_order(order, "t", "1234567890", True)
        assert place.call_args.kwargs["limit_price"] == 38_230.0


class TestKiwoomSellProceedsFunding:
    """plans/141 A1: 같은 실행의 해외 매도 대금을 달러 여력에 더한다(결제 전이라 예수금에 없어 거짓 SKIPPED 방지)."""

    def test_overseas_sell_proceeds_counts_only_successful_overseas_sells(self):
        from app.schemas.rebalancing import OrderResult
        from app.services.rebalancing._broker_order_flow import overseas_sell_proceeds_usd

        us_sell = _make_order(ticker="QQQ", market="NASDAQ", side="SELL", quantity=2, reference_price=250.0)
        kr_sell = _make_order(ticker="005930", market="KOSPI", side="SELL", quantity=1, reference_price=70_000.0)
        failed = _make_order(ticker="SPY", market="NYSE", side="SELL", quantity=1, reference_price=500.0)
        results = [
            OrderResult.for_order(us_sell, "SUCCESS"),
            OrderResult.for_order(kr_sell, "SUCCESS"),
            OrderResult.for_order(failed, "FAILED"),
        ]

        assert overseas_sell_proceeds_usd(results) == pytest.approx(500.0)

    @pytest.mark.asyncio
    async def test_regular_account_buy_uses_pending_sell_proceeds(self, override_settings):
        usd, krw, rate = _patch_funding(usd=0.0)
        with (
            usd,
            krw,
            rate,
            patch.object(
                _kiwoom_order_executor, "place_overseas_order", AsyncMock(return_value={"order_no": "1"})
            ) as place_fn,
        ):
            results = await _kiwoom_order_executor._execute_kiwoom_buys_with_cash_check(
                [_us_buy(quantity=4, limit_price=100.0)],
                "token",
                "1234567890",
                True,
                krw_order=False,
                cache=None,
                pending_sell_usd=500.0,
            )

        place_fn.assert_awaited_once()
        assert results[0].status == "SUCCESS"
        assert results[0].settlement_currency == "USD"

    @pytest.mark.asyncio
    async def test_krw_order_account_uses_sell_proceeds_before_krw(self, override_settings):
        # 매도 대금 $50 + 원화 환산 $1000 → $100.3 주문은 달러 부족분만 원화로
        usd, krw, rate = _patch_funding(usd=0.0, orderable_krw=1_030_000.0)
        with (
            usd,
            krw,
            rate,
            patch.object(_kiwoom_order_executor, "place_overseas_order", AsyncMock(return_value={"order_no": "1"})),
        ):
            enough = await _kiwoom_order_executor._execute_kiwoom_buys_with_cash_check(
                [_us_buy(quantity=1, limit_price=100.0)],
                "token",
                "1234567890",
                True,
                krw_order=True,
                cache=None,
                pending_sell_usd=200.0,
            )
            partial = await _kiwoom_order_executor._execute_kiwoom_buys_with_cash_check(
                [_us_buy(quantity=1, limit_price=100.0)],
                "token",
                "1234567890",
                True,
                krw_order=True,
                cache=None,
                pending_sell_usd=50.0,
            )

        assert enough[0].settlement_currency == "USD"
        assert partial[0].settlement_currency == "KRW"

    @pytest.mark.asyncio
    async def test_account_orders_pass_successful_sell_proceeds_to_buys(self, make_account, mock_db, mock_cache):
        from app.schemas.rebalancing import OrderResult
        from app.services.rebalancing import execution_service

        account = make_account(asset_type="STOCK_KIWOOM", data_source="KIWOOM_API")
        account.kiwoom_account_no = "1234567890"
        account.krw_overseas_order = False
        sell = _make_order(
            ticker="QQQ", market="NASDAQ", side="SELL", quantity=2, limit_price=250.0, order_type="LIMIT"
        )
        failed_sell = _make_order(ticker="SPY", market="NYSE", side="SELL", quantity=1, reference_price=500.0)
        buy = _us_buy(ticker="VOO", quantity=1, limit_price=400.0)
        sells_fn = AsyncMock(
            return_value=[OrderResult.for_order(sell, "SUCCESS"), OrderResult.for_order(failed_sell, "FAILED")]
        )
        buys_fn = AsyncMock(return_value=[OrderResult.for_order(buy, "SUCCESS")])

        with (
            patch.object(execution_service, "load_kiwoom_credentials", return_value=("k", "s")),
            patch.object(execution_service, "kiwoom_get_access_token", AsyncMock(return_value="token")),
            patch.object(execution_service, "_execute_kiwoom_sells_with_clamp", sells_fn),
            patch.object(execution_service, "_execute_kiwoom_buys_with_cash_check", buys_fn),
        ):
            results = await execution_service._execute_kiwoom_account_orders(
                account, [sell, failed_sell, buy], account.user_id, account.id, mock_db, mock_cache, True
            )

        assert [r.ticker for r in results] == ["QQQ", "SPY", "VOO"]
        assert buys_fn.await_args.kwargs["pending_sell_usd"] == pytest.approx(500.0)
