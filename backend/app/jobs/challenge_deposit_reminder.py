"""적립 챌린지 독려 알림 Job — 매월 25일 09:00 KST 실행.

이번 달 아직 목표를 채우지 못한 활성 입금 챌린지에 대해 이메일/푸시로 독려한다.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.jobs._job_helpers import run_alert_job
from app.models.challenge import CHALLENGE_ACTIVE, CHALLENGE_DEPOSIT, InvestmentChallenge
from app.models.user import User, UserSettings
from app.services import challenge_service
from app.services.alerts._dispatch import dispatch_dual_channel_alert
from app.services.email_service import send_challenge_reminder_email
from app.utils.cache_keys import CacheStoreType
from app.utils.durable_state import get_durable, set_durable

logger = structlog.get_logger()

_KST = ZoneInfo("Asia/Seoul")
_CONCURRENCY = 3
_DEDUP_TTL = 45 * 24 * 3600  # 45일 — 다음 달 발송 전까지만 유지되면 충분


def _month_label(month_str: str) -> str:
    y, m = month_str.split("-")
    return f"{y}년 {int(m)}월"


def _reminder_dedup_key(challenge_id, month: str) -> str:
    return f"challenge_reminder:{challenge_id}:{month}"


async def run_challenge_deposit_reminder() -> None:
    """매월 25일 09:00 KST — 이번 달 적립을 아직 안 한 입금 챌린지 독려."""
    await run_alert_job(_run_challenge_deposit_reminder, "challenge_deposit_reminder_job", needs_cache=True)


async def _run_challenge_deposit_reminder(db: AsyncSession, cache: CacheStoreType) -> None:
    result = await db.execute(
        select(User, UserSettings)
        .join(UserSettings, User.id == UserSettings.user_id)
        .where(
            User.is_active == True,
            UserSettings.challenge_reminders_enabled == True,
        )
    )
    users = result.all()
    sem = asyncio.Semaphore(_CONCURRENCY)
    await asyncio.gather(*(_check_user(user, settings_row, cache, sem) for user, settings_row in users))


async def _check_user(user: User, settings_row: UserSettings, cache: CacheStoreType, sem: asyncio.Semaphore) -> None:
    async with sem:
        month = datetime.now(_KST).strftime("%Y-%m")
        to_email = settings_row.notification_email or user.email
        try:
            async with AsyncSessionLocal() as db:
                challenges = (
                    (
                        await db.execute(
                            select(InvestmentChallenge).where(
                                InvestmentChallenge.user_id == user.id,
                                InvestmentChallenge.status == CHALLENGE_ACTIVE,
                                InvestmentChallenge.challenge_type == CHALLENGE_DEPOSIT,
                                InvestmentChallenge.reminder_enabled == True,
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                for challenge in challenges:
                    await _remind_one(db, user, settings_row, challenge, to_email, month)
        except Exception as e:
            logger.error("challenge_deposit_reminder_failed", user_id=str(user.id), error=str(e))


async def _remind_one(db, user, settings_row, challenge, to_email: str, month: str) -> None:
    progress = await challenge_service.compute_progress(challenge, user.id, db)
    done = progress.this_month_target_met if challenge.target_amount else progress.this_month_satisfied
    if done:
        return
    key = _reminder_dedup_key(challenge.id, month)
    if await get_durable(db, key) is not None:
        return

    target_amount = float(challenge.target_amount) if challenge.target_amount else None
    body = "이번 달 적립을 아직 완료하지 않았어요 — 습관을 이어가세요."
    await dispatch_dual_channel_alert(
        db,
        user.id,
        event_prefix="challenge_reminder",
        alert_type="CHALLENGE_REMINDER",
        history_message=f"[{challenge.title}] {_month_label(month)} 적립 미완료 — 이번 달 안에 적립하세요",
        send_email=lambda: send_challenge_reminder_email(
            to_email=to_email,
            title=challenge.title,
            month_label=_month_label(month),
            this_month_net_krw=progress.this_month_net_krw,
            target_amount=target_amount,
            current_streak=progress.current_streak,
        ),
        push_title="이번 달 적립 잊지 마세요",
        push_body=f"{challenge.title} — {body}",
        push_type="CHALLENGE_REMINDER",
        fcm_token=settings_row.fcm_token,
        after_sent=lambda: set_durable(db, key, "1", ttl=_DEDUP_TTL),
    )
    logger.info("challenge_reminder_sent", user_id=str(user.id), challenge_id=str(challenge.id))
