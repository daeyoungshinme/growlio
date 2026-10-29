"""키움 리밸런싱 주문 실행 — 국내주식·미국주식 단건 주문."""

from __future__ import annotations

from app.kis.order import is_overseas_market
from app.kiwoom.balance import get_domestic_balance as kiwoom_get_domestic_balance
from app.kiwoom.balance import get_overseas_balance as kiwoom_get_overseas_balance
from app.kiwoom.order import place_domestic_order, place_overseas_order
from app.schemas.rebalancing import ExecutionOrderItem, OrderResult
from app.services.rebalancing._broker_order_flow import (
    BrokerOrderOps,
    execute_buys_with_cash_check,
    execute_sells_with_clamp,
)
from app.services.rebalancing._order_executor_common import execute_single_order, snap_domestic_limit_price


async def _execute_kiwoom_single_order(
    order: ExecutionOrderItem,
    access_token: str,
    account_no: str,
    is_mock: bool,
) -> OrderResult:
    """키움 단건 주문 실행 — 국내/해외를 market으로 분기해 실행한다."""

    order = snap_domestic_limit_price(order)

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


def _kiwoom_ops(access_token: str, account_no: str, is_mock: bool) -> BrokerOrderOps:
    async def _budget() -> float:
        # kt00001의 orderable_krw(100stk_ord_alow_amt = 미수 없는 현금 매수여력)는 KIS `get_orderable_cash()`의
        # nrcvb_buy_amt와 대칭이며 매도예정금(D+2)을 포함한다. 없으면 deposit_krw(D+2 추정예수금)로 폴백한다.
        balance = await kiwoom_get_domestic_balance(access_token, account_no, is_mock=is_mock)
        return float(balance.get("orderable_krw") or balance.get("deposit_krw") or 0.0)

    return BrokerOrderOps(
        place=lambda order: _execute_kiwoom_single_order(order, access_token, account_no, is_mock),
        domestic_balance=lambda: kiwoom_get_domestic_balance(access_token, account_no, is_mock=is_mock),
        overseas_balance=lambda: kiwoom_get_overseas_balance(access_token, account_no, is_mock=is_mock),
        domestic_buy_budget=_budget,
        # 키움 해외잔고는 거래소를 주지 않아 market이 "US" 센티널이고(kiwoom/balance.py), 주문은 NYSE/NASDAQ/AMEX다 —
        # market까지 키에 넣으면 전부 보유 0으로 오판한다. 해외 매도만 비교하므로 ticker 단독 키로 충분하다.
        overseas_position_key=lambda p: p["ticker"],
        overseas_order_key=lambda o: o.ticker,
        log_prefix="kiwoom_",
    )


async def _execute_kiwoom_sells_with_clamp(
    sells: list[ExecutionOrderItem],
    access_token: str,
    account_no: str,
    is_mock: bool,
) -> list[OrderResult]:
    """키움 매도 주문을 실행 계좌의 실제 보유수량으로 clamp한 뒤 실행한다(`execute_sells_with_clamp`)."""
    return await execute_sells_with_clamp(_kiwoom_ops(access_token, account_no, is_mock), sells)


async def _execute_kiwoom_buys_with_cash_check(
    buys: list[ExecutionOrderItem],
    access_token: str,
    account_no: str,
    is_mock: bool,
) -> list[OrderResult]:
    """키움 FULL 전략 매수 — 현금 매수여력으로 clamp한다(`execute_buys_with_cash_check`)."""
    return await execute_buys_with_cash_check(_kiwoom_ops(access_token, account_no, is_mock), buys)
