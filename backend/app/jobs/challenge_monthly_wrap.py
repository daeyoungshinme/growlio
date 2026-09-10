"""적립 챌린지 월간 결산 Job — 매월 1일 09:30 KST 실행.

- 입금(DEPOSIT) 챌린지: 전월 달성/미달 + 연속 적립 개월수 + 마일스톤 축하.
- 수익률/평가금액 챌린지: 목표 도달 시 status=COMPLETED 전환 + 축하 알림.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.jobs._job_helpers import run_alert_job
from app.models.challenge import (
    CHALLENGE_ACTIVE,
    CHALLENGE_COMPLETED,
    CHALLENGE_DEPOSIT,
    InvestmentChallenge,
)
from app.models.user import User, UserSettings
from app.services import challenge_service
from app.services.alerts._dispatch import dispatch_dual_channel_alert
from app.services.email_service import send_challenge_wrap_email
from app.utils.cache_keys import CacheStoreType
from app.utils.durable_state import get_durable, set_durable

logger = structlog.get_logger()

_KST = ZoneInfo("Asia/Seoul")
_CONCURRENCY = 3
_DEDUP_TTL = 45 * 24 * 3600
_MILESTONES = (3, 6, 12, 24, 36, 60)


def _prev_month_str() -> str:
    today = datetime.now(_KST).date()
    prev_last = today.replace(day=1) - timedelta(days=1)
    return prev_last.strftime("%Y-%m")


def _month_label(month_str: str) -> str:
    y, m = month_str.split("-")
    return f"{y}년 {int(m)}월"


def _wrap_dedup_key(challenge_id, month: str) -> str:
    return f"challenge_wrap:{challenge_id}:{month}"


async def run_challenge_monthly_wrap() -> None:
    """매월 1일 09:30 KST — 지난달 적립 챌린지 결산 + 목표 도달 챌린지 완료 처리."""
    await run_alert_job(_run_challenge_monthly_wrap, "challenge_monthly_wrap_job", needs_cache=True)


async def _run_challenge_monthly_wrap(db: AsyncSession, cache: CacheStoreType) -> None:
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
    await asyncio.gather(*(_wrap_user(user, settings_row, cache, sem) for user, settings_row in users))


async def _wrap_user(user: User, settings_row: UserSettings, cache: CacheStoreType, sem: asyncio.Semaphore) -> None:
    async with sem:
        prev_month = _prev_month_str()
        to_email = settings_row.notification_email or user.email
        try:
            async with AsyncSessionLocal() as db:
                challenges = (
                    (
                        await db.execute(
                            select(InvestmentChallenge).where(
                                InvestmentChallenge.user_id == user.id,
                                InvestmentChallenge.status == CHALLENGE_ACTIVE,
                                InvestmentChallenge.reminder_enabled == True,
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                for challenge in challenges:
                    await _wrap_one(db, user, settings_row, challenge, to_email, prev_month)
        except Exception as e:
            logger.error("challenge_monthly_wrap_failed", user_id=str(user.id), error=str(e))


async def _wrap_one(db, user, settings_row, challenge, to_email: str, prev_month: str) -> None:
    key = _wrap_dedup_key(challenge.id, prev_month)
    if await get_durable(db, key) is not None:
        return

    progress = await challenge_service.compute_progress(challenge, user.id, db)

    if challenge.challenge_type == CHALLENGE_DEPOSIT:
        if challenge.start_month > prev_month:
            return  # 지난달에 아직 시작 전이던 챌린지 — 결산할 내용 없음
        prev_entry = next((mo for mo in progress.months if mo.month == prev_month), None)
        prev_net = prev_entry.net_krw if prev_entry else 0.0
        target_met = prev_entry.target_met if prev_entry else False
        completed = bool(challenge.target_months and progress.current_streak >= challenge.target_months)
        milestone = progress.current_streak if progress.current_streak in _MILESTONES else None
    else:
        # RETURN_PCT / TARGET_VALUE — 목표 도달 시에만 발송
        completed = progress.progress_pct is not None and progress.progress_pct >= 100
        if not completed:
            await set_durable(db, key, "1", ttl=_DEDUP_TTL)
            return
        prev_net = 0.0
        target_met = True
        milestone = None

    if completed and challenge.status != CHALLENGE_COMPLETED:
        challenge.status = CHALLENGE_COMPLETED
        challenge.completed_at = datetime.now(UTC)
        await db.commit()  # 발송 성공 여부와 무관하게 완료 상태는 영속화

    await dispatch_dual_channel_alert(
        db,
        user.id,
        event_prefix="challenge_wrap",
        alert_type="CHALLENGE_WRAPUP",
        history_message=_history_message(challenge.title, prev_month, target_met, progress.current_streak, completed),
        send_email=lambda: send_challenge_wrap_email(
            to_email=to_email,
            title=challenge.title,
            month_label=_month_label(prev_month),
            prev_month_net_krw=prev_net,
            target_met=target_met,
            current_streak=progress.current_streak,
            longest_streak=progress.longest_streak,
            milestone=milestone,
            completed=completed,
        ),
        push_title=_push_title(target_met, milestone, completed),
        push_body=f"{challenge.title} — {_month_label(prev_month)} 결산",
        push_type="CHALLENGE_WRAPUP",
        fcm_token=settings_row.fcm_token,
        after_sent=lambda: set_durable(db, key, "1", ttl=_DEDUP_TTL),
    )
    logger.info("challenge_wrap_sent", user_id=str(user.id), challenge_id=str(challenge.id), completed=completed)


def _history_message(title: str, month: str, target_met: bool, streak: int, completed: bool) -> str:
    if completed:
        return f"[{title}] 챌린지 달성 🎉"
    status = "달성" if target_met else "미달"
    return f"[{title}] {_month_label(month)} 적립 {status} — 연속 {streak}개월"


def _push_title(target_met: bool, milestone: int | None, completed: bool) -> str:
    if completed:
        return "챌린지 달성 🎉"
    if milestone:
        return f"연속 {milestone}개월 적립 달성 🎉"
    return "지난달 적립 결산"
