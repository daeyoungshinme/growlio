"""KIS 리밸런싱 주문 실행 — 단건·TWO_PHASE 전략."""

from __future__ import annotations

import structlog

from app.kis.balance import get_domestic_balance, get_orderable_cash, get_overseas_balance
from app.kis.order import is_overseas_market, place_domestic_order, place_overseas_order
from app.schemas.rebalancing import ExecutionOrderItem, OrderResult
from app.services.rebalancing._broker_order_flow import (
    BrokerOrderOps,
    execute_buys_with_cash_check,
    execute_sells_with_clamp,
)
from app.services.rebalancing._order_executor_common import execute_single_order
from app.services.rebalancing._order_quantity_guard import budget_skipped_result, fit_buy_to_budget
from app.services.rebalancing.krx_tick import domestic_limit_price
from app.utils.masking import mask_account_no

logger = structlog.get_logger()


async def _execute_single_order(
    order: ExecutionOrderItem,
    app_key: str,
    app_secret: str,
    access_token: str,
    account_no: str,
    is_mock: bool,
) -> OrderResult:
    # 수동 입력 지정가가 호가 격자에서 벗어나면 broker가 거부한다 — 주문 전에 맞추고, 결과(OrderResult.price)에도
    # 실제 주문가가 남도록 사본을 쓴다(plans/61 C2). 실시간 현재가는 이미 격자 위라 값이 바뀌지 않는다.
    if order.order_type == "LIMIT" and not is_overseas_market(order.market):
        order = order.model_copy(
            update={"limit_price": domestic_limit_price(order.limit_price, order.side, order.name)}
        )

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


def _kis_ops(app_key: str, app_secret: str, access_token: str, account_no: str, is_mock: bool) -> BrokerOrderOps:
    async def _budget() -> float:
        return await get_orderable_cash(app_key, app_secret, access_token, account_no, is_mock=is_mock)

    return BrokerOrderOps(
        place=lambda order: _execute_single_order(order, app_key, app_secret, access_token, account_no, is_mock),
        domestic_balance=lambda: get_domestic_balance(app_key, app_secret, access_token, account_no, is_mock=is_mock),
        overseas_balance=lambda: get_overseas_balance(app_key, app_secret, access_token, account_no, is_mock=is_mock),
        domestic_buy_budget=_budget,
        # KIS 해외잔고는 실제 거래소명을 준다 — 같은 티커가 다른 거래소에 있으면 따로 센다
        overseas_position_key=lambda p: f"{p['ticker']}:{str(p.get('market', '')).upper()}",
        overseas_order_key=lambda o: f"{o.ticker}:{o.market.upper()}",
    )


async def _execute_sells_with_clamp(
    sells: list[ExecutionOrderItem],
    app_key: str,
    app_secret: str,
    access_token: str,
    account_no: str,
    is_mock: bool,
) -> list[OrderResult]:
    """매도 주문을 실행 계좌의 실제 보유수량으로 clamp한 뒤 실행한다(`execute_sells_with_clamp`)."""
    return await execute_sells_with_clamp(_kis_ops(app_key, app_secret, access_token, account_no, is_mock), sells)


async def _execute_buys_with_cash_check(
    buys: list[ExecutionOrderItem],
    app_key: str,
    app_secret: str,
    access_token: str,
    account_no: str,
    is_mock: bool,
) -> list[OrderResult]:
    """FULL 전략 매수 — 주문가능금액(`get_orderable_cash`)으로 clamp한다(`execute_buys_with_cash_check`)."""
    return await execute_buys_with_cash_check(_kis_ops(app_key, app_secret, access_token, account_no, is_mock), buys)


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
        logger.info("two_phase_fallback_overseas_detected", account_no=mask_account_no(account_no))
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
        phase3_results, unaffordable, _ = await _execute_buys_within_budget(
            remaining_buys, new_orderable_cash, app_key, app_secret, access_token, account_no, is_mock
        )
        # 매도 후에도 살 수 없는 분량은 결과·이력에 SKIPPED로 남긴다 — 버리면 계획의 매수가
        # 어디에도 기록되지 않아 사용자가 미체결 사실을 알 수 없다(plans/62 A6)
        phase3_results += [budget_skipped_result(o) for o in unaffordable]

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
        fitted, leftover_qty = fit_buy_to_budget(order, remaining_budget)
        if fitted is None:
            remaining.append(order)
            continue
        if leftover_qty > 0:
            remaining.append(order.model_copy(update={"quantity": leftover_qty}))

        result = await _execute_single_order(fitted, app_key, app_secret, access_token, account_no, is_mock)
        results.append(result)

        # FULL과 달리 체결에 성공한 금액만 뺀다 — 실패분 예산은 다음 주문이 쓴다
        if result.status == "SUCCESS" and fitted.limit_price and fitted.limit_price > 0:
            remaining_budget -= fitted.quantity * fitted.limit_price

    return results, remaining, budget - remaining_budget
