"""적립식 코어 + 전술 보조(plans/71) — 자동매수 `TACTICAL` 게이트(전술 방어 국면이면 매수 보류)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.services.rebalancing.order_builder import is_market_signal_blocking_auto_mode, tactical_regime_for_gate


class TestGateDecision:
    def test_tactical_blocks_only_in_risk_off(self):
        assert is_market_signal_blocking_auto_mode("TACTICAL", "GREEN", "LIVE", "RISK_OFF") is True
        assert is_market_signal_blocking_auto_mode("TACTICAL", "RED", "LIVE", "NEUTRAL") is False
        assert is_market_signal_blocking_auto_mode("TACTICAL", "RED", "LIVE", "RISK_ON") is False

    def test_tactical_ignores_macro_staleness_and_missing_strategy(self):
        # 복합 신호 STALE은 CAUTIOUS/STRICT만 차단 — 전술 연동은 국면만 본다
        assert is_market_signal_blocking_auto_mode("TACTICAL", "GREEN", "STALE", "NEUTRAL") is False
        # 전략이 없어 국면을 모르면 통과(fail-open)
        assert is_market_signal_blocking_auto_mode("TACTICAL", "RED", "STALE", None) is False

    def test_existing_modes_unchanged(self):
        assert is_market_signal_blocking_auto_mode("CAUTIOUS", "RED", "LIVE", "RISK_ON") is True
        assert is_market_signal_blocking_auto_mode("CAUTIOUS", "YELLOW", "LIVE") is False
        assert is_market_signal_blocking_auto_mode("STRICT", "YELLOW", "LIVE") is True
        assert is_market_signal_blocking_auto_mode("DISABLED", "RED", "STALE", "RISK_OFF") is False


class TestRegimeLookup:
    @pytest.mark.asyncio
    async def test_queries_only_for_tactical_mode(self):
        db = MagicMock()
        db.scalar = AsyncMock(return_value="RISK_OFF")
        assert await tactical_regime_for_gate(None, db) is None
        assert await tactical_regime_for_gate(SimpleNamespace(market_condition_mode="STRICT"), db) is None
        db.scalar.assert_not_awaited()
        alert = SimpleNamespace(market_condition_mode="TACTICAL", portfolio_id=uuid.uuid4())
        assert await tactical_regime_for_gate(alert, db) == "RISK_OFF"
        db.scalar.assert_awaited_once()


class TestBlockedNotice:
    def test_email_labels_match_gate_rules(self):
        from app.services.notifications.email_templates.rebalancing import market_signal_gate_blocked_template

        _, cautious = market_signal_gate_blocked_template("P", "RED", "CAUTIOUS")
        _, strict = market_signal_gate_blocked_template("P", "YELLOW", "STRICT")
        assert "신중(RED만 차단)" in cautious
        assert "엄격(YELLOW·RED 차단)" in strict

    def test_tactical_email(self):
        from app.services.notifications.email_templates.rebalancing import market_signal_gate_blocked_template

        subject, html = market_signal_gate_blocked_template("적립", "GREEN", "TACTICAL")
        assert "적립 매수 보류" in subject
        assert "매도는 하지 않습니다" in html

    @pytest.mark.asyncio
    async def test_tactical_push_and_history(self):
        from app.services.rebalancing import plan_notifications as pn
        from app.services.rebalancing.plan_generation import MarketSignalGateBlocked

        alert = SimpleNamespace(id=uuid.uuid4(), user_id=uuid.uuid4())
        portfolio = SimpleNamespace(id=uuid.uuid4(), name="적립")
        blocked = MarketSignalGateBlocked("GREEN", "TACTICAL", "LIVE", tactical_regime="RISK_OFF")
        db = AsyncMock()
        push = AsyncMock()
        history = AsyncMock()
        with (
            patch("app.utils.durable_state.get_durable", AsyncMock(return_value=None)),
            patch("app.utils.durable_state.set_durable", AsyncMock()),
            patch("app.services.notifications.email_service.send_market_signal_gate_blocked_email", AsyncMock()),
            patch("app.services.notifications.push_service.send_push_to_user", push),
            patch("app.services.alerts._dispatch.save_alert_history", history),
        ):
            await pn.notify_market_signal_gate_blocked(alert, portfolio, blocked, "u@x.com", "tok", db)
        assert "적립 매수를 보류" in push.await_args.kwargs["body"]
        assert "전술 방어 국면" in history.await_args.args[3]


class TestSettingsValidation:
    @pytest.mark.asyncio
    async def test_tactical_requires_strategy(self):
        from app.api.v1.rebalancing_alerts import _validate_tactical_gate

        body = SimpleNamespace(market_condition_mode="TACTICAL")
        db = MagicMock()
        db.scalar = AsyncMock(return_value=None)
        with pytest.raises(HTTPException) as exc:
            await _validate_tactical_gate(db, body, uuid.uuid4())
        assert exc.value.status_code == 422
        db.scalar = AsyncMock(return_value=uuid.uuid4())
        await _validate_tactical_gate(db, body, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_other_modes_skip_lookup(self):
        from app.api.v1.rebalancing_alerts import _validate_tactical_gate

        db = MagicMock()
        db.scalar = AsyncMock()
        await _validate_tactical_gate(db, SimpleNamespace(market_condition_mode="STRICT"), uuid.uuid4())
        db.scalar.assert_not_awaited()


class TestTacticalDisableUnlinks:
    def test_delete_resets_linked_alerts(self):
        from sqlalchemy.ext.asyncio import AsyncSession

        from app.api.deps import get_current_user
        from app.core.database import get_db
        from app.main import app
        from app.services.tactical import tactical_allocation_service as tactical

        user = SimpleNamespace(id=uuid.uuid4(), email="t@example.com", is_active=True, needs_password_reset=False)
        db = AsyncMock(spec=AsyncSession)

        async def _auth():
            return user

        async def _db():
            yield db

        app.dependency_overrides[get_current_user] = _auth
        app.dependency_overrides[get_db] = _db
        strategy = SimpleNamespace(id=uuid.uuid4())
        try:
            with (
                patch.object(tactical, "get_strategy", AsyncMock(return_value=strategy)),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.delete(f"/api/v1/tactical/{uuid.uuid4()}")
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 204
        stmt = db.execute.await_args.args[0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "UPDATE rebalancing_alerts" in compiled
        assert "'TACTICAL'" in compiled
        assert "market_condition_mode='DISABLED'" in compiled
        db.delete.assert_awaited_once_with(strategy)
