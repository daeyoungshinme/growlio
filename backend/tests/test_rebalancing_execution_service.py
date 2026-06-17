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
        ticker=ticker, name=name, market=market,
        side=side, quantity=quantity, account_id=account_id,
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
        from app.services.rebalancing_execution_service import _load_account

        mock_db.scalar = AsyncMock(return_value=None)
        account_id = uuid.uuid4()
        user_id = uuid.uuid4()

        with pytest.raises(HTTPException) as exc:
            await _load_account(account_id, user_id, mock_db)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_raises_400_for_non_broker_account(self, mock_db, override_settings):
        from app.services.rebalancing_execution_service import _load_account

        account = _make_kis_account()
        account.asset_type = "BANK_ACCOUNT"
        mock_db.scalar = AsyncMock(return_value=account)

        with pytest.raises(HTTPException) as exc:
            await _load_account(account.id, account.user_id, mock_db)
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_raises_400_when_kis_account_no_missing(self, mock_db, override_settings):
        from app.services.rebalancing_execution_service import _load_account

        account = _make_kis_account()
        account.kis_account_no = None
        mock_db.scalar = AsyncMock(return_value=account)

        with pytest.raises(HTTPException) as exc:
            await _load_account(account.id, account.user_id, mock_db)
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_returns_account_when_valid(self, mock_db, override_settings):
        from app.services.rebalancing_execution_service import _load_account

        account = _make_kis_account()
        mock_db.scalar = AsyncMock(return_value=account)

        result = await _load_account(account.id, account.user_id, mock_db)
        assert result is account


# ── _execute_kiwoom_single_order 테스트 ────────────────────

class TestExecuteKiwoomSingleOrder:
    """_execute_kiwoom_single_order: 키움 단건 주문 실행."""

    @pytest.mark.asyncio
    async def test_skips_zero_quantity(self, override_settings):
        from app.services.rebalancing_execution_service import _execute_kiwoom_single_order

        order = _make_order(quantity=0)
        result = await _execute_kiwoom_single_order(order, "token", "12345", False, AsyncMock())

        assert result.status == "SKIPPED"

    @pytest.mark.asyncio
    async def test_skips_overseas_market(self, override_settings):
        from app.services.rebalancing_execution_service import _execute_kiwoom_single_order

        order = _make_order(ticker="AAPL", market="NASDAQ", quantity=5)
        result = await _execute_kiwoom_single_order(order, "token", "12345", False, AsyncMock())

        assert result.status == "SKIPPED"
        assert "국내주식" in result.error_msg

    @pytest.mark.asyncio
    async def test_returns_success_on_successful_order(self, override_settings):
        from app.services.rebalancing_execution_service import _execute_kiwoom_single_order

        order = _make_order(quantity=10)
        mock_place = AsyncMock(return_value={"order_no": "ORD001"})
        result = await _execute_kiwoom_single_order(order, "token", "12345", True, mock_place)

        assert result.status == "SUCCESS"
        assert result.order_no == "ORD001"

    @pytest.mark.asyncio
    async def test_returns_failed_on_exception(self, override_settings):
        from app.services.rebalancing_execution_service import _execute_kiwoom_single_order

        order = _make_order(quantity=10)
        mock_place = AsyncMock(side_effect=Exception("API 오류"))
        result = await _execute_kiwoom_single_order(order, "token", "12345", True, mock_place)

        assert result.status == "FAILED"
        assert result.error_msg is not None


# ── execute_rebalancing 테스트 ──────────────────────────────

class TestExecuteRebalancing:
    """execute_rebalancing: 주문 그룹화 및 SELL-BUY 순서 검증."""

    @pytest.mark.asyncio
    async def test_raises_400_when_no_orders(self, mock_db, mock_redis, override_settings):
        from app.services.rebalancing_execution_service import execute_rebalancing

        user_id = uuid.uuid4()
        with pytest.raises(HTTPException) as exc:
            await execute_rebalancing(user_id, None, [], mock_db, mock_redis)
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_sell_before_buy_execution_order(self, mock_db, mock_redis, override_settings):
        """SELL 주문이 BUY 주문보다 먼저 실행되어야 한다."""
        from app.services.rebalancing_execution_service import execute_rebalancing

        user_id = uuid.uuid4()
        account = _make_kis_account(user_id=user_id)
        acc_id = str(account.id)

        sell_order = _make_order(ticker="A", side="SELL", account_id=acc_id)
        buy_order = _make_order(ticker="B", side="BUY", account_id=acc_id)

        executed_tickers: list[str] = []

        async def mock_execute_single(order, app_key, app_secret, access_token, account_no, is_mock):
            executed_tickers.append(f"{order.side}:{order.ticker}")
            return OrderResult(
                ticker=order.ticker, name=order.name, market=order.market,
                side=order.side, quantity=order.quantity, status="SUCCESS",
            )

        mock_db.scalar = AsyncMock(return_value=account)
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()

        with (
            patch("app.services.rebalancing_execution_service.decrypt", return_value="decrypted"),
            patch(
                "app.services.rebalancing_execution_service.get_access_token",
                new_callable=AsyncMock,
                return_value="token",
            ),
            patch("app.services.rebalancing_execution_service._execute_single_order", side_effect=mock_execute_single),
        ):
            await execute_rebalancing(user_id, account.id, [buy_order, sell_order], mock_db, mock_redis)

        # SELL이 BUY보다 먼저 실행되어야 함
        assert executed_tickers.index("SELL:A") < executed_tickers.index("BUY:B")

    @pytest.mark.asyncio
    async def test_continues_after_individual_order_failure(self, mock_db, mock_redis, override_settings):
        """첫 주문 실패 시 나머지 주문은 계속 진행되어야 한다."""
        from app.services.rebalancing_execution_service import execute_rebalancing

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
                ticker=order.ticker, name=order.name, market=order.market,
                side=order.side, quantity=order.quantity, status=status,
                error_msg="API 오류" if status == "FAILED" else None,
            )

        mock_db.scalar = AsyncMock(return_value=account)
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()

        with (
            patch("app.services.rebalancing_execution_service.decrypt", return_value="decrypted"),
            patch(
                "app.services.rebalancing_execution_service.get_access_token",
                new_callable=AsyncMock,
                return_value="token",
            ),
            patch("app.services.rebalancing_execution_service._execute_single_order", side_effect=mock_execute_single),
        ):
            results = await execute_rebalancing(user_id, account.id, orders, mock_db, mock_redis)

        # 두 주문 모두 실행 시도됨
        assert call_count == 2
        assert results[0].fail_count == 1
        assert results[0].success_count == 1


class TestRebalancingSchemaValidators:
    """schemas/rebalancing.py 검증자 커버리지 (lines 81, 92-94)."""

    def test_execution_order_item_limit_with_no_price_raises(self):
        """order_type=LIMIT이고 limit_price 없으면 ValidationError (line 81)."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError, match="지정가 주문"):
            ExecutionOrderItem(
                ticker="005930", name="삼성전자", market="KOSPI",
                side="BUY", quantity=10, order_type="LIMIT", limit_price=None,
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
