"""연말(11~12월) 절세 리마인더 — 매주 월요일 09:00 KST, 옵트인(기본 OFF) 유저에게

절세 액션 플랜(tax_action_service — 연금 세액공제·ISA 이전/납입·해외 이익실현/손실수확·금융소득 한도)
상위 항목을 요약 발송한다. 알릴 내용이 하나도 없으면(전부 해당 없음) 발송을 건너뛴다 — 불필요한 알림 방지.

시장신호 매일 요약(market_signal_alert_service.send_market_signal_daily_digest)과 동일한
유저별 AsyncSessionLocal + DB(AlertHistory) 기반 dedup(AlertHistory 당일 발송 여부) + 세마포어 패턴을 따른다.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from functools import partial
from typing import TypedDict

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.alert import AlertHistory
from app.models.user import User, UserSettings
from app.services.tax_action_service import TaxAction, get_tax_action_plan
from app.utils.kst import today_kst

logger = structlog.get_logger()

_REMINDER_CONCURRENCY = 5
_REMINDER_TOP_N = 5


class TaxReminderContent(TypedDict):
    actions: list[TaxAction]
    total_benefit_krw: float
    has_content: bool


async def build_reminder_content(user_id: uuid.UUID, db: AsyncSession) -> TaxReminderContent:
    """절세 액션 플랜(tax_action_service)의 상위 액션을 리마인더 콘텐츠로 사용한다 — 앱 세금 탭과 같은 목록."""
    plan = await get_tax_action_plan(user_id, today_kst().year, db)
    actions = plan["actions"][:_REMINDER_TOP_N]
    return {
        "actions": actions,
        "total_benefit_krw": sum(a["benefit_krw"] or 0.0 for a in actions),
        "has_content": bool(actions),
    }


async def _get_reminder_subscribers(db: AsyncSession) -> list[tuple[User, UserSettings]]:
    """year_end_tax_reminder_enabled가 True인 활성 유저 목록. 기본값이 OFF이므로 inner join으로 충분."""
    result = await db.execute(
        select(User, UserSettings)
        .join(UserSettings, UserSettings.user_id == User.id)
        .where(
            User.is_active == True,
            UserSettings.year_end_tax_reminder_enabled == True,
        )
    )
    return [(user, user_settings) for user, user_settings in result.all()]


async def _already_sent_reminder_today(db: AsyncSession, user_id: uuid.UUID) -> bool:
    """오늘 이미 리마인더를 발송했으면 True — 스케줄러 재시작/misfire로 인한 중복 발송 방지."""
    today = today_kst()
    day_start = datetime(today.year, today.month, today.day, tzinfo=UTC)
    result = await db.execute(
        select(AlertHistory.id)
        .where(
            AlertHistory.user_id == user_id,
            AlertHistory.alert_type == "YEAR_END_TAX_REMINDER",
            AlertHistory.created_at >= day_start,
        )
        .limit(1)
    )
    return result.scalar() is not None


async def _send_reminder_to_user(user: User, user_settings: UserSettings, sem: asyncio.Semaphore) -> None:
    from app.services.alerts._dispatch import dispatch_dual_channel_alert
    from app.services.email_service import send_year_end_tax_reminder_email

    async with sem:
        try:
            async with AsyncSessionLocal() as db:
                if await _already_sent_reminder_today(db, user.id):
                    return

                content = await build_reminder_content(user.id, db)
                if not content["has_content"]:
                    return

                to_email = user_settings.notification_email or user.email

                top = content["actions"][0]
                push_body = top["title"]
                if len(content["actions"]) > 1:
                    push_body += f" 외 {len(content['actions']) - 1}건"

                await dispatch_dual_channel_alert(
                    db,
                    user.id,
                    event_prefix="year_end_tax_reminder",
                    alert_type="YEAR_END_TAX_REMINDER",
                    history_message="연말 절세 리마인더 발송",
                    send_email=partial(send_year_end_tax_reminder_email, to_email, content),
                    push_title="연말 절세 리마인더",
                    push_body=push_body,
                    push_type="YEAR_END_TAX_REMINDER",
                    fcm_token=user_settings.fcm_token,
                )
        except Exception as exc:
            logger.error("year_end_tax_reminder_user_failed", user_id=str(user.id), error=str(exc))


async def send_year_end_tax_reminder(db: AsyncSession) -> None:
    """11~12월 매주 월요일 09:00 KST — 옵트인 유저에게 활용 가능한 절세 방법을 요약 발송한다."""
    subscribers = await _get_reminder_subscribers(db)
    sem = asyncio.Semaphore(_REMINDER_CONCURRENCY)
    await asyncio.gather(*(_send_reminder_to_user(user, user_settings, sem) for user, user_settings in subscribers))
    logger.info("year_end_tax_reminder_completed", subscriber_count=len(subscribers))
