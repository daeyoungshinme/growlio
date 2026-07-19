"""KIS API 자격증명 AES-256 암호화/복호화."""

from __future__ import annotations

import binascii
import os
import uuid
from typing import TYPE_CHECKING

import structlog
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

if TYPE_CHECKING:
    from app.models.asset import AssetAccount

logger = structlog.get_logger()


def _get_key() -> bytes:
    key_hex = settings.kis_cred_encryption_key
    key_bytes = binascii.unhexlify(key_hex.replace("-", ""))
    if len(key_bytes) != 32:
        raise ValueError(f"KIS_CRED_ENCRYPTION_KEY는 64자 hex(32바이트)여야 합니다. 현재 {len(key_bytes)}바이트.")
    return key_bytes


def encrypt(plaintext: str) -> str:
    """문자열을 AES-256-GCM으로 암호화 → hex 문자열 반환."""
    key = _get_key()
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(nonce, plaintext.encode(), None)
    return (nonce + ct).hex()


def encrypt_if_present(plaintext: str | None) -> str | None:
    """값이 있으면 암호화하고, None이면 None을 반환한다."""
    return encrypt(plaintext) if plaintext else None


def decrypt(ciphertext_hex: str) -> str:
    """hex 문자열을 복호화 → 원문 반환."""
    key = _get_key()
    try:
        data = bytes.fromhex(ciphertext_hex)
        nonce, ct = data[:12], data[12:]
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ct, None).decode()
    except Exception as e:
        raise ValueError("Decryption failed") from e


def decrypt_kis_credentials(account: AssetAccount) -> tuple[str, str] | None:
    """계좌의 KIS App Key/Secret을 복호화한다. 둘 중 하나라도 미설정이면 None."""
    if not account.kis_app_key or not account.kis_app_secret:
        return None
    return decrypt(account.kis_app_key), decrypt(account.kis_app_secret)


def decrypt_kiwoom_credentials(account: AssetAccount) -> tuple[str, str] | None:
    """계좌의 키움 App Key/Secret을 복호화한다. 둘 중 하나라도 미설정이면 None."""
    if not account.kiwoom_app_key or not account.kiwoom_app_secret:
        return None
    return decrypt(account.kiwoom_app_key), decrypt(account.kiwoom_app_secret)


async def get_kis_user_credentials(user_id: uuid.UUID, db: AsyncSession) -> dict | None:
    """유저의 활성 KIS 계좌 자격증명을 조회해 액세스 토큰까지 발급한다.

    계좌별 자격증명이 없거나 토큰 발급 실패 시 None 반환.
    반환값: {"app_key", "app_secret", "access_token", "is_mock"}
    """
    from app.core.redis_client import get_redis
    from app.kis.auth import get_access_token
    from app.models.asset import AssetAccount

    account = await db.scalar(
        select(AssetAccount).where(
            AssetAccount.user_id == user_id,
            AssetAccount.data_source == "KIS_API",
            AssetAccount.is_active == True,  # noqa: E712
            AssetAccount.kis_app_key != None,  # noqa: E711
        )
    )
    if not account:
        return None

    creds = decrypt_kis_credentials(account)
    if creds is None:
        raise ValueError("KIS credentials are not configured for this account")
    app_key, app_secret = creds
    is_mock = account.is_mock_mode

    try:
        redis = await get_redis()
        access_token = await get_access_token(
            app_key,
            app_secret,
            is_mock=is_mock,
            redis=redis,
            db=db,
            user_id=str(user_id),
            account_id=str(account.id),
        )
        return {
            "app_key": app_key,
            "app_secret": app_secret,
            "access_token": access_token,
            "is_mock": is_mock,
        }
    except Exception as e:
        logger.warning("kis_credentials_fetch_failed", user_id=str(user_id), error=str(e))
        return None
