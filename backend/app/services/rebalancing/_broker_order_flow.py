"""KIS·키움 공용 주문 흐름 — 매도 보유수량 clamp, FULL 전략 매수 예산 clamp.

브로커마다 다른 것은 잔고·예산 조회 API, 단건 주문 함수, 해외 보유수량 키뿐이라 `BrokerOrderOps`로 주입한다.
각 실행기는 호출마다 ops를 만들고, 그 콜러블은 실행기 모듈의 이름을 **호출 시점에** 조회한다
(테스트가 `patch.object(_kis_order_executor, "get_domestic_balance", ...)`로 바꿔 끼우는 경로 유지).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import structlog

# 주문 라우팅용 해외 판정은 KIS 주문 가능 거래소(NYSE/NASDAQ/AMEX) 기준이다 — app.constants.OVERSEAS_MARKETS
# (TSE·HKEX 등 포함)로 바꾸면 그 거래소 주문이 해외 주문 API로 가 거부된다.
from app.kis.order import is_overseas_market
from app.schemas.rebalancing import ExecutionOrderItem, OrderResult
from app.services.rebalancing._order_quantity_guard import clamp_buy_orders_to_budget, clamp_sell_orders

logger = structlog.get_logger()


@dataclass(frozen=True)
class BrokerOrderOps:
    place: Callable[[ExecutionOrderItem], Awaitable[OrderResult]]
    domestic_balance: Callable[[], Awaitable[dict]]
    overseas_balance: Callable[[], Awaitable[dict]]
    # FULL 전략 국내 매수 예산(원). 실패 시 예외를 던지면 clamp 없이 원래 수량으로 주문한다.
    domestic_buy_budget: Callable[[], Awaitable[float]]
    # 해외 잔고 position → 보유수량 키, 주문 → 같은 키. KIS는 거래소까지, 키움은 잔고 market이
    # "US" 센티널이라 ticker 단독(계획 55 A1)이다.
    overseas_position_key: Callable[[dict], str]
    overseas_order_key: Callable[[ExecutionOrderItem], str]
    log_prefix: str = ""


def _held_qty(positions: list[dict], key: Callable[[dict], str]) -> dict[str, int]:
    held: dict[str, int] = {}
    for p in positions:
        k = key(p)
        held[k] = held.get(k, 0) + int(p.get("qty", 0))
    return held


async def execute_sells_with_clamp(ops: BrokerOrderOps, sells: list[ExecutionOrderItem]) -> list[OrderResult]:
    """매도 주문을 실행 계좌의 실제 보유수량으로 clamp한 뒤 실행한다.

    포트폴리오 합산 기준으로 계산된 매도 수량이 실행 계좌의 실제 보유수량을 초과하면
    브로커가 주문을 거부하므로, 실행 직전 실시간 잔고를 조회해 수량을 조정한다.
    잔고 조회 자체가 실패하면 clamp 없이 원래 수량으로 주문을 시도한다(기존 동작 유지).
    국내/해외는 잔고 조회 API가 분리되어 있어 각각 clamp한다.
    """
    if not sells:
        return []

    domestic_sells = [o for o in sells if not is_overseas_market(o.market)]
    overseas_sells = [o for o in sells if is_overseas_market(o.market)]
    results: list[OrderResult] = []

    if domestic_sells:
        try:
            balance = await ops.domestic_balance()
            held = _held_qty(balance.get("positions", []), lambda p: p["ticker"])
            adjusted, skipped = clamp_sell_orders(domestic_sells, held)
        except Exception as exc:
            logger.warning(f"{ops.log_prefix}sell_clamp_domestic_balance_failed", error=str(exc))
            adjusted, skipped = domestic_sells, []
        results.extend(skipped)
        for order in adjusted:
            results.append(await ops.place(order))

    if overseas_sells:
        try:
            balance = await ops.overseas_balance()
            held = _held_qty(balance.get("positions", []), ops.overseas_position_key)
            adjusted, skipped = clamp_sell_orders(overseas_sells, held, key_fn=ops.overseas_order_key)
        except Exception as exc:
            logger.warning(f"{ops.log_prefix}sell_clamp_overseas_balance_failed", error=str(exc))
            adjusted, skipped = overseas_sells, []
        results.extend(skipped)
        for order in adjusted:
            results.append(await ops.place(order))

    return results


async def execute_buys_with_cash_check(ops: BrokerOrderOps, buys: list[ExecutionOrderItem]) -> list[OrderResult]:
    """FULL 전략 매수 실행 — 매도 완료 후 실제 매수 예산을 재조회해 예산 내로 clamp한다.

    포트폴리오 합산 계획 수량을 그대로 밀어붙이면, 이번 리밸런싱의 매도 leg가 실패·부분체결·
    (AUTO 2단계 플랜의 경우) 만료됐을 때 매수가 실제 가용 현금을 초과해 브로커에 거부당하거나
    남은 주문이 줄줄이 실패로 떨어질 수 있다. TWO_PHASE 전략(Phase1/3)과 같은 개념의 clamp를 1회 적용한다.

    해외 주식이 섞이면 국내 예산으로 clamp하는 것이 의미가 없어(통화가 다름) 원래 수량 그대로 실행한다.
    예산 조회 자체가 실패해도 clamp 없이 원래 수량으로 시도한다(기존 동작 유지).
    """
    if not buys:
        return []

    if any(is_overseas_market(o.market) for o in buys):
        return [await ops.place(order) for order in buys]

    try:
        budget = await ops.domestic_buy_budget()
    except Exception as exc:
        logger.warning(f"{ops.log_prefix}full_strategy_buy_budget_failed", error=str(exc))
        return [await ops.place(order) for order in buys]

    adjusted, skipped = clamp_buy_orders_to_budget(buys, budget)
    results: list[OrderResult] = list(skipped)
    for order in adjusted:
        results.append(await ops.place(order))
    return results
