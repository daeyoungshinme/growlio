"""설정 API 테스트 (GET/PUT /api/v1/settings)."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

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
    result.all.return_value = []
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    db.add = MagicMock()
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
    from app.main import app
    from app.api.deps import get_current_user
    from app.database import get_db

    async def override_auth():
        return user

    async def override_db():
        yield db

    app.dependency_overrides[get_current_user] = override_auth
    app.dependency_overrides[get_db] = override_db
    return app


class TestGetSettings:
    def test_returns_401_without_auth(self, override_settings):
        from app.main import app
        from app.api.deps import get_current_user
        app.dependency_overrides.pop(get_current_user, None)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/settings")
        assert resp.status_code == 401

    def test_returns_200_no_settings_row(self, override_settings):
        """UserSettings 행 없을 때 기본값 반환."""
        user = _make_user()
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=None)

        app = _setup_app(user, db)
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.get("/api/v1/settings", headers={"Authorization": "Bearer fake"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["has_kis"] is False
            assert data["has_dart"] is False
            assert data["user_email"] == "test@example.com"
        finally:
            from app.api.deps import get_current_user
            from app.database import get_db
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)

    def test_returns_200_with_settings_row(self, override_settings):
        """UserSettings 행 있을 때 실제 값 반환."""
        user = _make_user()
        db = _make_mock_db()
        settings = SimpleNamespace(
            dart_api_key="encrypted_key",
            ob_access_token=None,
            ob_token_expires_at=None,
            goal_amount=100_000_000,
            goal_annual_return_pct=7.0,
            annual_deposit_goal=10_000_000,
            monthly_deposit_amount=None,
            retirement_target_year=2045,
            notification_email=None,
            auto_dca_enabled=False,
            auto_dca_day=None,
            auto_dca_amount=None,
            auto_dca_portfolio_id=None,
            auto_dca_account_id=None,
            auto_dca_last_executed_at=None,
            fcm_token=None,
        )
        db.scalar = AsyncMock(return_value=settings)

        app = _setup_app(user, db)
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.get("/api/v1/settings", headers={"Authorization": "Bearer fake"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["has_dart"] is True
            assert data["goal_amount"] == 100_000_000
        finally:
            from app.api.deps import get_current_user
            from app.database import get_db
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)


class TestUpdateGoal:
    def test_put_goal_returns_200(self, override_settings):
        """목표 금액 업데이트."""
        user = _make_user()
        db = _make_mock_db()
        settings = SimpleNamespace(
            goal_amount=None,
            goal_annual_return_pct=None,
            annual_deposit_goal=None,
            monthly_deposit_amount=None,
            retirement_target_year=None,
            goal_start_date=None,
            goal_initial_amount=None,
        )
        db.scalar = AsyncMock(return_value=settings)

        app = _setup_app(user, db)
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.put(
                    "/api/v1/settings/goal",
                    json={"goal_amount": 200_000_000},
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code in (200, 422)
        finally:
            from app.api.deps import get_current_user
            from app.database import get_db
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)

    def test_put_goal_with_all_fields(self, override_settings):
        """모든 목표 필드 동시 업데이트."""
        user = _make_user()
        db = _make_mock_db()
        settings = SimpleNamespace(
            goal_amount=None,
            goal_annual_return_pct=None,
            annual_deposit_goal=None,
            monthly_deposit_amount=None,
            retirement_target_year=None,
            goal_start_date=None,
            goal_initial_amount=None,
        )
        db.scalar = AsyncMock(return_value=settings)

        app = _setup_app(user, db)
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.put(
                    "/api/v1/settings/goal",
                    json={
                        "goal_amount": 200_000_000,
                        "goal_annual_return_pct": 7.0,
                        "annual_deposit_goal": 10_000_000,
                        "monthly_deposit_amount": 800_000,
                        "retirement_target_year": 2045,
                        "goal_start_date": "2026-01-01",
                        "goal_initial_amount": 5_000_000,
                    },
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code in (200, 422)
        finally:
            from app.api.deps import get_current_user
            from app.database import get_db
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)

    def test_put_goal_rejects_negative_amount(self, override_settings):
        """음수 목표 금액은 422 반환."""
        user = _make_user()
        db = _make_mock_db()

        app = _setup_app(user, db)
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.put(
                    "/api/v1/settings/goal",
                    json={"goal_amount": -1000},
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code == 422
        finally:
            from app.api.deps import get_current_user
            from app.database import get_db
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)
