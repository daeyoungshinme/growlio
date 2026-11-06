"""투자 목표 달성 알림 Job — 매일 18:45 KST 실행."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.job_runner import run_per_user
from app.jobs._job_helpers import run_alert_job
from app.models.alert import AlertHistory
from app.models.user import User, UserSettings
from app.services.alerts._dispatch import send_push_safely
from app.services.notifications.email_service import send_goal_achievement_email
from app.services.portfolio.asset_aggregator import get_dashboard_summary
from app.utils.cache_keys import TTL_ANNUAL_GOAL_ACHIEVED_SENT, CacheStoreType, goal_achieved_sent_key
from app.utils.durable_state import get_durable, set_durable
from app.utils.kst import KST, today_kst

logger = structlog.get_logger()

_GOAL_CHECK_CONCURRENCY = 3


async def _already_notified_this_month(db, user_id, alert_type: str) -> bool:
    """이번 달 해당 타입 목표 알림이 이미 발송됐으면 True.

    목표별 1회 키(`goal_achieved_sent_key`) 도입 전 발송분을 다시 보내지 않기 위한 이행용 확인이다."""
    today = today_kst()
    # KST 월초 — UTC 자정이면 KST 1일 00~09시 발송분이 지난달로 잡혀 이번 달에 중복 발송된다
    month_start = datetime(today.year, today.month, 1, tzinfo=KST)
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

    await run_per_user(
        users,
        lambda user, settings_row, to_email: _check_user_goals(user, settings_row, to_email, cache),
        concurrency=_GOAL_CHECK_CONCURRENCY,
        failure_event="goal_achievement_check_failed",
        release_session=db,
    )


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
    # True면 현재 금액을 대시보드 투자 자산(부동산 제외, 달성률과 같은 기준)에서, False면 목표 × 달성률로 역산
    current_from_investable_assets: bool = False
    # True면 연간 목표 — 같은 목표 금액이라도 해마다 한 번씩 알린다
    annual: bool = True

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
        current_from_investable_assets=True,
        annual=False,
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
    """목표 1개가 100% 이상이고 이 목표로 아직 안 보냈으면 이메일 → (성공 시) 이력·발송 키 저장 → 푸시.

    같은 목표는 한 번만 알린다(연간 목표는 연도별). 목표 금액을 바꾸면 새 목표로 보고 다시 알린다."""
    goal_raw = getattr(settings_row, spec.goal_attr)
    pct: float | None = summary.get(spec.pct_key)
    if not goal_raw or pct is None or pct < 100:
        return

    goal = float(goal_raw)
    sent_key = goal_achieved_sent_key(user.id, spec.alert_type, _goal_scope(spec, goal, today_kst()))
    sent_ttl = TTL_ANNUAL_GOAL_ACHIEVED_SENT if spec.annual else None
    if await get_durable(db, sent_key) is not None:
        return
    if await _already_notified_this_month(db, user.id, spec.alert_type):
        await set_durable(db, sent_key, "1", ttl=sent_ttl)
        return

    current = (
        float(summary.get("investable_assets_krw") or 0) if spec.current_from_investable_assets else goal * pct / 100
    )
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
    await set_durable(db, sent_key, "1", ttl=sent_ttl, commit=False)
    await db.commit()
    logger.info(f"{spec.log_prefix}_sent", user_id=str(user.id), pct=pct)
    await send_push_safely(
        user.id,
        title=spec.push_title,
        body=msg,
        fcm_token=settings_row.fcm_token,
        data={"type": spec.alert_type},
        failure_event=f"{spec.log_prefix}_push_failed",
    )


def _goal_scope(spec: _GoalSpec, goal: float, today: date) -> str:
    """발송 키의 목표 구분값 — 목표 금액, 연간 목표는 연도까지."""
    amount = f"{goal:.0f}"
    return f"{today.year}:{amount}" if spec.annual else amount


async def _check_user_goals(user: User, settings_row: UserSettings, to_email: str, cache: CacheStoreType) -> None:
    async with AsyncSessionLocal() as db:
        summary = await get_dashboard_summary(user.id, db, cache)
        for spec in _GOAL_SPECS:
            await _notify_goal(db, user, settings_row, spec, summary, to_email)
