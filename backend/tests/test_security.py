"""보안 접근 제어 테스트.

- 교차 유저 계좌 접근 → 404
- 유효하지 않은 토큰 → 401
- 만료 토큰(leeway 초과) → 401 (서비스 단위 테스트)
"""

import time
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession


def _make_user(user_id=None, email="user@example.com"):
    return SimpleNamespace(
        id=user_id or uuid.uuid4(),
        email=email,
        display_name="테스트유저",
        is_active=True,
        needs_password_reset=False,
    )


# ── 교차 유저 접근 제어 ───────────────────────────────────────

class TestCrossUserAccess:
    """다른 유저의 계좌에 접근하면 404를 반환한다."""

    def test_get_other_users_account_returns_404(self):
        """User A가 User B 소유 account_id로 GET 요청 → 404."""
        from app.main import app
        from app.database import get_db
        from app.api.deps import get_current_user

        user_a = _make_user()

        # DB가 None을 반환 → _get_owned_account가 404를 발생시킴
        db = AsyncMock(spec=AsyncSession)
        db.scalar = AsyncMock(return_value=None)

        async def override_user():
            return user_a

        async def override_db():
            yield db

        app.dependency_overrides[get_current_user] = override_user
        app.dependency_overrides[get_db] = override_db
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.get(
                    f"/api/v1/assets/{uuid.uuid4()}",
                    headers={"Authorization": "Bearer faketoken"},
                )
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)

    def test_get_own_account_returns_200_or_404_based_on_db(self):
        """User A가 본인 계좌를 DB에서 찾으면 200, 없으면 404 — 소유 여부 분기 확인."""
        from app.main import app
        from app.database import get_db
        from app.api.deps import get_current_user

        user_a = _make_user()
        account_id = uuid.uuid4()

        from datetime import datetime, timezone

        own_account = SimpleNamespace(
            id=account_id,
            user_id=user_a.id,
            name="내 계좌",
            asset_type="STOCK_KIS",
            data_source="KIS_API",
            institution=None,
            is_active=True,
            is_mock_mode=True,
            kis_account_no="12345678-01",
            kiwoom_account_no=None,
            deposit_krw=None,
            manual_amount=None,
            manual_positions=None,
            manual_currency="KRW",
            manual_updated_at=None,
            real_estate_details=None,
            include_in_total=True,
            sort_order=0,
            notes=None,
            created_at=datetime.now(timezone.utc),
            ob_fintech_use_no=None,
            kis_app_key=None,
            kis_app_secret=None,
            kiwoom_app_key=None,
            kiwoom_app_secret=None,
        )

        db = AsyncMock(spec=AsyncSession)
        db.scalar = AsyncMock(return_value=own_account)

        async def override_user():
            return user_a

        async def override_db():
            yield db

        app.dependency_overrides[get_current_user] = override_user
        app.dependency_overrides[get_db] = override_db
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.get(
                    f"/api/v1/assets/{account_id}",
                    headers={"Authorization": "Bearer faketoken"},
                )
            assert resp.status_code == 200
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)


# ── 토큰 검증 ────────────────────────────────────────────────

class TestTokenValidation:
    """유효하지 않은 토큰은 401을 반환한다."""

    def test_request_without_token_returns_401(self):
        """Authorization 헤더 없이 인증 필요 엔드포인트 요청 → 401."""
        from app.main import app

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/assets")
        assert resp.status_code == 401

    def test_invalid_token_format_returns_401(self):
        """잘못된 JWT 토큰으로 요청 → verify_supabase_token이 ValueError → 401."""
        from app.main import app

        with patch("app.api.deps.verify_supabase_token", side_effect=ValueError("Invalid token")):
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.get(
                    "/api/v1/assets",
                    headers={"Authorization": "Bearer totally.invalid.token"},
                )
        assert resp.status_code == 401

    def test_malformed_bearer_header_returns_401(self):
        """Bearer 접두사 없는 Authorization 헤더 → 401."""
        from app.main import app

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get(
                "/api/v1/assets",
                headers={"Authorization": "Basic dXNlcjpwYXNz"},
            )
        assert resp.status_code == 401


# ── verify_supabase_token 단위 테스트 ─────────────────────────

class TestVerifySupabaseToken:
    """auth_service.verify_supabase_token 단위 테스트."""

    def test_expired_token_raises_value_error(self):
        """만료된 토큰(leeway 5s 초과)은 ValueError('Token expired')를 발생시킨다."""
        import jwt as pyjwt
        from app.services.auth_service import verify_supabase_token

        secret = "test-hmac-secret"
        expired_at = int(time.time()) - 100  # 100초 전 만료

        token = pyjwt.encode(
            {"sub": "user-123", "exp": expired_at},
            secret,
            algorithm="HS256",
        )

        mock_signing_key = MagicMock()
        mock_signing_key.key = secret
        mock_signing_key.algorithm_name = "HS256"

        mock_jwks = MagicMock()
        mock_jwks.get_signing_key_from_jwt.return_value = mock_signing_key

        with patch("app.services.auth_service._get_jwks_client", return_value=mock_jwks):
            with pytest.raises(ValueError, match="Token expired"):
                verify_supabase_token(token)

    def test_valid_token_returns_payload(self):
        """유효한 토큰은 payload dict를 반환한다."""
        import jwt as pyjwt
        from app.services.auth_service import verify_supabase_token

        secret = "test-hmac-secret"
        future = int(time.time()) + 3600
        user_id = str(uuid.uuid4())

        token = pyjwt.encode(
            {"sub": user_id, "email": "test@example.com", "exp": future},
            secret,
            algorithm="HS256",
        )

        mock_signing_key = MagicMock()
        mock_signing_key.key = secret
        mock_signing_key.algorithm_name = "HS256"

        mock_jwks = MagicMock()
        mock_jwks.get_signing_key_from_jwt.return_value = mock_signing_key

        with patch("app.services.auth_service._get_jwks_client", return_value=mock_jwks):
            payload = verify_supabase_token(token)

        assert payload["sub"] == user_id
        assert payload["email"] == "test@example.com"

    def test_token_with_invalid_signature_raises_value_error(self):
        """서명이 다른 토큰은 ValueError를 발생시킨다."""
        import jwt as pyjwt
        from app.services.auth_service import verify_supabase_token

        token = pyjwt.encode(
            {"sub": "user-123", "exp": int(time.time()) + 3600},
            "wrong-secret",
            algorithm="HS256",
        )

        mock_signing_key = MagicMock()
        mock_signing_key.key = "correct-secret"
        mock_signing_key.algorithm_name = "HS256"

        mock_jwks = MagicMock()
        mock_jwks.get_signing_key_from_jwt.return_value = mock_signing_key

        with patch("app.services.auth_service._get_jwks_client", return_value=mock_jwks):
            with pytest.raises(ValueError):
                verify_supabase_token(token)
