"""API 의존성 함수 단위 테스트 (deps.py)."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException


def _make_user(user_id=None):
    return SimpleNamespace(
        id=user_id or uuid.uuid4(),
        email="test@example.com",
        is_active=True,
    )


class TestExtractToken:
    @pytest.mark.asyncio
    async def test_raises_401_when_no_authorization(self):
        from app.api.deps import get_current_user

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(authorization=None, db=AsyncMock())
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_raises_401_when_no_bearer_prefix(self):
        from app.api.deps import get_current_user

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(authorization="Token abc123", db=AsyncMock())
        assert exc_info.value.status_code == 401


class TestGetTokenPayload:
    @pytest.mark.asyncio
    async def test_returns_payload_for_valid_token(self, override_settings):
        from app.api.deps import get_token_payload

        mock_payload = {"sub": str(uuid.uuid4()), "email": "test@example.com"}
        with patch("app.api.deps.verify_supabase_token", return_value=mock_payload):
            result = await get_token_payload(authorization="Bearer valid_token")

        assert result == mock_payload

    @pytest.mark.asyncio
    async def test_raises_401_for_invalid_token(self, override_settings):
        from app.api.deps import get_token_payload

        with (
            patch("app.api.deps.verify_supabase_token", side_effect=ValueError("Invalid")),
            pytest.raises(HTTPException) as exc_info,
        ):
            await get_token_payload(authorization="Bearer invalid_token")

        assert exc_info.value.status_code == 401


class TestGetCurrentUser:
    @pytest.mark.asyncio
    async def test_raises_401_when_payload_has_no_sub(self, override_settings, mock_db):
        from app.api.deps import get_current_user

        with (
            patch("app.api.deps.verify_supabase_token", return_value={"email": "no_sub@test.com"}),
            pytest.raises(HTTPException) as exc_info,
        ):
            await get_current_user(authorization="Bearer token", db=mock_db)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_raises_401_when_user_not_found(self, override_settings, mock_db):
        from app.api.deps import get_current_user

        mock_db.scalar = AsyncMock(return_value=None)
        with (
            patch("app.api.deps.verify_supabase_token", return_value={"sub": str(uuid.uuid4())}),
            pytest.raises(HTTPException) as exc_info,
        ):
            await get_current_user(authorization="Bearer token", db=mock_db)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_returns_user_when_found(self, override_settings, mock_db):
        from app.api.deps import get_current_user

        user = _make_user()
        mock_db.scalar = AsyncMock(return_value=user)
        with patch("app.api.deps.verify_supabase_token", return_value={"sub": str(user.id)}):
            result = await get_current_user(authorization="Bearer token", db=mock_db)

        assert result is user


class TestGetOwnedResource:
    @pytest.mark.asyncio
    async def test_returns_resource_when_found(self, mock_db):
        from app.api.deps import get_owned_resource
        from app.models.asset import Transaction

        tx = SimpleNamespace(id=uuid.uuid4(), user_id=uuid.uuid4())
        mock_db.scalar = AsyncMock(return_value=tx)

        result = await get_owned_resource(Transaction, tx.id, tx.user_id, mock_db)
        assert result is tx

    @pytest.mark.asyncio
    async def test_raises_404_when_not_found(self, mock_db):
        from app.api.deps import get_owned_resource
        from app.models.asset import Transaction

        mock_db.scalar = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await get_owned_resource(Transaction, uuid.uuid4(), uuid.uuid4(), mock_db)

        assert exc_info.value.status_code == 404
