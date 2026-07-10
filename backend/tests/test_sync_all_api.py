"""POST /assets/sync-all, GET /assets/sync-all/status API 테스트."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


def _make_user():
    return SimpleNamespace(
        id=uuid.uuid4(),
        email="test@example.com",
        display_name="테스트",
        is_active=True,
        needs_password_reset=False,
    )


def _make_account(user_id, asset_type="STOCK_KIS"):
    return SimpleNamespace(id=uuid.uuid4(), user_id=user_id, asset_type=asset_type, name="계좌")


def _make_mock_db(accounts):
    from sqlalchemy.ext.asyncio import AsyncSession

    db = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.scalars.return_value.all.return_value = accounts
    db.execute = AsyncMock(return_value=result)
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


class TestSyncAllAccounts:
    def test_starts_background_sync_and_returns_total(self):
        user = _make_user()
        accounts = [_make_account(user.id), _make_account(user.id)]
        db = _make_mock_db(accounts)
        app = _setup_app(user, db)

        with (
            patch("app.api.v1.assets.is_sync_all_running", AsyncMock(return_value=False)),
            patch("app.api.v1.assets.run_sync_all", AsyncMock()) as mock_run,
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.post("/api/v1/assets/sync-all")

        assert resp.status_code == 200
        assert resp.json() == {"total": 2, "status": "started"}
        mock_run.assert_awaited_once()
        assert mock_run.call_args.args[0] == user.id
        assert len(mock_run.call_args.args[1]) == 2

    def test_conflict_when_already_running(self):
        user = _make_user()
        db = _make_mock_db([])
        app = _setup_app(user, db)

        with (
            patch("app.api.v1.assets.is_sync_all_running", AsyncMock(return_value=True)),
            patch("app.api.v1.assets.run_sync_all", AsyncMock()) as mock_run,
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.post("/api/v1/assets/sync-all")

        assert resp.status_code == 409
        mock_run.assert_not_called()


class TestGetSyncAllStatus:
    def test_returns_status_from_service(self):
        user = _make_user()
        db = _make_mock_db([])
        app = _setup_app(user, db)
        stored = {
            "status": "running",
            "total": 3,
            "done": 1,
            "failed": 0,
            "started_at": datetime.now(UTC).isoformat(),
        }

        with (
            patch("app.api.v1.assets.get_sync_all_status", AsyncMock(return_value=stored)),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get("/api/v1/assets/sync-all/status")

        assert resp.status_code == 200
        assert resp.json() == stored

    def test_returns_idle_when_nothing_running(self):
        user = _make_user()
        db = _make_mock_db([])
        app = _setup_app(user, db)

        with (
            patch("app.api.v1.assets.get_sync_all_status", AsyncMock(return_value={"status": "idle"})),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get("/api/v1/assets/sync-all/status")

        assert resp.status_code == 200
        assert resp.json() == {"status": "idle"}
