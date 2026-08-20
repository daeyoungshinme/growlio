"""매도/매수 주문 수량을 실제 계좌 잔고에 맞춰 clamp하는 공용 헬퍼.

리밸런싱 매도 수량은 포트폴리오에 연결된 전 계좌의 합산 보유수량 기준으로 계산되지만,
실제 주문은 단일 실행 계좌에만 제출된다. 실행 계좌의 실제 보유수량을 초과하는 매도 주문은
KIS/키움 API가 거부하므로, 주문 직전 실시간 잔고로 수량을 조정한다.
매수도 대칭적으로 — 계획 수량 그대로 밀어붙이면 매도 leg가 예상보다 적게 체결됐을 때
실제 가용 현금을 초과할 수 있어, 실행 직전 주문가능금액으로 수량을 조정한다.
"""

from __future__ import annotations

from collections.abc import Callable

import structlog

from app.schemas.rebalancing import ExecutionOrderItem, OrderResult

logger = structlog.get_logger()


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
                OrderResult(
                    ticker=order.ticker,
                    name=order.name,
                    market=order.market,
                    side=order.side,
                    quantity=order.quantity,
                    status="SKIPPED",
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

    Returns: (실행 가능한 조정된 주문 목록, SKIPPED 처리된 결과 목록)
    """
    adjusted: list[ExecutionOrderItem] = []
    skipped: list[OrderResult] = []
    remaining_budget = budget

    for order in buy_orders:
        price = order.limit_price
        if not price or price <= 0:
            adjusted.append(order)
            continue

        if remaining_budget <= 0:
            skipped.append(
                OrderResult(
                    ticker=order.ticker,
                    name=order.name,
                    market=order.market,
                    side=order.side,
                    quantity=order.quantity,
                    status="SKIPPED",
                    error_msg="주문가능금액이 부족해 매수를 건너뜁니다.",
                )
            )
            continue

        affordable_qty = int(remaining_budget // price)
        if affordable_qty <= 0:
            skipped.append(
                OrderResult(
                    ticker=order.ticker,
                    name=order.name,
                    market=order.market,
                    side=order.side,
                    quantity=order.quantity,
                    status="SKIPPED",
                    error_msg="주문가능금액이 부족해 매수를 건너뜁니다.",
                )
            )
            continue

        execute_qty = min(order.quantity, affordable_qty)
        if execute_qty < order.quantity:
            logger.warning(
                "buy_quantity_clamped_to_budget",
                ticker=order.ticker,
                market=order.market,
                requested_qty=order.quantity,
                clamped_qty=execute_qty,
            )
            adjusted.append(order.model_copy(update={"quantity": execute_qty}))
        else:
            adjusted.append(order)
        remaining_budget -= execute_qty * price

    return adjusted, skipped
