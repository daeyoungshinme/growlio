"""KIS API 자격증명 AES-256 암호화/복호화."""

import binascii
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings


def _get_key() -> bytes:
    key_hex = settings.kis_cred_encryption_key
    return binascii.unhexlify(key_hex.replace("-", ""))[:32]


def encrypt(plaintext: str) -> str:
    """문자열을 AES-256-GCM으로 암호화 → hex 문자열 반환."""
    key = _get_key()
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(nonce, plaintext.encode(), None)
    return (nonce + ct).hex()


def decrypt(ciphertext_hex: str) -> str:
    """hex 문자열을 복호화 → 원문 반환."""
    key = _get_key()
    data = bytes.fromhex(ciphertext_hex)
    nonce, ct = data[:12], data[12:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ct, None).decode()
