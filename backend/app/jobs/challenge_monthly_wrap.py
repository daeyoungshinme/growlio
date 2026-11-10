"""적립 챌린지 월간 결산 Job — 매월 1일 09:30 KST 실행.

- 입금(DEPOSIT) 챌린지: 전월 달성/미달 + 연속 적립 개월수 + 마일스톤 축하.
- 수익률/평가금액 챌린지: 목표 도달 시 status=COMPLETED 전환 + 축하 알림.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.job_runner import report_job_failure, run_per_user
from app.jobs._job_helpers import challenge_reminder_recipients, run_alert_job
from app.models.challenge import (
    CHALLENGE_ACTIVE,
    CHALLENGE_COMPLETED,
    CHALLENGE_DEPOSIT,
    InvestmentChallenge,
)
from app.models.user import User, UserSettings
from app.services import challenge_service
from app.services.alerts._dispatch import dispatch_dual_channel_alert
from app.services.notifications.email_service import send_challenge_wrap_email
from app.utils.cache_keys import CacheStoreType
from app.utils.durable_state import claim_durable, delete_durable, get_durable, set_durable
from app.utils.kst import kst_day_start, today_kst
from app.utils.kst import month_label as _month_label

logger = structlog.get_logger()

_CONCURRENCY = 3
_DEDUP_TTL = 45 * 24 * 3600
_MILESTONES = (3, 6, 12, 24, 36, 60)


def _prev_month_str() -> str:
    today = today_kst()
    prev_last = today.replace(day=1) - timedelta(days=1)
    return prev_last.strftime("%Y-%m")


def _wrap_dedup_key(challenge_id, month: str) -> str:
    return f"challenge_wrap:{challenge_id}:{month}"


def _auto_completed_key(challenge_id, month: str) -> str:
    """결산 잡이 이 달 결산에서 완료로 바꿨다는 표시 — 사용자가 직접 완료한 챌린지(PATCH)와 구분한다."""
    return f"challenge_wrap_completed:{challenge_id}:{month}"


async def run_challenge_monthly_wrap() -> None:
    """매월 1일 09:30 KST — 지난달 적립 챌린지 결산 + 목표 도달 챌린지 완료 처리."""
    await run_alert_job(_run_challenge_monthly_wrap, "challenge_monthly_wrap_job", needs_cache=True)


async def _run_challenge_monthly_wrap(db: AsyncSession, cache: CacheStoreType) -> None:
    users = await challenge_reminder_recipients(db)
    await run_per_user(
        users,
        lambda user, settings_row, to_email: _wrap_user(user, settings_row, to_email, cache),
        concurrency=_CONCURRENCY,
        failure_event="challenge_monthly_wrap_failed",
        release_session=db,
    )


async def _wrap_user(user: User, settings_row: UserSettings, to_email: str, cache: CacheStoreType) -> None:
    prev_month = _prev_month_str()
    # 이번 달(KST)에 완료 처리된 챌린지도 다시 본다 — 완료 전환은 알림과 무관하게 저장하므로, 결산 알림이
    # 실패했으면 같은 달 재실행(catch-up)이 dedup 키 없는 완료 챌린지에 알림을 다시 시도한다(plans/118 A1).
    # 다음 달에는 빠지므로 이미 알림이 나간 완료 챌린지가 새 월 키로 다시 발송되지 않는다.
    month_start = kst_day_start(today_kst().replace(day=1))
    async with AsyncSessionLocal() as db:
        challenges = (
            (
                await db.execute(
                    select(InvestmentChallenge).where(
                        InvestmentChallenge.user_id == user.id,
                        InvestmentChallenge.reminder_enabled == True,
                        or_(
                            InvestmentChallenge.status == CHALLENGE_ACTIVE,
                            and_(
                                InvestmentChallenge.status == CHALLENGE_COMPLETED,
                                InvestmentChallenge.completed_at >= month_start,
                            ),
                        ),
                    )
                )
            )
            .scalars()
            .all()
        )
        for challenge in challenges:
            # 챌린지 단위 savepoint — 한 챌린지의 예외가 같은 유저의 나머지 챌린지 결산을 막지 않게.
            # 내부 헬퍼는 전부 commit=False라 savepoint 해제 뒤 챌린지마다 커밋한다.
            try:
                async with db.begin_nested():
                    await _wrap_one(db, user, settings_row, challenge, to_email, prev_month)
                await db.commit()
            except Exception as e:
                report_job_failure(
                    "challenge_monthly_wrap_failed", e, user_id=str(user.id), challenge_id=str(challenge.id)
                )
        # 결산이 status=COMPLETED로 바꿀 수 있다 — 캐시(TTL 5분)가 이전 상태를 보이지 않게
        if challenges:
            await challenge_service.invalidate_challenge_cache(cache, user.id)


async def _wrap_one(db, user, settings_row, challenge, to_email: str, prev_month: str) -> None:
    key = _wrap_dedup_key(challenge.id, prev_month)
    # 확인 후 발송은 catch-up 잡과 본 잡이 겹치면 둘 다 보낸다 — 먼저 선점한다. 같은 키의 미커밋 INSERT는
    # 상대 트랜잭션이 끝날 때까지 기다리므로 savepoint 안 선점이 락 역할을 한다(plans/122 A4)
    if not await claim_durable(db, key, ttl=_DEDUP_TTL, commit=False):
        return

    progress = await challenge_service.compute_progress(challenge, user.id, db)
    # 이번 달 결산에서 이미 완료로 바뀐 챌린지(알림 재시도) — 그 뒤 수익률이 내려가도 달성은 확정이다
    already_completed = challenge.status == CHALLENGE_COMPLETED
    if already_completed and await get_durable(db, _auto_completed_key(challenge.id, prev_month), commit=False) is None:
        # 결산 잡이 아니라 사용자가 직접 완료한 챌린지 — 결산이 밀린 catch-up이 "달성 🎉"을 보내지 않게(plans/119 B3)
        return

    if challenge.challenge_type == CHALLENGE_DEPOSIT:
        if challenge.start_month > prev_month:
            return  # 지난달에 아직 시작 전이던 챌린지 — 결산할 내용 없음
        prev_entry = next((mo for mo in progress.months if mo.month == prev_month), None)
        prev_net = prev_entry.net_krw if prev_entry else 0.0
        target_met = prev_entry.target_met if prev_entry else False
        completed = already_completed or bool(
            challenge.target_months and progress.current_streak >= challenge.target_months
        )
        milestone = progress.current_streak if progress.current_streak in _MILESTONES else None
    else:
        # RETURN_PCT / TARGET_VALUE — 목표 도달 시에만 발송
        completed = already_completed or (progress.progress_pct is not None and progress.progress_pct >= 100)
        if not completed:
            await set_durable(db, key, "1", ttl=_DEDUP_TTL, commit=False)
            return
        prev_net = 0.0
        target_met = True
        milestone = None

    sent = await dispatch_dual_channel_alert(
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
        commit=False,
    )
    if not sent:
        await delete_durable(db, key, commit=False)  # 채널 없음·발송 실패 — 다음 실행이 다시 시도하게 선점을 푼다
    # 완료 전환은 알림 결과와 무관하게 저장한다 — 알림 채널이 하나도 없는 사용자(FCM 토큰 없음·메일 미설정)도
    # 달성이 기록돼야 하고, RETURN_PCT는 다음 달 수익률이 내려가면 달성 자체가 사라진다(plans/118 A1).
    # 알림 재시도는 위 조회가 "이번 달 완료 + dedup 키 없음"으로 처리한다.
    if completed and challenge.status != CHALLENGE_COMPLETED:
        challenge.status = CHALLENGE_COMPLETED
        challenge.completed_at = datetime.now(UTC)
        await set_durable(db, _auto_completed_key(challenge.id, prev_month), "1", ttl=_DEDUP_TTL, commit=False)
    logger.info(
        "challenge_wrap_sent" if sent else "challenge_wrap_not_sent",
        user_id=str(user.id),
        challenge_id=str(challenge.id),
        completed=completed,
    )


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
