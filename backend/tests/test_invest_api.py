"""DCA 투자 API 테스트 (GET /api/v1/invest/dca-analysis)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


def _make_user():
    return SimpleNamespace(
        id=uuid.uuid4(),
        email="test@example.com",
        display_name="테스트",
        is_active=True,
        needs_password_reset=False,
    )


def _make_mock_db():
    from sqlalchemy.ext.asyncio import AsyncSession

    db = AsyncMock(spec=AsyncSession)
    db.scalar = AsyncMock(return_value=None)
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=result)
    return db


@pytest.fixture(autouse=True)
def mock_redis_scheduler(monkeypatch):
    import app.redis_client as rc
    import app.scheduler as sched

    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)
    mock_redis.aclose = AsyncMock()
    monkeypatch.setattr(rc, "redis_client", mock_redis)
    monkeypatch.setattr(sched.scheduler, "start", lambda: None)
    monkeypatch.setattr(sched.scheduler, "shutdown", lambda: None)
    yield
    rc.redis_client = None


def _setup_app(user, db):
    from app.api.deps import get_current_user
    from app.database import get_db
    from app.main import app

    async def override_auth():
        return user

    async def override_db():
        yield db

    app.dependency_overrides[get_current_user] = override_auth
    app.dependency_overrides[get_db] = override_db
    return app


_MOCK_DCA = {
    "settings": {
        "monthly_deposit_amount": None,
        "goal_annual_return_pct": None,
        "goal_amount": None,
        "goal_start_date": None,
        "goal_initial_amount": None,
    },
    "projection_months": [],
    "yearly_achievements": [],
    "goal_timeline": {
        "months_to_goal": None,
        "expected_goal_date": None,
        "actual_expected_goal_date": None,
        "current_progress_pct": None,
        "on_track": None,
        "lead_lag_months": None,
    },
    "is_configured": False,
}


class TestDcaAnalysis:
    def test_returns_401_without_auth(self, override_settings):
        from app.api.deps import get_current_user
        from app.main import app

        app.dependency_overrides.pop(get_current_user, None)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/invest/dca-analysis")
        assert resp.status_code == 401

    def test_returns_200_with_mocked_service(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        with (
            patch(
                "app.api.v1.invest.dca_service.get_dca_analysis",
                AsyncMock(return_value=_MOCK_DCA),
            ),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get("/api/v1/invest/dca-analysis")
        assert resp.status_code == 200

    def test_returns_dca_data_structure(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        with (
            patch(
                "app.api.v1.invest.dca_service.get_dca_analysis",
                AsyncMock(return_value=_MOCK_DCA),
            ),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get("/api/v1/invest/dca-analysis")
        data = resp.json()
        assert "projection_months" in data
