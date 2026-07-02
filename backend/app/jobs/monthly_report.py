"""월별 포트폴리오 리포트 Job — 매월 1일 09:00 KST 실행."""

from __future__ import annotations

from datetime import date

import structlog
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.alert import AlertHistory
from app.models.user import User, UserSettings
from app.redis_client import get_redis
from app.services.asset_aggregator import get_dashboard_summary
from app.services.email_service import send_monthly_report_email

logger = structlog.get_logger()


def _prev_month_label(today: date) -> str:
    if today.month == 1:
        return f"{today.year - 1}년 12월"
    return f"{today.year}년 {today.month - 1}월"


async def run_monthly_report() -> None:
    """매월 1일 — 활성 유저에게 전월 포트폴리오 요약 리포트 이메일 발송."""
    redis = await get_redis()
    report_month = _prev_month_label(date.today())

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User, UserSettings).join(UserSettings, User.id == UserSettings.user_id).where(User.is_active == True)  # noqa: E712
        )
        users = result.all()

    for user, settings_row in users:
        # monthly_report_enabled=False이면 이메일 및 인앱 알림 건너뜀
        if not getattr(settings_row, "monthly_report_enabled", True):
            logger.info("monthly_report_skipped_disabled", user_id=str(user.id))
            continue

        to_email = settings_row.notification_email or user.email
        try:
            async with AsyncSessionLocal() as db:
                summary = await get_dashboard_summary(user.id, db, redis)

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
                continue

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
