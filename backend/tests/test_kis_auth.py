"""kis/auth.py 단위 테스트 — 토큰 발급 방어 로직 + 유저 레벨 토큰 승격(promote_user_token_to_account)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.exceptions import ProviderTokenError
from app.kis.auth import _fetch_and_store_token, promote_user_token_to_account


class TestFetchAndStoreTokenMissingAccessToken:
    @pytest.mark.asyncio
    async def test_raises_provider_token_error_when_access_token_missing(self, override_settings, mock_redis, mock_db):
        """KIS가 200 OK와 함께 에러 바디(access_token 없음)를 반환하면 KeyError 대신
        명확한 ProviderTokenError를 발생시켜야 한다."""
        response = httpx.Response(
            200,
            json={"msg_cd": "EGW00133", "msg1": "접근토큰 발급 잠시 후 다시 시도하세요(1분당 1회)"},
            request=httpx.Request("POST", "https://example.com/oauth2/tokenP"),
        )
        client = AsyncMock()
        client.post = AsyncMock(return_value=response)

        with (
            patch("app.kis.auth._get_client", return_value=client),
            pytest.raises(ProviderTokenError, match="접근토큰 발급"),
        ):
            await _fetch_and_store_token(
                "app-key",
                "app-secret",
                is_mock=True,
                redis=mock_redis,
                db=mock_db,
                user_id=str(uuid.uuid4()),
                account_id=None,
            )


class TestPromoteUserTokenToAccount:
    @pytest.mark.asyncio
    async def test_promotes_valid_user_level_token(self, override_settings, mock_redis, mock_db):
        user_id = str(uuid.uuid4())
        account_id = str(uuid.uuid4())
        token_row = SimpleNamespace(
            access_token="verified-token",
            expires_at=datetime.now(UTC) + timedelta(hours=12),
        )
        mock_db.scalar = AsyncMock(return_value=token_row)
        mock_db.execute = AsyncMock()
        mock_db.commit = AsyncMock()

        result = await promote_user_token_to_account(user_id, account_id, True, mock_redis, mock_db)

        assert result is True
        mock_db.execute.assert_awaited_once()
        mock_redis.setex.assert_awaited_once()
        args, _ = mock_redis.setex.await_args
        assert account_id in args[0]
        assert args[2] == "verified-token"

    @pytest.mark.asyncio
    async def test_returns_false_when_no_user_level_token(self, override_settings, mock_redis, mock_db):
        mock_db.scalar = AsyncMock(return_value=None)
        mock_db.execute = AsyncMock()

        result = await promote_user_token_to_account(str(uuid.uuid4()), str(uuid.uuid4()), True, mock_redis, mock_db)

        assert result is False
        mock_db.execute.assert_not_awaited()
        mock_redis.setex.assert_not_awaited()
