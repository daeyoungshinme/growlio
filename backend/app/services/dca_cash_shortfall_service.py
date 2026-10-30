"""정기 적립식 자동매수 예수금 부족 판정 — 18:30 사전 알림 잡(`jobs/dca_cash_shortfall.py`)과 홈 "지금 할 일"
(`action_items_service`)이 같은 판정을 쓴다(계획 37 E5).

- 예수금: 동기화로 저장된 `AssetAccount.deposit_krw`(D+2) — 증권사 API를 추가 호출하지 않는다. 포트폴리오에
  해외 종목이 있으면 `deposit_usd`를 환율로 환산해 더한다.
- 기준 금액: `UserSettings.monthly_deposit_amount`. 미설정이면 "사실상 비어 있음"(`_MIN_CASH_KRW` 미만)일 때만
  부족으로 본다.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.constants import CASH_EQUIVALENT_MARKET, DOMESTIC_MARKETS, TAX_DEFERRED_TAX_TYPES
from app.core.job_runner import report_handled_failure
from app.models.alert import RebalancingAlert
from app.models.asset import AssetAccount
from app.models.portfolio import GROUP_ROLE_DOMESTIC_ALT, Portfolio
from app.models.user import User, UserSettings
from app.services.alerts.calculator import next_auto_schedule_date
from app.utils.cache_keys import CacheStoreType
from app.utils.currency import fetch_usd_krw
from app.utils.kst import today_kst

logger = structlog.get_logger()

NOTICE_WINDOW_DAYS = (1, 3)
"""다음 실행일까지 남은 일수가 이 범위(포함)일 때만 확인한다."""
_MIN_CASH_KRW = 10_000.0

DCA_AUTO_BUY_PRESET: dict[str, str] = {
    "schedule_type": "MONTHLY",
    "trigger_condition": "SCHEDULE_ONLY",
    "mode": "AUTO",
    "strategy": "BUY_ONLY",
}
"""정기 적립식 자동매수 프리셋 — 프론트 `utils/dcaAutoBuy.ts::isDcaAutoBuyPreset`과 같은 판정.
`find_dca_cash_shortfalls` 쿼리와 `is_dca_auto_buy`가 이 한 곳을 공유한다."""


def is_dca_auto_buy(alert: RebalancingAlert) -> bool:
    return all(getattr(alert, field) == value for field, value in DCA_AUTO_BUY_PRESET.items())


def is_cash_short(cash_krw: float, expected_krw: float | None) -> bool:
    if expected_krw and expected_krw > 0:
        return cash_krw < expected_krw
    return cash_krw < _MIN_CASH_KRW


def buy_market(item: Any, tax_type: str | None) -> str:
    """실제로 매수될 종목의 시장 — 지수 그룹이 ISA·연금 계좌에서 국내 대체 종목으로 사는 경우 반영(plans/74)."""
    if tax_type in TAX_DEFERRED_TAX_TYPES and getattr(item, "group_key", None):
        alt = next((m for m in getattr(item, "members", None) or [] if m.role == GROUP_ROLE_DOMESTIC_ALT), None)
        if alt is not None and (item.market or "").upper() not in DOMESTIC_MARKETS:
            return alt.market
    return item.market


def account_cash_krw(account: AssetAccount, portfolio: Portfolio, usd_krw: float | None) -> float:
    """실행 계좌 예수금(원). 포트폴리오에 해외 종목이 있을 때만 달러 예수금을 환산해 더한다 —
    국내 종목만 사는 적립식이면 달러는 매수에 쓰이지 않아 부족 판정을 가리기만 한다."""
    cash = float(account.deposit_krw or 0)
    tax_type = getattr(account, "tax_type", None)
    has_overseas = any(
        (market or "").upper() not in DOMESTIC_MARKETS and market != CASH_EQUIVALENT_MARKET
        for market in (buy_market(item, tax_type) for item in portfolio.items)
    )
    if has_overseas and account.deposit_usd and usd_krw:
        cash += float(account.deposit_usd) * usd_krw
    return cash


@dataclass(frozen=True)
class DcaShortfall:
    """정기 적립식 자동매수 1건의 예수금 부족 판정 결과 — 잡 알림과 홈 "지금 할 일"이 공유한다."""

    alert: RebalancingAlert
    portfolio: Portfolio
    account: AssetAccount
    user: User
    settings_row: UserSettings | None
    run_date: date
    days_until: int
    cash_krw: float
    expected_krw: float | None


async def find_dca_cash_shortfalls(
    db: AsyncSession,
    cache: CacheStoreType,
    *,
    user_id: uuid.UUID | None = None,
    notice_window: tuple[int, int] | None = None,
) -> list[DcaShortfall]:
    """활성 정기 적립식 자동매수 중 다음 실행일 기준 예수금이 부족한 건.

    `notice_window`가 주어지면 실행일까지 남은 일수가 그 범위(포함)인 건만 판정한다(잡 알림 창).
    한 건의 판정 오류는 기록만 하고 나머지를 계속 본다.
    """
    stmt = (
        select(RebalancingAlert, Portfolio, AssetAccount, User, UserSettings)
        .join(Portfolio, Portfolio.id == RebalancingAlert.portfolio_id)
        .join(AssetAccount, AssetAccount.id == RebalancingAlert.account_id)
        .join(User, User.id == RebalancingAlert.user_id)
        .outerjoin(UserSettings, UserSettings.user_id == User.id)
        .options(selectinload(Portfolio.items))
        .where(
            RebalancingAlert.is_active == True,
            *(getattr(RebalancingAlert, field) == value for field, value in DCA_AUTO_BUY_PRESET.items()),
            AssetAccount.is_active == True,
            User.is_active == True,
        )
    )
    if user_id is not None:
        stmt = stmt.where(RebalancingAlert.user_id == user_id)
    rows = (await db.execute(stmt)).all()
    if not rows:
        return []

    today = today_kst()
    usd_krw: float | None = None
    shortfalls: list[DcaShortfall] = []
    for alert, portfolio, account, user, settings_row in rows:
        try:
            run_date = next_auto_schedule_date(alert, today)
            if run_date is None:
                continue
            days_until = (run_date - today).days
            if notice_window is not None and not (notice_window[0] <= days_until <= notice_window[1]):
                continue
            if usd_krw is None and account.deposit_usd:
                usd_krw = await fetch_usd_krw(cache)
            cash_krw = account_cash_krw(account, portfolio, usd_krw)
            expected_raw = settings_row.monthly_deposit_amount if settings_row else None
            expected_krw = float(expected_raw) if expected_raw else None
            if is_cash_short(cash_krw, expected_krw):
                shortfalls.append(
                    DcaShortfall(
                        alert, portfolio, account, user, settings_row, run_date, days_until, cash_krw, expected_krw
                    )
                )
        except Exception as e:
            report_handled_failure("dca_cash_shortfall_evaluate_failed", e, alert_id=str(alert.id))
    return shortfalls
