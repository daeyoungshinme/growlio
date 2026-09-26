"""정기 적립식 자동매수 예수금 부족 사전 알림 Job — 매일 18:30 KST (18:00 일일 동기화 직후).

정기 적립식 자동매수(AUTO · 매월 · SCHEDULE_ONLY · BUY_ONLY — 프론트 `isDcaAutoBuyPreset`과 같은 조합)는
실행 계좌에 이미 있는 예수금으로만 매수한다. 입금을 잊으면 예정일에 조용히 적게 사거나 아무것도 안 사므로,
다음 실행일 1~3일 전에 실행 계좌 예수금을 월 적립액과 비교해 부족하면 이메일·푸시로 알린다(계획 37 E5).

- 예수금: 동기화로 저장된 `AssetAccount.deposit_krw`(D+2) — 증권사 API를 추가 호출하지 않는다. 포트폴리오에
  해외 종목이 있으면 `deposit_usd`를 환율로 환산해 더한다.
- 기준 금액: `UserSettings.monthly_deposit_amount`. 미설정이면 "사실상 비어 있음"(`_MIN_CASH_KRW` 미만)일 때만 알린다.
- 중복 방지: 실행일 단위 durable 키 — 알림 창을 1~3일로 둬 잡이 하루 누락돼도(Render 슬립 등) 다음 날 보완된다.
"""

from __future__ import annotations

from datetime import date

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.constants import CASH_EQUIVALENT_MARKET, DOMESTIC_MARKETS
from app.jobs._job_helpers import report_job_failure, run_alert_job
from app.models.alert import RebalancingAlert
from app.models.asset import AssetAccount
from app.models.portfolio import Portfolio
from app.models.user import User, UserSettings
from app.services.alerts._dispatch import dispatch_dual_channel_alert
from app.services.alerts.calculator import next_auto_schedule_date
from app.services.email_service import send_dca_cash_shortfall_email
from app.utils.cache_keys import CacheStoreType
from app.utils.currency import fetch_usd_krw
from app.utils.durable_state import get_durable, set_durable
from app.utils.kst import KST, today_kst

logger = structlog.get_logger()

NOTICE_WINDOW_DAYS = (1, 3)
"""다음 실행일까지 남은 일수가 이 범위(포함)일 때만 확인한다."""
_MIN_CASH_KRW = 10_000.0
_DEDUP_TTL = 40 * 24 * 3600
_WEEKDAY_LABELS = "월화수목금토일"


_DCA_AUTO_BUY_PRESET: dict[str, str] = {
    "schedule_type": "MONTHLY",
    "trigger_condition": "SCHEDULE_ONLY",
    "mode": "AUTO",
    "strategy": "BUY_ONLY",
}
"""정기 적립식 자동매수 프리셋 — 프론트 `utils/dcaAutoBuy.ts::isDcaAutoBuyPreset`과 같은 판정.
잡 쿼리(`_run_dca_cash_shortfall_check`)와 `is_dca_auto_buy`가 이 한 곳을 공유한다."""


def is_dca_auto_buy(alert: RebalancingAlert) -> bool:
    return all(getattr(alert, field) == value for field, value in _DCA_AUTO_BUY_PRESET.items())


def is_cash_short(cash_krw: float, expected_krw: float | None) -> bool:
    if expected_krw and expected_krw > 0:
        return cash_krw < expected_krw
    return cash_krw < _MIN_CASH_KRW


def account_cash_krw(account: AssetAccount, portfolio: Portfolio, usd_krw: float | None) -> float:
    """실행 계좌 예수금(원). 포트폴리오에 해외 종목이 있을 때만 달러 예수금을 환산해 더한다 —
    국내 종목만 사는 적립식이면 달러는 매수에 쓰이지 않아 부족 판정을 가리기만 한다."""
    cash = float(account.deposit_krw or 0)
    has_overseas = any(
        (item.market or "").upper() not in DOMESTIC_MARKETS and item.market != CASH_EQUIVALENT_MARKET
        for item in portfolio.items
    )
    if has_overseas and account.deposit_usd and usd_krw:
        cash += float(account.deposit_usd) * usd_krw
    return cash


def run_date_label(d: date) -> str:
    return f"{d.month}월 {d.day}일({_WEEKDAY_LABELS[d.weekday()]})"


def _dedup_key(alert_id, run_date: date) -> str:
    return f"dca_cash_shortfall:{alert_id}:{run_date.isoformat()}"


async def run_dca_cash_shortfall_check() -> None:
    """매일 18:30 KST — 정기 적립식 자동매수 예정일 1~3일 전 예수금 부족 사전 알림."""
    await run_alert_job(_run_dca_cash_shortfall_check, "dca_cash_shortfall_check_job", needs_cache=True)


async def _run_dca_cash_shortfall_check(db: AsyncSession, cache: CacheStoreType) -> None:
    rows = (
        await db.execute(
            select(RebalancingAlert, Portfolio, AssetAccount, User, UserSettings)
            .join(Portfolio, Portfolio.id == RebalancingAlert.portfolio_id)
            .join(AssetAccount, AssetAccount.id == RebalancingAlert.account_id)
            .join(User, User.id == RebalancingAlert.user_id)
            .outerjoin(UserSettings, UserSettings.user_id == User.id)
            .options(selectinload(Portfolio.items))
            .where(
                RebalancingAlert.is_active == True,
                *(getattr(RebalancingAlert, field) == value for field, value in _DCA_AUTO_BUY_PRESET.items()),
                AssetAccount.is_active == True,
                User.is_active == True,
            )
        )
    ).all()
    if not rows:
        return

    today = today_kst()
    usd_krw: float | None = None
    for alert, portfolio, account, user, settings_row in rows:
        try:
            run_date = next_auto_schedule_date(alert, today)
            if run_date is None:
                continue
            days_until = (run_date - today).days
            if not (NOTICE_WINDOW_DAYS[0] <= days_until <= NOTICE_WINDOW_DAYS[1]):
                continue
            key = _dedup_key(alert.id, run_date)
            if await get_durable(db, key) is not None:
                continue

            if usd_krw is None and account.deposit_usd:
                usd_krw = await fetch_usd_krw(cache)
            cash_krw = account_cash_krw(account, portfolio, usd_krw)
            expected_raw = settings_row.monthly_deposit_amount if settings_row else None
            expected_krw = float(expected_raw) if expected_raw else None
            if not is_cash_short(cash_krw, expected_krw):
                continue

            await _notify(db, alert, portfolio, account, user, settings_row, run_date, cash_krw, expected_krw, key)
        except Exception as e:
            report_job_failure("dca_cash_shortfall_check_alert_failed", e, alert_id=str(alert.id))


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
