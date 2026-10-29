"""KIS/Kiwoom 단건 주문 실행 공용 헬퍼 — 결과 판정·OrderResult 생성·로깅."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import structlog

from app.core.logging import public_error_message, redact_secrets
from app.kis.order import is_overseas_market
from app.schemas.rebalancing import ExecutionOrderItem, OrderResult
from app.services.rebalancing.krx_tick import domestic_limit_price

logger = structlog.get_logger()

PlaceOrderFn = Callable[[], Awaitable[dict]]


def snap_domestic_limit_price(order: ExecutionOrderItem) -> ExecutionOrderItem:
    """국내 지정가를 호가 격자에 맞춘 사본을 돌려준다(시장가·해외는 그대로).

    수동 입력 지정가가 호가 격자에서 벗어나면 broker가 거부한다 — 주문 전에 맞추고, 결과(OrderResult.price)에도
    실제 주문가가 남도록 사본을 쓴다(plans/61 C2). 실시간 현재가는 이미 격자 위라 값이 바뀌지 않는다.
    """
    if order.order_type != "LIMIT" or is_overseas_market(order.market):
        return order
    return order.model_copy(update={"limit_price": domestic_limit_price(order.limit_price, order.side, order.name)})


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
            order_org_no=result.get("order_org_no"),
            order_type=order.order_type,
            price=price,
        )
    except Exception as e:
        logger.warning(
            f"{log_prefix}_failed",
            ticker=order.ticker,
            side=order.side,
            quantity=order.quantity,
            error=redact_secrets(str(e)),
            error_type=type(e).__name__,
        )
        return OrderResult(
            ticker=order.ticker,
            name=order.name,
            market=order.market,
            side=order.side,
            quantity=order.quantity,
            status="FAILED",
            error_msg=public_error_message(e),
            order_type=order.order_type,
            price=price,
        )
