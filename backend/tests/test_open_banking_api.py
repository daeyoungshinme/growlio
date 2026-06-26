"""오픈뱅킹 API 테스트 (GET /api/v1/open-banking/...)."""

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
    db.commit = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    return db




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


class TestOpenBankingConnect:
    def test_connect_returns_401_without_auth(self, override_settings):
        from app.api.deps import get_current_user
        from app.main import app

        app.dependency_overrides.pop(get_current_user, None)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/open-banking/connect")
        assert resp.status_code == 401

    def test_connect_returns_authorize_url(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        with (
            patch(
                "app.api.v1.open_banking.get_authorize_url",
                return_value="https://openbanking.example.com/oauth",
            ),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get("/api/v1/open-banking/connect")
        assert resp.status_code == 200
        assert "authorize_url" in resp.json()


class TestOpenBankingCallback:
    def test_callback_returns_400_for_invalid_state(self, override_settings):
        from app.api.deps import get_current_user
        from app.database import get_db
        from app.main import app

        db = _make_mock_db()

        async def override_db():
            yield db

        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides[get_db] = override_db

        import app.redis_client as rc

        rc.redis_client.getdel = AsyncMock(return_value=None)

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/open-banking/callback?code=abc&state=invalid")
        assert resp.status_code == 400
