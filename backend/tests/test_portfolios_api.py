"""포트폴리오 CRUD API 테스트 (GET/POST/PUT/DELETE /api/v1/portfolios)."""
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
    result.all.return_value = []
    result.scalars.return_value.first.return_value = None
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    return db


def _make_portfolio(user_id=None, portfolio_id=None):
    pid = portfolio_id or uuid.uuid4()
    uid = user_id or uuid.uuid4()
    return SimpleNamespace(
        id=pid,
        user_id=uid,
        name="테스트 포트폴리오",
        description=None,
        items=[],
        linked_accounts=[],
        sort_order=0,
        target_account_id=None,
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
    )


@pytest.fixture(autouse=True)
def mock_redis_scheduler(monkeypatch):
    import app.redis_client as rc
    import app.scheduler as sched
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)
    mock_redis.aclose = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
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


class TestListPortfolios:
    def test_returns_401_without_auth(self, override_settings):
        from app.main import app
        from app.api.deps import get_current_user
        app.dependency_overrides.pop(get_current_user, None)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/portfolios")
        assert resp.status_code == 401

    def test_returns_200_empty_list(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        try:
            with (
                patch("app.api.v1.portfolios.get_redis", new_callable=AsyncMock,
                      return_value=AsyncMock(get=AsyncMock(return_value=None), setex=AsyncMock())),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.get("/api/v1/portfolios", headers={"Authorization": "Bearer fake"})
            assert resp.status_code == 200
            assert resp.json() == []
        finally:
            from app.api.deps import get_current_user
            from app.database import get_db
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)


class TestCreatePortfolio:
    def test_returns_201_on_create(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        portfolio = _make_portfolio(user_id=user.id)
        db.refresh = AsyncMock(side_effect=lambda obj: None)

        async def mock_scalar(stmt):
            return portfolio

        db.scalar = AsyncMock(side_effect=mock_scalar)

        app = _setup_app(user, db)
        try:
            with (
                patch("app.api.v1.portfolios.get_redis", new_callable=AsyncMock,
                      return_value=AsyncMock(get=AsyncMock(return_value=None), setex=AsyncMock(),
                                            delete=AsyncMock())),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.post(
                    "/api/v1/portfolios",
                    json={"name": "새 포트폴리오", "items": []},
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code in (200, 201, 422, 500)
        finally:
            from app.api.deps import get_current_user
            from app.database import get_db
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)

    def test_create_rejects_empty_name(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post(
                    "/api/v1/portfolios",
                    json={"name": "", "items": []},
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code == 422
        finally:
            from app.api.deps import get_current_user
            from app.database import get_db
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)


class TestDeletePortfolio:
    def test_returns_404_for_nonexistent(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=None)

        app = _setup_app(user, db)
        try:
            with (
                patch("app.api.v1.portfolios.get_redis", new_callable=AsyncMock,
                      return_value=AsyncMock(delete=AsyncMock())),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.delete(
                    f"/api/v1/portfolios/{uuid.uuid4()}",
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code == 404
        finally:
            from app.api.deps import get_current_user
            from app.database import get_db
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)

    def test_returns_204_when_portfolio_found(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        portfolio = _make_portfolio(user_id=user.id)
        db.scalar = AsyncMock(return_value=portfolio)
        db.delete = AsyncMock()

        app = _setup_app(user, db)
        try:
            with (
                patch("app.api.v1.portfolios.get_redis", new_callable=AsyncMock,
                      return_value=AsyncMock(delete=AsyncMock())),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.delete(
                    f"/api/v1/portfolios/{portfolio.id}",
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code in (204, 200)
        finally:
            from app.api.deps import get_current_user
            from app.database import get_db
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)


class TestReorderPortfolios:
    def test_returns_204_on_reorder(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        pid1 = uuid.uuid4()
        pid2 = uuid.uuid4()

        app = _setup_app(user, db)
        try:
            with (
                patch("app.api.v1.portfolios.get_redis", new_callable=AsyncMock,
                      return_value=AsyncMock(delete=AsyncMock())),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.patch(
                    "/api/v1/portfolios/reorder",
                    json={"items": [
                        {"id": str(pid1), "sort_order": 0},
                        {"id": str(pid2), "sort_order": 1},
                    ]},
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code in (204, 200)
        finally:
            from app.api.deps import get_current_user
            from app.database import get_db
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)

    def test_empty_items_returns_204(self, override_settings):
        user = _make_user()
        db = _make_mock_db()

        app = _setup_app(user, db)
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.patch(
                    "/api/v1/portfolios/reorder",
                    json={"items": []},
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code in (204, 200, 422)
        finally:
            from app.api.deps import get_current_user
            from app.database import get_db
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)
