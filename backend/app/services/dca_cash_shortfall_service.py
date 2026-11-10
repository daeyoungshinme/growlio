"""정기 적립식 자동매수 예수금 부족 판정 — 18:30 사전 알림 잡(`jobs/dca_cash_shortfall.py`)과 홈 "지금 할 일"
(`action_items_service`)이 같은 판정을 쓴다(계획 37 E5).

- 예수금: 동기화로 저장된 `AssetAccount.deposit_krw`(D+2) — 증권사 API를 추가 호출하지 않는다. 포트폴리오에
  해외 종목이 있으면 `deposit_usd`를 환율로 환산해 더한다.
- 기준 금액: `UserSettings.monthly_deposit_amount`. 미설정이면 "사실상 비어 있음"(`_MIN_CASH_KRW` 미만)일 때만
  부족으로 본다.
- 정액 모드(알림에 `dca_amount_krw`, plans/120): 알림마다 그 금액을 국내/해외 몫으로 나눠 원화 예수금과 **달러 예수금을
  따로** 비교한다 — 해외 몫은 환전한 달러로만 사므로 원화가 넉넉해도 달러가 없으면 부족(환전 필요)이다.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import date
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.constants import CASH_EQUIVALENT_MARKET, DOMESTIC_MARKETS, TAX_DEFERRED_TAX_TYPES, is_non_tradable
from app.core.job_runner import report_handled_failure
from app.models.alert import RebalancingAlert
from app.models.asset import AssetAccount
from app.models.portfolio import GROUP_ROLE_DOMESTIC_ALT, Portfolio
from app.models.user import User, UserSettings
from app.services.alerts.calculator import already_fired_today, is_auto_schedule_day, next_auto_schedule_date
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
`find_dca_cash_shortfalls` 쿼리가 쓴다."""


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


def _buys_overseas(account: AssetAccount, portfolio: Portfolio) -> bool:
    tax_type = getattr(account, "tax_type", None)
    return any(
        (market or "").upper() not in DOMESTIC_MARKETS and market != CASH_EQUIVALENT_MARKET
        for market in (buy_market(item, tax_type) for item in portfolio.items)
    )


def account_cash_krw(account: AssetAccount, portfolio: Portfolio, usd_krw: float | None) -> float:
    """실행 계좌 예수금(원). 포트폴리오에 해외 종목이 있을 때만 달러 예수금을 환산해 더한다 —
    국내 종목만 사는 적립식이면 달러는 매수에 쓰이지 않아 부족 판정을 가리기만 한다."""
    cash = float(account.deposit_krw or 0)
    if account.deposit_usd and usd_krw and _buys_overseas(account, portfolio):
        cash += float(account.deposit_usd) * usd_krw
    return cash


def fixed_amount_needs(
    amount_krw: float, account: AssetAccount, portfolio: Portfolio, usd_krw: float | None
) -> tuple[float, float, bool]:
    """정액 적립 금액의 (원화 필요액, 달러 필요액, 해외 몫 존재). 달러 필요액은 실환율이 없으면 0으로 둔다(판정 보류).

    과세이연 계좌의 해외 종목은 살 수 없어 다른 종목에 재배분되므로(`dca_allocation`) 몫에서 뺀다.
    """
    tax_type = getattr(account, "tax_type", None)
    kr_weight = us_weight = 0.0
    for item in portfolio.items:
        weight = float(item.weight or 0)
        market = buy_market(item, tax_type)
        if weight <= 0 or market == CASH_EQUIVALENT_MARKET or is_non_tradable(item.ticker, market):
            continue
        if (market or "").upper() in DOMESTIC_MARKETS:
            kr_weight += weight
        elif tax_type not in TAX_DEFERRED_TAX_TYPES:
            us_weight += weight
    total = kr_weight + us_weight
    if total <= 0:
        return 0.0, 0.0, False
    krw_needed = amount_krw * kr_weight / total
    usd_needed = amount_krw * us_weight / total / usd_krw if us_weight > 0 and usd_krw else 0.0
    return krw_needed, usd_needed, us_weight > 0


def _cash_is_unknown(account: AssetAccount, portfolio: Portfolio, usd_krw: float | None) -> bool:
    """예수금을 모르는 경우 — 동기화 전이거나 달러로 사야 하는데 실환율이 없다. 모르는 것을 부족으로 단정하지 않는다."""
    if account.deposit_krw is None and not account.deposit_usd:
        return True
    return bool(account.deposit_usd) and not usd_krw and _buys_overseas(account, portfolio)


def _upcoming_run_date(alert: RebalancingAlert, today: date) -> date | None:
    """다음 실행일 — 오늘이 실행일이고 아직 안 돌았으면 오늘. 예전에는 당일 아침에도 다음 달 날짜를 보여줬다."""
    if is_auto_schedule_day(alert, today) and not already_fired_today(alert):
        return today
    return next_auto_schedule_date(alert, today)


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
    # 정액 모드에서 달러가 모자랄 때만 채운다(plans/120) — 원화 몫 부족과 별개로 "환전 필요"를 안내한다
    required_usd: float | None = None
    available_usd: float | None = None


def shortfall_detail(sf: DcaShortfall) -> str:
    """알림·홈 할 일에 쓰는 부족 설명 한 줄."""
    parts: list[str] = []
    if sf.expected_krw and sf.cash_krw < sf.expected_krw:
        label = "적립 금액" if getattr(sf.alert, "dca_amount_krw", None) else "월 적립액"
        parts.append(f"예수금 {sf.cash_krw:,.0f}원 — {label}보다 {sf.expected_krw - sf.cash_krw:,.0f}원 부족")
    if sf.required_usd is not None:
        parts.append(f"달러 ${sf.available_usd or 0:,.2f} — 해외 몫 ${sf.required_usd:,.2f} 환전 필요")
    if not parts:
        parts.append(f"예수금 {sf.cash_krw:,.0f}원 — 매수할 예수금이 거의 없어요")
    return " · ".join(parts)


def _fixed_amount_shortfall(
    alert: RebalancingAlert,
    portfolio: Portfolio,
    account: AssetAccount,
    user: User,
    settings_row: UserSettings | None,
    run_date: date,
    today: date,
    usd_krw: float | None,
) -> DcaShortfall | None:
    """정액 모드 1건 판정 — 원화 예수금 vs 국내 몫, 달러 예수금 vs 해외 몫. 둘 다 충분하면 None."""
    krw_needed, usd_needed, has_us = fixed_amount_needs(float(alert.dca_amount_krw or 0), account, portfolio, usd_krw)
    cash_krw = float(account.deposit_krw or 0)
    deposit_usd = float(account.deposit_usd or 0)
    krw_short = krw_needed > 0 and cash_krw < krw_needed
    usd_short = has_us and usd_needed > 0 and deposit_usd + 1e-6 < usd_needed
    if not (krw_short or usd_short):
        return None
    return DcaShortfall(
        alert,
        portfolio,
        account,
        user,
        settings_row,
        run_date,
        (run_date - today).days,
        cash_krw,
        round(krw_needed, 0) if krw_short else None,
        required_usd=round(usd_needed, 2) if usd_short else None,
        available_usd=round(deposit_usd, 2) if usd_short else None,
    )


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
    usd_checked = False
    by_user: dict[uuid.UUID, list[DcaShortfall]] = {}
    fixed: list[DcaShortfall] = []
    for alert, portfolio, account, user, settings_row in rows:
        try:
            run_date = _upcoming_run_date(alert, today)
            if run_date is None:
                continue
            is_fixed = bool(getattr(alert, "dca_amount_krw", None))
            if (account.deposit_usd or (is_fixed and _buys_overseas(account, portfolio))) and not usd_checked:
                # 판정에 쓰는 값이라 고정 fallback을 쓰지 않는다 — 1300이면 달러 예수금이 적게 잡혀 거짓 알림이 간다
                usd_krw = await fetch_usd_krw(cache, allow_fallback=False)
                usd_checked = True
            if is_fixed:
                # 정액은 알림마다 금액이 있어 사용자 합산 판정(월 적립액)과 섞지 않는다
                if account.deposit_krw is None and account.deposit_usd is None:
                    continue
                sf = _fixed_amount_shortfall(alert, portfolio, account, user, settings_row, run_date, today, usd_krw)
                if sf is not None and (notice_window is None or notice_window[0] <= sf.days_until <= notice_window[1]):
                    fixed.append(sf)
                continue
            if _cash_is_unknown(account, portfolio, usd_krw):
                continue
            expected_raw = settings_row.monthly_deposit_amount if settings_row else None
            by_user.setdefault(user.id, []).append(
                DcaShortfall(
                    alert,
                    portfolio,
                    account,
                    user,
                    settings_row,
                    run_date,
                    (run_date - today).days,
                    account_cash_krw(account, portfolio, usd_krw),
                    float(expected_raw) if expected_raw else None,
                )
            )
        except Exception as e:
            report_handled_failure("dca_cash_shortfall_evaluate_failed", e, alert_id=str(alert.id))

    shortfalls: list[DcaShortfall] = list(fixed)
    for evaluated in by_user.values():
        shortfalls.extend(_shortfalls_for_user(evaluated, notice_window))
    return shortfalls


def _shortfalls_for_user(evaluated: list[DcaShortfall], notice_window: tuple[int, int] | None) -> list[DcaShortfall]:
    """한 사용자의 자동매수 전체로 판정한다. 월 적립액은 사용자 단위 값이라 알림마다 비교하면 틀린다 — 두 계좌로
    나눠 사면 둘 다 부족으로 나오고, 한 계좌를 두 포트폴리오가 쓰면 같은 예수금을 두 번 세어 부족을 놓친다.

    합계는 알림 창 밖 계좌까지 포함해 계산하고(창 안 계좌만 보면 거짓 부족), 알림은 창 안의 가장 이른 건에만 낸다.
    """

    def in_window(sf: DcaShortfall) -> bool:
        return notice_window is None or notice_window[0] <= sf.days_until <= notice_window[1]

    cash_by_account = {str(sf.account.id): sf.cash_krw for sf in evaluated}
    expected = evaluated[0].expected_krw
    if expected:
        total_cash = sum(cash_by_account.values())
        candidates = [sf for sf in evaluated if in_window(sf)]
        if not candidates or not is_cash_short(total_cash, expected):
            return []
        return [replace(min(candidates, key=lambda sf: sf.days_until), cash_krw=total_cash)]

    # 월 적립액을 모르면 계좌마다 최소 예수금으로 본다 — 계좌당 한 건
    earliest: dict[str, DcaShortfall] = {}
    for sf in evaluated:
        key = str(sf.account.id)
        if (
            in_window(sf)
            and is_cash_short(sf.cash_krw, None)
            and (key not in earliest or sf.days_until < earliest[key].days_until)
        ):
            earliest[key] = sf
    return list(earliest.values())
