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

    def compute(portfolio, _overview, _threshold):
        return SimpleNamespace(portfolio_id=str(portfolio.id))

    db = SimpleNamespace(rollback=rollback)
    with (
        patch.object(svc, "get_linked_portfolios", new=linked),
        patch.object(svc, "get_active_alert_thresholds", new=AsyncMock(return_value={})),
        patch.object(
            svc, "get_settings_row", new=AsyncMock(return_value=SimpleNamespace(composite_signal_alerts_enabled=False))
        ),
        patch.object(svc, "build_portfolio_overview", new=overview),
        patch.object(svc, "compute_portfolio_drift_summary", new=compute),
    ):
        summaries = await svc.get_drift_summaries(uuid.uuid4(), db)

    assert [s.portfolio_id for s in summaries] == [str(ids[1])]
