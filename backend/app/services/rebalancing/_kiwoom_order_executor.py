"""키움 리밸런싱 주문 실행 — 국내주식·미국주식 단건 주문."""

from __future__ import annotations

import structlog

from app.kis.order import is_overseas_market
from app.kiwoom.balance import get_domestic_balance as kiwoom_get_domestic_balance
from app.kiwoom.balance import get_overseas_balance as kiwoom_get_overseas_balance
from app.kiwoom.order import place_domestic_order, place_overseas_order
from app.schemas.rebalancing import ExecutionOrderItem, OrderResult
from app.services.rebalancing._order_executor_common import execute_single_order
from app.services.rebalancing._order_quantity_guard import clamp_sell_orders

logger = structlog.get_logger()


async def _execute_kiwoom_single_order(
    order: ExecutionOrderItem,
    access_token: str,
    account_no: str,
    is_mock: bool,
) -> OrderResult:
    """키움 단건 주문 실행 — 국내/해외를 market으로 분기해 실행한다."""

    async def _place() -> dict:
        if is_overseas_market(order.market):
            return await place_overseas_order(
                access_token,
                account_no,
                side=order.side,
                ticker=order.ticker,
                market=order.market,
                quantity=order.quantity,
                is_mock=is_mock,
                order_type=order.order_type,
                limit_price=order.limit_price,
            )
        return await place_domestic_order(
            access_token,
            account_no,
            side=order.side,
            ticker=order.ticker,
            quantity=order.quantity,
            is_mock=is_mock,
            order_type=order.order_type,
            limit_price=order.limit_price,
        )

    return await execute_single_order(order, _place, is_mock, log_prefix="kiwoom_order")


async def _execute_kiwoom_sells_with_clamp(
    sells: list[ExecutionOrderItem],
    access_token: str,
    account_no: str,
    is_mock: bool,
) -> list[OrderResult]:
    """키움 매도 주문을 실행 계좌의 실제 보유수량으로 clamp한 뒤 실행한다.

    포트폴리오 합산 기준으로 계산된 매도 수량이 실행 계좌의 실제 보유수량을 초과하면
    주문이 거부되므로, 실행 직전 실시간 잔고를 조회해 수량을 조정한다.
    잔고 조회 자체가 실패하면 clamp 없이 원래 수량으로 주문을 시도한다(기존 동작 유지).
    국내/해외 매도는 잔고 조회 API가 분리되어 있어 각각 clamp한다(KIS 실행기와 동일 패턴).
    """
    if not sells:
        return []

    domestic_sells = [o for o in sells if not is_overseas_market(o.market)]
    overseas_sells = [o for o in sells if is_overseas_market(o.market)]

    results: list[OrderResult] = []

    if domestic_sells:
        try:
            balance = await kiwoom_get_domestic_balance(access_token, account_no, is_mock=is_mock)
            held: dict[str, int] = {}
            for p in balance.get("positions", []):
                held[p["ticker"]] = held.get(p["ticker"], 0) + int(p.get("qty", 0))
            adjusted, skipped = clamp_sell_orders(domestic_sells, held)
        except Exception as exc:
            logger.warning("kiwoom_sell_clamp_domestic_balance_failed", error=str(exc))
            adjusted, skipped = domestic_sells, []

        results.extend(skipped)
        for order in adjusted:
            results.append(await _execute_kiwoom_single_order(order, access_token, account_no, is_mock))

    if overseas_sells:
        try:
            balance = await kiwoom_get_overseas_balance(access_token, account_no, is_mock=is_mock)
            held_overseas: dict[str, int] = {}
            for p in balance.get("positions", []):
                key = f"{p['ticker']}:{str(p.get('market', '')).upper()}"
                held_overseas[key] = held_overseas.get(key, 0) + int(p.get("qty", 0))
            adjusted_o, skipped_o = clamp_sell_orders(
                overseas_sells, held_overseas, key_fn=lambda o: f"{o.ticker}:{o.market.upper()}"
            )
        except Exception as exc:
            logger.warning("kiwoom_sell_clamp_overseas_balance_failed", error=str(exc))
            adjusted_o, skipped_o = overseas_sells, []

        results.extend(skipped_o)
        for order in adjusted_o:
            results.append(await _execute_kiwoom_single_order(order, access_token, account_no, is_mock))

    return results
