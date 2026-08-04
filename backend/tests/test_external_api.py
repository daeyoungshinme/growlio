"""외부(자매 앱) 읽기 전용 API 테스트 (GET /api/v1/external/accounts)."""

from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


def _make_user():
    return SimpleNamespace(id=uuid.uuid4(), email="test@example.com", display_name="테스트", is_active=True)


def _make_account(user_id, **overrides):
    defaults = dict(
        id=uuid.uuid4(), user_id=user_id, name="테스트 계좌", asset_type="BANK_ACCOUNT", manual_amount=1000.0
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _setup_app(user, db):
    from app.api.deps import get_current_user
    from app.core.database import get_db
    from app.main import app

    async def override_auth():
        return user

    async def override_db():
        yield db

    app.dependency_overrides[get_current_user] = override_auth
    app.dependency_overrides[get_db] = override_db
    return app


class TestListAccountBalances:
    def test_returns_401_without_auth(self, override_settings):
        from app.api.deps import get_current_user
        from app.main import app

        app.dependency_overrides.pop(get_current_user, None)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/external/accounts")
        assert resp.status_code == 401

    def test_uses_latest_snapshot_when_available(self, override_settings):
        user = _make_user()
        account = _make_account(user.id)
        db = AsyncMock()
        app = _setup_app(user, db)
        snapshot = SimpleNamespace(amount_krw=1_234_000.0, snapshot_date=date(2026, 8, 1))

        with (
            patch("app.api.v1.external._list_accounts", AsyncMock(return_value=[account])),
            patch("app.api.v1.external.get_latest_snapshot_with_positions", AsyncMock(return_value=(snapshot, []))),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get("/api/v1/external/accounts")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["id"] == str(account.id)
        assert body[0]["current_value_krw"] == 1_234_000.0
        assert body[0]["as_of"] == "2026-08-01"

    def test_falls_back_to_manual_amount_without_snapshot(self, override_settings):
        user = _make_user()
        account = _make_account(user.id, manual_amount=500_000.0)
        db = AsyncMock()
        app = _setup_app(user, db)

        with (
            patch("app.api.v1.external._list_accounts", AsyncMock(return_value=[account])),
            patch("app.api.v1.external.get_latest_snapshot_with_positions", AsyncMock(return_value=(None, []))),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get("/api/v1/external/accounts")

        assert resp.status_code == 200
        body = resp.json()
        assert body[0]["current_value_krw"] == 500_000.0
        assert body[0]["as_of"] is None
