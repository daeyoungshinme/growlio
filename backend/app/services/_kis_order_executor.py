"""KIS 리밸런싱 주문 실행 — 단건·TWO_PHASE 전략."""

from __future__ import annotations

import structlog

from app.kis.balance import get_domestic_balance, get_orderable_cash, get_overseas_balance
from app.kis.order import is_overseas_market, place_domestic_order, place_overseas_order
from app.schemas.rebalancing import ExecutionOrderItem, OrderResult
from app.services._order_executor_common import execute_single_order
from app.services._order_quantity_guard import clamp_sell_orders

logger = structlog.get_logger()


async def _execute_single_order(
    order: ExecutionOrderItem,
    app_key: str,
    app_secret: str,
    access_token: str,
    account_no: str,
    is_mock: bool,
) -> OrderResult:
    async def _place() -> dict:
        if is_overseas_market(order.market):
            return await place_overseas_order(
                app_key,
                app_secret,
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
            app_key,
            app_secret,
            access_token,
            account_no,
            side=order.side,
            ticker=order.ticker,
            quantity=order.quantity,
            is_mock=is_mock,
            order_type=order.order_type,
            limit_price=order.limit_price,
        )

    return await execute_single_order(order, _place, is_mock, log_prefix="order")


async def _execute_sells_with_clamp(
    sells: list[ExecutionOrderItem],
    app_key: str,
    app_secret: str,
    access_token: str,
    account_no: str,
    is_mock: bool,
) -> list[OrderResult]:
    """매도 주문을 실행 계좌의 실제 보유수량으로 clamp한 뒤 실행한다.

    포트폴리오 합산 기준으로 계산된 매도 수량이 실행 계좌의 실제 보유수량을 초과하면
    KIS가 주문을 거부하므로, 실행 직전 실시간 잔고를 조회해 수량을 조정한다.
    잔고 조회 자체가 실패하면 clamp 없이 원래 수량으로 주문을 시도한다(기존 동작 유지).
    """
    if not sells:
        return []

    domestic_sells = [o for o in sells if not is_overseas_market(o.market)]
    overseas_sells = [o for o in sells if is_overseas_market(o.market)]

    results: list[OrderResult] = []

    if domestic_sells:
        try:
            balance = await get_domestic_balance(app_key, app_secret, access_token, account_no, is_mock=is_mock)
            held: dict[str, int] = {}
            for p in balance.get("positions", []):
                held[p["ticker"]] = held.get(p["ticker"], 0) + int(p.get("qty", 0))
            adjusted, skipped = clamp_sell_orders(domestic_sells, held)
        except Exception as exc:
            logger.warning("sell_clamp_domestic_balance_failed", error=str(exc))
            adjusted, skipped = domestic_sells, []

        results.extend(skipped)
        for order in adjusted:
            results.append(await _execute_single_order(order, app_key, app_secret, access_token, account_no, is_mock))

    if overseas_sells:
        try:
            balance = await get_overseas_balance(app_key, app_secret, access_token, account_no, is_mock=is_mock)
            held_overseas: dict[str, int] = {}
            for p in balance.get("positions", []):
                key = f"{p['ticker']}:{str(p.get('market', '')).upper()}"
                held_overseas[key] = held_overseas.get(key, 0) + int(p.get("qty", 0))
            adjusted_o, skipped_o = clamp_sell_orders(
                overseas_sells, held_overseas, key_fn=lambda o: f"{o.ticker}:{o.market.upper()}"
            )
        except Exception as exc:
            logger.warning("sell_clamp_overseas_balance_failed", error=str(exc))
            adjusted_o, skipped_o = overseas_sells, []

        results.extend(skipped_o)
        for order in adjusted_o:
            results.append(await _execute_single_order(order, app_key, app_secret, access_token, account_no, is_mock))

    return results


async def _execute_two_phase_orders(
    group_orders: list[ExecutionOrderItem],
    app_key: str,
    app_secret: str,
    access_token: str,
    account_no: str,
    is_mock: bool,
) -> list[OrderResult]:
    """TWO_PHASE 전략 실행: 예수금 매수 → 매도 → 매도금 추가 매수.

    Phase 1: KIS 주문가능금액 조회 → 예수금 범위 내 BUY 실행
    Phase 2: SELL 전체 실행
    Phase 3: 주문가능금액 재조회(매도예정금 포함) → 나머지 BUY 실행
    """
    sells = [o for o in group_orders if o.side == "SELL"]
    buys = [o for o in group_orders if o.side == "BUY"]

    if not buys and not sells:
        return []

    # 해외 주식 포함 시 get_orderable_cash()가 국내 전용이므로 FULL 방식으로 폴백
    has_overseas = any(is_overseas_market(o.market) for o in buys)
    if has_overseas:
        logger.info("two_phase_fallback_overseas_detected", account_no=account_no)
        sell_results = await _execute_sells_with_clamp(sells, app_key, app_secret, access_token, account_no, is_mock)
        buy_results: list[OrderResult] = []
        for order in buys:
            buy_results.append(
                await _execute_single_order(order, app_key, app_secret, access_token, account_no, is_mock)
            )
        return sell_results + buy_results

    # Phase 1: 예수금으로 매수 가능한 만큼 실행
    try:
        orderable_cash = await get_orderable_cash(app_key, app_secret, access_token, account_no, is_mock=is_mock)
    except Exception as exc:
        logger.warning("two_phase_orderable_cash_failed_p1", error=str(exc))
        orderable_cash = 0.0

    logger.info("two_phase_phase1_start", orderable_cash=orderable_cash, buy_count=len(buys))

    phase1_results, remaining_buys, _ = await _execute_buys_within_budget(
        buys, orderable_cash, app_key, app_secret, access_token, account_no, is_mock
    )

    # Phase 2: 매도 전체 실행 (실행 계좌의 실제 보유수량으로 clamp)
    logger.info("two_phase_phase2_sells", sell_count=len(sells))
    sell_results = await _execute_sells_with_clamp(sells, app_key, app_secret, access_token, account_no, is_mock)

    # Phase 3: 매도 후 주문가능금액 재조회 → 나머지 BUY 실행
    phase3_results: list[OrderResult] = []
    if remaining_buys:
        try:
            new_orderable_cash = await get_orderable_cash(
                app_key, app_secret, access_token, account_no, is_mock=is_mock
            )
        except Exception as exc:
            logger.warning("two_phase_orderable_cash_failed_p3", error=str(exc))
            new_orderable_cash = 0.0

        logger.info(
            "two_phase_phase3_start",
            new_orderable_cash=new_orderable_cash,
            remaining_buy_count=len(remaining_buys),
        )
        phase3_results, _, _ = await _execute_buys_within_budget(
            remaining_buys, new_orderable_cash, app_key, app_secret, access_token, account_no, is_mock
        )

    return phase1_results + sell_results + phase3_results


async def _execute_buys_within_budget(
    buy_orders: list[ExecutionOrderItem],
    budget: float,
    app_key: str,
    app_secret: str,
    access_token: str,
    account_no: str,
    is_mock: bool,
) -> tuple[list[OrderResult], list[ExecutionOrderItem], float]:
    """예산(budget) 범위 내에서 매수 주문을 실행한다.

    지정가(limit_price)가 있는 경우 예산 초과분은 수량 조정하고 나머지를 remaining에 추가한다.
    시장가 주문은 가격 추정이 불가하므로 전량 시도 후 remaining 없음.
    Returns: (실행 결과 목록, 예산 부족으로 남은 주문 목록, 사용된 예산)
    """
    results: list[OrderResult] = []
    remaining: list[ExecutionOrderItem] = []
    remaining_budget = budget

    for order in buy_orders:
        price = order.limit_price
        if price and price > 0:
            if remaining_budget <= 0:
                remaining.append(order)
                continue
            affordable_qty = int(remaining_budget // price)
            if affordable_qty <= 0:
                remaining.append(order)
                continue
            execute_qty = min(order.quantity, affordable_qty)
            leftover_qty = order.quantity - execute_qty
        else:
            # 시장가: 가격 모름, 전량 시도
            execute_qty = order.quantity
            leftover_qty = 0

        if execute_qty <= 0:
            remaining.append(order)
            continue

        if leftover_qty > 0:
            remaining.append(
                ExecutionOrderItem(
                    ticker=order.ticker,
                    name=order.name,
                    market=order.market,
                    side=order.side,
                    quantity=leftover_qty,
                    account_id=order.account_id,
                    order_type=order.order_type,
                    limit_price=order.limit_price,
                    reference_price=order.reference_price,
                )
            )

        exec_order = ExecutionOrderItem(
            ticker=order.ticker,
            name=order.name,
            market=order.market,
            side=order.side,
            quantity=execute_qty,
            account_id=order.account_id,
            order_type=order.order_type,
            limit_price=order.limit_price,
            reference_price=order.reference_price,
        )
        result = await _execute_single_order(exec_order, app_key, app_secret, access_token, account_no, is_mock)
        results.append(result)

        if result.status == "SUCCESS" and price and price > 0:
            remaining_budget -= execute_qty * price

    return results, remaining, budget - remaining_budget
