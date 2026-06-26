"""DART API 테스트 (GET /api/v1/dart/disclosures)."""

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
    result.all.return_value = []
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    db.add = MagicMock()
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


class TestDartDisclosures:
    def test_returns_401_without_auth(self, override_settings):
        from app.api.deps import get_current_user
        from app.main import app

        app.dependency_overrides.pop(get_current_user, None)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/dart/disclosures")
        assert resp.status_code == 401

    def test_returns_422_when_no_dart_key(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=None)  # settings_row = None
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/dart/disclosures")
        assert resp.status_code == 422

    def test_returns_422_when_dart_key_blank(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        settings_stub = SimpleNamespace(user_id=user.id, dart_api_key=None)
        db.scalar = AsyncMock(return_value=settings_stub)
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/dart/disclosures")
        assert resp.status_code == 422

    def test_returns_empty_when_no_tickers(self, override_settings):
        user = _make_user()
        db = _make_mock_db()

        settings_stub = SimpleNamespace(user_id=user.id, dart_api_key="encrypted_key")
        db.scalar = AsyncMock(return_value=settings_stub)

        result_stub = MagicMock()
        result_stub.all.return_value = []
        db.execute = AsyncMock(return_value=result_stub)

        app = _setup_app(user, db)
        with (
            patch("app.api.v1.dart.decrypt", return_value="real-dart-key"),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get("/api/v1/dart/disclosures")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_disclosures_from_service(self, override_settings):
        user = _make_user()
        db = _make_mock_db()

        settings_stub = SimpleNamespace(user_id=user.id, dart_api_key="encrypted_key")
        db.scalar = AsyncMock(return_value=settings_stub)

        result_stub = MagicMock()
        result_stub.all.return_value = [("005930",), ("035720",)]
        db.execute = AsyncMock(return_value=result_stub)

        mock_disclosures = [{"title": "삼성전자 공시", "ticker": "005930"}]

        app = _setup_app(user, db)
        with (
            patch("app.api.v1.dart.decrypt", return_value="real-dart-key"),
            patch(
                "app.api.v1.dart.fetch_disclosures_for_tickers",
                AsyncMock(return_value=mock_disclosures),
            ),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get("/api/v1/dart/disclosures")
        assert resp.status_code == 200
        assert len(resp.json()) == 1
