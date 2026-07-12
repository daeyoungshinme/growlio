"""auth_service.py 단위 테스트 — JWT 검증 엣지케이스."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


class TestGetJwksClient:
    def test_returns_pyjwkclient_instance(self):
        """_get_jwks_client은 PyJWKClient 인스턴스를 반환한다 (lazy init)."""
        import app.services.auth_service as svc

        # 싱글톤 초기화 전 상태로 리셋
        svc._jwks_client = None
        with patch("app.services.auth_service.PyJWKClient") as mock_cls:
            mock_cls.return_value = MagicMock(name="jwks_client_instance")
            client = svc._get_jwks_client()
            assert client is mock_cls.return_value
            mock_cls.assert_called_once()

    def test_returns_cached_instance_on_second_call(self):
        """두 번 호출해도 새 인스턴스를 생성하지 않는다."""
        import app.services.auth_service as svc

        svc._jwks_client = None
        with patch("app.services.auth_service.PyJWKClient") as mock_cls:
            mock_cls.return_value = MagicMock(name="cached_jwks")
            first = svc._get_jwks_client()
            second = svc._get_jwks_client()
            assert first is second
            mock_cls.assert_called_once()  # 두 번 호출해도 생성자는 1회만


class TestVerifySupabaseToken:
    def test_raises_value_error_on_jwks_fetch_failure(self):
        """JWKS 페치 실패(네트워크 에러 등) 시 ValueError 발생."""
        from app.services.auth_service import verify_supabase_token

        with patch("app.services.auth_service._get_jwks_client") as mock_getter:
            mock_getter.return_value.get_signing_key_from_jwt.side_effect = RuntimeError("connection refused")
            with pytest.raises(ValueError, match="Token verification failed"):
                verify_supabase_token("any.token.value")


class TestVerifyPassword:
    @pytest.mark.asyncio
    async def test_returns_true_on_200(self, monkeypatch):
        """Supabase password grant가 200을 반환하면 True."""
        from app.services.auth_service import verify_password

        monkeypatch.setattr("app.config.settings.supabase_project_url", "https://proj.supabase.co")
        monkeypatch.setattr("app.config.settings.supabase_anon_key", "anon-key")

        async def fake_post(self, url, params=None, headers=None, json=None, **kwargs):
            assert params == {"grant_type": "password"}
            assert headers["apikey"] == "anon-key"
            return httpx.Response(200, request=httpx.Request("POST", url))

        with patch("httpx.AsyncClient.post", new=fake_post):
            assert await verify_password("user@example.com", "correct") is True

    @pytest.mark.asyncio
    async def test_returns_false_on_400(self, monkeypatch):
        """잘못된 비밀번호면 Supabase가 400을 반환하고 False로 매핑된다."""
        from app.services.auth_service import verify_password

        monkeypatch.setattr("app.config.settings.supabase_project_url", "https://proj.supabase.co")
        monkeypatch.setattr("app.config.settings.supabase_anon_key", "anon-key")

        async def fake_post(self, url, **kwargs):
            return httpx.Response(400, request=httpx.Request("POST", url))

        with patch("httpx.AsyncClient.post", new=fake_post):
            assert await verify_password("user@example.com", "wrong") is False

    @pytest.mark.asyncio
    async def test_raises_on_network_error(self, monkeypatch):
        """네트워크 오류는 삼키지 않고 그대로 전파한다."""
        from app.services.auth_service import verify_password

        monkeypatch.setattr("app.config.settings.supabase_project_url", "https://proj.supabase.co")

        with (
            patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=httpx.ConnectError("refused"))),
            pytest.raises(httpx.ConnectError),
        ):
            await verify_password("user@example.com", "pw")


class TestDeleteSupabaseUser:
    @pytest.mark.asyncio
    async def test_calls_admin_api_with_service_role_key(self, monkeypatch):
        """Supabase Admin API를 service role key로 호출한다."""
        from app.services.auth_service import delete_supabase_user

        monkeypatch.setattr("app.config.settings.supabase_project_url", "https://proj.supabase.co")
        monkeypatch.setattr("app.config.settings.supabase_service_role_key", "service-role-key")

        captured = {}

        async def fake_delete(self, url, headers=None, **kwargs):
            captured["url"] = url
            captured["headers"] = headers
            return httpx.Response(200, request=httpx.Request("DELETE", url))

        with patch("httpx.AsyncClient.delete", new=fake_delete):
            await delete_supabase_user("user-id-123")

        assert captured["url"].endswith("/auth/v1/admin/users/user-id-123")
        assert captured["headers"]["apikey"] == "service-role-key"
        assert captured["headers"]["Authorization"] == "Bearer service-role-key"

    @pytest.mark.asyncio
    async def test_raises_on_error_status(self, monkeypatch):
        """Admin API가 에러 상태를 반환하면 예외를 전파한다."""
        from app.services.auth_service import delete_supabase_user

        monkeypatch.setattr("app.config.settings.supabase_project_url", "https://proj.supabase.co")

        async def fake_delete(self, url, **kwargs):
            return httpx.Response(404, request=httpx.Request("DELETE", url))

        with (
            patch("httpx.AsyncClient.delete", new=fake_delete),
            pytest.raises(httpx.HTTPStatusError),
        ):
            await delete_supabase_user("missing-user")


class TestCredentialServiceGetKey:
    def test_raises_if_key_not_32_bytes(self, monkeypatch):
        """decryption 키가 32바이트가 아니면 ValueError 발생."""
        import app.config as config_mod
        import app.services.credential_service as cs_mod

        # 10바이트 (20자 hex) — unhexlify 후 10바이트여서 != 32 에러
        short_hex = "aa" * 10
        monkeypatch.setattr(config_mod.settings, "kis_cred_encryption_key", short_hex)
        monkeypatch.setattr(cs_mod.settings, "kis_cred_encryption_key", short_hex)

        with pytest.raises(ValueError, match="32바이트"):
            cs_mod._get_key()
