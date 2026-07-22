"""연말(11~12월) 절세 리마인더 — 매주 월요일 09:00 KST, 옵트인(기본 OFF) 유저에게

활용 가능한 절세 방법(해외주식 손실수확 후보, 연금저축/IRP 세액공제 잔여한도, ISA 만기/한도초과)을
요약 발송한다. 알릴 내용이 하나도 없으면(전부 해당 없음) 발송을 건너뛴다 — 불필요한 알림 방지.

시장신호 매일 요약(market_signal_alert_service.send_market_signal_daily_digest)과 동일한
유저별 AsyncSessionLocal + DB(AlertHistory) 기반 dedup(AlertHistory 당일 발송 여부) + 세마포어 패턴을 따른다.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, date, datetime
from typing import Any, TypedDict

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.alert import AlertHistory
from app.models.asset import AssetAccount
from app.models.user import User, UserSettings
from app.services.alerts.alert_service import save_alert_history
from app.services.isa_service import get_isa_status_summary
from app.services.pension_contribution_service import calc_pension_contribution_status
from app.services.tax_service import get_tax_summary

logger = structlog.get_logger()

_REMINDER_CONCURRENCY = 5
_HARVESTING_TOP_N = 3
_ISA_MATURITY_WARNING_DAYS = 30
_PENSION_TAX_TYPES = ("PENSION_SAVINGS", "IRP")


class TaxReminderContent(TypedDict):
    harvesting_top: list[dict[str, Any]]
    harvesting_total_tax_saved_krw: float
    pension_remaining_krw: float
    isa_near_maturity: list[dict[str, Any]]
    isa_over_limit_count: int
    has_content: bool


async def _has_pension_accounts(user_id: uuid.UUID, db: AsyncSession) -> bool:
    result = await db.execute(
        select(AssetAccount.id)
        .where(
            AssetAccount.user_id == user_id,
            AssetAccount.tax_type.in_(_PENSION_TAX_TYPES),
            AssetAccount.is_active == True,  # noqa: E712
        )
        .limit(1)
    )
    return result.scalar() is not None


async def build_reminder_content(user_id: uuid.UUID, db: AsyncSession) -> TaxReminderContent:
    """세 도메인 서비스를 병렬 조회해 리마인더 콘텐츠로 조합한다."""
    current_year = date.today().year
    tax_summary, pension, isa, has_pension_accounts = await asyncio.gather(
        get_tax_summary(user_id, current_year, db),
        calc_pension_contribution_status(user_id, current_year, db),
        get_isa_status_summary(user_id, db),
        _has_pension_accounts(user_id, db),
    )

    harvesting = tax_summary.get("harvesting_recommendations", [])
    harvesting_top = harvesting[:_HARVESTING_TOP_N]
    harvesting_total_tax_saved = sum(item["tax_saved_krw"] for item in harvesting)

    pension_remaining = float(pension["total_remaining_krw"]) if has_pension_accounts else 0.0

    isa_accounts = isa.get("accounts", [])
    isa_near_maturity = [
        acc
        for acc in isa_accounts
        if not acc["is_mature"]
        and not acc["needs_open_date"]
        and acc["days_remaining"] is not None
        and acc["days_remaining"] <= _ISA_MATURITY_WARNING_DAYS
    ]
    isa_over_limit_count = sum(1 for acc in isa_accounts if acc["taxable_excess_krw"] > 0)

    has_content = bool(harvesting_top) or pension_remaining > 0 or bool(isa_near_maturity) or isa_over_limit_count > 0

    return {
        "harvesting_top": harvesting_top,
        "harvesting_total_tax_saved_krw": harvesting_total_tax_saved,
        "pension_remaining_krw": pension_remaining,
        "isa_near_maturity": isa_near_maturity,
        "isa_over_limit_count": isa_over_limit_count,
        "has_content": has_content,
    }


async def _get_reminder_subscribers(db: AsyncSession) -> list[tuple[User, UserSettings]]:
    """year_end_tax_reminder_enabled가 True인 활성 유저 목록. 기본값이 OFF이므로 inner join으로 충분."""
    result = await db.execute(
        select(User, UserSettings)
        .join(UserSettings, UserSettings.user_id == User.id)
        .where(
            User.is_active == True,  # noqa: E712
            UserSettings.year_end_tax_reminder_enabled == True,  # noqa: E712
        )
    )
    return [(user, user_settings) for user, user_settings in result.all()]


async def _already_sent_reminder_today(db: AsyncSession, user_id: uuid.UUID) -> bool:
    """오늘 이미 리마인더를 발송했으면 True — 스케줄러 재시작/misfire로 인한 중복 발송 방지."""
    today = date.today()
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
    from app.services.email_service import send_year_end_tax_reminder_email
    from app.services.push_service import send_push_to_user

    async with sem:
        try:
            async with AsyncSessionLocal() as db:
                if await _already_sent_reminder_today(db, user.id):
                    return

                content = await build_reminder_content(user.id, db)
                if not content["has_content"]:
                    return

                to_email = user_settings.notification_email or user.email

                email_sent = False
                try:
                    email_sent = await send_year_end_tax_reminder_email(to_email, content)
                except Exception as exc:
                    logger.error("year_end_tax_reminder_email_failed", user_id=str(user.id), error=str(exc))

                push_body_parts: list[str] = []
                if content["harvesting_top"]:
                    push_body_parts.append(f"손실수확 후보 {len(content['harvesting_top'])}종목")
                if content["pension_remaining_krw"] > 0:
                    push_body_parts.append(f"연금공제 잔여 {content['pension_remaining_krw']:,.0f}원")
                if content["isa_near_maturity"] or content["isa_over_limit_count"]:
                    push_body_parts.append("ISA 확인 필요")

                push_sent = False
                try:
                    push_sent = await send_push_to_user(
                        user_id=user.id,
                        title="연말 절세 리마인더",
                        body=" · ".join(push_body_parts) or "활용 가능한 절세 방법을 확인해보세요.",
                        fcm_token=user_settings.fcm_token,
                        data={"type": "YEAR_END_TAX_REMINDER"},
                    )
                except Exception as exc:
                    logger.error("year_end_tax_reminder_push_failed", user_id=str(user.id), error=str(exc))

                if email_sent or push_sent:
                    await save_alert_history(db, user.id, "YEAR_END_TAX_REMINDER", "연말 절세 리마인더 발송")
                    await db.commit()
        except Exception as exc:
            logger.error("year_end_tax_reminder_user_failed", user_id=str(user.id), error=str(exc))


async def send_year_end_tax_reminder(db: AsyncSession) -> None:
    """11~12월 매주 월요일 09:00 KST — 옵트인 유저에게 활용 가능한 절세 방법을 요약 발송한다."""
    subscribers = await _get_reminder_subscribers(db)
    sem = asyncio.Semaphore(_REMINDER_CONCURRENCY)
    await asyncio.gather(*(_send_reminder_to_user(user, user_settings, sem) for user, user_settings in subscribers))
    logger.info("year_end_tax_reminder_completed", subscriber_count=len(subscribers))
