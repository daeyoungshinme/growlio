"""drift_summary_service — 포트폴리오 루프 DB 오류 격리 (계획 59 A2)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.rebalancing import drift_summary_service as svc


class _Pf:
    """rollback 후 접근하면 async lazy load처럼 실패하는 Portfolio 흉내."""

    def __init__(self, pid: uuid.UUID) -> None:
        self._expired = False
        self._id = pid

    @property
    def id(self) -> uuid.UUID:
        if self._expired:
            raise RuntimeError("MissingGreenlet: expired attribute lazy load")
        return self._id

    @property
    def account_ids(self) -> None:
        if self._expired:
            raise RuntimeError("MissingGreenlet: expired attribute lazy load")
        return None


@pytest.mark.asyncio
async def test_db_error_on_first_portfolio_does_not_drop_the_rest():
    ids = [uuid.uuid4(), uuid.uuid4()]
    state = {"aborted": False, "loaded": []}

    async def linked(_db, _uid):
        if state["aborted"]:
            raise RuntimeError("PendingRollbackError")
        fresh = [_Pf(i) for i in ids]
        state["loaded"].extend(fresh)
        return fresh

    async def rollback():
        state["aborted"] = False
        for pf in state["loaded"]:
            pf._expired = True

    calls = {"n": 0}

    async def overview(*_a, **_k):
        if state["aborted"]:
            raise RuntimeError("PendingRollbackError")
        calls["n"] += 1
        if calls["n"] == 1:
            state["aborted"] = True
            raise RuntimeError("OperationalError")
        return {}

    def summarize(portfolio, _analysis, _threshold, _relative):
        return SimpleNamespace(portfolio_id=str(portfolio.id), needs_rebalancing=False, max_drift_pct=0.0)

    db = SimpleNamespace(rollback=rollback)
    with (
        patch.object(svc, "get_linked_portfolios", new=linked),
        patch.object(svc, "get_active_alerts_by_portfolio", new=AsyncMock(return_value={})),
        patch.object(svc, "get_last_rebalanced_at", new=AsyncMock(return_value={})),
        patch.object(svc, "_market_levels", new=AsyncMock(return_value=("GREEN", False))),
        patch.object(
            svc, "get_settings_row", new=AsyncMock(return_value=SimpleNamespace(composite_signal_alerts_enabled=False))
        ),
        patch.object(svc, "build_portfolio_overview", new=overview),
        patch.object(svc, "analyze_rebalancing", new=lambda *_a, **_k: SimpleNamespace(items=[])),
        patch.object(svc, "summarize_drift", new=summarize),
    ):
        summaries = await svc.get_drift_summaries(uuid.uuid4(), db)

    assert [s.portfolio_id for s in summaries] == [str(ids[1])]


# ── 시점 필드(plans/136) ─────────────────────────────────────────────────────


def _alert(**kw):
    base = {
        "trigger_condition": "DRIFT_ONLY",
        "mode": "NOTIFY",
        "market_condition_mode": "DISABLED",
        "schedule_type": "MONTHLY",
        "schedule_day_of_month": 25,
        "schedule_day_of_week": None,
        "last_triggered_at": None,
        "threshold_pct": 5.0,
        "relative_threshold_pct": None,
        "portfolio_id": None,
    }
    base.update(kw)
    return SimpleNamespace(**base)


def test_next_schedule_ignores_drift_only_and_picks_earliest():
    from datetime import date

    alerts = [
        _alert(trigger_condition="DRIFT_ONLY", schedule_day_of_month=20),
        _alert(trigger_condition="SCHEDULE_ONLY", schedule_day_of_month=28),
        _alert(trigger_condition="BOTH", schedule_type="WEEKLY", schedule_day_of_week=0),
    ]
    # 2026-11-19(목) → 다음 월요일 11-23이 11-28보다 먼저
    assert svc._next_schedule(alerts, date(2026, 11, 19)) == (date(2026, 11, 23), "WEEKLY")
    assert svc._next_schedule([alerts[0]], date(2026, 11, 19)) == (None, None)


@pytest.mark.asyncio
async def test_blocked_gate_mode_only_for_auto_alerts():
    db = SimpleNamespace()
    notify = _alert(mode="NOTIFY", market_condition_mode="CAUTIOUS")
    auto = _alert(mode="AUTO", market_condition_mode="STRICT")
    assert await svc._blocked_gate_mode([notify], db, "RED", False) is None
    assert await svc._blocked_gate_mode([auto], db, "YELLOW", False) == "STRICT"
    assert await svc._blocked_gate_mode([auto], db, "GREEN", False) is None
    # STALE이면 CAUTIOUS/STRICT 게이트가 막는다 — 자동 실행과 같은 판정
    assert await svc._blocked_gate_mode([auto], db, "GREEN", True) == "STRICT"


@pytest.mark.asyncio
async def test_market_levels_prefers_confirmed_and_falls_back_to_raw():
    with (
        patch.object(svc, "get_market_signal", new=AsyncMock(return_value={"composite_level": "YELLOW"})),
        patch.object(svc, "get_last_composite_level", new=AsyncMock(return_value="RED")),
    ):
        assert await svc._market_levels(SimpleNamespace(), None) == ("RED", False)
    with (
        patch.object(
            svc,
            "get_market_signal",
            new=AsyncMock(return_value={"composite_level": "YELLOW", "data_freshness": "STALE"}),
        ),
        patch.object(svc, "get_last_composite_level", new=AsyncMock(return_value=None)),
    ):
        assert await svc._market_levels(SimpleNamespace(), None) == ("YELLOW", True)
    with patch.object(svc, "get_market_signal", new=AsyncMock(side_effect=RuntimeError("down"))):
        assert await svc._market_levels(SimpleNamespace(), None) == (None, True)


@pytest.mark.asyncio
async def test_summary_fills_timing_fields():
    from datetime import UTC, datetime

    from app.schemas.rebalancing import PortfolioDriftSummary
    from app.services.rebalancing.diagnosis_service import SellCostEstimate

    pid = uuid.uuid4()
    pf = SimpleNamespace(id=pid, name="P", account_ids=None)
    executed_at = datetime(2026, 10, 1, tzinfo=UTC)
    alert = _alert(trigger_condition="BOTH", relative_threshold_pct=None, threshold_pct=4.0)

    def summarize(portfolio, _analysis, threshold, relative):
        return PortfolioDriftSummary(
            portfolio_id=portfolio.id,
            portfolio_name=portfolio.name,
            needs_rebalancing=True,
            threshold_pct=threshold,
            relative_threshold_pct=relative,
            max_drift_pct=6.0,
            drifted_items_count=1,
        )

    costs = SellCostEstimate(
        total_gain=0, overseas_gain=3_000_000, overseas_tax=110_000, fee=2_500, sell_notional=1_000_000, items=[]
    )
    with (
        patch.object(svc, "get_linked_portfolios", new=AsyncMock(return_value=[pf])),
        patch.object(svc, "get_active_alerts_by_portfolio", new=AsyncMock(return_value={str(pid): [alert]})),
        patch.object(svc, "get_last_rebalanced_at", new=AsyncMock(return_value={str(pid): executed_at})),
        patch.object(
            svc, "get_settings_row", new=AsyncMock(return_value=SimpleNamespace(composite_signal_alerts_enabled=False))
        ),
        patch.object(svc, "_market_levels", new=AsyncMock(return_value=("YELLOW", False))),
        patch.object(svc, "build_portfolio_overview", new=AsyncMock(return_value={})),
        patch.object(svc, "analyze_rebalancing", new=lambda *_a, **_k: SimpleNamespace(items=[])),
        patch.object(svc, "summarize_drift", new=summarize),
        patch.object(svc, "estimate_sell_costs", new=lambda *_a: costs),
    ):
        [summary] = await svc.get_drift_summaries(uuid.uuid4(), SimpleNamespace())

    assert summary.threshold_pct == 4.0
    assert summary.has_alert_configured is True
    assert summary.last_rebalanced_at == executed_at
    assert summary.next_scheduled_date is not None
    assert summary.schedule_type == "MONTHLY"
    assert summary.estimated_trade_krw == 1_000_000
    assert summary.estimated_cost_krw == 112_500
    assert summary.estimated_overseas_gain_krw == 3_000_000
    assert summary.timing == "SPLIT"
    assert "110,000원" in (summary.timing_reason or "")
