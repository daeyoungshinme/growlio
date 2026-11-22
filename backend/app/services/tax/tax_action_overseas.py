"""해외주식 절세 액션(이익실현·손실수확)과 연말 귀속 마감일 — `tax_action_builders`의 공용 조각을 쓴다.

정보 제공형 문구만 쓰고 자동 주문과 연결하지 않는다(AUTO 파이프라인과 분리).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.services.tax.tax_action_builders import (
    _HARVESTING_TOP_N,
    _LINK_TAX_ESTIMATE,
    TaxAction,
    _fmt_won,
    _make_action,
)
from app.services.tax.tax_service import OVERSEAS_FX_BASIS_NOTE
from app.utils.market_hours import us_year_end_trade_deadline


def overseas_sell_deadline(year: int) -> date:
    """올해 귀속 해외주식 매도 마감일(결제일 기준 — 12월 마지막 NYSE 거래일에서 2거래일 전)."""
    return us_year_end_trade_deadline(year)


_ET = ZoneInfo("America/New_York")
_US_CLOSE_HOUR_ET = 16


def deadline_passed(today: date, deadline: date, now: datetime | None = None) -> bool:
    """올해 귀속 매도 마감(`deadline`, 미국 날짜)이 지났는지 — `today`는 KST 날짜.

    마감일 장 마감(ET 16시)은 KST로 다음 날 새벽(06시, 서머타임 05시)이라 KST 날짜끼리 비교하면 그 새벽 동안
    아직 주문할 수 있는데 액션이 사라진다(plans/146 B4). KST 마감 다음 날에만 실제 시각(ET)으로 판정한다.
    """
    if today <= deadline:
        return False
    if today > deadline + timedelta(days=1):
        return True
    now_et = (now or datetime.now(UTC)).astimezone(_ET)
    return now_et.date() > deadline or now_et.hour >= _US_CLOSE_HOUR_ET


def _deadline_note(deadline: date) -> str:
    return f"결제일 기준이라 {deadline.month}월 {deadline.day}일(미국 거래일)까지 매도해야 올해 귀속돼요."


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
    now: datetime | None = None,
) -> TaxAction | None:
    """A4 — 해외주식 250만원 기본공제 범위 내 이익실현(취득가 상향).

    `realized_krw`(증권사 체결 + 미지원 계좌는 수기 SELL 기록 기준 올해 실현손익, E6)가 있으면
    공제 여유 = 공제 − 실현손익(손실이면 여유 증가), 없으면 올해 실현손익 0으로 가정한다.
    증권사 조회가 실패했으면(`realized_lookup_failed`) 0 가정이 위험하다 — 이미 공제를 다 쓴 사용자에게 "더 실현해도
    된다"고 안내하게 되므로 금액 없이 조회 실패만 알린다. 마감일이 지나면 올해 귀속이 안 되므로 내지 않는다.
    """
    gains = sum(p["unrealized_pnl_krw"] for p in positions if p["unrealized_pnl_krw"] > 0)
    deadline = overseas_sell_deadline(today.year)
    if gains <= 0 or deadline_passed(today, deadline, now):
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
            f"{OVERSEAS_FX_BASIS_NOTE} {_deadline_note(deadline)} 정보 제공 목적이며 매매 권유가 아닙니다."
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
    now: datetime | None = None,
) -> list[TaxAction]:
    """A5 — 기존 손실수확 추천(tax_service._build_harvesting_recommendations) 상위 N개를 액션화.

    추천 목록의 `tax_saved_krw`는 미실현 이익까지 전부 판다는 가정의 값이다. 손실만 팔면 올해 줄어드는 세금은
    이미 실현한 과세 이익만큼뿐이므로 절감액은 그 기준으로 다시 계산하고, 없으면 금액을 내지 않는다.
    """
    deadline = overseas_sell_deadline(today.year)
    if deadline_passed(today, deadline, now):
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
                    f"{reason} {OVERSEAS_FX_BASIS_NOTE} {_deadline_note(deadline)} "
                    "정보 제공 목적이며 매매 권유가 아닙니다."
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
