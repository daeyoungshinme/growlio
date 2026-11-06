import asyncio
from datetime import UTC, datetime, timedelta

import sentry_sdk
import structlog
from sqlalchemy import select

from app.core.cache_store import get_cache_store
from app.core.database import AsyncSessionLocal
from app.kis.auth import get_access_token
from app.models.asset import AssetAccount
from app.models.token import KisToken
from app.services.accounts.credential_service import decrypt_kis_credentials

logger = structlog.get_logger()

_TOKEN_REFRESH_CONCURRENCY = 3
# 06:00에 이보다 적게 남은 토큰만 새로 발급한다 — 강제 갱신이 없으면 get_access_token은 남은 토큰을 그대로
# 돌려줘, 전날 15:30 발급 토큰이 오늘 장중(15:30)에 만료됐다(plans/115 A7). 18시간이면 06:00 발급분이
# 다음 날 06:00까지 가서 장중 만료가 없다. 하루 1회라 KIS 잦은 발급 경고 기준에 걸리지 않는다.
_REFRESH_IF_EXPIRES_WITHIN = timedelta(hours=18)


def _report_refresh_failure(account_id: str, exc: BaseException) -> None:
    """Sentry에 실패를 알린다 — `report_job_failure`(capture_exception)는 쓰지 않는다.

    이 잡은 복호화된 app_key/app_secret을 지역변수로 들고 있어, 스택 프레임과 지역변수를 함께 보내는
    capture_exception 대신 스택 없는 capture_message로 예외 타입명과 계좌 id만 보낸다.
    """
    with sentry_sdk.new_scope() as scope:
        scope.set_tag("job", "token_refresh")
        scope.set_tag("account_id", account_id)
        sentry_sdk.capture_message(f"kis_account_token_refresh_failed: {type(exc).__name__}", level="error")


async def refresh_all_user_tokens() -> None:
    """매일 06:00 KST — 계좌별 KIS 자격증명 보유 계좌 토큰을 갱신."""
    cache = await get_cache_store()

    async with AsyncSessionLocal() as db:
        account_result = await db.execute(
            select(AssetAccount).where(
                AssetAccount.kis_app_key.is_not(None),
                AssetAccount.is_active == True,
                AssetAccount.data_source == "KIS_API",
            )
        )
        accounts_with_creds = account_result.scalars().all()

    sem = asyncio.Semaphore(_TOKEN_REFRESH_CONCURRENCY)

    async def _refresh_one(account: AssetAccount) -> None:
        async with sem:
            try:
                creds = decrypt_kis_credentials(account)
                if creds is None:
                    logger.warning(
                        "kis_account_token_refresh_skipped",
                        account_id=str(account.id),
                        reason="missing_credentials",
                    )
                    return
                app_key, app_secret = creds
                async with AsyncSessionLocal() as db:
                    expires_at = await db.scalar(select(KisToken.expires_at).where(KisToken.account_id == account.id))
                    force = expires_at is None or expires_at - datetime.now(UTC) < _REFRESH_IF_EXPIRES_WITHIN
                    await get_access_token(
                        app_key,
                        app_secret,
                        is_mock=account.is_mock_mode,
                        cache=cache,
                        db=db,
                        user_id=str(account.user_id),
                        account_id=str(account.id),
                        force_refresh=force,
                    )
                logger.info("kis_account_token_refreshed", account_id=str(account.id), forced=force)
            except Exception as e:
                logger.error("kis_account_token_refresh_failed", account_id=str(account.id), error=str(e))
                _report_refresh_failure(str(account.id), e)

    await asyncio.gather(*(_refresh_one(account) for account in accounts_with_creds))
