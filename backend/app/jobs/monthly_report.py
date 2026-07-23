"""월별 포트폴리오 리포트 Job — 매월 1일 09:00 KST 실행."""

from __future__ import annotations

import asyncio
from datetime import date

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.jobs._job_helpers import run_alert_job
from app.models.alert import AlertHistory
from app.models.user import User, UserSettings
from app.services.asset_aggregator import get_dashboard_summary
from app.services.email_service import send_monthly_report_email
from app.utils.cache_keys import CacheStoreType

logger = structlog.get_logger()

_MONTHLY_REPORT_CONCURRENCY = 3


def _prev_month_label(today: date) -> str:
    if today.month == 1:
        return f"{today.year - 1}년 12월"
    return f"{today.year}년 {today.month - 1}월"


async def _run_monthly_report(db: AsyncSession, cache: CacheStoreType) -> None:
    report_month = _prev_month_label(date.today())

    result = await db.execute(
        select(User, UserSettings).join(UserSettings, User.id == UserSettings.user_id).where(User.is_active == True)  # noqa: E712
    )
    users = result.all()

    sem = asyncio.Semaphore(_MONTHLY_REPORT_CONCURRENCY)
    await asyncio.gather(
        *(_send_report_for_user(user, settings_row, cache, report_month, sem) for user, settings_row in users)
    )


async def run_monthly_report() -> None:
    """매월 1일 — 활성 유저에게 전월 포트폴리오 요약 리포트 이메일 발송."""
    await run_alert_job(_run_monthly_report, "monthly_report_job", needs_cache=True)


async def _send_report_for_user(
    user: User, settings_row: UserSettings, cache, report_month: str, sem: asyncio.Semaphore
) -> None:
    async with sem:
        # monthly_report_enabled=False이면 이메일 및 인앱 알림 건너뜀
        if not getattr(settings_row, "monthly_report_enabled", True):
            logger.info("monthly_report_skipped_disabled", user_id=str(user.id))
            return

        to_email = settings_row.notification_email or user.email
        try:
            async with AsyncSessionLocal() as db:
                summary = await get_dashboard_summary(user.id, db, cache)

            monthly_trend: list[dict] = summary.get("monthly_trend") or []
            mom_change_krw: float | None = None
            mom_change_pct: float | None = None
            if len(monthly_trend) >= 2:
                prev_val = float(monthly_trend[-2]["total_krw"])
                curr_val = float(monthly_trend[-1]["total_krw"])
                mom_change_krw = curr_val - prev_val
                mom_change_pct = (mom_change_krw / prev_val * 100) if prev_val else None

            sent = await send_monthly_report_email(
                to_email=to_email,
                report_month=report_month,
                total_assets_krw=float(summary.get("total_assets_krw") or 0),
                mom_change_krw=mom_change_krw,
                mom_change_pct=mom_change_pct,
                annual_return_pct=summary.get("annual_return_pct"),
                xirr_pct=summary.get("xirr_pct"),
                goal_amount=summary.get("goal_amount"),
                goal_achievement_pct=summary.get("goal_achievement_pct"),
                annual_deposit_goal=summary.get("annual_deposit_goal"),
                deposit_achievement_pct=summary.get("deposit_achievement_pct"),
                annual_dividends_received=float(summary.get("annual_dividends_received") or 0),
                asset_allocation=summary.get("asset_allocation") or [],
            )
            if not sent:
                return

            # 이메일 발송 성공 후 인앱 AlertHistory 저장
            async with AsyncSessionLocal() as db:
                db.add(
                    AlertHistory(
                        user_id=user.id,
                        alert_type="MONTHLY_REPORT",
                        message=f"{report_month} 월간 포트폴리오 리포트가 발송되었습니다.",
                    )
                )
                await db.commit()

            logger.info(
                "monthly_report_sent",
                user_id=str(user.id),
                to=to_email,
                month=report_month,
            )
        except Exception as e:
            logger.error("monthly_report_failed", user_id=str(user.id), error=str(e))
