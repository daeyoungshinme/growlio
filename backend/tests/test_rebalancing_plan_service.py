"""rebalancing_plan_service.py 단위 테스트 — 플랜 생성/취소/승인/만료 전 경로."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.services.rebalancing import plan_service as svc


def _make_alert(**kwargs) -> SimpleNamespace:
    defaults = {
        "id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "account_id": uuid.uuid4(),
        "strategy": "FULL",
        "order_type": "MARKET",
        "buy_wait_minutes": 10,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _make_portfolio(**kwargs) -> SimpleNamespace:
    defaults = {"id": uuid.uuid4(), "name": "포트폴리오"}
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _make_drift_item(ticker="005930", diff_krw=-100000.0, shares_to_trade=-5.0, **kwargs):
    defaults = {
        "ticker": ticker,
        "name": "삼성전자",
        "market": "KOSPI",
        "diff_krw": diff_krw,
        "shares_to_trade": shares_to_trade,
        "current_price_krw": 70000.0,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _make_ticker_account(account_id, quantity, asset_type="STOCK_KIS"):
    from app.schemas.rebalancing import TickerAccountInfo

    return TickerAccountInfo(
        account_id=str(account_id),
        account_name="계좌",
        asset_type=asset_type,
        quantity=quantity,
        value_krw=quantity * 70000.0,
    )


# ── generate_pending_plan_for_alert ──────────────────────────


class TestGeneratePendingPlanForAlert:
    @pytest.mark.asyncio
    async def test_buy_only_strategy_creates_no_sell_leg(self, mock_db):
        alert = _make_alert(strategy="BUY_ONLY")
        portfolio = _make_portfolio()
        drifting = [
            _make_drift_item(ticker="005930", diff_krw=100000.0, shares_to_trade=5.0),
            _make_drift_item(ticker="000660", diff_krw=-50000.0, shares_to_trade=-2.0),
        ]

        with (
            patch("app.core.redis_client.get_redis", new=AsyncMock(return_value=MagicMock())),
            patch("app.services.price_service.fetch_prices_batch", new=AsyncMock(return_value={})),
        ):
            plan, buy_token, sell_token = await svc.generate_pending_plan_for_alert(
                alert, portfolio, drifting, mock_db, {}, "GREEN"
            )

        assert plan is not None
        assert buy_token is not None
        assert sell_token is None
        assert len(plan.legs) == 1
        assert plan.legs[0].side == "BUY"
        assert plan.legs[0].items[0].quantity == 5

    @pytest.mark.asyncio
    async def test_explicitly_registers_leg_and_items_with_session(self, mock_db):
        """back_populates만으로는 실 DB에 저장 안 되는 사례가 확인돼 db.add()로 명시 등록한다 —
        회귀 시 leg/item이 조용히 저장 누락되는 걸 막는 핵심 테스트."""
        alert = _make_alert(strategy="BUY_ONLY")
        portfolio = _make_portfolio()
        drifting = [_make_drift_item(ticker="005930", diff_krw=100000.0, shares_to_trade=5.0)]

        with (
            patch("app.core.redis_client.get_redis", new=AsyncMock(return_value=MagicMock())),
            patch("app.services.price_service.fetch_prices_batch", new=AsyncMock(return_value={})),
        ):
            plan, _, _ = await svc.generate_pending_plan_for_alert(alert, portfolio, drifting, mock_db, {}, "GREEN")

        buy_leg = plan.legs[0]
        mock_db.add.assert_any_call(buy_leg)
        mock_db.add_all.assert_any_call(buy_leg.items)

    @pytest.mark.asyncio
    async def test_full_strategy_creates_both_legs_with_correct_deadlines(self, mock_db):
        from app.utils.market_hours import korean_market_close_datetime

        alert = _make_alert(strategy="FULL", buy_wait_minutes=15)
        portfolio = _make_portfolio()
        holder_account = uuid.uuid4()
        ticker_account_map = {"000660": [_make_ticker_account(holder_account, quantity=10)]}
        drifting = [
            _make_drift_item(ticker="005930", diff_krw=100000.0, shares_to_trade=5.0),
            _make_drift_item(ticker="000660", diff_krw=-50000.0, shares_to_trade=-2.0),
        ]

        before = datetime.now(tz=UTC)
        with (
            patch("app.core.redis_client.get_redis", new=AsyncMock(return_value=MagicMock())),
            patch("app.services.price_service.fetch_prices_batch", new=AsyncMock(return_value={})),
        ):
            plan, buy_token, sell_token = await svc.generate_pending_plan_for_alert(
                alert, portfolio, drifting, mock_db, ticker_account_map, "GREEN"
            )

        assert plan is not None
        assert buy_token is not None
        assert sell_token is not None
        sides = {leg.side for leg in plan.legs}
        assert sides == {"BUY", "SELL"}

        buy_leg = next(leg for leg in plan.legs if leg.side == "BUY")
        sell_leg = next(leg for leg in plan.legs if leg.side == "SELL")
        assert buy_leg.deadline_at >= before + timedelta(minutes=15)

        expected_close = korean_market_close_datetime().astimezone(UTC)
        assert abs((sell_leg.deadline_at - expected_close).total_seconds()) < 5

    @pytest.mark.asyncio
    async def test_no_orders_returns_none_tuple(self, mock_db):
        alert = _make_alert()
        portfolio = _make_portfolio()
        drifting = [_make_drift_item(shares_to_trade=None)]

        with (
            patch("app.core.redis_client.get_redis", new=AsyncMock(return_value=MagicMock())),
            patch("app.services.price_service.fetch_prices_batch", new=AsyncMock(return_value={})),
        ):
            result = await svc.generate_pending_plan_for_alert(alert, portfolio, drifting, mock_db, {}, "GREEN")

        assert result == (None, None, None)

    @pytest.mark.asyncio
    async def test_sell_with_no_holding_account_produces_no_sell_leg(self, mock_db):
        """보유 계좌 정보가 없으면(ticker_account_map에 없음) 매도 leg 자체가 생성되지 않는다."""
        alert = _make_alert(strategy="FULL")
        portfolio = _make_portfolio()
        drifting = [_make_drift_item(ticker="005930", diff_krw=-100000.0, shares_to_trade=-5.0)]

        with (
            patch("app.core.redis_client.get_redis", new=AsyncMock(return_value=MagicMock())),
            patch("app.services.price_service.fetch_prices_batch", new=AsyncMock(return_value={})),
        ):
            plan, buy_token, sell_token = await svc.generate_pending_plan_for_alert(
                alert, portfolio, drifting, mock_db, {}, "GREEN"
            )

        assert plan is None
        assert buy_token is None
        assert sell_token is None

    @pytest.mark.asyncio
    async def test_explicitly_refreshes_legs_after_commit(self, mock_db):
        """buy_items/persisted_buy_items 진단 로그를 위해 attribute_names=["legs"]로 명시 refresh해야 한다."""
        alert = _make_alert(strategy="BUY_ONLY")
        portfolio = _make_portfolio()
        drifting = [_make_drift_item(ticker="005930", diff_krw=100000.0, shares_to_trade=5.0)]

        with (
            patch("app.core.redis_client.get_redis", new=AsyncMock(return_value=MagicMock())),
            patch("app.services.price_service.fetch_prices_batch", new=AsyncMock(return_value={})),
        ):
            plan, _, _ = await svc.generate_pending_plan_for_alert(alert, portfolio, drifting, mock_db, {}, "GREEN")

        mock_db.refresh.assert_awaited_once_with(plan, attribute_names=["legs"])


# ── notify_plan_generated ────────────────────────────────────


class TestNotifyPlanGenerated:
    @pytest.mark.asyncio
    async def test_sell_only_plan_still_sends_email(self, mock_db):
        """buy_token이 없어도(매도 전용 플랜) sell_token만 있으면 이메일을 발송해야 한다 —
        buy_token 유무로만 게이트하면 매도전용 드리프트에서 이메일이 조용히 스킵된다."""
        alert = _make_alert()
        portfolio = _make_portfolio()
        sell_leg = SimpleNamespace(side="SELL", items=[SimpleNamespace(ticker="005930")], deadline_at=datetime.now(UTC))
        plan = SimpleNamespace(id=uuid.uuid4(), account_id=None, legs=[sell_leg])

        mock_email = AsyncMock(return_value=True)
        with (
            patch("app.services.email_service.send_rebalancing_plan_pending_email", new=mock_email),
            patch("app.services.push_service.send_push_to_user", new=AsyncMock(return_value=True)),
            patch("app.services.rebalancing.plan_service.save_alert_history", new=AsyncMock()),
        ):
            email_sent = await svc.notify_plan_generated(
                plan, alert, portfolio, None, "sell-token", "user@test.com", None, "GREEN", mock_db
            )

        assert email_sent is True
        mock_email.assert_awaited_once()
        _, kwargs = mock_email.call_args
        assert kwargs["buy_cancel_token"] is None
        assert kwargs["sell_action_token"] == "sell-token"

    @pytest.mark.asyncio
    async def test_no_tokens_skips_email(self, mock_db):
        alert = _make_alert()
        portfolio = _make_portfolio()
        plan = SimpleNamespace(id=uuid.uuid4(), account_id=None, legs=[])

        mock_email = AsyncMock()
        with (
            patch("app.services.email_service.send_rebalancing_plan_pending_email", new=mock_email),
            patch("app.services.push_service.send_push_to_user", new=AsyncMock(return_value=True)),
            patch("app.services.rebalancing.plan_service.save_alert_history", new=AsyncMock()),
        ):
            email_sent = await svc.notify_plan_generated(
                plan, alert, portfolio, None, None, "user@test.com", None, "GREEN", mock_db
            )

        assert email_sent is False
        mock_email.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_email_address_skips_send(self, mock_db):
        alert = _make_alert()
        portfolio = _make_portfolio()
        buy_leg = SimpleNamespace(side="BUY", items=[SimpleNamespace(ticker="005930")], deadline_at=datetime.now(UTC))
        plan = SimpleNamespace(id=uuid.uuid4(), account_id=None, legs=[buy_leg])

        mock_email = AsyncMock()
        with (
            patch("app.services.email_service.send_rebalancing_plan_pending_email", new=mock_email),
            patch("app.services.push_service.send_push_to_user", new=AsyncMock(return_value=True)),
            patch("app.services.rebalancing.plan_service.save_alert_history", new=AsyncMock()),
        ):
            email_sent = await svc.notify_plan_generated(
                plan, alert, portfolio, "buy-token", None, None, None, "GREEN", mock_db
            )

        assert email_sent is False
        mock_email.assert_not_awaited()


# ── get_plan_leg_by_token ─────────────────────────────────────


class TestGetPlanLegByToken:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_match(self, mock_db):
        mock_db.scalar = AsyncMock(return_value=None)
        result = await svc.get_plan_leg_by_token("raw-token", None, mock_db)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_side_mismatch(self, mock_db):
        leg = SimpleNamespace(side="BUY")
        mock_db.scalar = AsyncMock(return_value=leg)
        result = await svc.get_plan_leg_by_token("raw-token", "SELL", mock_db)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_leg_when_side_matches(self, mock_db):
        leg = SimpleNamespace(side="SELL")
        mock_db.scalar = AsyncMock(return_value=leg)
        result = await svc.get_plan_leg_by_token("raw-token", "SELL", mock_db)
        assert result is leg

    @pytest.mark.asyncio
    async def test_returns_leg_when_expected_side_none(self, mock_db):
        leg = SimpleNamespace(side="BUY")
        mock_db.scalar = AsyncMock(return_value=leg)
        result = await svc.get_plan_leg_by_token("raw-token", None, mock_db)
        assert result is leg


# ── cancel_buy_leg / reject_sell_leg ─────────────────────────


class TestCancelBuyLeg:
    @pytest.mark.asyncio
    async def test_cancels_pending_leg(self, mock_db):
        plan_id = uuid.uuid4()
        locked_leg = SimpleNamespace(
            id=uuid.uuid4(),
            plan_id=plan_id,
            status="PENDING",
            token_consumed_at=None,
            decided_at=None,
            decided_by=None,
        )
        plan = SimpleNamespace(id=plan_id, user_id=uuid.uuid4())

        mock_db.scalar = AsyncMock(return_value=locked_leg)
        mock_db.get = AsyncMock(return_value=plan)

        with patch("app.services.rebalancing.plan_service.save_alert_history", new=AsyncMock()) as mock_save:
            await svc.cancel_buy_leg(locked_leg, mock_db, decided_by="USER_APP")

        assert locked_leg.status == "CANCELED"
        assert locked_leg.decided_by == "USER_APP"
        assert locked_leg.token_consumed_at is not None
        mock_save.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_409_when_already_decided(self, mock_db):
        locked_leg = SimpleNamespace(id=uuid.uuid4(), status="CANCELED", token_consumed_at=None)
        mock_db.scalar = AsyncMock(return_value=locked_leg)

        with pytest.raises(HTTPException) as exc_info:
            await svc.cancel_buy_leg(locked_leg, mock_db, decided_by="USER_APP")
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_raises_409_when_token_already_consumed(self, mock_db):
        locked_leg = SimpleNamespace(id=uuid.uuid4(), status="PENDING", token_consumed_at=datetime.now(tz=UTC))
        mock_db.scalar = AsyncMock(return_value=locked_leg)

        with pytest.raises(HTTPException) as exc_info:
            await svc.cancel_buy_leg(locked_leg, mock_db, decided_by="USER_APP")
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_raises_404_when_leg_not_found(self, mock_db):
        mock_db.scalar = AsyncMock(return_value=None)
        leg = SimpleNamespace(id=uuid.uuid4())

        with pytest.raises(HTTPException) as exc_info:
            await svc.cancel_buy_leg(leg, mock_db, decided_by="USER_APP")
        assert exc_info.value.status_code == 404


class TestRejectSellLeg:
    @pytest.mark.asyncio
    async def test_rejects_pending_leg(self, mock_db):
        plan_id = uuid.uuid4()
        locked_leg = SimpleNamespace(
            id=uuid.uuid4(),
            plan_id=plan_id,
            status="PENDING",
            token_consumed_at=None,
            decided_at=None,
            decided_by=None,
        )
        plan = SimpleNamespace(id=plan_id, user_id=uuid.uuid4())

        mock_db.scalar = AsyncMock(return_value=locked_leg)
        mock_db.get = AsyncMock(return_value=plan)

        with patch("app.services.rebalancing.plan_service.save_alert_history", new=AsyncMock()) as mock_save:
            await svc.reject_sell_leg(locked_leg, mock_db, decided_by="USER_EMAIL")

        assert locked_leg.status == "REJECTED"
        assert locked_leg.decided_by == "USER_EMAIL"
        mock_save.assert_called_once()


# ── approve_sell_leg ──────────────────────────────────────────


def _make_pending_sell_leg(plan_id, quantity=5):
    item = SimpleNamespace(
        ticker="005930",
        name="삼성전자",
        market="KOSPI",
        quantity=quantity,
        account_id=str(uuid.uuid4()),
        order_type="MARKET",
        limit_price=None,
        reference_price=70000.0,
    )
    return SimpleNamespace(
        id=uuid.uuid4(),
        plan_id=plan_id,
        side="SELL",
        status="PENDING",
        token_consumed_at=None,
        items=[item],
        decided_at=None,
        decided_by=None,
        execution_id=None,
        error_message=None,
    )


class TestApproveSellLeg:
    @pytest.mark.asyncio
    async def test_approve_executes_and_marks_executed(self, mock_db):
        plan_id = uuid.uuid4()
        locked_leg = _make_pending_sell_leg(plan_id)
        plan = SimpleNamespace(
            id=plan_id,
            user_id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            portfolio_id=uuid.uuid4(),
            strategy="FULL",
        )

        mock_db.scalar = AsyncMock(return_value=locked_leg)
        mock_db.get = AsyncMock(return_value=plan)
        mock_db.refresh = AsyncMock()

        execution_id = uuid.uuid4()
        with (
            patch("app.services.price_service.fetch_prices_batch", new=AsyncMock(return_value={})),
            patch(
                "app.services.rebalancing.execution_service.execute_rebalancing",
                new=AsyncMock(return_value=([], execution_id)),
            ),
            patch("app.services.rebalancing.plan_service._send_leg_execution_email", new=AsyncMock()),
        ):
            result = await svc.approve_sell_leg(locked_leg, mock_db, MagicMock(), decided_by="USER_EMAIL")

        assert result == execution_id
        assert locked_leg.status == "EXECUTED"
        assert locked_leg.execution_id == execution_id
        assert locked_leg.decided_by == "USER_EMAIL"

    @pytest.mark.asyncio
    async def test_approve_marks_failed_on_execution_error(self, mock_db):
        plan_id = uuid.uuid4()
        locked_leg = _make_pending_sell_leg(plan_id)
        plan = SimpleNamespace(
            id=plan_id,
            user_id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            portfolio_id=uuid.uuid4(),
            strategy="FULL",
        )

        mock_db.scalar = AsyncMock(return_value=locked_leg)
        mock_db.get = AsyncMock(return_value=plan)
        mock_db.refresh = AsyncMock()

        with (
            patch("app.services.price_service.fetch_prices_batch", new=AsyncMock(return_value={})),
            patch(
                "app.services.rebalancing.execution_service.execute_rebalancing",
                new=AsyncMock(side_effect=RuntimeError("broker error")),
            ),
        ):
            result = await svc.approve_sell_leg(locked_leg, mock_db, MagicMock(), decided_by="USER_EMAIL")

        assert result is None
        assert locked_leg.status == "FAILED"
        assert locked_leg.error_message == "broker error"

    @pytest.mark.asyncio
    async def test_rejects_buy_side_leg(self, mock_db):
        locked_leg = SimpleNamespace(
            id=uuid.uuid4(), plan_id=uuid.uuid4(), side="BUY", status="PENDING", token_consumed_at=None
        )
        mock_db.scalar = AsyncMock(return_value=locked_leg)

        with pytest.raises(HTTPException) as exc_info:
            await svc.approve_sell_leg(locked_leg, mock_db, MagicMock(), decided_by="USER_EMAIL")
        assert exc_info.value.status_code == 400


# ── approve_buy_leg ───────────────────────────────────────────


def _make_pending_buy_leg(plan_id, quantity=5):
    item = SimpleNamespace(
        ticker="005930",
        name="삼성전자",
        market="KOSPI",
        quantity=quantity,
        account_id=str(uuid.uuid4()),
        order_type="MARKET",
        limit_price=None,
        reference_price=70000.0,
    )
    return SimpleNamespace(
        id=uuid.uuid4(),
        plan_id=plan_id,
        side="BUY",
        status="PENDING",
        token_consumed_at=None,
        items=[item],
        decided_at=None,
        decided_by=None,
        execution_id=None,
        error_message=None,
    )


class TestApproveBuyLeg:
    """앱에서 매수 대기시간을 건너뛰고 즉시 실행하는 경로 — approve_sell_leg과 동일한 _approve_leg_now 공유."""

    @pytest.mark.asyncio
    async def test_approve_executes_and_marks_executed(self, mock_db):
        plan_id = uuid.uuid4()
        locked_leg = _make_pending_buy_leg(plan_id)
        plan = SimpleNamespace(
            id=plan_id,
            user_id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            portfolio_id=uuid.uuid4(),
            strategy="BUY_ONLY",
        )

        mock_db.scalar = AsyncMock(return_value=locked_leg)
        mock_db.get = AsyncMock(return_value=plan)
        mock_db.refresh = AsyncMock()

        execution_id = uuid.uuid4()
        with (
            patch("app.services.price_service.fetch_prices_batch", new=AsyncMock(return_value={})),
            patch(
                "app.services.rebalancing.execution_service.execute_rebalancing",
                new=AsyncMock(return_value=([], execution_id)),
            ),
            patch("app.services.rebalancing.plan_service._send_leg_execution_email", new=AsyncMock()),
        ):
            result = await svc.approve_buy_leg(locked_leg, mock_db, MagicMock(), decided_by="USER_APP")

        assert result == execution_id
        assert locked_leg.status == "EXECUTED"
        assert locked_leg.execution_id == execution_id
        assert locked_leg.decided_by == "USER_APP"

    @pytest.mark.asyncio
    async def test_rejects_sell_side_leg(self, mock_db):
        locked_leg = SimpleNamespace(
            id=uuid.uuid4(), plan_id=uuid.uuid4(), side="SELL", status="PENDING", token_consumed_at=None
        )
        mock_db.scalar = AsyncMock(return_value=locked_leg)

        with pytest.raises(HTTPException) as exc_info:
            await svc.approve_buy_leg(locked_leg, mock_db, MagicMock(), decided_by="USER_APP")
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_rejects_already_consumed_leg(self, mock_db):
        locked_leg = SimpleNamespace(
            id=uuid.uuid4(), plan_id=uuid.uuid4(), side="BUY", status="PENDING", token_consumed_at=datetime.now(UTC)
        )
        mock_db.scalar = AsyncMock(return_value=locked_leg)

        with pytest.raises(HTTPException) as exc_info:
            await svc.approve_buy_leg(locked_leg, mock_db, MagicMock(), decided_by="USER_APP")
        assert exc_info.value.status_code == 409


# ── execute_due_buy_legs ──────────────────────────────────────


class TestExecuteDueBuyLegs:
    @pytest.mark.asyncio
    async def test_expires_buy_leg_when_market_closed(self, mock_db):
        leg_id = uuid.uuid4()
        due_result = MagicMock()
        due_result.all.return_value = [(leg_id,)]
        locked_leg = SimpleNamespace(
            id=leg_id,
            side="BUY",
            status="PENDING",
            deadline_at=datetime.now(tz=UTC) - timedelta(minutes=5),
            decided_at=None,
            decided_by=None,
            error_message=None,
        )

        mock_db.execute = AsyncMock(return_value=due_result)
        mock_db.scalar = AsyncMock(return_value=locked_leg)

        with patch("app.utils.market_hours.is_korean_market_open", return_value=False):
            count = await svc.execute_due_buy_legs(mock_db, MagicMock())

        assert count == 1
        assert locked_leg.status == "EXPIRED"
        assert locked_leg.error_message == "market_closed_before_execution"

    @pytest.mark.asyncio
    async def test_executes_buy_leg_when_market_open(self, mock_db):
        leg_id = uuid.uuid4()
        plan_id = uuid.uuid4()
        due_result = MagicMock()
        due_result.all.return_value = [(leg_id,)]
        item = SimpleNamespace(
            ticker="005930",
            name="삼성전자",
            market="KOSPI",
            quantity=5,
            account_id=str(uuid.uuid4()),
            order_type="MARKET",
            limit_price=None,
            reference_price=70000.0,
        )
        locked_leg = SimpleNamespace(
            id=leg_id,
            plan_id=plan_id,
            side="BUY",
            status="PENDING",
            items=[item],
            decided_at=None,
            decided_by=None,
            execution_id=None,
            error_message=None,
            token_consumed_at=None,
        )
        plan = SimpleNamespace(
            id=plan_id, user_id=uuid.uuid4(), account_id=uuid.uuid4(), portfolio_id=uuid.uuid4(), strategy="BUY_ONLY"
        )

        mock_db.execute = AsyncMock(return_value=due_result)
        mock_db.scalar = AsyncMock(return_value=locked_leg)
        mock_db.get = AsyncMock(return_value=plan)
        mock_db.refresh = AsyncMock()

        execution_id = uuid.uuid4()
        with (
            patch("app.utils.market_hours.is_korean_market_open", return_value=True),
            patch("app.services.price_service.fetch_prices_batch", new=AsyncMock(return_value={})),
            patch(
                "app.services.rebalancing.execution_service.execute_rebalancing",
                new=AsyncMock(return_value=([], execution_id)),
            ),
            patch("app.services.rebalancing.plan_service._send_leg_execution_email", new=AsyncMock()),
        ):
            count = await svc.execute_due_buy_legs(mock_db, MagicMock())

        assert count == 1
        assert locked_leg.status == "EXECUTED"
        assert locked_leg.execution_id == execution_id

    @pytest.mark.asyncio
    async def test_no_due_legs_returns_zero(self, mock_db):
        due_result = MagicMock()
        due_result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=due_result)

        count = await svc.execute_due_buy_legs(mock_db, MagicMock())

        assert count == 0


# ── expire_due_sell_legs ──────────────────────────────────────


class TestExpireDueSellLegs:
    @pytest.mark.asyncio
    async def test_expires_pending_sell_legs_past_deadline(self, mock_db):
        leg_id = uuid.uuid4()
        plan_id = uuid.uuid4()
        due_result = MagicMock()
        due_result.all.return_value = [(leg_id,)]
        locked_leg = SimpleNamespace(
            id=leg_id, plan_id=plan_id, side="SELL", status="PENDING", decided_at=None, decided_by=None
        )
        plan = SimpleNamespace(id=plan_id, user_id=uuid.uuid4())

        mock_db.execute = AsyncMock(return_value=due_result)
        mock_db.scalar = AsyncMock(return_value=locked_leg)
        mock_db.get = AsyncMock(return_value=plan)

        with patch("app.services.rebalancing.plan_service.save_alert_history", new=AsyncMock()) as mock_save:
            count = await svc.expire_due_sell_legs(mock_db)

        assert count == 1
        assert locked_leg.status == "EXPIRED"
        assert locked_leg.decided_by == "SYSTEM_EXPIRY"
        mock_save.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_leg_already_decided_concurrently(self, mock_db):
        """다른 요청이 FOR UPDATE 락을 먼저 잡아 이미 상태가 바뀐 경우 건너뛴다."""
        leg_id = uuid.uuid4()
        due_result = MagicMock()
        due_result.all.return_value = [(leg_id,)]
        locked_leg = SimpleNamespace(id=leg_id, side="SELL", status="EXECUTED")

        mock_db.execute = AsyncMock(return_value=due_result)
        mock_db.scalar = AsyncMock(return_value=locked_leg)

        count = await svc.expire_due_sell_legs(mock_db)

        assert count == 0


# ── has_pending_plan_for_alert / list_recent_plan_legs ───────


class TestHasPendingPlanForAlert:
    @pytest.mark.asyncio
    async def test_returns_true_when_pending_leg_exists(self, mock_db):
        result_mock = MagicMock()
        result_mock.first.return_value = (uuid.uuid4(),)
        mock_db.execute = AsyncMock(return_value=result_mock)

        result = await svc.has_pending_plan_for_alert(uuid.uuid4(), mock_db)

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_no_pending_leg(self, mock_db):
        result_mock = MagicMock()
        result_mock.first.return_value = None
        mock_db.execute = AsyncMock(return_value=result_mock)

        result = await svc.has_pending_plan_for_alert(uuid.uuid4(), mock_db)

        assert result is False


class TestListRecentPlanLegs:
    @pytest.mark.asyncio
    async def test_returns_rows_from_query(self, mock_db):
        rows = [(SimpleNamespace(), SimpleNamespace(), "포트폴리오", "계좌")]
        result_mock = MagicMock()
        result_mock.all.return_value = rows
        mock_db.execute = AsyncMock(return_value=result_mock)

        result = await svc.list_recent_plan_legs(uuid.uuid4(), mock_db, limit=10)

        assert result == rows
