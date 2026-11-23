"""낙폭 추매 안내 알림 Job(plans/147) — 주문 없음.

- 18:40 KST(사전): 정기 적립일 1~3일 전이고 지수 낙폭으로 추매 금액이 있으면 금액·종목을 알린다(입금할 시간).
- 08:10 KST(당일): 오늘이 적립일이면 미국장 마감 종가 기준 확정 금액·종목. 사전 안내를 보냈는데 그 사이 회복해
  금액이 0이 됐으면 "이번엔 추매 없음"을 알린다.
- 중복 방지: 플랜·적립일·시점 단위 durable 키. 사전 창을 1~3일로 둬 잡이 하루 빠져도 보완된다.
- 사용자별 DB 쓰기는 사용자마다 새 세션 — 한 건의 DB 오류가 다른 사용자 알림을 막지 않게(jobs/dca_cash_shortfall 패턴).
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Literal

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache_store import get_cache_store
from app.core.database import AsyncSessionLocal
from app.core.job_runner import report_job_failure
from app.jobs.dca_cash_shortfall import run_date_label
from app.models.dip_buy import DipBuyPlan
from app.models.user import User, UserSettings
from app.services.alerts._dispatch import dispatch_dual_channel_alert
from app.services.dip_buy_service import DipBuySummary, allocate_items, summarize_user_plans
from app.services.notifications.email_service import send_dip_buy_email
from app.utils.cache_keys import CacheStoreType
from app.utils.durable_state import get_durable, set_durable
from app.utils.kst import today_kst

logger = structlog.get_logger()

PRE_NOTICE_DAYS = (1, 3)
_DEDUP_TTL = 40 * 24 * 3600
ALERT_TYPE = "DCA_DIP_BUY"

Phase = Literal["PRE", "DAY", "CANCELLED"]


def dedup_key(plan_id: uuid.UUID, run_date: date, slot: str) -> str:
    return f"dip_buy:{plan_id}:{run_date.isoformat()}:{slot}"


def pre_notice_target(summary: DipBuySummary, today: date) -> bool:
    if summary.is_run_day or summary.next_run_date is None or summary.due_amount_krw <= 0:
        return False
    days = (summary.next_run_date - today).days
    return PRE_NOTICE_DAYS[0] <= days <= PRE_NOTICE_DAYS[1]


async def run_dip_buy_pre_notice() -> None:
    """매일 18:40 KST — 적립일 1~3일 전 추매 예정 안내."""
    await _run("PRE")


async def run_dip_buy_day_notice() -> None:
    """매일 08:10 KST — 적립일 당일 확정 안내(회복 시 취소 안내)."""
    await _run("DAY")


async def _run(slot: Literal["PRE", "DAY"]) -> None:
    cache = await get_cache_store()
    try:
        async with AsyncSessionLocal() as db:
            stmt = select(DipBuyPlan.user_id).where(DipBuyPlan.is_active == True).distinct()
            user_ids = list((await db.execute(stmt)).scalars().all())
    except Exception as e:
        report_job_failure(f"dip_buy_{slot.lower()}_notice_failed", e)
        return
    for user_id in user_ids:
        try:
            async with AsyncSessionLocal() as db:
                await _notify_user(db, cache, user_id, slot)
        except Exception as e:
            report_job_failure(f"dip_buy_{slot.lower()}_notice_user_failed", e, user_id=str(user_id))


async def _notify_user(
    db: AsyncSession, cache: CacheStoreType, user_id: uuid.UUID, slot: Literal["PRE", "DAY"]
) -> None:
    today = today_kst()
    summaries = await summarize_user_plans(db, cache, user_id, allocate=False, active_only=True, today=today)
    for s in summaries:
        if s.next_run_date is None:
            continue
        if slot == "PRE":
            if not pre_notice_target(s, today):
                continue
            phase: Phase = "PRE"
        else:
            if not s.is_run_day:
                continue
            if s.due_amount_krw > 0:
                phase = "DAY"
            elif await get_durable(db, dedup_key(s.plan.id, s.next_run_date, "PRE")) is not None:
                phase = "CANCELLED"
            else:
                continue
        key = dedup_key(s.plan.id, s.next_run_date, slot)
        if await get_durable(db, key) is not None:
            continue
        if phase != "CANCELLED":
            await allocate_items(db, cache, s)
        await _send(db, s, phase, key)


async def _send(db: AsyncSession, s: DipBuySummary, phase: Phase, key: str) -> None:
    if s.next_run_date is None:  # 호출부가 거르지만 타입 좁히기 겸 방어 — assert는 -O에서 사라진다(bandit B101)
        return
    row = (
        await db.execute(
            select(User.email, UserSettings.notification_email, UserSettings.fcm_token)
            .outerjoin(UserSettings, UserSettings.user_id == User.id)
            .where(User.id == s.plan.user_id)
        )
    ).first()
    if row is None:
        return
    email, notification_email, fcm_token = row
    label = run_date_label(s.next_run_date)
    ticker = s.plan.index_ticker
    dd = f"{s.drawdown_pct:.1f}%" if s.drawdown_pct is not None else "확인 불가"
    name = s.portfolio.name
    if phase == "CANCELLED":
        title = "이번 적립일엔 추매하지 않아요"
        body = f"{label} {name} · {ticker} {dd}로 회복해 추매 구간을 벗어났어요"
    else:
        head = "오늘 추매" if phase == "DAY" else f"{label} 추매 예정"
        title = f"{head} {s.due_amount_krw:,.0f}원"
        body = f"{name} · {ticker} 52주 고점 대비 {dd}" + (
            " · " + ", ".join(f"{i.name} {i.shares:g}주" for i in s.items[:3]) if s.items else ""
        )
    items = [(i.name, i.shares, i.amount_krw, i.amount_usd) for i in s.items]
    sent = await dispatch_dual_channel_alert(
        db,
        s.plan.user_id,
        event_prefix="dip_buy",
        alert_type=ALERT_TYPE,
        history_message=f"[{name}] {title} · {body}",
        send_email=lambda: send_dip_buy_email(
            notification_email or email,
            name,
            phase,
            label,
            ticker,
            s.drawdown_pct,
            s.due_amount_krw,
            items,
            float(s.plan.reserve_krw or 0),
        ),
        push_title=title,
        push_body=body,
        push_type=ALERT_TYPE,
        fcm_token=fcm_token,
        after_sent=lambda: set_durable(db, key, "1", ttl=_DEDUP_TTL),
    )
    if sent:
        logger.info(
            "dip_buy_notified",
            plan_id=str(s.plan.id),
            phase=phase,
            run_date=s.next_run_date.isoformat(),
            amount_krw=s.due_amount_krw,
        )
