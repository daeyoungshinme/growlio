"""월별 포트폴리오 리포트 Job — 매월 1일 09:00 KST 실행."""

from __future__ import annotations

from datetime import date, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.job_runner import run_per_user
from app.jobs._job_helpers import run_alert_job
from app.models.alert import AlertHistory
from app.models.user import User, UserSettings
from app.services.dividend.aggregator import get_annual_dividends_received
from app.services.notifications.email_service import email_configured, send_monthly_report_email
from app.services.portfolio.asset_aggregator import get_dashboard_summary, get_net_deposits_for_year
from app.utils.cache_keys import TTL_MONTHLY_REPORT_SENT, CacheStoreType, monthly_report_sent_key
from app.utils.durable_state import get_durable, set_durable
from app.utils.kst import today_kst
from app.utils.masking import mask_email

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


async def _report_year_figures(user_id, db: AsyncSession, summary: dict, report_year: int) -> dict:
    """리포트 대상 연도의 연간 배당·입금 달성률.

    대시보드 요약은 올해 기준이라, 1월 초에 보내는 12월 리포트에서는 새해 값(≈0)이 된다.
    대상 연도가 올해가 아니면 그 연도로 다시 집계한다."""
    if report_year == today_kst().year:
        return {
            "annual_dividends_received": float(summary.get("annual_dividends_received") or 0),
            "deposit_achievement_pct": summary.get("deposit_achievement_pct"),
        }
    goal = summary.get("annual_deposit_goal")
    net_deposits = await get_net_deposits_for_year(user_id, db, report_year)
    return {
        "annual_dividends_received": await get_annual_dividends_received(user_id, db, report_year),
        "deposit_achievement_pct": (net_deposits / float(goal) * 100) if goal else None,
    }


async def _run_monthly_report(db: AsyncSession, cache: CacheStoreType) -> None:
    # 메일 미설정이면 유저마다 대시보드를 집계해 놓고 발송만 실패한다 — catch-up이 1~3일 매시간 다시 돌리므로
    # 루프 전에 빠져나온다(plans/115 A6). 인앱 이력도 메일 발송 성공 후에만 남기므로 잃는 것이 없다.
    if not email_configured():
        logger.warning("monthly_report_skipped_email_not_configured")
        return
    today = today_kst()
    report_month = _prev_month_label(today)
    month_key = _prev_month_key(today)

    result = await db.execute(
        select(User, UserSettings).join(UserSettings, User.id == UserSettings.user_id).where(User.is_active == True)
    )
    users = result.all()

    await run_per_user(
        users,
        lambda user, settings_row, to_email: _send_report_for_user(
            user, settings_row, to_email, cache, report_month, month_key
        ),
        concurrency=_MONTHLY_REPORT_CONCURRENCY,
        failure_event="monthly_report_failed",
        release_session=db,
    )


async def run_monthly_report() -> None:
    """매월 1일 — 활성 유저에게 전월 포트폴리오 요약 리포트 이메일 발송."""
    await run_alert_job(_run_monthly_report, "monthly_report_job", needs_cache=True)


async def _send_report_for_user(
    user: User, settings_row: UserSettings, to_email: str, cache: CacheStoreType, report_month: str, month_key: str
) -> None:
    # monthly_report_enabled=False이면 이메일 및 인앱 알림 건너뜀
    if not getattr(settings_row, "monthly_report_enabled", True):
        logger.info("monthly_report_skipped_disabled", user_id=str(user.id))
        return

    dedup_key = monthly_report_sent_key(user.id, month_key)
    async with AsyncSessionLocal() as db:
        # 재시작·misfire로 같은 달 잡이 다시 돌아도 한 번만 보낸다
        if await get_durable(db, dedup_key) is not None:
            logger.info("monthly_report_skipped_already_sent", user_id=str(user.id), month=month_key)
            return
        summary = await get_dashboard_summary(user.id, db, cache)
        year_figures = await _report_year_figures(user.id, db, summary, int(month_key[:4]))

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
        deposit_achievement_pct=year_figures["deposit_achievement_pct"],
        annual_dividends_received=year_figures["annual_dividends_received"],
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
        to=mask_email(to_email),
        month=report_month,
    )
