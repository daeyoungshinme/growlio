"""낙폭 추매 안내 알림 Job(plans/147·148) — 주문 없음. 알림 방식은 사용자 설정(`DipBuySettings.notify_mode`).

- ON_REACH(구간 도달 다음 날 아침): 08:10 KST에 미국장 마감 종가 기준으로 새로 도달한 구간이 있으면 한 번 알린다.
  보낸 구간은 규칙의 `notified_tiers`에 남겨 다시 보내지 않는다(사이클 초기화 때 비워짐).
- MONTHLY_DAY(매달 정한 날, 휴장이면 다음 거래일):
  - 18:40 KST(사전): 알림일 1~3일 전이고 추매 금액이 있으면 금액·ETF를 알린다(입금할 시간).
  - 08:10 KST(당일): 확정 금액·ETF. 사전 안내를 보냈는데 그 사이 회복해 금액이 0이 됐으면 "이번엔 추매 없음".
  - 중복 방지: 사용자·알림일·시점 단위 durable 키. 사전 창을 1~3일로 둬 잡이 하루 빠져도 보완된다.
- 한 사용자에 규칙이 여럿이어도 메일·푸시는 한 건으로 묶는다.
- 사용자별 DB 쓰기는 사용자마다 새 세션 — 한 건의 DB 오류가 다른 사용자 알림을 막지 않게(jobs/dca_cash_shortfall 패턴).
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import date
from typing import Literal

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache_store import get_cache_store
from app.core.database import AsyncSessionLocal
from app.core.job_runner import report_job_failure
from app.jobs.dca_cash_shortfall import run_date_label
from app.models.dip_buy import DipBuySettings
from app.models.user import User, UserSettings
from app.services.alerts._dispatch import dispatch_dual_channel_alert
from app.services.dip_buy_calculator import INDEX_LABEL, recovered_above_tiers
from app.services.dip_buy_service import (
    EtfOption,
    RuleSummary,
    UserDipBuySummary,
    attach_etfs,
    load_goal_candidates,
    summarize_user,
)
from app.services.notifications.email_service import send_dip_buy_email
from app.utils.cache_keys import CacheStoreType
from app.utils.durable_state import get_durable, set_durable
from app.utils.kst import today_kst

logger = structlog.get_logger()

PRE_NOTICE_DAYS = (1, 3)
_DEDUP_TTL = 40 * 24 * 3600
ALERT_TYPE = "DCA_DIP_BUY"

Phase = Literal["REACHED", "PRE", "DAY", "CANCELLED"]


def dedup_key(user_id: uuid.UUID, run_date: date, slot: str) -> str:
    return f"dip_buy:{user_id}:{run_date.isoformat()}:{slot}"


def rule_label(index_ticker: str) -> str:
    return f"{INDEX_LABEL.get(index_ticker, index_ticker)}({index_ticker})"


def pre_notice_target(summary: UserDipBuySummary, today: date) -> bool:
    run = summary.next_notify_date
    if run is None or summary.due_amount_krw <= 0:
        return False
    return PRE_NOTICE_DAYS[0] <= (run - today).days <= PRE_NOTICE_DAYS[1]


def recovered_since_pre_notice(summary: UserDipBuySummary) -> bool:
    """켜 둔 규칙 전부가 첫 구간 위로 회복했으면 True — 취소(CANCELLED) 안내는 이때만 보낸다."""
    active = [r for r in summary.rules if r.rule.is_active]
    return bool(active) and all(recovered_above_tiers(r.rule.tiers, r.drawdown_pct) for r in active)


def etf_push_text(etf: EtfOption) -> str:
    """푸시 한 줄 — 안내 금액이 1주 값에 못 미치면 "0주" 대신 1주 가격을 알린다."""
    if etf.shares > 0:
        return f"{etf.name} {etf.shares}주"
    return f"{etf.name} 1주 약 {etf.price_krw:,.0f}원(금액 부족)"


async def run_dip_buy_pre_notice() -> None:
    """매일 18:40 KST — 매달 정한 알림일 1~3일 전 추매 예정 안내."""
    await _run("PRE")


async def run_dip_buy_day_notice() -> None:
    """매일 08:10 KST — 구간 도달 안내(ON_REACH)와 알림일 당일 확정 안내(MONTHLY_DAY, 회복 시 취소 안내)."""
    await _run("DAY")


async def _run(slot: Literal["PRE", "DAY"]) -> None:
    cache = await get_cache_store()
    try:
        async with AsyncSessionLocal() as db:
            stmt = (
                select(DipBuySettings.user_id)
                .join(User, User.id == DipBuySettings.user_id)
                .where(DipBuySettings.is_active == True, User.is_active == True)
            )
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
    s = await summarize_user(db, cache, user_id, with_etfs=False, today=today)
    if not s.active or s.settings is None:
        return
    if s.settings.notify_mode == "ON_REACH":
        if slot != "DAY":
            return
        targets = [r for r in s.due_rules if r.new_due_tiers]
        if not targets:
            return
        await attach_etfs(db, cache, user_id, targets, await load_goal_candidates(db, user_id))

        async def mark_notified() -> None:
            for r in targets:
                r.rule.notified_tiers = sorted({*(int(t) for t in r.rule.notified_tiers or []), *r.due_tiers})

        await _send(db, user_id, s, "REACHED", targets, None, mark_notified)
        return

    run = s.next_notify_date
    if run is None:
        return
    phase: Phase
    if slot == "PRE":
        if not pre_notice_target(s, today):
            return
        phase = "PRE"
    else:
        if run != today:
            return
        if s.due_amount_krw > 0:
            phase = "DAY"
        elif recovered_since_pre_notice(s) and await get_durable(db, dedup_key(user_id, run, "PRE")) is not None:
            phase = "CANCELLED"
        else:
            # 이미 추매했다고 기록했거나 여윳돈·규칙을 바꿔 금액이 0이면 "회복해 취소" 안내는 틀린 말이다
            return
    key = dedup_key(user_id, run, slot)
    if await get_durable(db, key) is not None:
        return
    if phase == "CANCELLED":
        targets = [r for r in s.rules if r.rule.is_active]
    else:
        targets = s.due_rules
        await attach_etfs(db, cache, user_id, targets, await load_goal_candidates(db, user_id))
    await _send(db, user_id, s, phase, targets, run, lambda: set_durable(db, key, "1", ttl=_DEDUP_TTL))


async def _send(
    db: AsyncSession,
    user_id: uuid.UUID,
    s: UserDipBuySummary,
    phase: Phase,
    targets: list[RuleSummary],
    run_date: date | None,
    after_sent: Callable[[], Awaitable[None]],
) -> None:
    row = (
        await db.execute(
            select(User.email, UserSettings.notification_email, UserSettings.fcm_token)
            .outerjoin(UserSettings, UserSettings.user_id == User.id)
            .where(User.id == user_id)
        )
    ).first()
    if row is None:
        return
    email, notification_email, fcm_token = row
    label = run_date_label(run_date) if run_date else None
    dd_parts = ", ".join(
        f"{r.rule.index_ticker} {r.drawdown_pct:.1f}%" if r.drawdown_pct is not None else r.rule.index_ticker
        for r in targets
    )
    total = sum(r.due_amount_krw for r in targets)
    if phase == "CANCELLED":
        title = "이번 알림일엔 추매하지 않아요"
        body = f"{label} · {dd_parts}로 회복해 추매 구간을 벗어났어요"
    else:
        head = {"REACHED": "추매 구간 도달", "DAY": "오늘 추매", "PRE": f"{label} 추매 예정"}[phase]
        title = f"{head} {total:,.0f}원"
        first_etfs = [etf_push_text(r.etfs[0]) for r in targets if r.etfs]
        body = f"52주 고점 대비 {dd_parts}" + (" · " + ", ".join(first_etfs) if first_etfs else "")
        if s.dca_held_portfolios:
            body += " · 적립 자동매수는 전술 방어 국면이라 보류 중"
    mail_rules = [
        (
            rule_label(r.rule.index_ticker),
            r.drawdown_pct,
            r.due_amount_krw,
            [(e.name, float(e.shares), e.amount_krw, e.amount_usd) for e in r.etfs],
        )
        for r in targets
    ]
    sent = await dispatch_dual_channel_alert(
        db,
        user_id,
        event_prefix="dip_buy",
        alert_type=ALERT_TYPE,
        history_message=f"{title} · {body}",
        send_email=lambda: send_dip_buy_email(
            notification_email or email,
            phase,
            label,
            mail_rules,
            s.reserve_krw,
            s.dca_held_portfolios,
        ),
        push_title=title,
        push_body=body,
        push_type=ALERT_TYPE,
        fcm_token=fcm_token,
        after_sent=after_sent,
    )
    if sent:
        logger.info(
            "dip_buy_notified",
            user_id=str(user_id),
            phase=phase,
            run_date=run_date.isoformat() if run_date else None,
            amount_krw=total,
            rules=[r.rule.index_ticker for r in targets],
        )
