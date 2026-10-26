"""지수 그룹 항목 → 종목 단위 매매 전개 (plans/74, 순수 함수).

그룹 항목은 이탈을 대표 종목+멤버 합계로 판정하지만 주문은 종목 단위로 나가야 한다. 그룹의 금액 차이를
멤버에 배분하는 규칙:

- 매수(부족): 대표 매수 종목으로 전부 산다. 매수 계좌가 ISA·연금저축·IRP이고 대표 종목이 해외 상장이면
  국내 대체 종목(DOMESTIC_ALT)으로 산다 — 대체 종목이 없으면 그대로 두고 order_builder가 해외 매수를 건너뛴다.
- 매도(초과): 대표가 아닌 멤버부터 보유액이 작은 순으로 전량 정리하고(한 종목으로 모이는 방향), 남은 금액은
  대표 종목에서 판다. 계좌 간 매도 순서는 order_builder `_build_sell_orders`가 정한다.
- 레버리지 멤버(QLD=2배): 그룹 차이는 노출 단위다. 레버리지 멤버를 1원 팔면 노출이 배수만큼 줄어드므로
  줄일 노출 ÷ 배수만큼만 판다. 매수 대상(대표·국내 대체)은 항상 1배라 매수 금액 = 노출 차이.

전개된 멤버 행은 일반 항목과 같은 모양(`target_value_krw`·`current_qty`)이라 `refresh_live_prices`가
`floor(target_value / price) - current_qty`로 다시 계산해도 같은 의미가 유지된다.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.constants import DOMESTIC_MARKETS, TAX_DEFERRED_TAX_TYPES
from app.schemas.rebalancing import RebalancingItem
from app.services.rebalancing._order_quantity_guard import floor_shares

ROLE_PRIMARY = "PRIMARY"
ROLE_MEMBER = "MEMBER"
ROLE_DOMESTIC_ALT = "DOMESTIC_ALT"


def is_group_item(item: object) -> bool:
    return bool(getattr(item, "group_key", None))


def _buy_target(members: list[RebalancingItem], buy_account_tax_type: str | None) -> RebalancingItem:
    primary = next(m for m in members if m.group_role == ROLE_PRIMARY)
    if buy_account_tax_type in TAX_DEFERRED_TAX_TYPES and primary.market not in DOMESTIC_MARKETS:
        alt = next((m for m in members if m.group_role == ROLE_DOMESTIC_ALT), None)
        if alt is not None:
            return alt
    return primary


def _set_trade(member: RebalancingItem, target_value: float, base_krw: float) -> None:
    member.target_value_krw = round(target_value, 0)
    member.diff_krw = round(target_value - member.current_value_krw, 0)
    member.target_weight_pct = round(target_value / base_krw * 100, 2) if base_krw > 0 else 0.0
    member.weight_diff_pct = round(member.target_weight_pct - member.current_weight_pct, 2)
    qty = member.current_qty or 0.0
    if target_value <= 0:
        member.target_qty = 0.0
        member.shares_to_trade = -qty if qty else None
        return
    price = member.current_price_krw
    if price and price > 0:
        member.target_qty = float(floor_shares(target_value / price))
        member.shares_to_trade = member.target_qty - qty
    else:
        member.target_qty = None
        member.shares_to_trade = None


def _base_krw(group: RebalancingItem) -> float:
    if group.target_weight_pct > 0:
        return group.target_value_krw * 100 / group.target_weight_pct
    if group.current_weight_pct > 0:
        return group.current_value_krw * 100 / group.current_weight_pct
    return 0.0


def allocate_group_trades(group: RebalancingItem, buy_account_tax_type: str | None = None) -> list[RebalancingItem]:
    """그룹 행의 금액 차이를 멤버에 배분한 멤버 행 사본 전체를 반환한다(매매 없는 멤버는 수량 0)."""
    members = [m.model_copy(deep=True) for m in group.members]
    if not members:
        return []
    base_krw = _base_krw(group)
    for m in members:
        m.target_value_krw = m.current_value_krw
        m.target_weight_pct = m.current_weight_pct
        m.weight_diff_pct = 0.0
        m.diff_krw = 0.0
        m.target_qty = m.current_qty
        m.shares_to_trade = 0.0
    diff = group.target_value_krw - group.current_value_krw
    if diff > 0:
        buyer = _buy_target(members, buy_account_tax_type)
        _set_trade(buyer, buyer.current_value_krw + diff, base_krw)
    elif diff < 0:
        remaining = -diff
        others = sorted(
            (m for m in members if m.group_role != ROLE_PRIMARY and m.current_value_krw > 0),
            key=lambda m: m.current_value_krw,
        )
        primary = [m for m in members if m.group_role == ROLE_PRIMARY and m.current_value_krw > 0]
        for m in [*others, *primary]:
            if remaining <= 0:
                break
            leverage = m.leverage or 1.0
            take_exposure = min(remaining, m.current_value_krw * leverage)
            _set_trade(m, m.current_value_krw - take_exposure / leverage, base_krw)
            remaining -= take_exposure
    return members


def _has_trade(member: RebalancingItem) -> bool:
    return member.target_value_krw != member.current_value_krw


def expand_group_items(
    items: Iterable[RebalancingItem], buy_account_tax_type: str | None = None
) -> list[RebalancingItem]:
    """그룹 행을 매매가 있는 멤버 행으로 펼친다(그 외 항목은 그대로) — 주문 생성 직전에 호출.

    매매 없는 멤버는 넣지 않는다 — `refresh_live_prices`가 라이브 시세로 수량을 다시 계산하면서
    목표=현재인 멤버에 시세 차이만큼의 매매를 만들기 때문.
    그룹 행의 members도 이번 배분 결과로 바꿔 둔다 — 반환된 멤버 행과 같은 객체라 이후 `refresh_live_prices`의
    라이브 시세 갱신이 `iter_trade_items(analysis.items)`(세금영향 게이트)에도 반영된다.
    """
    result: list[RebalancingItem] = []
    for item in items:
        if is_group_item(item):
            item.members = allocate_group_trades(item, buy_account_tax_type)
            result.extend(m for m in item.members if _has_trade(m))
        else:
            result.append(item)
    return result


def iter_trade_items(items: Iterable[RebalancingItem]) -> list[RebalancingItem]:
    """분석 결과(이미 대표 종목 기준으로 배분된 members)를 종목 단위로 평탄화 — 세금 미리보기 등 표시용."""
    result: list[RebalancingItem] = []
    for item in items:
        if is_group_item(item):
            result.extend(m for m in item.members if _has_trade(m))
        else:
            result.append(item)
    return result
