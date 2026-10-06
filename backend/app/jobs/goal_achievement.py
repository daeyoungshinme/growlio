"""투자 목표 달성 알림 Job — 매일 18:45 KST 실행."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.jobs._job_helpers import report_job_failure, run_alert_job
from app.models.alert import AlertHistory
from app.models.user import User, UserSettings
from app.services.asset_aggregator import get_dashboard_summary
from app.services.email_service import send_goal_achievement_email
from app.services.push_service import send_push_to_user
from app.utils.cache_keys import CacheStoreType
from app.utils.kst import today_kst

logger = structlog.get_logger()

_GOAL_CHECK_CONCURRENCY = 3


async def _already_notified_this_month(db, user_id, alert_type: str) -> bool:
    """이번 달 해당 타입 목표 알림이 이미 발송됐으면 True."""
    today = today_kst()
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


async def _run_goal_achievement_check(db: AsyncSession, cache: CacheStoreType) -> None:
    result = await db.execute(
        select(User, UserSettings)
        .join(UserSettings, User.id == UserSettings.user_id)
        .where(
            User.is_active == True,
            UserSettings.goal_achievement_alerts_enabled == True,
            UserSettings.goal_amount.isnot(None)
            | UserSettings.annual_deposit_goal.isnot(None)
            | UserSettings.annual_dividend_goal.isnot(None),
        )
    )
    users = result.all()

    sem = asyncio.Semaphore(_GOAL_CHECK_CONCURRENCY)
    await asyncio.gather(*(_check_user_goals(user, settings_row, cache, sem) for user, settings_row in users))


async def run_goal_achievement_check() -> None:
    """매일 18:45 KST — 총 자산·연간 입금·연간 배당 목표 달성 시 이메일 알림."""
    await run_alert_job(_run_goal_achievement_check, "goal_achievement_check_job", needs_cache=True)


@dataclass(frozen=True)
class _GoalSpec:
    """목표 유형 1개의 알림 규칙 — 설정값 필드·대시보드 달성률 키·문구·이벤트명."""

    goal_type: str  # send_goal_achievement_email의 goal_type
    goal_attr: str  # UserSettings 필드
    pct_key: str  # get_dashboard_summary 응답 키
    label: str  # 메시지 접두 ("총 자산 목표")
    push_title: str
    # True면 현재 금액을 대시보드 총자산에서, False면 목표 × 달성률로 역산
    current_from_total_assets: bool = False

    @property
    def alert_type(self) -> str:
        return f"GOAL_{self.goal_type}"

    @property
    def log_prefix(self) -> str:
        return f"goal_{self.goal_type.lower()}_alert"


_GOAL_SPECS: tuple[_GoalSpec, ...] = (
    _GoalSpec(
        goal_type="ASSET",
        goal_attr="goal_amount",
        pct_key="goal_achievement_pct",
        label="총 자산 목표",
        push_title="자산 목표 달성",
        current_from_total_assets=True,
    ),
    _GoalSpec(
        goal_type="DEPOSIT",
        goal_attr="annual_deposit_goal",
        pct_key="deposit_achievement_pct",
        label="연간 입금 목표",
        push_title="입금 목표 달성",
    ),
    _GoalSpec(
        goal_type="DIVIDEND",
        goal_attr="annual_dividend_goal",
        pct_key="dividend_goal_achievement_pct",
        label="연간 배당 목표",
        push_title="배당 목표 달성",
    ),
)


async def _notify_goal(
    db: AsyncSession,
    user: User,
    settings_row: UserSettings,
    spec: _GoalSpec,
    summary: dict,
    to_email: str,
) -> None:
    """목표 1개가 100% 이상이고 이번 달 미발송이면 이메일 → (성공 시) 이력 저장 → 푸시."""
    goal_raw = getattr(settings_row, spec.goal_attr)
    pct: float | None = summary.get(spec.pct_key)
    if not goal_raw or pct is None or pct < 100:
        return
    if await _already_notified_this_month(db, user.id, spec.alert_type):
        return

    goal = float(goal_raw)
    current = float(summary.get("total_assets_krw") or 0) if spec.current_from_total_assets else goal * pct / 100
    sent = await send_goal_achievement_email(
        to_email=to_email,
        goal_type=spec.goal_type,
        goal_amount=goal,
        current_amount=current,
        achievement_pct=pct,
    )
    if not sent:
        return

    msg = f"{spec.label} 달성 {pct:.1f}% — {current:,.0f}원 / {goal:,.0f}원"
    db.add(AlertHistory(user_id=user.id, alert_type=spec.alert_type, message=msg))
    await db.commit()
    logger.info(f"{spec.log_prefix}_sent", user_id=str(user.id), pct=pct)
    try:
        await send_push_to_user(
            user_id=user.id,
            title=spec.push_title,
            body=msg,
            fcm_token=settings_row.fcm_token,
            data={"type": spec.alert_type},
        )
    except Exception as exc:
        logger.warning(f"{spec.log_prefix}_push_failed", user_id=str(user.id), error=str(exc))


async def _check_user_goals(user: User, settings_row: UserSettings, cache, sem: asyncio.Semaphore) -> None:
    async with sem:
        to_email = settings_row.notification_email or user.email
        try:
            async with AsyncSessionLocal() as db:
                summary = await get_dashboard_summary(user.id, db, cache)
                for spec in _GOAL_SPECS:
                    await _notify_goal(db, user, settings_row, spec, summary, to_email)
        except Exception as e:
            report_job_failure("goal_achievement_check_failed", e, user_id=str(user.id))
