"""Auth API 엔드포인트 통합 테스트 (FastAPI TestClient + DB mock)."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


# ── 공통 헬퍼 ────────────────────────────────────────────────

def _make_mock_db(existing_user=None):
    """DB 동작을 커스터마이징할 수 있는 mock 세션 반환."""
    from unittest.mock import AsyncMock, MagicMock
    from sqlalchemy.ext.asyncio import AsyncSession

    db = AsyncMock(spec=AsyncSession)
    db.scalar = AsyncMock(return_value=existing_user)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()

    async def _refresh(obj):
        if hasattr(obj, "id") and obj.id is None:
            import uuid as _uuid
            obj.id = _uuid.uuid4()

    db.refresh = AsyncMock(side_effect=_refresh)
    return db


def _make_user(email="test@example.com", password_hash="hashed"):
    """테스트용 User 유사 객체."""
    return SimpleNamespace(
        id=uuid.uuid4(),
        email=email,
        hashed_password=password_hash,
        display_name="테스트 유저",
        is_active=True,
    )


# ── Register ─────────────────────────────────────────────────

class TestRegister:
    """POST /api/v1/auth/register"""

    def test_register_success(self):
        """신규 이메일로 등록하면 201과 유저 정보를 반환한다."""
        from app.main import app
        from app.database import get_db

        new_user = _make_user()
        db = _make_mock_db(existing_user=None)

        async def override_get_db():
            yield db

        app.dependency_overrides[get_db] = override_get_db
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post("/api/v1/auth/register", json={
                    "email": "new@example.com",
                    "password": "secure123",
                    "display_name": "테스터",
                })
            assert resp.status_code == 201
            body = resp.json()
            assert body["email"] == "new@example.com"
        finally:
            app.dependency_overrides.pop(get_db, None)

    def test_register_duplicate_email_returns_400(self):
        """이미 존재하는 이메일로 등록 시도하면 400을 반환한다."""
        from app.main import app
        from app.database import get_db

        existing = _make_user(email="dup@example.com")
        db = _make_mock_db(existing_user=existing)

        async def override_get_db():
            yield db

        app.dependency_overrides[get_db] = override_get_db
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post("/api/v1/auth/register", json={
                    "email": "dup@example.com",
                    "password": "pass123",
                    "display_name": "중복",
                })
            assert resp.status_code == 400
            assert "이메일" in resp.json()["detail"]
        finally:
            app.dependency_overrides.pop(get_db, None)


# ── Login ─────────────────────────────────────────────────────

class TestLogin:
    """POST /api/v1/auth/login"""

    def test_login_success_returns_tokens(self):
        """올바른 자격증명으로 로그인하면 access/refresh 토큰을 반환한다."""
        from app.main import app
        from app.database import get_db
        from app.services.auth_service import hash_password

        user = _make_user(email="user@example.com", password_hash=hash_password("correct_pw"))
        db = _make_mock_db(existing_user=user)

        async def override_get_db():
            yield db

        app.dependency_overrides[get_db] = override_get_db
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post("/api/v1/auth/login", json={
                    "email": "user@example.com",
                    "password": "correct_pw",
                })
            assert resp.status_code == 200
            body = resp.json()
            assert "access_token" in body
            assert "refresh_token" in body
        finally:
            app.dependency_overrides.pop(get_db, None)

    def test_login_wrong_password_returns_401(self):
        """잘못된 비밀번호로 로그인 시도하면 401을 반환한다."""
        from app.main import app
        from app.database import get_db
        from app.services.auth_service import hash_password

        user = _make_user(email="user@example.com", password_hash=hash_password("correct_pw"))
        db = _make_mock_db(existing_user=user)

        async def override_get_db():
            yield db

        app.dependency_overrides[get_db] = override_get_db
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post("/api/v1/auth/login", json={
                    "email": "user@example.com",
                    "password": "wrong_pw",
                })
            assert resp.status_code == 401
        finally:
            app.dependency_overrides.pop(get_db, None)

    def test_login_nonexistent_user_returns_401(self):
        """존재하지 않는 유저로 로그인 시도하면 401을 반환한다."""
        from app.main import app
        from app.database import get_db

        db = _make_mock_db(existing_user=None)

        async def override_get_db():
            yield db

        app.dependency_overrides[get_db] = override_get_db
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post("/api/v1/auth/login", json={
                    "email": "ghost@example.com",
                    "password": "any_pw",
                })
            assert resp.status_code == 401
        finally:
            app.dependency_overrides.pop(get_db, None)


# ── Token Refresh ─────────────────────────────────────────────

class TestRefresh:
    """POST /api/v1/auth/refresh"""

    def test_valid_refresh_token_returns_new_tokens(self):
        """유효한 refresh 토큰으로 요청하면 새 토큰 쌍을 반환한다."""
        from app.main import app
        from app.database import get_db
        from app.services.auth_service import create_refresh_token

        user_id = str(uuid.uuid4())
        user = _make_user()
        user.id = user_id  # type: ignore[assignment]
        db = _make_mock_db(existing_user=user)

        async def override_get_db():
            yield db

        app.dependency_overrides[get_db] = override_get_db
        try:
            refresh_token = create_refresh_token(user_id)
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
            assert resp.status_code == 200
            body = resp.json()
            assert "access_token" in body
        finally:
            app.dependency_overrides.pop(get_db, None)

    def test_invalid_refresh_token_returns_401(self):
        """잘못된 refresh 토큰으로 요청하면 401을 반환한다."""
        from app.main import app
        from app.database import get_db

        db = _make_mock_db()

        async def override_get_db():
            yield db

        app.dependency_overrides[get_db] = override_get_db
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post("/api/v1/auth/refresh", json={"refresh_token": "not.a.valid.token"})
            assert resp.status_code == 401
        finally:
            app.dependency_overrides.pop(get_db, None)

    def test_access_token_as_refresh_returns_401(self):
        """access 토큰을 refresh 엔드포인트에 사용하면 401을 반환한다."""
        from app.main import app
        from app.database import get_db
        from app.services.auth_service import create_access_token

        user_id = str(uuid.uuid4())
        db = _make_mock_db()

        async def override_get_db():
            yield db

        app.dependency_overrides[get_db] = override_get_db
        try:
            access_token = create_access_token(user_id)
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post("/api/v1/auth/refresh", json={"refresh_token": access_token})
            assert resp.status_code == 401
            assert "토큰" in resp.json()["detail"]
        finally:
            app.dependency_overrides.pop(get_db, None)
