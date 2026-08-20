"""키움 리밸런싱 주문 실행 — 국내주식·미국주식 단건 주문."""

from __future__ import annotations

import structlog

from app.kis.order import is_overseas_market
from app.kiwoom.balance import get_domestic_balance as kiwoom_get_domestic_balance
from app.kiwoom.balance import get_overseas_balance as kiwoom_get_overseas_balance
from app.kiwoom.order import place_domestic_order, place_overseas_order
from app.schemas.rebalancing import ExecutionOrderItem, OrderResult
from app.services.rebalancing._order_executor_common import execute_single_order
from app.services.rebalancing._order_quantity_guard import clamp_buy_orders_to_budget, clamp_sell_orders

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


async def _execute_kiwoom_buys_with_cash_check(
    buys: list[ExecutionOrderItem],
    access_token: str,
    account_no: str,
    is_mock: bool,
) -> list[OrderResult]:
    """키움 FULL 전략 매수 실행 — 매도 완료 후 실제 예수금을 재조회해 예산 내로 clamp한다.

    KIS 실행기의 `_execute_buys_with_cash_check`와 동일한 목적(매도 leg가 예상보다 적게
    체결되거나 실패해도 매수가 실제 가용 현금을 초과하지 않도록)의 대응 함수. 키움에는 KIS의
    `get_orderable_cash()`(미수 없는 매수가능금액 전용 조회)에 대응하는 API가 없어,
    `get_domestic_balance()`가 함께 반환하는 국내 현금 예수금(`deposit_krw`)을 예산으로 쓴다
    — 미수/신용 한도까지는 반영하지 못하는 보수적인 근사치이지만, 예수금을 초과해 시도하는
    것보다는 안전하다.

    해외 주식 포함 시 국내 예수금으로 clamp하는 것이 의미가 없어(통화·계좌가 다름) 원래 수량
    그대로 실행한다. 예수금 조회 자체가 실패해도 마찬가지로 clamp 없이 원래 수량으로 시도한다
    (기존 동작 유지).
    """
    if not buys:
        return []

    if any(is_overseas_market(o.market) for o in buys):
        return [await _execute_kiwoom_single_order(order, access_token, account_no, is_mock) for order in buys]

    try:
        balance = await kiwoom_get_domestic_balance(access_token, account_no, is_mock=is_mock)
        deposit_krw = float(balance.get("deposit_krw") or 0.0)
    except Exception as exc:
        logger.warning("kiwoom_full_strategy_deposit_lookup_failed", error=str(exc))
        return [await _execute_kiwoom_single_order(order, access_token, account_no, is_mock) for order in buys]

    adjusted, skipped = clamp_buy_orders_to_budget(buys, deposit_krw)
    results: list[OrderResult] = list(skipped)
    for order in adjusted:
        results.append(await _execute_kiwoom_single_order(order, access_token, account_no, is_mock))
    return results
