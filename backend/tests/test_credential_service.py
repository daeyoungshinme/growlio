"""AES-256-GCM 암호화/복호화 단위 테스트."""

import pytest


@pytest.fixture(autouse=True)
def patch_encryption_key(monkeypatch):
    """KIS_CRED_ENCRYPTION_KEY를 테스트용 값으로 직접 패치한다.

    importlib.reload(app.core.config) 대신 속성 직접 패치를 사용한다.
    reload는 새 Settings() 인스턴스를 생성해 다른 모듈의 settings 참조를 끊어
    monkeypatch 격리가 깨지는 부작용이 있다.
    """
    import app.core.config as config_mod
    import app.services.credential_service as cs_mod

    test_key = "a" * 64
    monkeypatch.setattr(config_mod.settings, "kis_cred_encryption_key", test_key)
    # credential_service도 같은 settings 객체를 사용하지만, 혹시 다른 참조가 있을 경우 패치
    monkeypatch.setattr(cs_mod.settings, "kis_cred_encryption_key", test_key)


@pytest.mark.parametrize(
    "plaintext",
    [
        "simple-api-key",
        "a" * 200,  # 긴 문자열
        "한국어-키값-테스트",  # 유니코드
        "special!@#$%^&*()",
    ],
)
def test_encrypt_decrypt_roundtrip(plaintext):
    """암호화 후 복호화하면 원문이 복원된다."""
    from app.services.credential_service import decrypt, encrypt

    ciphertext = encrypt(plaintext)
    assert ciphertext != plaintext
    assert decrypt(ciphertext) == plaintext


def test_encrypt_produces_different_ciphertext_each_time():
    """같은 평문도 매번 다른 암호문을 생성한다 (nonce 무작위)."""
    from app.services.credential_service import decrypt, encrypt

    plaintext = "same-key-value"
    c1 = encrypt(plaintext)
    c2 = encrypt(plaintext)
    assert c1 != c2
    assert decrypt(c1) == decrypt(c2) == plaintext


def test_decrypt_invalid_ciphertext_raises():
    """손상된 암호문 복호화 시 예외 발생."""
    from app.services.credential_service import decrypt

    with pytest.raises(ValueError, match="Decryption failed"):
        decrypt("invalid_hex_data_that_cannot_be_decrypted_0000")


def test_ciphertext_is_hex_string():
    """암호문이 hex 문자열 형태여야 한다."""
    from app.services.credential_service import encrypt

    ciphertext = encrypt("test-value")
    assert all(c in "0123456789abcdef" for c in ciphertext.lower())


class TestGetKisUserCredentials:
    """get_kis_user_credentials 함수 커버 (lines 71-94)."""

    @pytest.mark.asyncio
    async def test_returns_none_when_no_account(self):
        """KIS 계좌 없으면 None 반환."""
        import uuid
        from unittest.mock import AsyncMock

        from app.services.credential_service import get_kis_user_credentials

        db = AsyncMock()
        db.scalar = AsyncMock(return_value=None)
        result = await get_kis_user_credentials(uuid.uuid4(), db)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_credentials_on_success(self):
        """계좌 있고 토큰 발급 성공 시 자격증명 반환 (lines 71-91)."""
        import uuid
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch

        from app.services.credential_service import encrypt, get_kis_user_credentials

        raw_key = "test-app-key"
        raw_secret = "test-app-secret"
        account = SimpleNamespace(
            id=uuid.uuid4(),
            kis_app_key=encrypt(raw_key),
            kis_app_secret=encrypt(raw_secret),
            is_mock_mode=False,
        )

        db = AsyncMock()
        db.scalar = AsyncMock(return_value=account)

        with (
            patch("app.kis.auth.get_access_token", AsyncMock(return_value="fake-token")),
            patch("app.core.cache_store.get_cache_store", AsyncMock(return_value=AsyncMock())),
        ):
            result = await get_kis_user_credentials(uuid.uuid4(), db)

        assert result is not None
        assert result["app_key"] == raw_key
        assert result["access_token"] == "fake-token"

    @pytest.mark.asyncio
    async def test_returns_none_on_token_error(self):
        """토큰 발급 실패 시 None 반환 및 경고 로그 (lines 92-94)."""
        import uuid
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch

        from app.services.credential_service import encrypt, get_kis_user_credentials

        account = SimpleNamespace(
            id=uuid.uuid4(),
            kis_app_key=encrypt("key"),
            kis_app_secret=encrypt("secret"),
            is_mock_mode=False,
        )

        db = AsyncMock()
        db.scalar = AsyncMock(return_value=account)

        with (
            patch("app.kis.auth.get_access_token", AsyncMock(side_effect=Exception("token error"))),
            patch("app.core.cache_store.get_cache_store", AsyncMock(return_value=AsyncMock())),
        ):
            result = await get_kis_user_credentials(uuid.uuid4(), db)

        assert result is None
