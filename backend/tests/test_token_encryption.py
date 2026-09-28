"""KIS/키움 access_token DB 저장 암호화 테스트.

App Key/Secret과 달리 KisToken/KiwoomToken.access_token은 과거 평문으로 저장됐다.
이 테스트는 (1) DB에 쓰는 값이 암호문인지, (2) 캐시/반환값은 여전히 평문인지,
(3) 마이그레이션 이전 평문 row를 만나도 안전하게 폴백하는지를 검증한다.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def patch_encryption_key(monkeypatch):
    """test_credential_service.py와 동일한 패턴 — settings 속성을 직접 패치."""
    import app.core.config as config_mod
    import app.services.credential_service as cs_mod

    test_key = "a" * 64
    monkeypatch.setattr(config_mod.settings, "kis_cred_encryption_key", test_key)
    monkeypatch.setattr(cs_mod.settings, "kis_cred_encryption_key", test_key)


class TestGetOrFetchTokenDecryption:
    """app/providers/_token_cache.py::get_or_fetch_token"""

    @pytest.mark.asyncio
    async def test_decrypts_encrypted_db_row_and_caches_plaintext(self):
        from app.providers._token_cache import get_or_fetch_token
        from app.services.credential_service import encrypt

        plaintext = "real-plaintext-access-token"
        row = SimpleNamespace(access_token=encrypt(plaintext), expires_at=datetime.now(UTC) + timedelta(hours=1))
        cache = AsyncMock()
        cache.get = AsyncMock(return_value=None)

        result = await get_or_fetch_token(
            "cache-key",
            cache,
            force_refresh=False,
            ttl_buffer=60,
            query_token_row=AsyncMock(return_value=row),
            fetch=AsyncMock(return_value="should-not-be-used"),
        )

        assert result == plaintext
        cache.setex.assert_awaited_once()
        assert cache.setex.await_args.args[2] == plaintext

    @pytest.mark.asyncio
    async def test_falls_back_to_fetch_on_legacy_plaintext_row(self):
        """암호화 적용 이전 저장된 평문 row는 decrypt 실패 → 캐시 미스로 간주하고 재발급."""
        from app.providers._token_cache import get_or_fetch_token

        legacy_plaintext_row = SimpleNamespace(
            access_token="legacy-plaintext-not-ciphertext",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        cache = AsyncMock()
        cache.get = AsyncMock(return_value=None)
        fetch = AsyncMock(return_value="freshly-issued-token")

        result = await get_or_fetch_token(
            "cache-key",
            cache,
            force_refresh=False,
            ttl_buffer=60,
            query_token_row=AsyncMock(return_value=legacy_plaintext_row),
            fetch=fetch,
        )

        assert result == "freshly-issued-token"
        fetch.assert_awaited_once()
        cache.setex.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cache_hit_short_circuits_without_touching_db(self):
        from app.providers._token_cache import get_or_fetch_token

        cache = AsyncMock()
        cache.get = AsyncMock(return_value="cached-plaintext-token")
        query_token_row = AsyncMock()

        result = await get_or_fetch_token(
            "cache-key",
            cache,
            force_refresh=False,
            ttl_buffer=60,
            query_token_row=query_token_row,
            fetch=AsyncMock(),
        )

        assert result == "cached-plaintext-token"
        query_token_row.assert_not_awaited()


class TestKisFetchAndStoreTokenEncryption:
    @pytest.mark.asyncio
    async def test_stores_encrypted_token_but_returns_plaintext(self):
        from app.kis.auth import _fetch_and_store_token
        from app.services.credential_service import decrypt

        fake_response = MagicMock()
        fake_response.raise_for_status = MagicMock()
        fake_response.json.return_value = {"access_token": "plain-kis-token", "expires_in": 86400}
        fake_client = MagicMock()
        fake_client.post = AsyncMock(return_value=fake_response)

        cache = AsyncMock()
        db = AsyncMock()

        with patch("app.kis.auth._get_client", return_value=fake_client):
            result = await _fetch_and_store_token(
                "app-key",
                "app-secret",
                is_mock=True,
                cache=cache,
                db=db,
                user_id=str(uuid.uuid4()),
                account_id=None,
            )

        assert result == "plain-kis-token"
        cache.setex.assert_awaited_once()
        assert cache.setex.await_args.args[2] == "plain-kis-token"

        db.execute.assert_awaited_once()
        stmt = db.execute.await_args.args[0]
        stored_value = stmt.compile().params["access_token"]
        assert stored_value != "plain-kis-token"
        assert decrypt(stored_value) == "plain-kis-token"


class TestKiwoomFetchAndStoreTokenEncryption:
    @pytest.mark.asyncio
    async def test_stores_encrypted_token_but_returns_plaintext(self):
        from app.kiwoom.auth import _fetch_and_store_token
        from app.services.credential_service import decrypt

        fake_response = MagicMock()
        fake_response.status_code = 200
        fake_response.raise_for_status = MagicMock()
        fake_response.json.return_value = {
            "return_code": 0,
            "token": "plain-kiwoom-token",
            "expires_dt": (datetime.now(UTC) + timedelta(hours=1)).strftime("%Y%m%d%H%M%S"),
        }
        fake_client = MagicMock()
        fake_client.post = AsyncMock(return_value=fake_response)

        cache = AsyncMock()
        db = AsyncMock()

        with patch("app.kiwoom.auth._get_client", return_value=fake_client):
            result = await _fetch_and_store_token(
                "app-key",
                "app-secret",
                is_mock=True,
                cache=cache,
                db=db,
                user_id=str(uuid.uuid4()),
                account_id=str(uuid.uuid4()),
            )

        assert result == "plain-kiwoom-token"
        db.execute.assert_awaited_once()
        stmt = db.execute.await_args.args[0]
        stored_value = stmt.compile().params["access_token"]
        assert stored_value != "plain-kiwoom-token"
        assert decrypt(stored_value) == "plain-kiwoom-token"


class TestPromoteUserTokenToAccount:
    @pytest.mark.asyncio
    async def test_copies_already_encrypted_ciphertext_as_is(self):
        from app.kis.auth import promote_user_token_to_account
        from app.services.credential_service import encrypt

        encrypted = encrypt("promoted-plaintext-token")
        row = SimpleNamespace(access_token=encrypted, expires_at=datetime.now(UTC) + timedelta(hours=1))
        db = AsyncMock()
        db.scalar = AsyncMock(return_value=row)
        cache = AsyncMock()

        result = await promote_user_token_to_account(str(uuid.uuid4()), str(uuid.uuid4()), False, cache, db)

        assert result is True
        stmt = db.execute.await_args.args[0]
        assert stmt.compile().params["access_token"] == encrypted
        cache.setex.assert_awaited_once()
        assert cache.setex.await_args.args[2] == "promoted-plaintext-token"

    @pytest.mark.asyncio
    async def test_encrypts_legacy_plaintext_row_on_promotion(self):
        """마이그레이션 이전 평문 row를 승격시킬 때도 새 row는 암호화되어야 한다."""
        from app.kis.auth import promote_user_token_to_account
        from app.services.credential_service import decrypt

        row = SimpleNamespace(access_token="legacy-plaintext-token", expires_at=datetime.now(UTC) + timedelta(hours=1))
        db = AsyncMock()
        db.scalar = AsyncMock(return_value=row)
        cache = AsyncMock()

        result = await promote_user_token_to_account(str(uuid.uuid4()), str(uuid.uuid4()), False, cache, db)

        assert result is True
        stmt = db.execute.await_args.args[0]
        stored_value = stmt.compile().params["access_token"]
        assert stored_value != "legacy-plaintext-token"
        assert decrypt(stored_value) == "legacy-plaintext-token"
        assert cache.setex.await_args.args[2] == "legacy-plaintext-token"


class TestStoreToken:
    """app/providers/_token_cache.py::store_token — KIS/키움/토스 공용 발급 후 저장."""

    @pytest.mark.asyncio
    async def test_cache_ttl_subtracts_buffer_and_upsert_uses_conflict_target(self):
        from sqlalchemy.dialects import postgresql

        from app.constants import TOKEN_CACHE_TTL_BUFFER
        from app.models.token import KisToken
        from app.providers._token_cache import store_token
        from app.services.credential_service import decrypt

        cache = AsyncMock()
        db = AsyncMock()
        expires_at = datetime.now(UTC) + timedelta(hours=24)

        await store_token(
            cache,
            db,
            cache_key="k",
            access_token="plain",
            expires_at=expires_at,
            model=KisToken,
            values={"user_id": str(uuid.uuid4()), "account_id": None, "is_mock_mode": False},
            index_elements=["user_id", "is_mock_mode"],
            index_where=KisToken.account_id.is_(None),
        )

        key, ttl, value = cache.setex.await_args.args
        assert (key, value) == ("k", "plain")
        assert 86400 - TOKEN_CACHE_TTL_BUFFER - 2 <= ttl <= 86400 - TOKEN_CACHE_TTL_BUFFER

        stmt = db.execute.await_args.args[0]
        sql = str(stmt.compile(dialect=postgresql.dialect()))
        assert "ON CONFLICT (user_id, is_mock_mode) WHERE" in sql
        assert decrypt(stmt.compile().params["access_token"]) == "plain"
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_short_lived_token_ttl_floors_at_60(self):
        from app.models.token import TossToken
        from app.providers._token_cache import store_token

        cache = AsyncMock()
        await store_token(
            cache,
            AsyncMock(),
            cache_key="k",
            access_token="plain",
            expires_at=datetime.now(UTC) + timedelta(seconds=30),
            model=TossToken,
            values={"user_id": str(uuid.uuid4()), "account_id": str(uuid.uuid4())},
            index_elements=["account_id"],
        )
        assert cache.setex.await_args.args[1] == 60
