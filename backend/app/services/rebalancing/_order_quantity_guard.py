"""매도/매수 주문 수량을 실제 계좌 잔고에 맞춰 clamp하는 공용 헬퍼.

리밸런싱 매도 수량은 포트폴리오에 연결된 전 계좌의 합산 보유수량 기준으로 계산되지만,
실제 주문은 단일 실행 계좌에만 제출된다. 실행 계좌의 실제 보유수량을 초과하는 매도 주문은
KIS/키움 API가 거부하므로, 주문 직전 실시간 잔고로 수량을 조정한다.
매수도 대칭적으로 — 계획 수량 그대로 밀어붙이면 매도 leg가 예상보다 적게 체결됐을 때
실제 가용 현금을 초과할 수 있어, 실행 직전 주문가능금액으로 수량을 조정한다.
"""

from __future__ import annotations

import math
from collections.abc import Callable

import structlog

from app.schemas.rebalancing import ExecutionOrderItem, OrderResult

logger = structlog.get_logger()

# 금액/가격 나눗셈의 부동소수 오차(예: 300000/100000.00000001 → 2.9999999)로 1주가 빠지지 않게 하는 허용치
_SHARES_EPSILON = 1e-9


def floor_shares(value: float) -> int:
    """목표 금액 ÷ 가격을 정수 주식 수로 내린다(부동소수 경계 오차 보정)."""
    return math.floor(value + _SHARES_EPSILON)


def clamp_sell_orders(
    sells: list[ExecutionOrderItem],
    held_qty: dict[str, int],
    key_fn: Callable[[ExecutionOrderItem], str] = lambda o: o.ticker,
) -> tuple[list[ExecutionOrderItem], list[OrderResult]]:
    """매도 주문 수량을 held_qty(실제 보유수량 맵)에 맞춰 조정한다.

    보유수량이 0이면 SKIPPED 결과로 즉시 반환하고, 부족하면 보유수량만큼 줄인다.
    Returns: (실행 가능한 조정된 주문 목록, SKIPPED 처리된 결과 목록)
    """
    adjusted: list[ExecutionOrderItem] = []
    skipped: list[OrderResult] = []

    for order in sells:
        actual = held_qty.get(key_fn(order), 0)

        if actual <= 0:
            skipped.append(
                OrderResult.for_order(
                    order,
                    "SKIPPED",
                    error_msg="해당 계좌에 보유 수량이 없어 매도를 건너뜁니다.",
                )
            )
            continue

        if actual < order.quantity:
            logger.warning(
                "sell_quantity_clamped",
                ticker=order.ticker,
                market=order.market,
                requested_qty=order.quantity,
                actual_qty=actual,
            )
            adjusted.append(order.model_copy(update={"quantity": actual}))
        else:
            adjusted.append(order)

    return adjusted, skipped


BUDGET_SHORT_MSG = "주문가능금액이 부족해 매수를 건너뜁니다."


def budget_skipped_result(order: ExecutionOrderItem) -> OrderResult:
    """예산이 모자라 내지 못한 매수 주문의 SKIPPED 결과."""
    return OrderResult.for_order(
        order,
        "SKIPPED",
        error_msg=BUDGET_SHORT_MSG,
    )


def fit_buy_to_budget(order: ExecutionOrderItem, budget: float) -> tuple[ExecutionOrderItem | None, int]:
    """매수 주문 하나를 budget 안에 맞춘다 — (낼 주문 또는 None, 못 산 수량).

    지정가는 `int(budget // 지정가)`주까지만 낸다. 1주도 못 사면 None과 전체 수량을 돌려준다.
    시장가는 체결가를 미리 알 수 없어 그대로 통과시킨다(못 산 수량 0).
    FULL 전략의 `clamp_buy_orders_to_budget`와 TWO_PHASE의 `_execute_buys_within_budget`가 같이 쓴다.
    """
    price = order.limit_price
    if not price or price <= 0:
        return order, 0
    affordable_qty = int(budget // price) if budget > 0 else 0
    if affordable_qty <= 0:
        return None, order.quantity
    execute_qty = min(order.quantity, affordable_qty)
    if execute_qty == order.quantity:
        return order, 0
    return order.model_copy(update={"quantity": execute_qty}), order.quantity - execute_qty


def clamp_buy_orders_to_budget(
    buy_orders: list[ExecutionOrderItem],
    budget: float,
) -> tuple[list[ExecutionOrderItem], list[OrderResult]]:
    """매수 주문 수량을 budget(실행 직전 조회한 주문가능금액) 범위 내로 조정한다.

    포트폴리오 합산 계획 수량을 그대로 실행하면, 같은 실행 묶음의 매도 leg가 예상보다
    적게 체결됐거나(AUTO 2단계 플랜처럼 매도·매수가 분리 실행되는 경우 포함) 아예
    실패·만료됐을 때 매수가 실제 가용 현금을 초과할 수 있다. 지정가 주문은 예산 초과분만큼
    수량을 줄이고 예산이 아예 없으면 SKIPPED 처리한다. 시장가 주문은 실행 시점 체결가를
    미리 알 수 없어 clamp 대상에서 제외한다 — 최종 안전장치는 브로커의 주문 거부에 있다.
    예산은 계획 금액으로 바로 차감한다(체결 여부와 무관).

    Returns: (실행 가능한 조정된 주문 목록, SKIPPED 처리된 결과 목록)
    """
    adjusted: list[ExecutionOrderItem] = []
    skipped: list[OrderResult] = []
    remaining_budget = budget

    for order in buy_orders:
        fitted, leftover_qty = fit_buy_to_budget(order, remaining_budget)
        if fitted is None:
            skipped.append(budget_skipped_result(order))
            continue
        if leftover_qty > 0:
            logger.warning(
                "buy_quantity_clamped_to_budget",
                ticker=order.ticker,
                market=order.market,
                requested_qty=order.quantity,
                clamped_qty=fitted.quantity,
            )
        adjusted.append(fitted)
        if fitted.limit_price and fitted.limit_price > 0:
            remaining_budget -= fitted.quantity * fitted.limit_price

    return adjusted, skipped
