"""절세 액션 플랜의 순수 계산 — 세법 수치 테이블(`_DEDUCTION_RULES`), 우선순위, 액션별 빌더.

DB 조회와 조합은 `tax_action_service.py`. 세법 수치는 연도별 테이블로 둔다(출처·기준연도 주석) — 매년 확인 후 갱신.
이익실현(A4)·손실수확(A5)은 정보 제공형 문구만 쓰고 자동 주문과 연결하지 않는다(AUTO 파이프라인과 분리).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Literal, TypedDict

from app.constants import COMPREHENSIVE_TAX_THRESHOLD_KRW
from app.enums import IncomeBracket
from app.services.tax.isa_service import (
    ISA_ANNUAL_CONTRIBUTION_LIMIT_KRW,
    ISA_TOTAL_CONTRIBUTION_LIMIT_KRW,
    IsaAccountStatus,
    IsaContributionStatus,
)
from app.services.tax.pension_contribution_service import PensionContributionStatus
from app.services.tax.tax_service import OVERSEAS_FX_BASIS_NOTE, pick_year_rule

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
_FINANCIAL_INCOME_WATCH_KRW = 15_000_000  # 금융소득 종합과세(COMPREHENSIVE_TAX_THRESHOLD_KRW) 접근 경고 시작선
_HARVESTING_TOP_N = 3
_HIGH_PRIORITY_DAYS = 30
_MEDIUM_PRIORITY_DAYS = 90
_HIGH_PRIORITY_BENEFIT_KRW = 500_000
_MEDIUM_PRIORITY_BENEFIT_KRW = 100_000
_PRIORITY_ORDER: dict[ActionPriority, int] = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}

# 입금 기록은 계좌관리 › 내역 › 현금 흐름, ISA 현황은 절세 › 한도 현황의 ISA 카드(#isa-status)로 바로 보낸다
_LINK_CASH_FLOW = "/assets?tab=계좌관리&atab=내역&history=현금 흐름"
_LINK_ISA_STATUS = "/invest-plan?tab=절세&taxTab=한도 현황#isa-status"
_LINK_TAX_ESTIMATE = "/invest-plan?tab=절세&taxTab=세금 추정"

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
    return pick_year_rule(_DEDUCTION_RULES, year)


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


def _fmt_limit(amount: int) -> str:
    """세법 한도 문구용 — 20_000_000 → "2,000만원", 100_000_000 → "1억원"."""
    if amount % 100_000_000 == 0:
        return f"{amount // 100_000_000:,}억원"
    return f"{amount // 10_000:,}만원"


def overseas_sell_deadline(year: int) -> date:
    """올해 귀속 해외주식 매도의 보수적 마감일(12월 마지막 주 월요일). 결제일 기준이라 12/31에 팔면 내년 귀속이다."""
    last_day = date(year, 12, 31)
    return last_day - timedelta(days=last_day.weekday())


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
        cta_link=_LINK_CASH_FLOW,
        uses_income_bracket=True,
    )


def build_isa_transfer_actions(
    isa_accounts: list[IsaAccountStatus],
    rules: _DeductionRules,
    rate: float,
    income_bracket: str | None,
    today: date,
    balances: dict[str, float] | None = None,
) -> list[TaxAction]:
    """A2 — ISA 만기 D-90 ~ 만기 후 60일: 만기자금 연금계좌 이전 시 추가 세액공제.

    혜택은 옮길 수 있는 금액의 10%(상한 300만원)이므로 계좌 평가액(`balances`, 계좌 id → 원)으로 계산한다.
    평가액을 모르면 금액·절세액을 내지 않는다 — 잔액과 무관한 최대치를 보여주면 정렬과 리마인더 합계까지 부풀려진다.
    """
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
        balance = (balances or {}).get(acc["account_id"])
        amount: float | None = None
        benefit: float | None = None
        size_note = f"{_fmt_won(max_transfer)} 이상 이전 시 최대 공제"
        if balance is not None and balance > 0:
            transferable = min(balance, max_transfer)
            extra_limit = transferable * rules["isa_transfer_rate"]
            amount = transferable
            benefit = extra_limit * rate
            if balance < max_transfer:
                size_note = f"현재 평가액 {_fmt_won(balance)} 전액을 옮기면 공제한도 {_fmt_won(extra_limit)} 추가"
        actions.append(
            _make_action(
                action_id=f"isa-transfer-{acc['account_id']}",
                category="ISA_PENSION_TRANSFER",
                title=f"{acc['account_name']} 만기 자금을 연금계좌로 이전",
                detail=(
                    f"{timing} 연금저축/IRP로 옮기면 이전액의 {rules['isa_transfer_rate'] * 100:.0f}%"
                    f"(최대 {_fmt_won(rules['isa_transfer_cap_krw'])})가 올해 연금 공제한도에 더해져요. "
                    f"{size_note} — 공제율 {rate * 100:.1f}% 기준"
                    f"{'' if income_bracket else '(낮은 구간)'}."
                ),
                amount=amount,
                benefit=benefit,
                deadline=window_end,
                today=today,
                cta_label="ISA 현황 보기",
                cta_link=_LINK_ISA_STATUS,
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
                    f"ISA 납입한도는 연 {_fmt_limit(ISA_ANNUAL_CONTRIBUTION_LIMIT_KRW)}"
                    f"(총 {_fmt_limit(ISA_TOTAL_CONTRIBUTION_LIMIT_KRW)})이고 "
                    f"못 채운 한도는 다음 해로 이월돼요{carry}. "
                    "ISA 안의 배당·매매이익은 비과세 한도 후 9.9% 분리과세라 과세계좌보다 유리해요. "
                    "입금 내역 기준 추정치예요."
                ),
                amount=remaining,
                benefit=None,
                deadline=None,
                today=today,
                cta_label="입금 내역 기록",
                cta_link=_LINK_CASH_FLOW,
            )
        )
    return actions


def _realized_note(
    realized_krw: float | None, realized_partial: bool, from_records: bool = False, estimated: bool = False
) -> str:
    if realized_krw is None:
        return (
            "올해 이미 실현한 해외 손익이 있다면 그만큼 공제 여유가 줄어요(실현손익 0 가정) — "
            "매도 내역을 기록하면 반영돼요. "
        )
    basis = "증권사 체결·직접 기록한 매도 기준" if from_records else "증권사 체결 기준"
    note = f"{basis} 올해 실현손익 {_fmt_won(realized_krw)}을 반영했어요. "
    if estimated:
        note += "기록한 매도 일부는 취득가를 평균단가로 추정했어요. "
    if realized_partial:
        note += "자동 집계가 안 되는 계좌(키움·토스·수기)는 매도 내역을 기록해야 반영돼요. "
    return note


def build_overseas_gain_harvest_action(
    positions: list[dict],
    deduction_krw: float,
    gain_tax_rate: float,
    today: date,
    realized_krw: float | None = None,
    realized_partial: bool = False,
    realized_from_records: bool = False,
    realized_estimated: bool = False,
    realized_lookup_failed: bool = False,
) -> TaxAction | None:
    """A4 — 해외주식 250만원 기본공제 범위 내 이익실현(취득가 상향).

    `realized_krw`(증권사 체결 + 미지원 계좌는 수기 SELL 기록 기준 올해 실현손익, E6)가 있으면
    공제 여유 = 공제 − 실현손익(손실이면 여유 증가), 없으면 올해 실현손익 0으로 가정한다.
    증권사 조회가 실패했으면(`realized_lookup_failed`) 0 가정이 위험하다 — 이미 공제를 다 쓴 사용자에게 "더 실현해도
    된다"고 안내하게 되므로 금액 없이 조회 실패만 알린다. 마감일이 지나면 올해 귀속이 안 되므로 내지 않는다.
    """
    gains = sum(p["unrealized_pnl_krw"] for p in positions if p["unrealized_pnl_krw"] > 0)
    deadline = overseas_sell_deadline(today.year)
    if gains <= 0 or today > deadline:
        return None
    if realized_lookup_failed:
        return _make_action(
            action_id="overseas-gain-harvest",
            category="OVERSEAS_GAIN_HARVEST",
            title="올해 해외 실현손익을 확인하지 못했어요",
            detail=(
                "증권사 조회에 실패해 양도세 공제가 얼마나 남았는지 계산하지 않았어요. 이미 공제를 다 썼을 수 있으니 "
                "잠시 후 다시 확인한 뒤 이익 실현을 판단하세요."
            ),
            amount=None,
            benefit=None,
            deadline=deadline,
            today=today,
            cta_label="해외 종목 보기",
            cta_link=_LINK_TAX_ESTIMATE,
        )
    room = max(0.0, deduction_krw - (realized_krw or 0.0))
    if room <= 0:
        return None
    amount = min(gains, room)
    return _make_action(
        action_id="overseas-gain-harvest",
        category="OVERSEAS_GAIN_HARVEST",
        title=f"해외주식 이익 {_fmt_won(amount)}까지 연내 실현 검토 (기본공제 범위)",
        detail=(
            f"해외주식 양도차익은 연 {_fmt_won(deduction_krw)}까지 공제돼요. 공제 범위만큼 이익을 실현하고 "
            "다시 사면 취득가가 올라가 나중에 낼 양도세가 줄어요(아래 절감액은 향후 매도 시 기준). "
            f"{_realized_note(realized_krw, realized_partial, realized_from_records, realized_estimated)}"
            f"{OVERSEAS_FX_BASIS_NOTE} 결제일 기준이라 12월 마지막 주 "
            "초까지 매도해야 올해 귀속돼요. 정보 제공 목적이며 매매 권유가 아닙니다."
        ),
        amount=amount,
        benefit=amount * gain_tax_rate,
        deadline=deadline,
        today=today,
        cta_label="해외 종목 보기",
        cta_link=_LINK_TAX_ESTIMATE,
    )


def build_loss_harvest_actions(
    harvesting: list[dict],
    today: date,
    realized_krw: float | None = None,
    deduction_krw: float = 0.0,
    gain_tax_rate: float = 0.0,
) -> list[TaxAction]:
    """A5 — 기존 손실수확 추천(tax_service._build_harvesting_recommendations) 상위 N개를 액션화.

    추천 목록의 `tax_saved_krw`는 미실현 이익까지 전부 판다는 가정의 값이다. 손실만 팔면 올해 줄어드는 세금은
    이미 실현한 과세 이익만큼뿐이므로 절감액은 그 기준으로 다시 계산하고, 없으면 금액을 내지 않는다.
    """
    deadline = overseas_sell_deadline(today.year)
    if today > deadline:
        return []
    remaining_gain = max(0.0, (realized_krw or 0.0) - deduction_krw)
    actions: list[TaxAction] = []
    for item in harvesting[:_HARVESTING_TOP_N]:
        loss = abs(float(item["unrealized_loss_krw"]))
        offset = min(loss, remaining_gain)
        remaining_gain -= offset
        if offset > 0:
            reason = "올해 이미 실현한 해외주식 이익과 손익을 통산하면 양도세를 줄일 수 있어요."
        elif realized_krw is None:
            reason = "올해 실현손익을 확인하지 못해 절감액을 계산하지 않았어요."
        else:
            reason = (
                "올해 실현한 이익이 공제 범위 안이라 지금 손실만 팔아도 올해 세금은 줄지 않아요. "
                "연내 이익을 실현할 계획이 있을 때 손익을 통산할 수 있어요."
            )
        account_id = item.get("account_id")
        actions.append(
            _make_action(
                # 같은 종목을 두 계좌에 보유하면 항목이 둘이다
                action_id=f"loss-harvest-{account_id}-{item['ticker']}"
                if account_id
                else f"loss-harvest-{item['ticker']}",
                category="TAX_LOSS_HARVEST",
                title=f"{item['name']} 손실 {_fmt_won(loss)} 실현 검토",
                detail=(
                    f"{reason} {OVERSEAS_FX_BASIS_NOTE} 결제일 기준이라 12월 마지막 주 "
                    "초까지 매도해야 올해 귀속돼요. 정보 제공 목적이며 매매 권유가 아닙니다."
                ),
                amount=loss,
                benefit=offset * gain_tax_rate if offset > 0 else None,
                deadline=deadline,
                today=today,
                cta_label="손실수확 보기",
                cta_link=_LINK_TAX_ESTIMATE,
            )
        )
    return actions


def build_financial_income_action(tax_summary: dict, today: date) -> TaxAction | None:
    """A6 — 과세계좌 금융소득(배당 + 기록된 이자, E7)이 2,000만원 종합과세 기준에 근접/초과."""
    dividend = float(tax_summary.get("dividend_income_krw") or 0)
    interest = float(tax_summary.get("interest_income_krw") or 0)
    financial = float(tax_summary.get("financial_income_krw") or (dividend + interest))
    if financial < _FINANCIAL_INCOME_WATCH_KRW:
        return None
    remaining = float(tax_summary.get("comprehensive_tax_remaining_krw") or 0)
    breakdown = (
        f"배당 {_fmt_won(dividend)} + 이자 {_fmt_won(interest)}"
        if interest > 0
        else f"배당 {_fmt_won(dividend)}, 기록된 이자 없음"
    )
    interest_hint = "" if interest > 0 else " 예금·CMA 이자가 있다면 이자 내역을 기록해야 정확해져요."
    if financial <= COMPREHENSIVE_TAX_THRESHOLD_KRW:  # 기준은 "초과" — 정확히 2,000만원은 아직 대상이 아니다
        title = f"금융소득 종합과세까지 {_fmt_won(remaining)} 남음"
        detail = (
            f"올해 과세계좌 금융소득이 {_fmt_won(financial)}({breakdown})이에요. "
            f"{_fmt_limit(COMPREHENSIVE_TAX_THRESHOLD_KRW)}을 넘으면 초과분이 "
            "다른 소득과 합산돼 더 높은 세율이 적용될 수 있어요. 연내 추가 배당이 예상되는 고배당 종목은 "
            "ISA·연금계좌에서 보유하고, 예금 만기·이자 수령 시점을 내년으로 미루는 방법을 검토해 보세요."
            f"{interest_hint}"
        )
    else:
        title = "금융소득 종합과세 대상 가능성"
        detail = (
            f"올해 과세계좌 금융소득이 {_fmt_won(financial)}({breakdown})로 "
            f"{_fmt_limit(COMPREHENSIVE_TAX_THRESHOLD_KRW)} 기준을 넘었어요. "
            "내년부터 고배당 종목은 ISA·연금계좌로 옮겨 보유하고, 예금 이자 수령 시점을 분산하는 방법을 "
            f"검토해 보세요.{interest_hint}"
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
