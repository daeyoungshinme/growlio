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
    def test_delete_404_for_other_user(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=None)
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.delete(f"/api/v1/challenges/{uuid.uuid4()}")
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


_RESP = {
    "id": str(uuid.uuid4()),
    "title": "t",
    "challenge_type": "RETURN_PCT",
    "target_amount": None,
    "target_pct": 10.0,
    "target_months": None,
    "account_id": None,
    "start_month": "2026-01",
    "deadline_month": None,
    "reminder_enabled": True,
    "status": "ACTIVE",
    "completed_at": None,
    "created_at": "2026-01-01T00:00:00+00:00",
    "progress": {"current_streak": 0, "longest_streak": 0, "months": []},
}


class TestUpdateValidation:
    """수정이 생성 검증을 우회하지 않는지 (plans/61 A3)."""

    def _patch(self, challenge, payload):
        user = _make_user()
        challenge.user_id = user.id
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=challenge)
        app = _setup_app(user, db)
        update = AsyncMock(return_value=challenge)
        with (
            patch("app.services.challenge_service.update_challenge", update),
            patch("app.services.challenge_service.get_challenge_response", AsyncMock(return_value=_RESP)),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.patch(f"/api/v1/challenges/{challenge.id}", json=payload)
        return resp, update

    @staticmethod
    def _challenge(challenge_type="RETURN_PCT", **kw):
        base = {
            "id": uuid.uuid4(),
            "challenge_type": challenge_type,
            "target_amount": None,
            "target_pct": 10.0,
            "target_months": None,
            "account_id": None,
        }
        base.update(kw)
        return SimpleNamespace(**base)

    def test_rejects_null_title(self, override_settings):
        resp, update = self._patch(self._challenge(), {"title": None})
        assert resp.status_code == 422
        update.assert_not_called()

    def test_rejects_null_reminder_enabled(self, override_settings):
        resp, _ = self._patch(self._challenge(), {"reminder_enabled": None})
        assert resp.status_code == 422

    def test_rejects_out_of_range_pct(self, override_settings):
        resp, _ = self._patch(self._challenge(), {"target_pct": 99999})
        assert resp.status_code == 422

    def test_rejects_negative_months(self, override_settings):
        resp, _ = self._patch(self._challenge("DEPOSIT", target_pct=None), {"target_months": -5})
        assert resp.status_code == 422

    def test_rejects_clearing_return_pct_target(self, override_settings):
        resp, update = self._patch(self._challenge(), {"target_pct": None})
        assert resp.status_code == 422
        update.assert_not_called()

    def test_rejects_clearing_target_value_amount(self, override_settings):
        challenge = self._challenge("TARGET_VALUE", target_pct=None, target_amount=1_000_000)
        resp, _ = self._patch(challenge, {"target_amount": None})
        assert resp.status_code == 422

    def test_omitted_fields_keep_existing_targets(self, override_settings):
        # 제목만 바꿔도 기존 target_pct로 규칙을 만족하므로 통과
        resp, update = self._patch(self._challenge(), {"title": "새 제목"})
        assert resp.status_code == 200
        update.assert_awaited_once()

    def test_frontend_edit_payload_for_deposit_passes(self, override_settings):
        # ChallengeSection.handleSubmit이 보내는 형태(목표 수익률·개월수 null)
        payload = {
            "title": "매달 적립",
            "target_amount": 500000,
            "target_pct": None,
            "target_months": None,
            "deadline_month": None,
            "reminder_enabled": True,
        }
        resp, _ = self._patch(self._challenge("DEPOSIT", target_pct=None), payload)
        assert resp.status_code == 200
