"""정기 적립식 자동매수 예수금 부족 사전 알림 Job — 매일 18:30 KST (18:00 일일 동기화 직후).

정기 적립식 자동매수(AUTO · 매월 · SCHEDULE_ONLY · BUY_ONLY — 프론트 `isDcaAutoBuyPreset`과 같은 조합)는
실행 계좌에 이미 있는 예수금으로만 매수한다. 입금을 잊으면 예정일에 조용히 적게 사거나 아무것도 안 사므로,
다음 실행일 1~3일 전에 실행 계좌 예수금을 월 적립액과 비교해 부족하면 이메일·푸시로 알린다(계획 37 E5).

- 부족 판정: `services/dca_cash_shortfall_service.find_dca_cash_shortfalls` (홈 "지금 할 일"과 공유).
- 중복 방지: 실행일 단위 durable 키 — 알림 창을 1~3일로 둬 잡이 하루 누락돼도(Render 슬립 등) 다음 날 보완된다.
- 알림별 DB 쓰기(dedup 조회·이력·플래그)는 알림마다 새 세션에서 한다 — 한 건의 DB 오류로 공유 세션이
  rollback 대기 상태가 되면 이후 알림이 전부 실패하기 때문이다(docs/plans/39 N3). 조회한 ORM 객체는
  `expire_on_commit=False`라 바깥 세션에서 그대로 읽힌다.
"""

from __future__ import annotations

from datetime import date

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.job_runner import report_job_failure
from app.jobs._job_helpers import run_alert_job
from app.models.alert import RebalancingAlert
from app.models.asset import AssetAccount
from app.models.portfolio import Portfolio
from app.models.user import User, UserSettings
from app.services.alerts._dispatch import dispatch_dual_channel_alert
from app.services.dca_cash_shortfall_service import NOTICE_WINDOW_DAYS, find_dca_cash_shortfalls
from app.services.email_service import send_dca_cash_shortfall_email
from app.utils.cache_keys import CacheStoreType
from app.utils.durable_state import get_durable, set_durable
from app.utils.kst import KST

logger = structlog.get_logger()

_DEDUP_TTL = 40 * 24 * 3600
_WEEKDAY_LABELS = "월화수목금토일"


def run_date_label(d: date) -> str:
    return f"{d.month}월 {d.day}일({_WEEKDAY_LABELS[d.weekday()]})"


def _dedup_key(alert_id, run_date: date) -> str:
    return f"dca_cash_shortfall:{alert_id}:{run_date.isoformat()}"


async def run_dca_cash_shortfall_check() -> None:
    """매일 18:30 KST — 정기 적립식 자동매수 예정일 1~3일 전 예수금 부족 사전 알림."""
    await run_alert_job(_run_dca_cash_shortfall_check, "dca_cash_shortfall_check_job", needs_cache=True)


async def _run_dca_cash_shortfall_check(db: AsyncSession, cache: CacheStoreType) -> None:
    for sf in await find_dca_cash_shortfalls(db, cache, notice_window=NOTICE_WINDOW_DAYS):
        try:
            key = _dedup_key(sf.alert.id, sf.run_date)
            async with AsyncSessionLocal() as item_db:
                if await get_durable(item_db, key) is not None:
                    continue
                await _notify(
                    item_db,
                    sf.alert,
                    sf.portfolio,
                    sf.account,
                    sf.user,
                    sf.settings_row,
                    sf.run_date,
                    sf.cash_krw,
                    sf.expected_krw,
                    key,
                )
        except Exception as e:
            report_job_failure("dca_cash_shortfall_check_alert_failed", e, alert_id=str(sf.alert.id))


async def _notify(
    db: AsyncSession,
    alert: RebalancingAlert,
    portfolio: Portfolio,
    account: AssetAccount,
    user: User,
    settings_row: UserSettings | None,
    run_date: date,
    cash_krw: float,
    expected_krw: float | None,
    key: str,
) -> None:
    label = run_date_label(run_date)
    synced_label = account.last_synced_at.astimezone(KST).strftime("%m/%d %H:%M") if account.last_synced_at else None
    to_email = (settings_row.notification_email if settings_row else None) or user.email
    if expected_krw:
        detail = f"예수금 {cash_krw:,.0f}원 — 월 적립액보다 {expected_krw - cash_krw:,.0f}원 부족"
    else:
        detail = f"예수금 {cash_krw:,.0f}원 — 매수할 예수금이 거의 없어요"

    sent = await dispatch_dual_channel_alert(
        db,
        user.id,
        event_prefix="dca_cash_shortfall",
        alert_type="DCA_CASH_SHORTFALL",
        history_message=f"[{portfolio.name}] {label} 자동매수 예정 · {account.name} {detail}",
        send_email=lambda: send_dca_cash_shortfall_email(
            to_email, portfolio.name, account.name, label, cash_krw, expected_krw, synced_label
        ),
        push_title="자동매수 전 예수금을 채워주세요",
        push_body=f"{label} {portfolio.name} 자동매수 · {detail}",
        push_type="DCA_CASH_SHORTFALL",
        fcm_token=settings_row.fcm_token if settings_row else None,
        after_sent=lambda: set_durable(db, key, "1", ttl=_DEDUP_TTL),
    )
    if sent:
        logger.info(
            "dca_cash_shortfall_notified",
            alert_id=str(alert.id),
            run_date=run_date.isoformat(),
            cash_krw=cash_krw,
            expected_krw=expected_krw,
        )
