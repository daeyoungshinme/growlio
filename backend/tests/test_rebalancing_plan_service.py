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
            patch("app.core.cache_store.get_cache_store", new=AsyncMock(return_value=MagicMock())),
            patch("app.services.price_service.fetch_prices_batch", new=AsyncMock(return_value={})),
        ):
            plan, buy_tokens, sell_tokens = await svc.generate_pending_plan_for_alert(
                alert, portfolio, drifting, mock_db, {}, "GREEN"
            )

        assert plan is not None
        assert len(buy_tokens) == 1
        assert sell_tokens == []
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
            patch("app.core.cache_store.get_cache_store", new=AsyncMock(return_value=MagicMock())),
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
            patch("app.core.cache_store.get_cache_store", new=AsyncMock(return_value=MagicMock())),
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
    async def test_order_value_cap_clamps_quantity(self, mock_db):
        """1건당 거래대금 상한(auto_rebalancing_max_order_value_krw)을 넘는 수량은 축소된다."""
        alert = _make_alert(strategy="BUY_ONLY")
        portfolio = _make_portfolio()
        # 5주 × 70,000원 = 350,000원 — 한도 100,000원이면 최대 1주까지만 허용
        drifting = [
            _make_drift_item(ticker="005930", diff_krw=350000.0, shares_to_trade=5.0, current_price_krw=70000.0)
        ]

        with (
            patch("app.core.cache_store.get_cache_store", new=AsyncMock(return_value=MagicMock())),
            patch("app.services.price_service.fetch_prices_batch", new=AsyncMock(return_value={})),
            patch.object(svc.settings, "auto_rebalancing_max_order_value_krw", 100_000.0),
        ):
            plan, buy_token, _ = await svc.generate_pending_plan_for_alert(
                alert, portfolio, drifting, mock_db, {}, "GREEN"
            )

        assert plan is not None
        assert buy_token is not None
        assert plan.legs[0].items[0].quantity == 1

    @pytest.mark.asyncio
    async def test_no_orders_returns_none_tuple(self, mock_db):
        alert = _make_alert()
        portfolio = _make_portfolio()
        drifting = [_make_drift_item(shares_to_trade=None)]

        with (
            patch("app.core.cache_store.get_cache_store", new=AsyncMock(return_value=MagicMock())),
            patch("app.services.price_service.fetch_prices_batch", new=AsyncMock(return_value={})),
        ):
            result = await svc.generate_pending_plan_for_alert(alert, portfolio, drifting, mock_db, {}, "GREEN")

        assert result == (None, [], [])

    @pytest.mark.asyncio
    async def test_sell_with_no_holding_account_produces_no_sell_leg(self, mock_db):
        """보유 계좌 정보가 없으면(ticker_account_map에 없음) 매도 leg 자체가 생성되지 않는다."""
        alert = _make_alert(strategy="FULL")
        portfolio = _make_portfolio()
        drifting = [_make_drift_item(ticker="005930", diff_krw=-100000.0, shares_to_trade=-5.0)]

        with (
            patch("app.core.cache_store.get_cache_store", new=AsyncMock(return_value=MagicMock())),
            patch("app.services.price_service.fetch_prices_batch", new=AsyncMock(return_value={})),
        ):
            plan, buy_tokens, sell_tokens = await svc.generate_pending_plan_for_alert(
                alert, portfolio, drifting, mock_db, {}, "GREEN"
            )

        assert plan is None
        assert buy_tokens == []
        assert sell_tokens == []

    @pytest.mark.asyncio
    async def test_explicitly_refreshes_legs_after_commit(self, mock_db):
        """buy_items/persisted_buy_items 진단 로그를 위해 attribute_names=["legs"]로 명시 refresh해야 한다."""
        alert = _make_alert(strategy="BUY_ONLY")
        portfolio = _make_portfolio()
        drifting = [_make_drift_item(ticker="005930", diff_krw=100000.0, shares_to_trade=5.0)]

        with (
            patch("app.core.cache_store.get_cache_store", new=AsyncMock(return_value=MagicMock())),
            patch("app.services.price_service.fetch_prices_batch", new=AsyncMock(return_value={})),
        ):
            plan, _, _ = await svc.generate_pending_plan_for_alert(alert, portfolio, drifting, mock_db, {}, "GREEN")

        mock_db.refresh.assert_awaited_once_with(plan, attribute_names=["legs"])

    @pytest.mark.asyncio
    async def test_mixed_kr_us_buy_creates_two_legs(self, mock_db):
        """국내+해외 매수가 섞여 있으면 leg가 시장별로(KR/US) 분리 생성돼야 한다 — 두 시장은
        개장시간이 달라 하나의 leg로 묶으면 실행/만료를 leg 단위로 정확히 판단할 수 없다."""
        alert = _make_alert(strategy="BUY_ONLY")
        portfolio = _make_portfolio()
        drifting = [
            _make_drift_item(ticker="005930", market="KOSPI", diff_krw=100000.0, shares_to_trade=5.0),
            _make_drift_item(
                ticker="AAPL", market="NASDAQ", diff_krw=100000.0, shares_to_trade=3.0, current_price_krw=200000.0
            ),
        ]

        with (
            patch("app.core.cache_store.get_cache_store", new=AsyncMock(return_value=MagicMock())),
            patch("app.services.price_service.fetch_prices_batch", new=AsyncMock(return_value={})),
        ):
            plan, buy_tokens, sell_tokens = await svc.generate_pending_plan_for_alert(
                alert, portfolio, drifting, mock_db, {}, "GREEN"
            )

        assert plan is not None
        assert sell_tokens == []
        assert len(buy_tokens) == 2
        assert {mkt for mkt, _ in buy_tokens} == {"KR", "US"}
        assert len(plan.legs) == 2
        legs_by_market = {leg.market: leg for leg in plan.legs}
        assert set(legs_by_market) == {"KR", "US"}
        for leg in plan.legs:
            assert leg.side == "BUY"
            assert len(leg.items) == 1

        us_item = legs_by_market["US"].items[0]
        assert us_item.order_type == "LIMIT"
        assert us_item.limit_price == 200000.0

    @pytest.mark.asyncio
    async def test_overseas_market_order_without_price_is_skipped(self, mock_db):
        """참고가(reference_price)를 구하지 못한 해외 MARKET 주문은 무인 실행 리스크가 있어
        LIMIT으로 강제 변환할 수 없으므로 스킵된다(익일 이월 없이 조용히 누락)."""
        alert = _make_alert(strategy="BUY_ONLY")
        portfolio = _make_portfolio()
        drifting = [
            _make_drift_item(
                ticker="AAPL", market="NASDAQ", diff_krw=100000.0, shares_to_trade=3.0, current_price_krw=None
            ),
        ]

        with (
            patch("app.core.cache_store.get_cache_store", new=AsyncMock(return_value=MagicMock())),
            patch("app.services.price_service.fetch_prices_batch", new=AsyncMock(return_value={})),
        ):
            result = await svc.generate_pending_plan_for_alert(alert, portfolio, drifting, mock_db, {}, "GREEN")

        assert result == (None, [], [])

    @pytest.mark.asyncio
    async def test_mixed_kr_us_sell_uses_market_appropriate_deadlines(self, mock_db):
        from app.utils.market_hours import korean_market_close_datetime, us_market_close_datetime

        alert = _make_alert(strategy="FULL")
        portfolio = _make_portfolio()
        kr_holder = uuid.uuid4()
        us_holder = uuid.uuid4()
        ticker_account_map = {
            "005930": [_make_ticker_account(kr_holder, quantity=10)],
            "AAPL": [_make_ticker_account(us_holder, quantity=10)],
        }
        drifting = [
            _make_drift_item(ticker="005930", market="KOSPI", diff_krw=-100000.0, shares_to_trade=-5.0),
            _make_drift_item(
                ticker="AAPL", market="NASDAQ", diff_krw=-100000.0, shares_to_trade=-3.0, current_price_krw=200000.0
            ),
        ]

        with (
            patch("app.core.cache_store.get_cache_store", new=AsyncMock(return_value=MagicMock())),
            patch("app.services.price_service.fetch_prices_batch", new=AsyncMock(return_value={})),
        ):
            plan, buy_tokens, sell_tokens = await svc.generate_pending_plan_for_alert(
                alert, portfolio, drifting, mock_db, ticker_account_map, "GREEN"
            )

        assert buy_tokens == []
        assert len(sell_tokens) == 2
        sell_legs = {leg.market: leg for leg in plan.legs if leg.side == "SELL"}
        assert set(sell_legs) == {"KR", "US"}

        expected_kr_close = korean_market_close_datetime().astimezone(UTC)
        expected_us_close = us_market_close_datetime().astimezone(UTC)
        assert abs((sell_legs["KR"].deadline_at - expected_kr_close).total_seconds()) < 5
        assert abs((sell_legs["US"].deadline_at - expected_us_close).total_seconds()) < 5


# ── notify_plan_generated ────────────────────────────────────


class TestNotifyPlanGenerated:
    @pytest.mark.asyncio
    async def test_sell_only_plan_still_sends_email(self, mock_db):
        """buy leg가 없어도(매도 전용 플랜) sell leg만 있으면 이메일을 발송해야 한다 —
        buy leg 유무로만 게이트하면 매도전용 드리프트에서 이메일이 조용히 스킵된다."""
        alert = _make_alert()
        portfolio = _make_portfolio()
        sell_leg = SimpleNamespace(
            side="SELL", market="KR", items=[SimpleNamespace(ticker="005930")], deadline_at=datetime.now(UTC)
        )
        plan = SimpleNamespace(id=uuid.uuid4(), account_id=None, legs=[sell_leg])

        mock_email = AsyncMock(return_value=True)
        with (
            patch("app.services.email_service.send_rebalancing_plan_pending_email", new=mock_email),
            patch("app.services.push_service.send_push_to_user", new=AsyncMock(return_value=True)),
            patch("app.services.rebalancing.plan_service.save_alert_history", new=AsyncMock()),
        ):
            email_sent = await svc.notify_plan_generated(
                plan, alert, portfolio, [], [("KR", "sell-token")], "user@test.com", None, "GREEN", mock_db
            )

        assert email_sent is True
        mock_email.assert_awaited_once()
        _, kwargs = mock_email.call_args
        assert kwargs["buy_legs"] == []
        assert len(kwargs["sell_legs"]) == 1
        assert kwargs["sell_legs"][0].token == "sell-token"

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
                plan, alert, portfolio, [], [], "user@test.com", None, "GREEN", mock_db
            )

        assert email_sent is False
        mock_email.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_email_address_skips_send(self, mock_db):
        alert = _make_alert()
        portfolio = _make_portfolio()
        buy_leg = SimpleNamespace(
            side="BUY", market="KR", items=[SimpleNamespace(ticker="005930")], deadline_at=datetime.now(UTC)
        )
        plan = SimpleNamespace(id=uuid.uuid4(), account_id=None, legs=[buy_leg])

        mock_email = AsyncMock()
        with (
            patch("app.services.email_service.send_rebalancing_plan_pending_email", new=mock_email),
            patch("app.services.push_service.send_push_to_user", new=AsyncMock(return_value=True)),
            patch("app.services.rebalancing.plan_service.save_alert_history", new=AsyncMock()),
        ):
            email_sent = await svc.notify_plan_generated(
                plan, alert, portfolio, [("KR", "buy-token")], [], None, None, "GREEN", mock_db
            )

        assert email_sent is False
        mock_email.assert_not_awaited()


# ── notify_tax_gate_blocked ────────────────────────────────────


class TestNotifyTaxGateBlocked:
    @pytest.mark.asyncio
    async def test_sends_email_and_push_and_marks_dedup(self, mock_db):
        alert = _make_alert()
        portfolio = _make_portfolio()
        blocked = svc.TaxGateBlocked(estimated_tax_krw=200_000.0, max_tax_impact_krw=100_000.0)

        mock_email = AsyncMock(return_value=True)
        with (
            patch("app.services.email_service.send_tax_impact_gate_blocked_email", new=mock_email),
            patch("app.services.push_service.send_push_to_user", new=AsyncMock(return_value=True)),
            patch("app.services.rebalancing.plan_service.save_alert_history", new=AsyncMock()),
            patch("app.utils.durable_state.get_durable", new=AsyncMock(return_value=None)),
            patch("app.utils.durable_state.set_durable", new=AsyncMock()) as mock_set_durable,
        ):
            await svc.notify_tax_gate_blocked(alert, portfolio, blocked, "user@test.com", "fcm-token", mock_db)

        mock_email.assert_awaited_once_with("user@test.com", portfolio.name, 200_000.0, 100_000.0)
        mock_set_durable.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skips_when_already_sent_today(self, mock_db):
        """같은 알림에 대해 하루 1회만 발송 — 5분 tick마다 스팸처럼 가지 않도록 dedup."""
        alert = _make_alert()
        portfolio = _make_portfolio()
        blocked = svc.TaxGateBlocked(estimated_tax_krw=200_000.0, max_tax_impact_krw=100_000.0)

        mock_email = AsyncMock()
        with (
            patch("app.services.email_service.send_tax_impact_gate_blocked_email", new=mock_email),
            patch("app.utils.durable_state.get_durable", new=AsyncMock(return_value="1")),
        ):
            await svc.notify_tax_gate_blocked(alert, portfolio, blocked, "user@test.com", "fcm-token", mock_db)

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

        mock_notify_failed = AsyncMock()
        with (
            patch("app.services.price_service.fetch_prices_batch", new=AsyncMock(return_value={})),
            patch(
                "app.services.rebalancing.execution_service.execute_rebalancing",
                new=AsyncMock(side_effect=RuntimeError("broker error")),
            ),
            patch("app.services.rebalancing.plan_service._notify_leg_execution_failed", new=mock_notify_failed),
            patch("app.services.rebalancing.plan_service.save_alert_history", new=AsyncMock()),
        ):
            result = await svc.approve_sell_leg(locked_leg, mock_db, MagicMock(), decided_by="USER_EMAIL")

        assert result is None
        assert locked_leg.status == "FAILED"
        assert locked_leg.error_message == "broker error"
        mock_notify_failed.assert_awaited_once_with(plan, "SELL", "broker error", mock_db)

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
            market="KR",
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
            market="KR",
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
    async def test_market_signal_gate_blocks_execution_and_leaves_leg_pending(self, mock_db):
        """대기시간 동안 시장 상황이 악화되면 실행 직전 재확인해 건너뛴다 — leg는 PENDING으로 남아
        다음 tick(1분 간격)에 재시도되고, 계속 막히면 장마감 시 EXPIRED로 자연 정리된다."""
        from app.models.alert import RebalancingAlert
        from app.models.rebalancing_plan import RebalancingPlan

        leg_id = uuid.uuid4()
        plan_id = uuid.uuid4()
        alert_id = uuid.uuid4()
        due_result = MagicMock()
        due_result.all.return_value = [(leg_id,)]
        locked_leg = SimpleNamespace(
            id=leg_id,
            plan_id=plan_id,
            side="BUY",
            market="KR",
            status="PENDING",
            decided_at=None,
            decided_by=None,
            execution_id=None,
            error_message=None,
            token_consumed_at=None,
        )
        plan = SimpleNamespace(
            id=plan_id,
            alert_id=alert_id,
            user_id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            portfolio_id=uuid.uuid4(),
            strategy="BUY_ONLY",
        )
        alert = SimpleNamespace(id=alert_id, market_condition_mode="STRICT")

        async def _get_side_effect(model, _pk):
            if model is RebalancingPlan:
                return plan
            if model is RebalancingAlert:
                return alert
            return None

        mock_db.execute = AsyncMock(return_value=due_result)
        mock_db.scalar = AsyncMock(return_value=locked_leg)
        mock_db.get = AsyncMock(side_effect=_get_side_effect)

        with (
            patch("app.utils.market_hours.is_korean_market_open", return_value=True),
            patch(
                "app.services.market_signal_service.get_market_signal",
                new=AsyncMock(return_value={"composite_level": "YELLOW", "data_freshness": "LIVE"}),
            ),
        ):
            count = await svc.execute_due_buy_legs(mock_db, MagicMock())

        assert count == 0
        assert locked_leg.status == "PENDING"
        assert locked_leg.token_consumed_at is None

    @pytest.mark.asyncio
    async def test_no_due_legs_returns_zero(self, mock_db):
        due_result = MagicMock()
        due_result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=due_result)

        count = await svc.execute_due_buy_legs(mock_db, MagicMock())

        assert count == 0

    @pytest.mark.asyncio
    async def test_us_leg_executes_when_nyse_open_even_if_krx_closed(self, mock_db):
        """KR/US leg는 독립적으로 게이팅된다 — KRX가 닫혀 있어도 US leg는 NYSE 개장 여부로 실행 판단한다."""
        leg_id = uuid.uuid4()
        plan_id = uuid.uuid4()
        due_result = MagicMock()
        due_result.all.return_value = [(leg_id,)]
        item = SimpleNamespace(
            ticker="AAPL",
            name="Apple",
            market="NASDAQ",
            quantity=3,
            account_id=str(uuid.uuid4()),
            order_type="LIMIT",
            limit_price=200000.0,
            reference_price=200000.0,
        )
        locked_leg = SimpleNamespace(
            id=leg_id,
            plan_id=plan_id,
            side="BUY",
            market="US",
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
            patch("app.utils.market_hours.is_korean_market_open", return_value=False),
            patch("app.utils.market_hours.is_us_market_open", return_value=True),
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
    async def test_us_leg_expires_when_nyse_closed_even_if_krx_open(self, mock_db):
        """반대 방향도 독립적 — KRX가 열려 있어도 US leg는 NYSE가 닫혀 있으면 EXPIRED 처리된다."""
        leg_id = uuid.uuid4()
        due_result = MagicMock()
        due_result.all.return_value = [(leg_id,)]
        locked_leg = SimpleNamespace(
            id=leg_id,
            side="BUY",
            market="US",
            status="PENDING",
            deadline_at=datetime.now(tz=UTC) - timedelta(minutes=5),
            decided_at=None,
            decided_by=None,
            error_message=None,
        )

        mock_db.execute = AsyncMock(return_value=due_result)
        mock_db.scalar = AsyncMock(return_value=locked_leg)

        with (
            patch("app.utils.market_hours.is_korean_market_open", return_value=True),
            patch("app.utils.market_hours.is_us_market_open", return_value=False),
        ):
            count = await svc.execute_due_buy_legs(mock_db, MagicMock())

        assert count == 1
        assert locked_leg.status == "EXPIRED"
        assert locked_leg.error_message == "market_closed_before_execution"


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

    @pytest.mark.asyncio
    async def test_expires_us_leg_with_next_day_kst_deadline(self, mock_db):
        """해외(US) SELL leg는 마감시각이 다음날(KST 기준) 새벽으로 찍히지만, deadline_at은 항상
        절대 UTC 시각으로 저장되므로 시장 구분 없이 `deadline_at <= now`만으로 정확히 만료된다 —
        이 job에 시장별 분기 로직이 필요 없음을 보이는 회귀 테스트."""
        leg_id = uuid.uuid4()
        plan_id = uuid.uuid4()
        due_result = MagicMock()
        due_result.all.return_value = [(leg_id,)]
        locked_leg = SimpleNamespace(
            id=leg_id, plan_id=plan_id, side="SELL", market="US", status="PENDING", decided_at=None, decided_by=None
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
