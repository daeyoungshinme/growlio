"""리밸런싱 실행 주문 미체결 취소 (plans/89) — order_cancel_service + 이력 저장·라우터 연결."""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.exceptions import BrokerOrderRejectedError
from app.kis.client import KisApiError
from app.models.asset import RebalancingExecutionResult
from app.schemas.rebalancing import ExecutionResult, OrderResult
from app.services.rebalancing.order_cancel_service import (
    CANCEL_FAILED,
    CANCELED,
    cancel_block_reason,
    cancel_execution_order,
)

SVC = "app.services.rebalancing.order_cancel_service"
EXEC_SVC = "app.services.rebalancing.execution_service"


def _row(**kw) -> RebalancingExecutionResult:
    defaults = {
        "id": uuid.uuid4(),
        "execution_id": uuid.uuid4(),
        "account_id": str(uuid.uuid4()),
        "account_name": "계좌",
        "is_mock": True,
        "action": "BUY",
        "ticker": "069500",
        "name": "KODEX 200",
        "market": "KOSPI",
        "quantity": 3,
        "status": "SUCCESS",
        "order_no": "0000123",
        "order_org_no": "91252",
        "order_type": "LIMIT",
        "cancel_status": None,
        "cancel_message": None,
        "canceled_at": None,
    }
    defaults.update(kw)
    return RebalancingExecutionResult(**defaults)


def _account(row: RebalancingExecutionResult, asset_type: str = "STOCK_KIS"):
    return SimpleNamespace(
        id=uuid.UUID(row.account_id),
        asset_type=asset_type,
        kis_account_no="12345678-01" if asset_type == "STOCK_KIS" else None,
        kiwoom_account_no="5555" if asset_type == "STOCK_KIWOOM" else None,
    )


def _execution(executed_at: datetime | None = None, portfolio_id=None):
    return SimpleNamespace(
        id=uuid.uuid4(), executed_at=executed_at or datetime.now(UTC), portfolio_id=portfolio_id, user_id=uuid.uuid4()
    )


def _wire_db(mock_db, row, execution, account):
    result = MagicMock()
    result.first.return_value = (row, execution) if row is not None else None
    mock_db.execute = AsyncMock(return_value=result)
    mock_db.scalar = AsyncMock(return_value=account)
    mock_db.rollback = AsyncMock()


class TestCancelBlockReason:
    def test_cancelable_kis_domestic_today(self):
        assert cancel_block_reason(_row(), datetime.now(UTC), "STOCK_KIS") is None

    @pytest.mark.parametrize(
        "kw",
        [
            {"status": "FAILED"},
            {"status": "SKIPPED", "action": "SKIPPED"},
            {"order_no": None},
        ],
    )
    def test_not_placed_orders_blocked(self, kw):
        assert cancel_block_reason(_row(**kw), datetime.now(UTC), "STOCK_KIS") == "접수된 주문만 취소할 수 있습니다."

    def test_already_canceled_blocked(self):
        assert cancel_block_reason(_row(cancel_status=CANCELED), datetime.now(UTC), "STOCK_KIS") is not None

    def test_failed_cancel_can_retry(self):
        assert cancel_block_reason(_row(cancel_status=CANCEL_FAILED), datetime.now(UTC), "STOCK_KIS") is None

    def test_toss_or_deleted_account_blocked(self):
        assert cancel_block_reason(_row(), datetime.now(UTC), "STOCK_TOSS") is not None
        assert cancel_block_reason(_row(), datetime.now(UTC), None) is not None

    def test_domestic_previous_kst_day_blocked(self):
        # KST 10-29 00:30 기준, 10-28 23:00 KST 주문은 전날 주문
        now = datetime(2026, 10, 28, 15, 30, tzinfo=UTC)
        executed = datetime(2026, 10, 28, 14, 0, tzinfo=UTC)
        assert cancel_block_reason(_row(), executed, "STOCK_KIS", now=now) == "당일 주문만 취소할 수 있습니다."

    def test_overseas_crosses_kst_midnight_within_window(self):
        now = datetime(2026, 10, 28, 17, 0, tzinfo=UTC)  # KST 02:00
        executed = datetime(2026, 10, 28, 14, 0, tzinfo=UTC)  # KST 전날 23:00
        row = _row(market="NASDAQ", ticker="QQQ", order_org_no=None)
        assert cancel_block_reason(row, executed, "STOCK_KIS", now=now) is None

    def test_overseas_after_window_blocked(self):
        now = datetime.now(UTC)
        row = _row(market="NYSE", ticker="SPY")
        assert cancel_block_reason(row, now - timedelta(hours=25), "STOCK_KIS", now=now) is not None

    def test_kis_domestic_without_org_no_blocked(self):
        reason = cancel_block_reason(_row(order_org_no=None), datetime.now(UTC), "STOCK_KIS")
        assert reason is not None
        assert "증권사 앱" in reason

    def test_kiwoom_domestic_needs_no_org_no(self):
        assert cancel_block_reason(_row(order_org_no=None), datetime.now(UTC), "STOCK_KIWOOM") is None


class TestCancelExecutionOrder:
    @pytest.fixture(autouse=True)
    def _creds(self):
        with (
            patch(f"{EXEC_SVC}.decrypt_kis_credentials", return_value=("k", "s")),
            patch(f"{EXEC_SVC}.decrypt_kiwoom_credentials", return_value=("k", "s")),
            patch(f"{SVC}.get_access_token", new=AsyncMock(return_value="tok")),
            patch(f"{SVC}.kiwoom_get_access_token", new=AsyncMock(return_value="ktok")),
        ):
            yield

    @pytest.mark.asyncio
    async def test_kis_domestic_success(self, mock_db, mock_cache):
        row = _row()
        execution = _execution(portfolio_id=uuid.uuid4())
        _wire_db(mock_db, row, execution, _account(row))
        cancel = AsyncMock(return_value={"order_no": "999"})
        with (
            patch(f"{SVC}.kis_order.cancel_domestic_order", new=cancel),
            patch(f"{SVC}.invalidate_rebalancing_analysis_cache", new=AsyncMock()) as inv,
        ):
            out = await cancel_execution_order(uuid.uuid4(), row.id, mock_db, mock_cache)

        assert out.cancel_status == CANCELED
        assert out.canceled_at is not None
        kwargs = cancel.await_args.kwargs
        assert kwargs["order_org_no"] == "91252"
        assert kwargs["order_no"] == "0000123"
        assert kwargs["is_mock"] is True
        mock_db.commit.assert_awaited_once()
        inv.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_kis_overseas_uses_saved_market_and_quantity(self, mock_db, mock_cache):
        row = _row(market="AMEX", ticker="SPY", quantity=2, order_org_no=None)
        _wire_db(mock_db, row, _execution(), _account(row))
        cancel = AsyncMock(return_value={})
        with patch(f"{SVC}.kis_order.cancel_overseas_order", new=cancel):
            out = await cancel_execution_order(uuid.uuid4(), row.id, mock_db, mock_cache)

        assert out.cancel_status == CANCELED
        kwargs = cancel.await_args.kwargs
        assert (kwargs["market"], kwargs["ticker"], kwargs["quantity"]) == ("AMEX", "SPY", 2)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("market", "fn"), [("KOSPI", "cancel_domestic_order"), ("NASDAQ", "cancel_overseas_order")]
    )
    async def test_kiwoom_routes_by_market(self, mock_db, mock_cache, market, fn):
        row = _row(market=market, order_org_no=None)
        _wire_db(mock_db, row, _execution(), _account(row, "STOCK_KIWOOM"))
        cancel = AsyncMock(return_value={})
        with patch(f"{SVC}.kiwoom_order.{fn}", new=cancel):
            out = await cancel_execution_order(uuid.uuid4(), row.id, mock_db, mock_cache)

        assert out.cancel_status == CANCELED
        assert cancel.await_args.args == ("ktok", "5555")

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "error",
        [
            BrokerOrderRejectedError("취소가능수량이 없습니다"),
            KisApiError("7", "취소가능수량이 없습니다"),
        ],
    )
    async def test_broker_rejection_recorded_as_cancel_failed(self, mock_db, mock_cache, error):
        row = _row()
        _wire_db(mock_db, row, _execution(), _account(row))
        reject = AsyncMock(side_effect=error)
        with patch(f"{SVC}.kis_order.cancel_domestic_order", new=reject):
            out = await cancel_execution_order(uuid.uuid4(), row.id, mock_db, mock_cache)

        assert out.cancel_status == CANCEL_FAILED
        assert "취소가능수량이 없습니다" in out.cancel_message
        assert out.canceled_at is None
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_network_error_is_502_and_not_recorded(self, mock_db, mock_cache):
        row = _row()
        _wire_db(mock_db, row, _execution(), _account(row))
        with (
            patch(f"{SVC}.kis_order.cancel_domestic_order", new=AsyncMock(side_effect=TimeoutError("boom"))),
            pytest.raises(HTTPException) as exc,
        ):
            await cancel_execution_order(uuid.uuid4(), row.id, mock_db, mock_cache)

        assert exc.value.status_code == 502
        assert row.cancel_status is None
        mock_db.commit.assert_not_awaited()
        mock_db.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_other_users_order_is_404(self, mock_db, mock_cache):
        _wire_db(mock_db, None, None, None)
        with pytest.raises(HTTPException) as exc:
            await cancel_execution_order(uuid.uuid4(), uuid.uuid4(), mock_db, mock_cache)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "kw", [{"cancel_status": CANCELED}, {"status": "FAILED"}, {"order_org_no": None}, {"account_id": "default"}]
    )
    async def test_blocked_orders_are_400_without_broker_call(self, mock_db, mock_cache, kw):
        row = _row(**kw)
        account = _account(row) if kw.get("account_id") != "default" else None
        _wire_db(mock_db, row, _execution(), account)
        cancel = AsyncMock()
        with patch(f"{SVC}.kis_order.cancel_domestic_order", new=cancel), pytest.raises(HTTPException) as exc:
            await cancel_execution_order(uuid.uuid4(), row.id, mock_db, mock_cache)

        assert exc.value.status_code == 400
        cancel.assert_not_awaited()


class TestSaveExecutionHistory:
    @pytest.mark.asyncio
    async def test_saves_org_no_and_sets_result_ids(self, mock_db):
        from app.services.rebalancing.execution_service import _save_execution_history

        placed = OrderResult(
            ticker="069500",
            name="KODEX 200",
            market="KOSPI",
            side="BUY",
            quantity=1,
            status="SUCCESS",
            order_no="1",
            order_org_no="91252",
        )
        failed = OrderResult(ticker="X", name="X", market="KOSPI", side="BUY", quantity=1, status="FAILED")
        results = [
            ExecutionResult(
                account_id=str(uuid.uuid4()),
                account_name="a",
                is_mock=True,
                orders=[placed, failed],
                success_count=1,
                fail_count=1,
                executed_at="",
            )
        ]

        await _save_execution_history(mock_db, uuid.uuid4(), None, "MANUAL", "FULL", results, 1, 1, 0)

        rows = [c.args[0] for c in mock_db.add.call_args_list if isinstance(c.args[0], RebalancingExecutionResult)]
        assert rows[0].order_org_no == "91252"
        assert placed.result_id == rows[0].id
        assert placed.cancelable is True
        assert failed.result_id == rows[1].id
        assert failed.cancelable is False
        # 조직번호는 응답 JSON에 내보내지 않는다
        assert "order_org_no" not in placed.model_dump()


class TestRouter:
    @pytest.mark.asyncio
    async def test_cancel_endpoint_messages(self, mock_db, mock_request):
        from app.api.v1.rebalancing_execution import cancel_rebalancing_order

        user = SimpleNamespace(id=uuid.uuid4())
        for status, expected in [(CANCELED, "취소되었습니다"), (CANCEL_FAILED, "취소가능수량이 없습니다")]:
            row = _row(
                cancel_status=status, cancel_message="취소가능수량이 없습니다" if status == CANCEL_FAILED else None
            )
            with patch("app.api.v1.rebalancing_execution.cancel_execution_order", new=AsyncMock(return_value=row)):
                resp = await cancel_rebalancing_order(
                    request=mock_request, result_id=row.id, current_user=user, db=mock_db, cache=None
                )
            assert resp.cancel_status == status
            assert expected in resp.message

    @pytest.mark.asyncio
    async def test_history_detail_exposes_cancel_fields(self, mock_db, mock_request):
        from app.api.v1.rebalancing_execution import get_rebalancing_execution_detail

        user = SimpleNamespace(id=uuid.uuid4())
        cancelable = _row()
        legacy = _row(account_id=cancelable.account_id, order_org_no=None)
        execution = SimpleNamespace(
            id=uuid.uuid4(),
            portfolio_id=None,
            triggered_by="MANUAL",
            strategy="FULL",
            total_success=2,
            total_fail=0,
            total_skipped=0,
            executed_at=datetime.now(UTC),
            result_items=[cancelable, legacy],
        )
        detail_result = MagicMock()
        detail_result.scalar_one_or_none.return_value = execution
        types_result = MagicMock()
        types_result.all.return_value = [(uuid.UUID(cancelable.account_id), "STOCK_KIS")]
        mock_db.execute = AsyncMock(side_effect=[detail_result, types_result])

        detail = await get_rebalancing_execution_detail(
            request=mock_request, execution_id=execution.id, current_user=user, db=mock_db
        )

        orders = detail.results[0].orders
        assert [o.result_id for o in orders] == [cancelable.id, legacy.id]
        assert [o.cancelable for o in orders] == [True, False]
