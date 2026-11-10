"""정기 적립 정액 분할(plans/120, 순수 함수).

스케줄일에 정한 금액(원)만 포트폴리오 목표 비중대로 나눠 산다 — 현재 보유 비중과는 무관한 순수 적립식이다.
예수금이 더 많아도 이 금액을 넘지 않는다.

- 대상: 목표 비중 > 0이고 시세·주문이 있는 종목(현금·부동산 등 `is_non_tradable` 제외). 비중은 대상 합으로 재정규화.
- 지수 그룹: 금액 전부를 매수 대상 멤버 1개(`buy_target_member` — ISA·연금이면 국내 대체 종목)에 배정.
- 수량: `floor(배분액 / 현재가)`. 남은 돈은 "배분액 대비 덜 산 금액이 큰 종목"부터 1주씩 보충(총액 ≤ 금액).
- 1주 가격이 너무 비싸 0주가 된 종목은 `unaffordable`로 돌려준다(이번 회차 미매수 안내용).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.constants import OVERSEAS_MARKETS, TAX_DEFERRED_TAX_TYPES, is_non_tradable
from app.schemas.rebalancing import RebalancingItem
from app.services.rebalancing._order_quantity_guard import floor_shares
from app.services.rebalancing.group_expansion import buy_target_member, is_group_item


@dataclass
class DcaAllocation:
    items: list[RebalancingItem] = field(default_factory=list)
    """매수 수량(`shares_to_trade` > 0)이 정해진 종목 행 — 그룹은 이미 멤버 행으로 펼쳐져 있다."""
    unaffordable: list[str] = field(default_factory=list)
    """배분액으로 1주도 못 사 이번 회차에서 빠진 종목명."""
    spent_krw: float = 0.0


def dca_buy_rows(items: list[RebalancingItem], buy_tax_type: str | None) -> list[tuple[RebalancingItem, float]]:
    """분석 행 → (매수 행 사본, 목표 비중) 목록. 원본 분석 행은 바꾸지 않는다."""
    rows: list[tuple[RebalancingItem, float]] = []
    for item in items:
        weight = float(item.target_weight_pct or 0)
        if weight <= 0:
            continue
        if is_group_item(item):
            if not item.members:
                continue
            target = buy_target_member(item.members, buy_tax_type).model_copy(deep=True)
            target.group_key = None
        else:
            target = item.model_copy(deep=True)
        if is_non_tradable(target.ticker, target.market):
            continue
        # 과세이연 계좌는 해외 종목을 못 산다(order_builder도 건너뜀) — 그 몫이 매번 남지 않게 다른 종목에 재배분한다
        if target.market in OVERSEAS_MARKETS and buy_tax_type in TAX_DEFERRED_TAX_TYPES:
            continue
        target.members = []
        rows.append((target, weight))
    return rows


def allocate_dca_amount(rows: list[tuple[RebalancingItem, float]], amount_krw: float) -> DcaAllocation:
    """금액을 비중대로 나눠 종목별 매수 수량을 정한다. 행의 `current_price_krw`는 라이브 시세여야 한다."""
    priced = [(item, weight) for item, weight in rows if item.current_price_krw and item.current_price_krw > 0]
    no_price = [item.name for item, _ in rows if not (item.current_price_krw and item.current_price_krw > 0)]
    total_weight = sum(weight for _, weight in priced)
    if amount_krw <= 0 or total_weight <= 0:
        return DcaAllocation(unaffordable=[item.name for item, _ in rows])

    budgets = [amount_krw * weight / total_weight for _, weight in priced]
    prices = [float(item.current_price_krw or 0) for item, _ in priced]
    qtys = [floor_shares(budget / price) for budget, price in zip(budgets, prices, strict=True)]
    leftover = amount_krw - sum(q * p for q, p in zip(qtys, prices, strict=True))

    # 남은 돈으로 1주씩 보충 — 매번 "배분액 대비 덜 산 금액"이 가장 큰 종목(살 수 있는 것 중)을 고른다
    while True:
        best = -1
        best_unmet = float("-inf")
        for i, price in enumerate(prices):
            if price > leftover + 1e-6:
                continue
            unmet = budgets[i] - qtys[i] * price
            if unmet > best_unmet:
                best, best_unmet = i, unmet
        if best < 0:
            break
        qtys[best] += 1
        leftover -= prices[best]

    result = DcaAllocation(unaffordable=list(no_price))
    for (item, _), qty, price in zip(priced, qtys, prices, strict=True):
        if qty <= 0:
            result.unaffordable.append(item.name)
            continue
        value = qty * price
        current_qty = item.current_qty or 0.0
        item.shares_to_trade = float(qty)
        item.target_qty = current_qty + qty
        item.diff_krw = round(value, 0)
        item.target_value_krw = round(item.current_value_krw + value, 0)
        result.items.append(item)
        result.spent_krw += value
    result.spent_krw = round(result.spent_krw, 0)
    return result
