"""키움 리밸런싱 주문 실행 — 국내주식 단건 주문."""

from __future__ import annotations

import structlog

from app.kis.order import is_overseas_market
from app.kiwoom.balance import get_domestic_balance as kiwoom_get_domestic_balance
from app.schemas.rebalancing import ExecutionOrderItem, OrderResult
from app.services._order_quantity_guard import clamp_sell_orders

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


async def _execute_kiwoom_sells_with_clamp(
    sells: list[ExecutionOrderItem],
    access_token: str,
    account_no: str,
    is_mock: bool,
    place_order_fn,
) -> list[OrderResult]:
    """키움 매도 주문을 실행 계좌의 실제 보유수량으로 clamp한 뒤 실행한다.

    포트폴리오 합산 기준으로 계산된 매도 수량이 실행 계좌의 실제 보유수량을 초과하면
    주문이 거부되므로, 실행 직전 실시간 잔고를 조회해 수량을 조정한다.
    잔고 조회 자체가 실패하면 clamp 없이 원래 수량으로 주문을 시도한다(기존 동작 유지).
    """
    if not sells:
        return []

    try:
        balance = await kiwoom_get_domestic_balance(access_token, account_no, is_mock=is_mock)
        held: dict[str, int] = {}
        for p in balance.get("positions", []):
            held[p["ticker"]] = held.get(p["ticker"], 0) + int(p.get("qty", 0))
        adjusted, skipped = clamp_sell_orders(sells, held)
    except Exception as exc:
        logger.warning("kiwoom_sell_clamp_balance_failed", error=str(exc))
        adjusted, skipped = sells, []

    results = list(skipped)
    for order in adjusted:
        results.append(await _execute_kiwoom_single_order(order, access_token, account_no, is_mock, place_order_fn))
    return results
