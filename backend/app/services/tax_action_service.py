"""절세 액션 플랜 — "언제·얼마를·어느 계좌에 하면 얼마 아낀다"를 실행 가능한 액션 목록으로 조합한다.

계산은 기존 도메인 서비스(pension_contribution_service/isa_service/tax_service)에 위임하고 이 모듈은
조합·우선순위화만 한다. 연말 절세 리마인더(alerts/tax_reminder_service)도 같은 액션 목록을 재사용한다.

- 세법 수치는 `_DEDUCTION_RULES` 연도별 테이블로 둔다(출처·기준연도 주석) — 매년 확인 후 갱신.
- 이익실현(A4)·손실수확(A5)은 정보 제공형 문구만 쓰고 자동 주문과 연결하지 않는다(AUTO 파이프라인과 분리).
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Literal, TypedDict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import IncomeBracket
from app.models.asset import AssetAccount
from app.models.user import UserSettings
from app.services.isa_service import (
    IsaAccountStatus,
    IsaContributionStatus,
    calc_isa_contribution_status,
    get_isa_status_summary,
)
from app.services.pension_contribution_service import PensionContributionStatus, calc_pension_contribution_status
from app.services.tax_service import get_overseas_positions_detail, get_tax_summary
from app.utils.kst import today_kst

ActionCategory = Literal[
    "PENSION_DEDUCTION",
    "ISA_PENSION_TRANSFER",
    "ISA_CONTRIBUTION",
    "OVERSEAS_GAIN_HARVEST",
    "TAX_LOSS_HARVEST",
    "FINANCIAL_INCOME_LIMIT",
]
ActionPriority = Literal["HIGH", "MEDIUM", "LOW"]


class _DeductionRules(TypedDict):
    pension_rate_under_55m: float  # 총급여 5,500만원(종합소득 4,500만원) 이하 세액공제율(지방세 포함)
    pension_rate_over_55m: float  # 초과 세액공제율(지방세 포함)
    isa_transfer_rate: float  # ISA 만기자금 연금계좌 이전액 중 추가 공제한도 인정 비율
    isa_transfer_cap_krw: int  # 이전분 추가 공제한도 상한
    isa_transfer_window_days: int  # 만기(해지)일로부터 이전 인정 기간


# 조세특례제한법 §59의3(연금계좌 세액공제, 2023년 귀속부터 16.5%/13.2%) — 2025·2026년 동일.
_DEDUCTION_RULES: dict[int, _DeductionRules] = {
    2025: _DeductionRules(
        pension_rate_under_55m=0.165,
        pension_rate_over_55m=0.132,
        isa_transfer_rate=0.10,
        isa_transfer_cap_krw=3_000_000,
        isa_transfer_window_days=60,
    ),
    2026: _DeductionRules(
        pension_rate_under_55m=0.165,
        pension_rate_over_55m=0.132,
        isa_transfer_rate=0.10,
        isa_transfer_cap_krw=3_000_000,
        isa_transfer_window_days=60,
    ),
}

_ISA_TRANSFER_LEAD_DAYS = 90  # 만기 D-90부터 이전 준비 안내
_FINANCIAL_INCOME_WATCH_KRW = 15_000_000  # 금융소득 종합과세(2,000만) 접근 경고 시작선
_HARVESTING_TOP_N = 3
_HIGH_PRIORITY_DAYS = 30
_MEDIUM_PRIORITY_DAYS = 90
_HIGH_PRIORITY_BENEFIT_KRW = 500_000
_MEDIUM_PRIORITY_BENEFIT_KRW = 100_000
_PRIORITY_ORDER: dict[ActionPriority, int] = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}

_LINK_ACCOUNTS = "/assets?tab=계좌관리"
_LINK_TAX_ESTIMATE = "/assets?tab=투자현황&portfolioTab=세금&taxTab=세금 추정"

_ACTION_PLAN_NOTE = (
    "입출금·배당 내역(수기 입력 포함)과 최신 스냅샷 기준 참고용 추정치입니다. "
    "매매 관련 항목은 정보 제공 목적이며 투자 권유가 아닙니다. 세법 수치는 기준연도 현행 규정 기준입니다."
)


class TaxActionCta(TypedDict):
    label: str
    link: str


class TaxAction(TypedDict):
    id: str
    category: ActionCategory
    title: str
    detail: str
    amount_krw: float | None
    benefit_krw: float | None
    deadline: str | None
    priority: ActionPriority
    uses_income_bracket: bool
    cta: TaxActionCta


class TaxActionPlan(TypedDict):
    year: int
    income_bracket: str | None
    actions: list[TaxAction]
    note: str


def _get_rules(year: int) -> _DeductionRules:
    if year in _DEDUCTION_RULES:
        return _DEDUCTION_RULES[year]
    closest = min(_DEDUCTION_RULES.keys(), key=lambda y: abs(y - year))
    return _DEDUCTION_RULES[closest]


def pension_credit_rate(income_bracket: str | None, rules: _DeductionRules) -> float:
    """소득 구간별 연금 세액공제율. 미입력이면 보수적으로 낮은 공제율(13.2%)을 쓴다."""
    if income_bracket == IncomeBracket.UNDER_55M:
        return rules["pension_rate_under_55m"]
    return rules["pension_rate_over_55m"]


def _priority(deadline: date | None, benefit: float | None, today: date) -> ActionPriority:
    days_left = (deadline - today).days if deadline is not None else None
    amount = benefit or 0.0
    if (days_left is not None and days_left <= _HIGH_PRIORITY_DAYS) or amount >= _HIGH_PRIORITY_BENEFIT_KRW:
        return "HIGH"
    if (days_left is not None and days_left <= _MEDIUM_PRIORITY_DAYS) or amount >= _MEDIUM_PRIORITY_BENEFIT_KRW:
        return "MEDIUM"
    return "LOW"


def _make_action(
    *,
    action_id: str,
    category: ActionCategory,
    title: str,
    detail: str,
    amount: float | None,
    benefit: float | None,
    deadline: date | None,
    today: date,
    cta_label: str,
    cta_link: str,
    uses_income_bracket: bool = False,
) -> TaxAction:
    return {
        "id": action_id,
        "category": category,
        "title": title,
        "detail": detail,
        "amount_krw": round(amount, 0) if amount is not None else None,
        "benefit_krw": round(benefit, 0) if benefit is not None else None,
        "deadline": deadline.isoformat() if deadline else None,
        "priority": _priority(deadline, benefit, today),
        "uses_income_bracket": uses_income_bracket,
        "cta": {"label": cta_label, "link": cta_link},
    }


def _fmt_won(amount: float) -> str:
    return f"{amount:,.0f}원"


def build_pension_action(
    pension: PensionContributionStatus,
    has_pension_savings: bool,
    has_irp: bool,
    rate: float,
    income_bracket: str | None,
    today: date,
) -> TaxAction | None:
    """A1 — 연말까지 연금저축/IRP 추가 납입 시 세액공제."""
    if not (has_pension_savings or has_irp):
        return None
    total_remaining = float(pension["total_remaining_krw"])
    ps_remaining = float(pension["pension_savings_remaining_krw"])
    # IRP가 있으면 합산 한도(900만) 잔여 전체를 채울 수 있고, 연금저축만 있으면 연금저축 한도(600만)까지만
    recommendable = total_remaining if has_irp else min(ps_remaining, total_remaining)
    if recommendable <= 0:
        return None

    deadline = date(today.year, 12, 31)
    months_left = 12 - today.month + 1
    monthly = recommendable / months_left
    if has_irp and has_pension_savings and ps_remaining > 0:
        where = f"연금저축 최대 {_fmt_won(min(ps_remaining, recommendable))}, 나머지는 IRP"
    elif has_irp:
        where = "IRP"
    else:
        where = "연금저축"
    rate_note = (
        f"공제율 {rate * 100:.1f}% 적용"
        if income_bracket
        else f"공제율 {rate * 100:.1f}%(낮은 구간) 기준 — 소득 구간을 입력하면 정확해져요"
    )
    split_note = f"이번 달부터 매월 약 {_fmt_won(monthly)}씩 나눠 넣을 수 있어요. " if months_left > 1 else ""
    return _make_action(
        action_id="pension-deduction",
        category="PENSION_DEDUCTION",
        title=f"12/31까지 {where}에 {_fmt_won(recommendable)} 추가 납입",
        detail=(
            f"올해 세액공제 한도가 {_fmt_won(recommendable)} 남았어요. {split_note}"
            f"{rate_note}. 납입액은 입출금 내역 기준이라, 이미 넣었다면 입금 내역을 기록해 주세요."
        ),
        amount=recommendable,
        benefit=recommendable * rate,
        deadline=deadline,
        today=today,
        cta_label="입금 내역 기록",
        cta_link=_LINK_ACCOUNTS,
        uses_income_bracket=True,
    )


def build_isa_transfer_actions(
    isa_accounts: list[IsaAccountStatus], rules: _DeductionRules, rate: float, income_bracket: str | None, today: date
) -> list[TaxAction]:
    """A2 — ISA 만기 D-90 ~ 만기 후 60일: 만기자금 연금계좌 이전 시 추가 세액공제."""
    actions: list[TaxAction] = []
    max_transfer = rules["isa_transfer_cap_krw"] / rules["isa_transfer_rate"]
    for acc in isa_accounts:
        if not acc["maturity_date"]:
            continue
        maturity = date.fromisoformat(acc["maturity_date"])
        window_end = maturity + timedelta(days=rules["isa_transfer_window_days"])
        if not (maturity - timedelta(days=_ISA_TRANSFER_LEAD_DAYS) <= today <= window_end):
            continue
        timing = (
            f"만기일({maturity.isoformat()})이 지났어요 — {window_end.isoformat()}까지"
            if today >= maturity
            else f"만기일({maturity.isoformat()}) 이후 {rules['isa_transfer_window_days']}일 이내에"
        )
        benefit = rules["isa_transfer_cap_krw"] * rate
        actions.append(
            _make_action(
                action_id=f"isa-transfer-{acc['account_id']}",
                category="ISA_PENSION_TRANSFER",
                title=f"{acc['account_name']} 만기 자금을 연금계좌로 이전",
                detail=(
                    f"{timing} 연금저축/IRP로 옮기면 이전액의 {rules['isa_transfer_rate'] * 100:.0f}%"
                    f"(최대 {_fmt_won(rules['isa_transfer_cap_krw'])})가 올해 연금 공제한도에 더해져요. "
                    f"{_fmt_won(max_transfer)} 이상 이전 시 최대 공제 — 공제율 {rate * 100:.1f}% 기준"
                    f"{'' if income_bracket else '(낮은 구간)'}."
                ),
                amount=max_transfer,
                benefit=benefit,
                deadline=window_end,
                today=today,
                cta_label="ISA 현황 보기",
                cta_link=_LINK_ACCOUNTS,
                uses_income_bracket=True,
            )
        )
    return actions


def build_isa_contribution_actions(isa_contrib: list[IsaContributionStatus], today: date) -> list[TaxAction]:
    """A3 — 올해 ISA 납입 가능 잔여한도(미납입분 이월 반영)."""
    actions: list[TaxAction] = []
    for acc in isa_contrib:
        remaining = float(acc["remaining_krw"])
        if remaining <= 0:
            continue
        carry = " (지난해 미납입분 이월 포함)" if acc["carryover_applied"] else ""
        actions.append(
            _make_action(
                action_id=f"isa-contribution-{acc['account_id']}",
                category="ISA_CONTRIBUTION",
                title=f"{acc['account_name']}에 올해 {_fmt_won(remaining)} 더 납입 가능",
                detail=(
                    f"ISA 납입한도는 연 2,000만원(총 1억원)이고 못 채운 한도는 다음 해로 이월돼요{carry}. "
                    "ISA 안의 배당·매매이익은 비과세 한도 후 9.9% 분리과세라 과세계좌보다 유리해요. "
                    "입금 내역 기준 추정치예요."
                ),
                amount=remaining,
                benefit=None,
                deadline=None,
                today=today,
                cta_label="입금 내역 기록",
                cta_link=_LINK_ACCOUNTS,
            )
        )
    return actions


def build_overseas_gain_harvest_action(
    positions: list[dict], deduction_krw: float, gain_tax_rate: float, today: date
) -> TaxAction | None:
    """A4 — 해외주식 250만원 기본공제 범위 내 이익실현(취득가 상향). 올해 실현손익은 0으로 가정."""
    gains = sum(p["unrealized_pnl_krw"] for p in positions if p["unrealized_pnl_krw"] > 0)
    if gains <= 0:
        return None
    amount = min(gains, deduction_krw)
    return _make_action(
        action_id="overseas-gain-harvest",
        category="OVERSEAS_GAIN_HARVEST",
        title=f"해외주식 이익 {_fmt_won(amount)}까지 연내 실현 시 양도세 0원",
        detail=(
            f"해외주식 양도차익은 연 {_fmt_won(deduction_krw)}까지 공제돼요. 공제 범위만큼 이익을 실현하고 "
            "다시 사면 취득가가 올라가 나중에 낼 양도세가 줄어요(아래 절감액은 향후 매도 시 기준). "
            "올해 이미 실현한 해외 손익이 있다면 그만큼 공제 여유가 줄어요. 결제일 기준이라 12월 마지막 주 "
            "초까지 매도해야 올해 귀속돼요. 정보 제공 목적이며 매매 권유가 아닙니다."
        ),
        amount=amount,
        benefit=amount * gain_tax_rate,
        deadline=date(today.year, 12, 31),
        today=today,
        cta_label="해외 종목 보기",
        cta_link=_LINK_TAX_ESTIMATE,
    )


def build_loss_harvest_actions(harvesting: list[dict], today: date) -> list[TaxAction]:
    """A5 — 기존 손실수확 추천(tax_service._build_harvesting_recommendations) 상위 N개를 액션화."""
    return [
        _make_action(
            action_id=f"loss-harvest-{item['ticker']}",
            category="TAX_LOSS_HARVEST",
            title=f"{item['name']} 손실 {_fmt_won(abs(item['unrealized_loss_krw']))} 실현 검토",
            detail=(
                "해외주식 과세 이익과 손익을 통산하면 올해 양도세를 줄일 수 있어요. 결제일 기준이라 12월 마지막 주 "
                "초까지 매도해야 올해 귀속돼요. 정보 제공 목적이며 매매 권유가 아닙니다."
            ),
            amount=abs(float(item["unrealized_loss_krw"])),
            benefit=float(item["tax_saved_krw"]),
            deadline=date(today.year, 12, 31),
            today=today,
            cta_label="손실수확 보기",
            cta_link=_LINK_TAX_ESTIMATE,
        )
        for item in harvesting[:_HARVESTING_TOP_N]
    ]


def build_financial_income_action(tax_summary: dict, today: date) -> TaxAction | None:
    """A6 — 과세계좌 배당(금융소득)이 2,000만원 종합과세 기준에 근접/초과."""
    dividend = float(tax_summary.get("dividend_income_krw") or 0)
    if dividend < _FINANCIAL_INCOME_WATCH_KRW:
        return None
    remaining = float(tax_summary.get("comprehensive_tax_remaining_krw") or 0)
    if remaining > 0:
        title = f"금융소득 종합과세까지 {_fmt_won(remaining)} 남음"
        detail = (
            f"올해 과세계좌 배당이 {_fmt_won(dividend)}이에요. 2,000만원을 넘으면 초과분이 다른 소득과 합산돼 "
            "더 높은 세율이 적용될 수 있어요. 연내 추가 배당이 예상되는 고배당 종목은 ISA·연금계좌에서 "
            "보유하는 방법을 검토해 보세요. 이자소득은 반영되지 않았어요."
        )
    else:
        title = "금융소득 종합과세 대상 가능성"
        detail = (
            f"올해 과세계좌 배당이 {_fmt_won(dividend)}로 2,000만원 기준을 넘었어요. 내년부터 고배당 종목은 "
            "ISA·연금계좌로 옮겨 보유하는 방법을 검토해 보세요. 이자소득은 반영되지 않았어요."
        )
    return _make_action(
        action_id="financial-income-limit",
        category="FINANCIAL_INCOME_LIMIT",
        title=title,
        detail=detail,
        amount=remaining if remaining > 0 else None,
        benefit=None,
        deadline=date(today.year, 12, 31),
        today=today,
        cta_label="세금 추정 보기",
        cta_link=_LINK_TAX_ESTIMATE,
    )


def _sort_actions(actions: list[TaxAction]) -> list[TaxAction]:
    """우선순위 → 마감 임박 → 절세액 큰 순."""
    return sorted(
        actions,
        key=lambda a: (
            _PRIORITY_ORDER[a["priority"]],
            a["deadline"] or "9999-12-31",
            -(a["benefit_krw"] or 0.0),
        ),
    )


async def _get_account_tax_types(user_id: uuid.UUID, db: AsyncSession) -> set[str]:
    result = await db.execute(
        select(AssetAccount.tax_type)
        .where(AssetAccount.user_id == user_id, AssetAccount.is_active == True, AssetAccount.tax_type.is_not(None))
        .distinct()
    )
    return {row[0] for row in result.all()}


async def _get_income_bracket(user_id: uuid.UUID, db: AsyncSession) -> str | None:
    result = await db.execute(select(UserSettings.income_bracket).where(UserSettings.user_id == user_id))
    return result.scalar()


async def get_tax_action_plan(user_id: uuid.UUID, year: int, db: AsyncSession) -> TaxActionPlan:
    """연도별 절세 액션 플랜. 도메인 서비스를 순차 호출한다(같은 AsyncSession 동시 사용 금지)."""
    today = today_kst()
    rules = _get_rules(year)
    income_bracket = await _get_income_bracket(user_id, db)
    rate = pension_credit_rate(income_bracket, rules)
    tax_types = await _get_account_tax_types(user_id, db)

    actions: list[TaxAction] = []

    has_ps = "PENSION_SAVINGS" in tax_types
    has_irp = "IRP" in tax_types
    if has_ps or has_irp:
        pension = await calc_pension_contribution_status(user_id, year, db)
        pension_action = build_pension_action(pension, has_ps, has_irp, rate, income_bracket, today)
        if pension_action:
            actions.append(pension_action)

    if "ISA" in tax_types:
        isa = await get_isa_status_summary(user_id, db)
        actions.extend(build_isa_transfer_actions(isa["accounts"], rules, rate, income_bracket, today))
        isa_contrib = await calc_isa_contribution_status(user_id, year, db)
        actions.extend(build_isa_contribution_actions(isa_contrib, today))

    tax_summary = await get_tax_summary(user_id, year, db)
    positions = await get_overseas_positions_detail(user_id, db)
    gain_action = build_overseas_gain_harvest_action(
        positions,
        float(tax_summary["overseas_gain_deduction_krw"]),
        float(tax_summary["rates"]["overseas_tax_rate_pct"]) / 100,
        today,
    )
    if gain_action:
        actions.append(gain_action)
    actions.extend(build_loss_harvest_actions(tax_summary.get("harvesting_recommendations", []), today))
    financial_action = build_financial_income_action(tax_summary, today)
    if financial_action:
        actions.append(financial_action)

    return {
        "year": year,
        "income_bracket": income_bracket,
        "actions": _sort_actions(actions),
        "note": _ACTION_PLAN_NOTE,
    }
