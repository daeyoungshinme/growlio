"""투자 목표 달성 알림 Job — 매일 18:45 KST 실행."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime

import structlog
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.alert import AlertHistory
from app.models.user import User, UserSettings
from app.redis_client import get_redis
from app.services.asset_aggregator import get_dashboard_summary
from app.services.email_service import send_goal_achievement_email

logger = structlog.get_logger()

_GOAL_CHECK_CONCURRENCY = 3


async def _already_notified_this_month(db, user_id, alert_type: str) -> bool:
    """이번 달 해당 타입 목표 알림이 이미 발송됐으면 True."""
    today = date.today()
    month_start = datetime(today.year, today.month, 1, tzinfo=UTC)
    result = await db.execute(
        select(AlertHistory.id)
        .where(
            AlertHistory.user_id == user_id,
            AlertHistory.alert_type == alert_type,
            AlertHistory.created_at >= month_start,
        )
        .limit(1)
    )
    return result.scalar() is not None


async def run_goal_achievement_check() -> None:
    """매일 18:45 KST — 총 자산·연간 입금·연간 배당 목표 달성 시 이메일 알림."""
    redis = await get_redis()

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User, UserSettings)
            .join(UserSettings, User.id == UserSettings.user_id)
            .where(
                User.is_active == True,  # noqa: E712
                UserSettings.goal_amount.isnot(None)
                | UserSettings.annual_deposit_goal.isnot(None)
                | UserSettings.annual_dividend_goal.isnot(None),
            )
        )
        users = result.all()

    sem = asyncio.Semaphore(_GOAL_CHECK_CONCURRENCY)
    await asyncio.gather(*(_check_user_goals(user, settings_row, redis, sem) for user, settings_row in users))


async def _check_user_goals(user: User, settings_row: UserSettings, redis, sem: asyncio.Semaphore) -> None:
    async with sem:
        to_email = settings_row.notification_email or user.email
        try:
            async with AsyncSessionLocal() as db:
                summary = await get_dashboard_summary(user.id, db, redis)

                total_assets = float(summary.get("total_assets_krw") or 0)
                goal_pct: float | None = summary.get("goal_achievement_pct")
                deposit_pct: float | None = summary.get("deposit_achievement_pct")
                dividend_pct: float | None = summary.get("dividend_goal_achievement_pct")

                if (
                    settings_row.goal_amount
                    and goal_pct is not None
                    and goal_pct >= 100
                    and not await _already_notified_this_month(db, user.id, "GOAL_ASSET")
                ):
                    goal_amount = float(settings_row.goal_amount)
                    sent = await send_goal_achievement_email(
                        to_email=to_email,
                        goal_type="ASSET",
                        goal_amount=goal_amount,
                        current_amount=total_assets,
                        achievement_pct=goal_pct,
                    )
                    if sent:
                        msg = f"총 자산 목표 달성 {goal_pct:.1f}% — {total_assets:,.0f}원 / {goal_amount:,.0f}원"
                        db.add(
                            AlertHistory(
                                user_id=user.id,
                                alert_type="GOAL_ASSET",
                                message=msg,
                            )
                        )
                        await db.commit()
                        logger.info("goal_asset_alert_sent", user_id=str(user.id), pct=goal_pct)

                if (
                    settings_row.annual_deposit_goal
                    and deposit_pct is not None
                    and deposit_pct >= 100
                    and not await _already_notified_this_month(db, user.id, "GOAL_DEPOSIT")
                ):
                    deposit_goal = float(settings_row.annual_deposit_goal)
                    current_deposit = deposit_goal * deposit_pct / 100
                    sent = await send_goal_achievement_email(
                        to_email=to_email,
                        goal_type="DEPOSIT",
                        goal_amount=deposit_goal,
                        current_amount=current_deposit,
                        achievement_pct=deposit_pct,
                    )
                    if sent:
                        msg = (
                            f"연간 입금 목표 달성 {deposit_pct:.1f}% — {current_deposit:,.0f}원 / {deposit_goal:,.0f}원"
                        )
                        db.add(
                            AlertHistory(
                                user_id=user.id,
                                alert_type="GOAL_DEPOSIT",
                                message=msg,
                            )
                        )
                        await db.commit()
                        logger.info("goal_deposit_alert_sent", user_id=str(user.id), pct=deposit_pct)

                if (
                    settings_row.annual_dividend_goal
                    and dividend_pct is not None
                    and dividend_pct >= 100
                    and not await _already_notified_this_month(db, user.id, "GOAL_DIVIDEND")
                ):
                    dividend_goal = float(settings_row.annual_dividend_goal)
                    current_dividend = dividend_goal * dividend_pct / 100
                    sent = await send_goal_achievement_email(
                        to_email=to_email,
                        goal_type="DIVIDEND",
                        goal_amount=dividend_goal,
                        current_amount=current_dividend,
                        achievement_pct=dividend_pct,
                    )
                    if sent:
                        msg = (
                            f"연간 배당 목표 달성 {dividend_pct:.1f}% — "
                            f"{current_dividend:,.0f}원 / {dividend_goal:,.0f}원"
                        )
                        db.add(
                            AlertHistory(
                                user_id=user.id,
                                alert_type="GOAL_DIVIDEND",
                                message=msg,
                            )
                        )
                        await db.commit()
                        logger.info("goal_dividend_alert_sent", user_id=str(user.id), pct=dividend_pct)

        except Exception as e:
            logger.error("goal_achievement_check_failed", user_id=str(user.id), error=str(e))
