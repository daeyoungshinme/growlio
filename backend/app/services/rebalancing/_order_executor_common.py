"""KIS/Kiwoom 단건 주문 실행 공용 헬퍼 — 결과 판정·OrderResult 생성·로깅."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import structlog

from app.schemas.rebalancing import ExecutionOrderItem, OrderResult

logger = structlog.get_logger()

PlaceOrderFn = Callable[[], Awaitable[dict]]


async def execute_single_order(
    order: ExecutionOrderItem,
    place_order: PlaceOrderFn,
    is_mock: bool,
    log_prefix: str,
) -> OrderResult:
    """주문 배치를 실행하고 결과를 OrderResult로 변환한다.

    `place_order`는 브로커별 실제 주문 API 호출을 캡슐화한 콜백(인자 없이 호출)이다.
    수량<=0 skip, 성공/실패 로깅과 OrderResult 필드 구성은 KIS/Kiwoom이 동일했던 부분.
    """
    price = order.limit_price or order.reference_price

    if order.quantity <= 0:
        return OrderResult(
            ticker=order.ticker,
            name=order.name,
            market=order.market,
            side=order.side,
            quantity=order.quantity,
            status="SKIPPED",
            error_msg="주문 수량이 0 이하입니다.",
            price=price,
        )

    try:
        result = await place_order()
        logger.info(
            f"{log_prefix}_placed",
            ticker=order.ticker,
            side=order.side,
            quantity=order.quantity,
            order_no=result.get("order_no"),
            is_mock=is_mock,
            order_type=order.order_type,
        )
        return OrderResult(
            ticker=order.ticker,
            name=order.name,
            market=order.market,
            side=order.side,
            quantity=order.quantity,
            status="SUCCESS",
            order_no=result.get("order_no"),
            order_type=order.order_type,
            price=price,
        )
    except Exception as e:
        logger.warning(
            f"{log_prefix}_failed",
            ticker=order.ticker,
            side=order.side,
            quantity=order.quantity,
            error=str(e),
        )
        return OrderResult(
            ticker=order.ticker,
            name=order.name,
            market=order.market,
            side=order.side,
            quantity=order.quantity,
            status="FAILED",
            error_msg=str(e),
            order_type=order.order_type,
            price=price,
        )
