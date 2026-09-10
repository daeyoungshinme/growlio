"""적립식 투자 챌린지 API 테스트 (/api/v1/challenges)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


def _make_user():
    return SimpleNamespace(
        id=uuid.uuid4(), email="test@example.com", display_name="테스트", is_active=True, needs_password_reset=False
    )


def _make_mock_db():
    from sqlalchemy.ext.asyncio import AsyncSession

    db = AsyncMock(spec=AsyncSession)
    db.scalar = AsyncMock(return_value=None)
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=result)
    return db


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


class TestListChallenges:
    def test_401_without_auth(self, override_settings):
        from app.api.deps import get_current_user
        from app.main import app

        app.dependency_overrides.pop(get_current_user, None)
        with TestClient(app, raise_server_exceptions=False) as client:
            assert client.get("/api/v1/challenges").status_code == 401

    def test_returns_list(self, override_settings):
        user = _make_user()
        app = _setup_app(user, _make_mock_db())
        with (
            patch(
                "app.services.challenge_service.list_challenges_with_progress",
                AsyncMock(return_value=[]),
            ),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get("/api/v1/challenges")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_summary_endpoint(self, override_settings):
        user = _make_user()
        app = _setup_app(user, _make_mock_db())
        with (
            patch(
                "app.services.challenge_service.get_challenge_summary",
                AsyncMock(return_value=SimpleNamespace(needs_attention=True, count=2)),
            ),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get("/api/v1/challenges/summary")
        assert resp.status_code == 200
        assert resp.json() == {"needs_attention": True, "count": 2}


class TestCreateChallenge:
    def test_rejects_return_pct_with_account_id(self, override_settings):
        user = _make_user()
        app = _setup_app(user, _make_mock_db())
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post(
                "/api/v1/challenges",
                json={
                    "title": "수익률 10%",
                    "challenge_type": "RETURN_PCT",
                    "target_pct": 10,
                    "account_id": str(uuid.uuid4()),
                    "start_month": "2026-01",
                },
            )
        assert resp.status_code == 422

    def test_rejects_bad_month_format(self, override_settings):
        user = _make_user()
        app = _setup_app(user, _make_mock_db())
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post(
                "/api/v1/challenges",
                json={"title": "x", "challenge_type": "DEPOSIT", "start_month": "2026/01"},
            )
        assert resp.status_code == 422

    def test_creates_deposit_challenge(self, override_settings):
        user = _make_user()
        app = _setup_app(user, _make_mock_db())
        fake = SimpleNamespace(id=uuid.uuid4())
        resp_model = {
            "id": str(fake.id),
            "title": "매달 50만원",
            "challenge_type": "DEPOSIT",
            "target_amount": 500000.0,
            "target_pct": None,
            "target_months": 12,
            "account_id": None,
            "start_month": "2026-01",
            "deadline_month": None,
            "reminder_enabled": True,
            "status": "ACTIVE",
            "completed_at": None,
            "created_at": "2026-01-01T00:00:00+00:00",
            "progress": {"current_streak": 0, "longest_streak": 0, "months": []},
        }
        with (
            patch("app.services.challenge_service.create_challenge", AsyncMock(return_value=fake)),
            patch(
                "app.services.challenge_service.get_challenge_response",
                AsyncMock(return_value=resp_model),
            ),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.post(
                "/api/v1/challenges",
                json={
                    "title": "매달 50만원",
                    "challenge_type": "DEPOSIT",
                    "target_amount": 500000,
                    "target_months": 12,
                    "start_month": "2026-01",
                },
            )
        assert resp.status_code == 201
        assert resp.json()["title"] == "매달 50만원"


class TestGetUpdateDelete:
    def test_get_404_for_other_user(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=None)
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get(f"/api/v1/challenges/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_delete_204(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        challenge = SimpleNamespace(id=uuid.uuid4(), user_id=user.id, challenge_type="DEPOSIT")
        db.scalar = AsyncMock(return_value=challenge)
        app = _setup_app(user, db)
        with (
            patch("app.services.challenge_service.delete_challenge", AsyncMock()),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.delete(f"/api/v1/challenges/{challenge.id}")
        assert resp.status_code == 204
