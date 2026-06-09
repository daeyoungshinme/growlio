"""AES-256-GCM 암호화/복호화 단위 테스트."""

import pytest


@pytest.fixture(autouse=True)
def patch_encryption_key(monkeypatch):
    """KIS_CRED_ENCRYPTION_KEY를 테스트용 값으로 직접 패치한다.

    importlib.reload(app.config) 대신 속성 직접 패치를 사용한다.
    reload는 새 Settings() 인스턴스를 생성해 다른 모듈의 settings 참조를 끊어
    monkeypatch 격리가 깨지는 부작용이 있다.
    """
    import app.config as config_mod
    import app.services.credential_service as cs_mod

    test_key = "a" * 64
    monkeypatch.setattr(config_mod.settings, "kis_cred_encryption_key", test_key)
    # credential_service도 같은 settings 객체를 사용하지만, 혹시 다른 참조가 있을 경우 패치
    monkeypatch.setattr(cs_mod.settings, "kis_cred_encryption_key", test_key)


@pytest.mark.parametrize("plaintext", [
    "simple-api-key",
    "a" * 200,        # 긴 문자열
    "한국어-키값-테스트",  # 유니코드
    "special!@#$%^&*()",
])
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

    with pytest.raises(Exception):
        decrypt("invalid_hex_data_that_cannot_be_decrypted_0000")


def test_ciphertext_is_hex_string():
    """암호문이 hex 문자열 형태여야 한다."""
    from app.services.credential_service import encrypt

    ciphertext = encrypt("test-value")
    assert all(c in "0123456789abcdef" for c in ciphertext.lower())
