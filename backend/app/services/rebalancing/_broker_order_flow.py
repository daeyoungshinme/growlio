"""KIS·키움 공용 주문 흐름 — 매도→매수 순서, 매도 보유수량 clamp, FULL 전략 매수 예산 clamp.

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
from app.core.job_runner import report_handled_failure
from app.kis.order import is_overseas_market
from app.schemas.rebalancing import ExecutionOrderItem, OrderResult
from app.services.rebalancing._order_quantity_guard import (
    budget_unit_price,
    clamp_buy_orders_to_budget,
    clamp_sell_orders,
)
from app.services.rebalancing.usd_buying_power import FX_FEE_BUFFER

logger = structlog.get_logger()


@dataclass(frozen=True)
class OverseasFunding:
    """해외 매수 직전 결제 여력(plans/140).

    `krw_as_usd`는 원화주문 계좌의 원화 매수여력을 달러로 환산한 값 — 일반 계좌는 0, 실환율이 없어 판정할 수
    없으면 None. 키움 REST 해외 주문엔 결제통화 필드가 없어 원화 결제 여부는 계좌의 원화주문 신청이 정하고,
    신청 계좌는 증권사가 보유 달러를 먼저 쓰고 부족분만 원화로 결제한다.
    """

    usd: float
    krw_order: bool
    krw_as_usd: float | None = 0.0


@dataclass(frozen=True)
class BrokerOrderOps:
    place: Callable[[ExecutionOrderItem], Awaitable[OrderResult]]
    domestic_balance: Callable[[], Awaitable[dict]]
    overseas_balance: Callable[[], Awaitable[dict]]
    # FULL 전략 국내 매수 예산(원). 실패 시 예외를 던지면 예산 0으로 보고 매수를 건너뛴다(plans/119 B4).
    domestic_buy_budget: Callable[[], Awaitable[float]]
    # 해외 잔고 position → 보유수량 키, 주문 → 같은 키. KIS는 거래소까지, 키움은 잔고 market이
    # "US" 센티널이라 ticker 단독(계획 55 A1)이다.
    overseas_position_key: Callable[[dict], str]
    overseas_order_key: Callable[[ExecutionOrderItem], str]
    log_prefix: str = ""
    # 해외 매수 결제 여력(달러·원화주문) — 있으면 해외 매수를 주문마다 판정한다(키움, plans/140).
    # None이면 판정 없이 발주
    overseas_buy_funding: Callable[[], Awaitable[OverseasFunding]] | None = None


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
            # 보유수량 초과 매도는 브로커가 거부할 뿐이라 원래 수량으로 시도한다 — 실자금 경로라 Sentry에 남긴다
            report_handled_failure(f"{ops.log_prefix}sell_clamp_domestic_balance_failed", exc)
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
            # 보유수량 초과 매도는 브로커가 거부할 뿐이라 원래 수량으로 시도한다 — 실자금 경로라 Sentry에 남긴다
            report_handled_failure(f"{ops.log_prefix}sell_clamp_overseas_balance_failed", exc)
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
    예산 조회가 실패하면 예산 0으로 보고 매수를 건너뛴다 — TWO_PHASE 경로(`_kis_order_executor`)와 같다.
    예전엔 clamp 없이 원래 수량을 그대로 발주했다(plans/119 B4).
    """
    if not buys:
        return []

    if ops.overseas_buy_funding is not None:
        domestic_buys = [o for o in buys if not is_overseas_market(o.market)]
        overseas_buys = [o for o in buys if is_overseas_market(o.market)]
        results = await _execute_domestic_buys_within_budget(ops, domestic_buys) if domestic_buys else []
        # 국내 매수 뒤에 조회해야 원화주문 계좌의 원화 여력이 방금 쓴 몫만큼 줄어 있다
        results.extend(await execute_overseas_buys_with_funding(ops, overseas_buys))
        return results

    if any(is_overseas_market(o.market) for o in buys):
        return [await ops.place(order) for order in buys]

    return await _execute_domestic_buys_within_budget(ops, buys)


async def _execute_domestic_buys_within_budget(
    ops: BrokerOrderOps, buys: list[ExecutionOrderItem]
) -> list[OrderResult]:
    """국내 매수를 원화 매수여력(`domestic_buy_budget`)으로 clamp해 발주한다. 조회 실패면 예산 0."""
    try:
        budget = await ops.domestic_buy_budget()
    except Exception as exc:
        report_handled_failure(f"{ops.log_prefix}full_strategy_buy_budget_failed", exc)
        budget = 0.0

    adjusted, skipped = clamp_buy_orders_to_budget(buys, budget)
    results: list[OrderResult] = list(skipped)
    for order in adjusted:
        results.append(await ops.place(order))
    return results


def usd_short_message(required: float, available: float) -> str:
    return (
        f"달러 예수금이 부족해 매수를 건너뜁니다(필요 약 ${required:,.2f}, 남은 ${available:,.2f}). "
        "환전하거나, 키움 원화주문을 신청했다면 계좌관리에서 '원화주문'을 켜세요."
    )


def krw_order_short_message(required: float, available: float) -> str:
    return (
        f"달러·원화 매수여력이 모두 부족해 매수를 건너뜁니다"
        f"(필요 약 ${required:,.2f}, 원화 포함 여력 약 ${available:,.2f})."
    )


def overseas_required_usd(order: ExecutionOrderItem) -> float | None:
    """해외 매수 주문 하나에 필요한 달러(지정가, 시장가면 참고 시세+여유 × 수수료 여유). 가격을 모르면 None."""
    price = budget_unit_price(order)
    if price is None:
        return None
    return order.quantity * price * FX_FEE_BUFFER


def overseas_sell_proceeds_usd(sell_results: list[OrderResult]) -> float:
    """같은 실행에서 접수된 해외 매도의 예상 대금(달러, 여유 없이) — 매수 결제 여력에 더한다(plans/141 A1).

    미국 주식 매도 대금은 결제(T+1) 전이라 외화예수금(`fc_entra`)에 아직 안 잡힐 수 있다. 빼면 매도→매수 리밸런싱의
    매수가 거짓 '달러 부족'으로 SKIPPED된다. 예수금에 이미 반영됐다면 과대 계상이지만, 그때는 발주가 나가 증권사가
    최종 판정한다(기존 원칙). 접수 실패·가격 모름은 더하지 않는다.
    """
    total = 0.0
    for r in sell_results:
        if r.status != "SUCCESS" or r.side != "SELL" or not is_overseas_market(r.market):
            continue
        if r.price and r.price > 0 and r.quantity > 0:
            total += r.quantity * r.price
    return total


async def execute_overseas_buys_with_funding(ops: BrokerOrderOps, buys: list[ExecutionOrderItem]) -> list[OrderResult]:
    """해외 매수를 주문 순서대로 결제 여력에 맞춰 판정·발주한다(plans/140).

    - 남은 달러로 충분 → 발주(USD 결제)
    - 달러 부족 + 원화주문 계좌 → 남은 달러 + 원화 환산 여력으로 충분하면 발주(부족분 원화 결제), 아니면 SKIPPED
    - 달러 부족 + 일반 계좌 → SKIPPED(API로 원화 결제를 고를 수 없다)
    - 가격 모름·여력 조회 실패·원화 환산 불가(실환율 없음) → 판정 없이 발주(증권사가 최종 판정 — 기존 원칙)
    여력은 성공한 주문 몫만 뺀다(실패한 주문이 다음 주문을 거짓으로 막지 않게).
    """
    if not buys:
        return []
    funding_fn = ops.overseas_buy_funding
    if funding_fn is None or all(overseas_required_usd(o) is None for o in buys):
        return [await ops.place(order) for order in buys]
    try:
        funding = await funding_fn()
    except Exception as exc:
        report_handled_failure(f"{ops.log_prefix}overseas_buy_funding_failed", exc)
        return [await ops.place(order) for order in buys]

    usd_left = max(0.0, funding.usd)
    krw_left = funding.krw_as_usd if funding.krw_order else 0.0
    results: list[OrderResult] = []
    for order in buys:
        required = overseas_required_usd(order)
        if required is None:
            results.append(await ops.place(order))
            continue
        if required <= usd_left + 1e-6:
            result = await ops.place(order)
            if result.status == "SUCCESS":
                usd_left = max(0.0, usd_left - required)
                result = result.model_copy(update={"settlement_currency": "USD"})
            results.append(result)
            continue
        if not funding.krw_order:
            logger.info(
                f"{ops.log_prefix}overseas_buy_usd_short",
                ticker=order.ticker,
                required_usd=round(required, 2),
                available_usd=round(usd_left, 2),
            )
            results.append(OrderResult.for_order(order, "SKIPPED", error_msg=usd_short_message(required, usd_left)))
            continue
        if krw_left is None:
            # 실환율이 없어 원화 여력을 달러로 못 바꾼다 — 판정 없이 보내 증권사에 맡긴다
            logger.info(f"{ops.log_prefix}overseas_buy_krw_capacity_unknown", ticker=order.ticker)
            results.append(await ops.place(order))
            continue
        if required <= usd_left + krw_left + 1e-6:
            result = await ops.place(order)
            if result.status == "SUCCESS":
                krw_left = max(0.0, krw_left - (required - usd_left))
                usd_left = 0.0
                result = result.model_copy(update={"settlement_currency": "KRW"})
            results.append(result)
            continue
        logger.info(
            f"{ops.log_prefix}overseas_buy_krw_order_short",
            ticker=order.ticker,
            required_usd=round(required, 2),
            available_usd=round(usd_left + krw_left, 2),
        )
        results.append(
            OrderResult.for_order(order, "SKIPPED", error_msg=krw_order_short_message(required, usd_left + krw_left))
        )
    return results


async def execute_sell_then_buy(
    orders: list[ExecutionOrderItem],
    execute_sells: Callable[[list[ExecutionOrderItem]], Awaitable[list[OrderResult]]],
    execute_buys: Callable[[list[ExecutionOrderItem]], Awaitable[list[OrderResult]]],
) -> list[OrderResult]:
    """매도 → 매수 순으로 실행한다(매도 대금이 매수 예산 재조회에 반영되도록). 브로커별 실행기는 호출부가 주입한다."""
    sells = [o for o in orders if o.side == "SELL"]
    buys = [o for o in orders if o.side == "BUY"]
    results = list(await execute_sells(sells))
    results.extend(await execute_buys(buys))
    return results
