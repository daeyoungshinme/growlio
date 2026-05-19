"""AES-256-GCM 암호화/복호화 단위 테스트."""

import pytest

from app.services import credential_service


@pytest.mark.parametrize("plaintext", [
    "simple-api-key",
    "a" * 200,        # 긴 문자열
    "한국어-키값-테스트",  # 유니코드
    "special!@#$%^&*()",
])
def test_encrypt_decrypt_roundtrip(plaintext, override_settings):
    """암호화 후 복호화하면 원문이 복원된다."""
    # config를 재로드하도록 강제 (monkeypatch 적용 후)
    import importlib
    import app.config
    importlib.reload(app.config)
    import app.services.credential_service as cs
    importlib.reload(cs)

    ciphertext = cs.encrypt(plaintext)
    assert ciphertext != plaintext
    assert cs.decrypt(ciphertext) == plaintext


def test_encrypt_produces_different_ciphertext_each_time(override_settings):
    """같은 평문도 매번 다른 암호문을 생성한다 (nonce 무작위)."""
    import importlib
    import app.config
    importlib.reload(app.config)
    import app.services.credential_service as cs
    importlib.reload(cs)

    plaintext = "same-key-value"
    c1 = cs.encrypt(plaintext)
    c2 = cs.encrypt(plaintext)
    assert c1 != c2  # nonce가 다르므로 암호문도 다름
    # 하지만 복호화하면 동일한 값
    assert cs.decrypt(c1) == cs.decrypt(c2) == plaintext


def test_decrypt_invalid_ciphertext_raises(override_settings):
    """손상된 암호문 복호화 시 예외 발생."""
    import importlib
    import app.config
    importlib.reload(app.config)
    import app.services.credential_service as cs
    importlib.reload(cs)

    with pytest.raises(Exception):
        cs.decrypt("invalid_hex_data_that_cannot_be_decrypted_0000")


def test_ciphertext_is_hex_string(override_settings):
    """암호문이 hex 문자열 형태여야 한다."""
    import importlib
    import app.config
    importlib.reload(app.config)
    import app.services.credential_service as cs
    importlib.reload(cs)

    ciphertext = cs.encrypt("test-value")
    # hex 문자열 검증: 모든 문자가 0-9, a-f
    assert all(c in "0123456789abcdef" for c in ciphertext.lower())
