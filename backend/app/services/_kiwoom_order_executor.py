"""키움 리밸런싱 주문 실행 — 국내주식 단건 주문."""

from __future__ import annotations

import structlog

from app.kis.order import is_overseas_market
from app.schemas.rebalancing import ExecutionOrderItem, OrderResult

logger = structlog.get_logger()


async def _execute_kiwoom_single_order(
    order: ExecutionOrderItem,
    access_token: str,
    account_no: str,
    is_mock: bool,
    place_order_fn,
) -> OrderResult:
    """키움 단건 주문 실행 — 국내주식만 지원 (해외주식 미지원)."""
    if order.quantity <= 0:
        return OrderResult(
            ticker=order.ticker,
            name=order.name,
            market=order.market,
            side=order.side,
            quantity=order.quantity,
            status="SKIPPED",
            error_msg="주문 수량이 0 이하입니다.",
        )
    if is_overseas_market(order.market):
        return OrderResult(
            ticker=order.ticker,
            name=order.name,
            market=order.market,
            side=order.side,
            quantity=order.quantity,
            status="SKIPPED",
            error_msg="키움 연동은 국내주식만 지원합니다.",
        )

    try:
        result = await place_order_fn(
            access_token,
            account_no,
            side=order.side,
            ticker=order.ticker,
            quantity=order.quantity,
            is_mock=is_mock,
            order_type=order.order_type,
            limit_price=order.limit_price,
        )
        logger.info(
            "kiwoom_order_placed",
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
        )
    except Exception as e:
        logger.warning("kiwoom_order_failed", ticker=order.ticker, side=order.side, error=str(e))
        return OrderResult(
            ticker=order.ticker,
            name=order.name,
            market=order.market,
            side=order.side,
            quantity=order.quantity,
            status="FAILED",
            error_msg=str(e),
            order_type=order.order_type,
        )
