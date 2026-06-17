"""Auth API 엔드포인트 통합 테스트 (FastAPI TestClient + DB mock)."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

# ── 공통 헬퍼 ────────────────────────────────────────────────


def _make_mock_db(existing_user=None):
    from sqlalchemy.ext.asyncio import AsyncSession

    db = AsyncMock(spec=AsyncSession)
    db.scalar = AsyncMock(return_value=existing_user)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()

    async def _refresh(obj):
        if hasattr(obj, "id") and obj.id is None:
            obj.id = uuid.uuid4()

    db.refresh = AsyncMock(side_effect=_refresh)
    return db


def _make_user(email="test@example.com"):
    return SimpleNamespace(
        id=uuid.uuid4(),
        email=email,
        display_name="테스트 유저",
        is_active=True,
        needs_password_reset=False,
    )


def _valid_jwt_payload(user_id: str, email: str = "test@example.com") -> dict:
    return {"sub": user_id, "email": email}


# ── GET /auth/me ──────────────────────────────────────────────


class TestMe:
    """GET /api/v1/auth/me"""

    def test_me_returns_user_info(self):
        """유효한 JWT로 요청하면 유저 정보를 반환한다."""
        from app.api.deps import get_current_user
        from app.main import app

        user = _make_user()

        async def override_get_current_user():
            return user

        app.dependency_overrides[get_current_user] = override_get_current_user
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer faketoken"})
            assert resp.status_code == 200
            body = resp.json()
            assert body["email"] == user.email
            assert "needs_password_reset" in body
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_me_without_token_returns_401(self):
        """토큰 없이 요청하면 401을 반환한다."""
        from app.main import app

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401


# ── POST /auth/sync-profile ───────────────────────────────────


class TestSyncProfile:
    """POST /api/v1/auth/sync-profile"""

    def test_sync_profile_creates_new_user(self):
        """신규 유저 JWT로 요청하면 users + user_settings 행을 생성한다."""
        from app.api.deps import get_token_payload
        from app.database import get_db
        from app.main import app

        user_id = str(uuid.uuid4())
        db = _make_mock_db(existing_user=None)

        async def override_db():
            yield db

        async def override_payload():
            return _valid_jwt_payload(user_id)

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_token_payload] = override_payload
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post(
                    "/api/v1/auth/sync-profile",
                    json={"display_name": "새유저"},
                    headers={"Authorization": "Bearer faketoken"},
                )
            assert resp.status_code == 200
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_token_payload, None)

    def test_sync_profile_invalid_payload_returns_401(self):
        """sub 또는 email 없는 페이로드로 요청하면 401을 반환한다 (line 36)."""
        from app.api.deps import get_token_payload
        from app.main import app

        async def override_payload():
            return {"sub": None, "email": None}

        app.dependency_overrides[get_token_payload] = override_payload
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post(
                    "/api/v1/auth/sync-profile",
                    json={"display_name": "테스트"},
                    headers={"Authorization": "Bearer faketoken"},
                )
            assert resp.status_code == 401
        finally:
            app.dependency_overrides.pop(get_token_payload, None)

    def test_sync_profile_idempotent(self):
        """이미 존재하는 유저 JWT로 요청하면 기존 유저를 반환한다 (200)."""
        from app.api.deps import get_token_payload
        from app.database import get_db
        from app.main import app

        user_id = str(uuid.uuid4())
        existing = _make_user()
        db = _make_mock_db(existing_user=existing)

        async def override_db():
            yield db

        async def override_payload():
            return _valid_jwt_payload(user_id)

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_token_payload] = override_payload
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post(
                    "/api/v1/auth/sync-profile",
                    json={"display_name": None},
                    headers={"Authorization": "Bearer faketoken"},
                )
            assert resp.status_code == 200
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_token_payload, None)


# ── POST /auth/find-account ───────────────────────────────────


class TestFindAccount:
    """POST /api/v1/auth/find-account"""

    @pytest.mark.asyncio
    async def test_find_account_returns_fixed_message(self, override_settings):
        """display_name 검색 시 사용자 열거 방지를 위해 항상 고정 메시지를 반환한다."""
        from starlette.requests import Request

        from app.api.v1.auth import find_account
        from app.schemas.auth import FindAccountRequest

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/auth/find-account",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 12345),
        }
        mock_req = Request(scope=scope)
        body = FindAccountRequest(display_name="홍길동")

        # __wrapped__ bypasses @limiter.limit decorator (slowapi uses @wraps)
        result = await find_account.__wrapped__(request=mock_req, req=body)

        assert result.message
        assert len(result.message) > 0
