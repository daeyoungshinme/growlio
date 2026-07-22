"""rebalancing_execution_service 단위 테스트.

실제 KIS/키움 API 호출 없이 주문 분류·단건 실행 로직을 검증한다.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.schemas.rebalancing import ExecutionOrderItem, OrderResult


def _make_order(
    ticker: str = "005930",
    name: str = "삼성전자",
    market: str = "KOSPI",
    side: str = "BUY",
    quantity: int = 10,
    account_id: str | None = None,
) -> ExecutionOrderItem:
    return ExecutionOrderItem(
        ticker=ticker,
        name=name,
        market=market,
        side=side,
        quantity=quantity,
        account_id=account_id,
    )


def _make_kis_account(
    account_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    is_mock: bool = True,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=account_id or uuid.uuid4(),
        user_id=user_id or uuid.uuid4(),
        name="KIS 테스트 계좌",
        asset_type="STOCK_KIS",
        data_source="KIS_API",
        is_active=True,
        is_mock_mode=is_mock,
        kis_account_no="12345678-01",
        kis_app_key=b"encrypted_key",
        kis_app_secret=b"encrypted_secret",
        kiwoom_account_no=None,
        kiwoom_app_key=None,
        kiwoom_app_secret=None,
    )


# ── _load_account 테스트 ────────────────────────────────────


class TestLoadAccount:
    """_load_account: DB에서 계좌 유효성 검증."""

    @pytest.mark.asyncio
    async def test_raises_404_when_account_not_found(self, mock_db, override_settings):
        from app.services.rebalancing.execution_service import _load_account

        mock_db.scalar = AsyncMock(return_value=None)
        account_id = uuid.uuid4()
        user_id = uuid.uuid4()

        with pytest.raises(HTTPException) as exc:
            await _load_account(account_id, user_id, mock_db)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_raises_400_for_non_broker_account(self, mock_db, override_settings):
        from app.services.rebalancing.execution_service import _load_account

        account = _make_kis_account()
        account.asset_type = "BANK_ACCOUNT"
        mock_db.scalar = AsyncMock(return_value=account)

        with pytest.raises(HTTPException) as exc:
            await _load_account(account.id, account.user_id, mock_db)
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_raises_400_when_kis_account_no_missing(self, mock_db, override_settings):
        from app.services.rebalancing.execution_service import _load_account

        account = _make_kis_account()
        account.kis_account_no = None
        mock_db.scalar = AsyncMock(return_value=account)

        with pytest.raises(HTTPException) as exc:
            await _load_account(account.id, account.user_id, mock_db)
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_returns_account_when_valid(self, mock_db, override_settings):
        from app.services.rebalancing.execution_service import _load_account

        account = _make_kis_account()
        mock_db.scalar = AsyncMock(return_value=account)

        result = await _load_account(account.id, account.user_id, mock_db)
        assert result is account


# ── _execute_kiwoom_single_order 테스트 ────────────────────


class TestExecuteKiwoomSingleOrder:
    """_execute_kiwoom_single_order: 키움 단건 주문 실행 (국내/해외)."""

    @pytest.mark.asyncio
    async def test_skips_zero_quantity(self, override_settings):
        from app.services.rebalancing import _kiwoom_order_executor
        from app.services.rebalancing.execution_service import _execute_kiwoom_single_order

        order = _make_order(quantity=0)
        with patch.object(_kiwoom_order_executor, "place_domestic_order", AsyncMock()):
            result = await _execute_kiwoom_single_order(order, "token", "12345", False)

        assert result.status == "SKIPPED"

    @pytest.mark.asyncio
    async def test_overseas_market_executes_via_place_overseas_order(self, override_settings):
        from app.services.rebalancing import _kiwoom_order_executor
        from app.services.rebalancing.execution_service import _execute_kiwoom_single_order

        order = _make_order(ticker="AAPL", market="NASDAQ", quantity=5)
        with patch.object(
            _kiwoom_order_executor, "place_overseas_order", AsyncMock(return_value={"order_no": "ORD002"})
        ) as overseas_fn:
            result = await _execute_kiwoom_single_order(order, "token", "12345", False)

        assert result.status == "SUCCESS"
        assert result.order_no == "ORD002"
        overseas_fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_success_on_successful_order(self, override_settings):
        from app.services.rebalancing import _kiwoom_order_executor
        from app.services.rebalancing.execution_service import _execute_kiwoom_single_order

        order = _make_order(quantity=10)
        with patch.object(
            _kiwoom_order_executor, "place_domestic_order", AsyncMock(return_value={"order_no": "ORD001"})
        ):
            result = await _execute_kiwoom_single_order(order, "token", "12345", True)

        assert result.status == "SUCCESS"
        assert result.order_no == "ORD001"

    @pytest.mark.asyncio
    async def test_returns_failed_on_exception(self, override_settings):
        from app.services.rebalancing import _kiwoom_order_executor
        from app.services.rebalancing.execution_service import _execute_kiwoom_single_order

        order = _make_order(quantity=10)
        with patch.object(_kiwoom_order_executor, "place_domestic_order", AsyncMock(side_effect=Exception("API 오류"))):
            result = await _execute_kiwoom_single_order(order, "token", "12345", True)

        assert result.status == "FAILED"
        assert result.error_msg is not None


# ── _execute_sells_with_clamp (KIS) 테스트 ──────────────────


class TestExecuteSellsWithClamp:
    """_execute_sells_with_clamp: 매도 주문을 실행 계좌의 실제 보유수량으로 clamp."""

    @pytest.mark.asyncio
    async def test_empty_sells_returns_empty(self, override_settings):
        from app.services.rebalancing._kis_order_executor import _execute_sells_with_clamp

        result = await _execute_sells_with_clamp([], "key", "secret", "token", "12345678-01", True)
        assert result == []

    @pytest.mark.asyncio
    async def test_clamps_domestic_sell_to_actual_holdings(self, override_settings):
        from app.services.rebalancing import _kis_order_executor

        order = _make_order(ticker="005930", market="KOSPI", side="SELL", quantity=10)
        mock_balance = AsyncMock(return_value={"positions": [{"ticker": "005930", "qty": 3}]})
        captured_quantity = None

        async def mock_execute_single(order, app_key, app_secret, access_token, account_no, is_mock):
            nonlocal captured_quantity
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
            patch.object(_kis_order_executor, "get_domestic_balance", mock_balance),
            patch.object(_kis_order_executor, "_execute_single_order", side_effect=mock_execute_single),
        ):
            results = await _kis_order_executor._execute_sells_with_clamp(
                [order], "key", "secret", "token", "12345678-01", True
            )

        assert captured_quantity == 3
        assert results[0].status == "SUCCESS"

    @pytest.mark.asyncio
    async def test_skips_sell_with_zero_holdings(self, override_settings):
        from app.services.rebalancing import _kis_order_executor

        order = _make_order(ticker="005930", market="KOSPI", side="SELL", quantity=10)
        mock_balance = AsyncMock(return_value={"positions": []})

        with patch.object(_kis_order_executor, "get_domestic_balance", mock_balance):
            results = await _kis_order_executor._execute_sells_with_clamp(
                [order], "key", "secret", "token", "12345678-01", True
            )

        assert len(results) == 1
        assert results[0].status == "SKIPPED"

    @pytest.mark.asyncio
    async def test_balance_fetch_failure_falls_back_to_unclamped_execution(self, override_settings):
        from app.services.rebalancing import _kis_order_executor

        order = _make_order(ticker="005930", market="KOSPI", side="SELL", quantity=10)
        mock_balance = AsyncMock(side_effect=Exception("API 오류"))

        async def mock_execute_single(order, app_key, app_secret, access_token, account_no, is_mock):
            return OrderResult(
                ticker=order.ticker,
                name=order.name,
                market=order.market,
                side=order.side,
                quantity=order.quantity,
                status="SUCCESS",
            )

        with (
            patch.object(_kis_order_executor, "get_domestic_balance", mock_balance),
            patch.object(_kis_order_executor, "_execute_single_order", side_effect=mock_execute_single),
        ):
            results = await _kis_order_executor._execute_sells_with_clamp(
                [order], "key", "secret", "token", "12345678-01", True
            )

        assert results[0].status == "SUCCESS"
        assert results[0].quantity == 10  # clamp 실패 시 원래 수량으로 진행(기존 동작 유지)

    @pytest.mark.asyncio
    async def test_clamps_overseas_sell_using_ticker_and_market(self, override_settings):
        from app.services.rebalancing import _kis_order_executor

        order = _make_order(ticker="AAPL", market="NASDAQ", side="SELL", quantity=10)
        mock_balance = AsyncMock(return_value={"positions": [{"ticker": "AAPL", "market": "NASDAQ", "qty": 2}]})
        captured_quantity = None

        async def mock_execute_single(order, app_key, app_secret, access_token, account_no, is_mock):
            nonlocal captured_quantity
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
            patch.object(_kis_order_executor, "get_overseas_balance", mock_balance),
            patch.object(_kis_order_executor, "_execute_single_order", side_effect=mock_execute_single),
        ):
            results = await _kis_order_executor._execute_sells_with_clamp(
                [order], "key", "secret", "token", "12345678-01", True
            )

        assert captured_quantity == 2
        assert results[0].status == "SUCCESS"


# ── _execute_kiwoom_sells_with_clamp 테스트 ──────────────────


class TestExecuteKiwoomSellsWithClamp:
    """_execute_kiwoom_sells_with_clamp: 키움 매도 주문을 실행 계좌의 실제 보유수량으로 clamp."""

    @pytest.mark.asyncio
    async def test_empty_sells_returns_empty(self, override_settings):
        from app.services.rebalancing._kiwoom_order_executor import _execute_kiwoom_sells_with_clamp

        result = await _execute_kiwoom_sells_with_clamp([], "token", "12345", True)
        assert result == []

    @pytest.mark.asyncio
    async def test_clamps_sell_to_actual_holdings(self, override_settings):
        from app.services.rebalancing import _kiwoom_order_executor

        order = _make_order(ticker="005930", side="SELL", quantity=10)
        mock_balance = AsyncMock(return_value={"positions": [{"ticker": "005930", "qty": 4}]})
        mock_place = AsyncMock(return_value={"order_no": "ORD001"})

        with (
            patch.object(_kiwoom_order_executor, "kiwoom_get_domestic_balance", mock_balance),
            patch.object(_kiwoom_order_executor, "place_domestic_order", mock_place),
        ):
            results = await _kiwoom_order_executor._execute_kiwoom_sells_with_clamp([order], "token", "12345", True)

        assert results[0].status == "SUCCESS"
        _, kwargs = mock_place.call_args
        assert kwargs["quantity"] == 4

    @pytest.mark.asyncio
    async def test_skips_sell_with_zero_holdings(self, override_settings):
        from app.services.rebalancing import _kiwoom_order_executor

        order = _make_order(ticker="005930", side="SELL", quantity=10)
        mock_balance = AsyncMock(return_value={"positions": []})

        with (
            patch.object(_kiwoom_order_executor, "kiwoom_get_domestic_balance", mock_balance),
            patch.object(_kiwoom_order_executor, "place_domestic_order", AsyncMock()),
        ):
            results = await _kiwoom_order_executor._execute_kiwoom_sells_with_clamp([order], "token", "12345", True)

        assert len(results) == 1
        assert results[0].status == "SKIPPED"


# ── execute_rebalancing 테스트 ──────────────────────────────


class TestExecuteRebalancing:
    """execute_rebalancing: 주문 그룹화 및 SELL-BUY 순서 검증."""

    @pytest.mark.asyncio
    async def test_raises_400_when_no_orders(self, mock_db, mock_cache, override_settings):
        from app.services.rebalancing.execution_service import execute_rebalancing

        user_id = uuid.uuid4()
        with pytest.raises(HTTPException) as exc:
            await execute_rebalancing(user_id, None, [], mock_db, mock_cache)
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_sell_before_buy_execution_order(self, mock_db, mock_cache, override_settings):
        """SELL 주문이 BUY 주문보다 먼저 실행되어야 한다."""
        from app.services.rebalancing.execution_service import execute_rebalancing

        user_id = uuid.uuid4()
        account = _make_kis_account(user_id=user_id)
        acc_id = str(account.id)

        sell_order = _make_order(ticker="A", side="SELL", account_id=acc_id)
        buy_order = _make_order(ticker="B", side="BUY", account_id=acc_id)

        executed_tickers: list[str] = []

        async def mock_execute_single(order, app_key, app_secret, access_token, account_no, is_mock):
            executed_tickers.append(f"{order.side}:{order.ticker}")
            return OrderResult(
                ticker=order.ticker,
                name=order.name,
                market=order.market,
                side=order.side,
                quantity=order.quantity,
                status="SUCCESS",
            )

        async def mock_execute_sells_with_clamp(sells, app_key, app_secret, access_token, account_no, is_mock):
            return [
                await mock_execute_single(order, app_key, app_secret, access_token, account_no, is_mock)
                for order in sells
            ]

        mock_db.scalar = AsyncMock(return_value=account)
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()

        with (
            patch(
                "app.services.rebalancing.execution_service.decrypt_kis_credentials",
                return_value=("decrypted", "decrypted"),
            ),
            patch(
                "app.services.rebalancing.execution_service.get_access_token",
                new_callable=AsyncMock,
                return_value="token",
            ),
            patch("app.services.rebalancing.execution_service._execute_single_order", side_effect=mock_execute_single),
            patch(
                "app.services.rebalancing.execution_service._execute_sells_with_clamp",
                side_effect=mock_execute_sells_with_clamp,
            ),
        ):
            await execute_rebalancing(user_id, account.id, [buy_order, sell_order], mock_db, mock_cache)

        # SELL이 BUY보다 먼저 실행되어야 함
        assert executed_tickers.index("SELL:A") < executed_tickers.index("BUY:B")

    @pytest.mark.asyncio
    async def test_continues_after_individual_order_failure(self, mock_db, mock_cache, override_settings):
        """첫 주문 실패 시 나머지 주문은 계속 진행되어야 한다."""
        from app.services.rebalancing.execution_service import execute_rebalancing

        user_id = uuid.uuid4()
        account = _make_kis_account(user_id=user_id)
        acc_id = str(account.id)

        orders = [
            _make_order(ticker="A", side="BUY", quantity=10, account_id=acc_id),
            _make_order(ticker="B", side="BUY", quantity=5, account_id=acc_id),
        ]

        call_count = 0

        async def mock_execute_single(order, app_key, app_secret, access_token, account_no, is_mock):
            nonlocal call_count
            call_count += 1
            # _execute_single_order는 내부에서 예외를 잡아 FAILED를 반환함
            status = "FAILED" if order.ticker == "A" else "SUCCESS"
            return OrderResult(
                ticker=order.ticker,
                name=order.name,
                market=order.market,
                side=order.side,
                quantity=order.quantity,
                status=status,
                error_msg="API 오류" if status == "FAILED" else None,
            )

        mock_db.scalar = AsyncMock(return_value=account)
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()

        with (
            patch(
                "app.services.rebalancing.execution_service.decrypt_kis_credentials",
                return_value=("decrypted", "decrypted"),
            ),
            patch(
                "app.services.rebalancing.execution_service.get_access_token",
                new_callable=AsyncMock,
                return_value="token",
            ),
            patch("app.services.rebalancing.execution_service._execute_single_order", side_effect=mock_execute_single),
        ):
            results, _execution_id = await execute_rebalancing(user_id, account.id, orders, mock_db, mock_cache)

        # 두 주문 모두 실행 시도됨
        assert call_count == 2
        assert results[0].fail_count == 1
        assert results[0].success_count == 1

    @pytest.mark.asyncio
    async def test_one_account_group_failure_does_not_lose_other_group_results(
        self, mock_db, mock_cache, override_settings
    ):
        """한 계좌 그룹 처리 중 예외가 발생해도 다른 계좌 그룹의 정상 결과는 보존돼야 한다."""
        from app.services.rebalancing.execution_service import execute_rebalancing

        user_id = uuid.uuid4()
        valid_account = _make_kis_account(user_id=user_id)
        missing_account_id = uuid.uuid4()

        valid_order = _make_order(ticker="A", side="BUY", account_id=str(valid_account.id))
        broken_order = _make_order(ticker="B", side="BUY", account_id=str(missing_account_id))

        async def mock_execute_single(order, app_key, app_secret, access_token, account_no, is_mock):
            return OrderResult(
                ticker=order.ticker,
                name=order.name,
                market=order.market,
                side=order.side,
                quantity=order.quantity,
                status="SUCCESS",
            )

        mock_db.scalar = AsyncMock(side_effect=[valid_account, None])
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()

        with (
            patch(
                "app.services.rebalancing.execution_service.decrypt_kis_credentials",
                return_value=("decrypted", "decrypted"),
            ),
            patch(
                "app.services.rebalancing.execution_service.get_access_token",
                new_callable=AsyncMock,
                return_value="token",
            ),
            patch("app.services.rebalancing.execution_service._execute_single_order", side_effect=mock_execute_single),
        ):
            results, _execution_id = await execute_rebalancing(
                user_id, None, [valid_order, broken_order], mock_db, mock_cache
            )

        assert len(results) == 2
        valid_result = next(r for r in results if r.account_id == str(valid_account.id))
        broken_result = next(r for r in results if r.account_id == str(missing_account_id))

        assert valid_result.success_count == 1
        assert valid_result.fail_count == 0
        assert broken_result.fail_count == 1
        assert broken_result.orders[0].status == "FAILED"
        assert "찾을 수 없습니다" in (broken_result.orders[0].error_msg or "")


class TestRebalancingSchemaValidators:
    """schemas/rebalancing.py 검증자 커버리지 (lines 81, 92-94)."""

    def test_execution_order_item_limit_with_no_price_raises(self):
        """order_type=LIMIT이고 limit_price 없으면 ValidationError (line 81)."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="지정가 주문"):
            ExecutionOrderItem(
                ticker="005930",
                name="삼성전자",
                market="KOSPI",
                side="BUY",
                quantity=10,
                order_type="LIMIT",
                limit_price=None,
            )

    def test_execution_request_empty_orders_raises(self):
        """orders 빈 리스트로 ExecutionRequest 생성 시 ValidationError (lines 92-93)."""
        from pydantic import ValidationError

        from app.schemas.rebalancing import ExecutionRequest

        with pytest.raises(ValidationError, match="최소 1개"):
            ExecutionRequest(orders=[])

    def test_execution_request_valid_orders_accepted(self):
        """유효한 orders로 ExecutionRequest 생성 성공 (line 94)."""
        from app.schemas.rebalancing import ExecutionRequest

        order = _make_order()
        req = ExecutionRequest(orders=[order])
        assert len(req.orders) == 1
