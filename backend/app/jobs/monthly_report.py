"""월별 포트폴리오 리포트 Job — 매월 1일 09:00 KST 실행."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.jobs._job_helpers import report_job_failure, run_alert_job
from app.models.alert import AlertHistory
from app.models.user import User, UserSettings
from app.services.asset_aggregator import get_dashboard_summary
from app.services.email_service import send_monthly_report_email
from app.utils.cache_keys import TTL_MONTHLY_REPORT_SENT, CacheStoreType, monthly_report_sent_key
from app.utils.durable_state import get_durable, set_durable
from app.utils.kst import today_kst

logger = structlog.get_logger()

_MONTHLY_REPORT_CONCURRENCY = 3


def _prev_month_label(today: date) -> str:
    if today.month == 1:
        return f"{today.year - 1}년 12월"
    return f"{today.year}년 {today.month - 1}월"


def _prev_month_key(today: date) -> str:
    return (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")


def _mom_change(monthly_trend: list[dict], month_key: str) -> tuple[float | None, float | None]:
    """리포트 대상 월(`month_key`, YYYY-MM)과 그 직전 항목의 전월 대비 변화.

    위치(`[-2]`·`[-1]`)로 집으면, 발송 전에 당월 스냅샷(계좌 수정·수동 sync)이 생겼을 때
    당월 부분합과 비교해 "지난달 급락"으로 보인다 — 반드시 월 키로 찾는다.
    """
    idx = next((i for i, row in enumerate(monthly_trend) if str(row["month"]).startswith(month_key)), None)
    if idx is None or idx == 0:
        return None, None
    prev_val = float(monthly_trend[idx - 1]["total_krw"])
    curr_val = float(monthly_trend[idx]["total_krw"])
    change = curr_val - prev_val
    return change, (change / prev_val * 100) if prev_val else None


async def _run_monthly_report(db: AsyncSession, cache: CacheStoreType) -> None:
    today = today_kst()
    report_month = _prev_month_label(today)
    month_key = _prev_month_key(today)

    result = await db.execute(
        select(User, UserSettings).join(UserSettings, User.id == UserSettings.user_id).where(User.is_active == True)
    )
    users = result.all()

    sem = asyncio.Semaphore(_MONTHLY_REPORT_CONCURRENCY)
    await asyncio.gather(
        *(
            _send_report_for_user(user, settings_row, cache, report_month, month_key, sem)
            for user, settings_row in users
        )
    )


async def run_monthly_report() -> None:
    """매월 1일 — 활성 유저에게 전월 포트폴리오 요약 리포트 이메일 발송."""
    await run_alert_job(_run_monthly_report, "monthly_report_job", needs_cache=True)


async def _send_report_for_user(
    user: User, settings_row: UserSettings, cache, report_month: str, month_key: str, sem: asyncio.Semaphore
) -> None:
    async with sem:
        # monthly_report_enabled=False이면 이메일 및 인앱 알림 건너뜀
        if not getattr(settings_row, "monthly_report_enabled", True):
            logger.info("monthly_report_skipped_disabled", user_id=str(user.id))
            return

        to_email = settings_row.notification_email or user.email
        dedup_key = monthly_report_sent_key(user.id, month_key)
        try:
            async with AsyncSessionLocal() as db:
                # 재시작·misfire로 같은 달 잡이 다시 돌아도 한 번만 보낸다
                if await get_durable(db, dedup_key) is not None:
                    logger.info("monthly_report_skipped_already_sent", user_id=str(user.id), month=month_key)
                    return
                summary = await get_dashboard_summary(user.id, db, cache)

            monthly_trend: list[dict] = summary.get("monthly_trend") or []
            mom_change_krw, mom_change_pct = _mom_change(monthly_trend, month_key)

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
                await set_durable(db, dedup_key, "1", ttl=TTL_MONTHLY_REPORT_SENT, commit=False)
                await db.commit()

            logger.info(
                "monthly_report_sent",
                user_id=str(user.id),
                to=to_email,
                month=report_month,
            )
        except Exception as e:
            report_job_failure("monthly_report_failed", e, user_id=str(user.id))
