"""매도 주문 수량을 실제 계좌 보유수량으로 clamp하는 공용 헬퍼.

리밸런싱 매도 수량은 포트폴리오에 연결된 전 계좌의 합산 보유수량 기준으로 계산되지만,
실제 주문은 단일 실행 계좌에만 제출된다. 실행 계좌의 실제 보유수량을 초과하는 매도 주문은
KIS/키움 API가 거부하므로, 주문 직전 실시간 잔고로 수량을 조정한다.
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
