"""게이트 차단 보류 알림 3종 — `dispatch_dual_channel_alert` 공통 흐름 (plans/79 B)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.rebalancing import plan_notifications as pn
from app.services.rebalancing.plan_generation import DailyValueCapBlocked, MarketSignalGateBlocked, TaxGateBlocked

_CASES = [
    (pn.notify_tax_gate_blocked, TaxGateBlocked(estimated_tax_krw=200_000.0, max_tax_impact_krw=100_000.0)),
    (pn.notify_market_signal_gate_blocked, MarketSignalGateBlocked("RED", "STRICT", "LIVE")),
    (
        pn.notify_daily_value_cap_blocked,
        DailyValueCapBlocked(today_total_krw=900_000.0, attempted_value_krw=300_000.0, cap_krw=1_000_000.0),
    ),
]


def _run(notify, blocked, *, email_ok: bool, push_ok: bool):
    alert = SimpleNamespace(id=uuid.uuid4(), user_id=uuid.uuid4())
    portfolio = SimpleNamespace(id=uuid.uuid4(), name="P")
    mocks = {
        "set_durable": AsyncMock(),
        "history": AsyncMock(),
        "push": AsyncMock(return_value=push_ok),
        "email": AsyncMock(return_value=email_ok),
    }

    async def _go():
        with (
            patch("app.utils.durable_state.get_durable", AsyncMock(return_value=None)),
            patch("app.utils.durable_state.set_durable", mocks["set_durable"]),
            patch("app.services.alerts._dispatch.save_alert_history", mocks["history"]),
            patch("app.services.notifications.push_service.send_push_to_user", mocks["push"]),
            patch("app.services.notifications.email_service.send_tax_impact_gate_blocked_email", mocks["email"]),
            patch("app.services.notifications.email_service.send_market_signal_gate_blocked_email", mocks["email"]),
            patch("app.services.notifications.email_service.send_daily_value_cap_gate_blocked_email", mocks["email"]),
        ):
            await notify(alert, portfolio, blocked, "u@x.com", "tok", AsyncMock())

    return portfolio, mocks, _go


@pytest.mark.asyncio
@pytest.mark.parametrize(("notify", "blocked"), _CASES)
async def test_sent_saves_history_and_dedup_with_portfolio_push_data(notify, blocked):
    portfolio, mocks, go = _run(notify, blocked, email_ok=False, push_ok=True)
    await go()
    mocks["history"].assert_awaited_once()
    mocks["set_durable"].assert_awaited_once()
    assert mocks["push"].await_args.kwargs["data"]["portfolio_id"] == str(portfolio.id)


@pytest.mark.asyncio
@pytest.mark.parametrize(("notify", "blocked"), _CASES)
async def test_both_channels_failed_leaves_no_history_or_dedup(notify, blocked):
    _, mocks, go = _run(notify, blocked, email_ok=False, push_ok=False)
    await go()
    mocks["history"].assert_not_awaited()
    mocks["set_durable"].assert_not_awaited()
