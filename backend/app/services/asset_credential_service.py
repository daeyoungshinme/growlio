"""계좌 KIS/키움 자격증명 검증·삭제 — assets.py 라우터에서 분리된 서비스 레이어.

credential_service.py(AES-256 암복호화 순수 유틸)와 책임 레벨이 다르다 — 이 모듈은
계좌 상태 변경(토큰 삭제·캐시 무효화)과 KIS API 호출(검증)을 포함하는 유스케이스를 담당한다.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete as sql_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import AssetAccount
from app.models.token import KisToken, KiwoomToken
from app.utils.cache_keys import account_detail_key, invalidate_user_caches


async def verify_kis_credentials(
    kis_app_key: str,
    kis_app_secret: str,
    is_mock: bool,
    user_id: uuid.UUID,
    db: AsyncSession,
    redis,
) -> None:
    """KIS 자격증명 유효성을 확인한다 (계좌 생성 없이). 실패 시 httpx 예외를 그대로 전파한다."""
    from app.kis.auth import _fetch_and_store_token

    await _fetch_and_store_token(
        kis_app_key,
        kis_app_secret,
        is_mock=is_mock,
        redis=redis,
        db=db,
        user_id=str(user_id),
        account_id=None,
    )


async def delete_kis_credentials(account: AssetAccount, db: AsyncSession, redis) -> None:
    """계좌별 KIS API 자격증명을 삭제한다. 이후 전역 자격증명으로 폴백된다."""
    await _delete_credentials(
        account,
        db,
        redis,
        app_key_attr="kis_app_key",
        app_secret_attr="kis_app_secret",  # nosec B106 — 속성명 문자열, 비밀번호 아님
        token_model=KisToken,
        redis_key=f"kis_token:account:{account.id}",
    )


async def delete_kiwoom_credentials(account: AssetAccount, db: AsyncSession, redis) -> None:
    """계좌별 키움 API 자격증명을 삭제한다."""
    await _delete_credentials(
        account,
        db,
        redis,
        app_key_attr="kiwoom_app_key",
        app_secret_attr="kiwoom_app_secret",  # nosec B106 — 속성명 문자열, 비밀번호 아님
        token_model=KiwoomToken,
        redis_key=f"kiwoom_token:account:{account.id}",
    )


async def _delete_credentials(
    account: AssetAccount,
    db: AsyncSession,
    redis,
    *,
    app_key_attr: str,
    app_secret_attr: str,
    token_model,
    redis_key: str,
) -> None:
    setattr(account, app_key_attr, None)
    setattr(account, app_secret_attr, None)
    await db.execute(sql_delete(token_model).where(token_model.account_id == account.id))
    await db.commit()

    await redis.delete(redis_key)
    await invalidate_user_caches(redis, account_detail_key(account.user_id, account.id))
