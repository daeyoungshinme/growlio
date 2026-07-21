"""리밸런싱 실행 주문 생성 로직.

AUTO 자동실행(`rebalancing_auto_execution` job)·원클릭 실행(`quick_execute_rebalancing`)·
대기 플랜 생성(`rebalancing/plan_service.generate_pending_plan_for_alert`)이 공유하는
주문 생성 헬퍼. 알림 발송 책임(`rebalancing/alert_check.py`)과 분리하기 위해 별도 모듈로 둔다.
"""

from __future__ import annotations

import math
import uuid
from typing import Any, Literal

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import CASH_EQUIVALENT_TICKER
from app.services.tax_service import _OVERSEAS_MARKETS, _TAX_DEFERRED_TYPES

logger = structlog.get_logger()

_BROKER_ASSET_TYPES = {"STOCK_KIS", "STOCK_KIWOOM"}
_NON_TRADABLE_TICKERS = ("CASH", "REAL_ESTATE", CASH_EQUIVALENT_TICKER)
"""실제 주문을 낼 수 없는 합성 포트폴리오 항목 티커 — 가격 조회·주문 생성 양쪽에서 제외."""


def filter_drifting_items(items: list[Any], threshold_pct: float) -> list[Any]:
    """threshold_pct(%)를 초과하는 드리프트 항목만 반환한다."""
    return [item for item in items if abs(item.weight_diff_pct) > threshold_pct]


def _build_sell_orders(
    item: Any,
    qty: int,
    ticker_account_map: dict[str, list],
    effective_order_type: str,
    limit_price: float | None,
    reference_price: float | None = None,
) -> list[Any]:
    """매도 주문을 실제 종목을 보유한 브로커 연동 계좌(들)로 분산 생성한다.

    포트폴리오 전체 합산 기준으로 계산된 매도 수량을, 종목을 실제로 보유한 계좌들 중
    보유수량이 큰 순서로 채워나간다. 배분 후에도 부족분이 남으면 억지로 다른 계좌에 밀어넣지 않고
    건너뛴다(계좌 실행 시점의 실시간 잔고 clamp가 최종 안전망 역할을 한다).
    """
    from app.schemas.rebalancing import ExecutionOrderItem

    holders = [
        a for a in ticker_account_map.get(item.ticker, []) if a.asset_type in _BROKER_ASSET_TYPES and a.quantity > 0
    ]
    # 과세이연 계좌(ISA/연금저축/IRP)는 최후순위로 매도해 절세 혜택을 보호한다 — 일반/해외전용 계좌를 먼저 소진.
    holders.sort(key=lambda a: (a.tax_type in _TAX_DEFERRED_TYPES, -a.quantity))

    orders: list[Any] = []
    remaining = qty
    for acc in holders:
        if remaining <= 0:
            break
        take = min(remaining, int(acc.quantity))
        if take <= 0:
            continue
        orders.append(
            ExecutionOrderItem(
                ticker=item.ticker,
                name=item.name,
                market=item.market,
                side="SELL",
                quantity=take,
                account_id=acc.account_id,
                order_type=effective_order_type,
                limit_price=limit_price,
                reference_price=reference_price,
            )
        )
        remaining -= take

    if remaining > 0:
        logger.info(
            "rebalancing_auto_sell_unallocated",
            ticker=item.ticker,
            requested_qty=qty,
            unallocated_qty=remaining,
            holder_accounts=len(holders),
        )
    return orders


async def refresh_live_prices(
    items: list,
    user_id: uuid.UUID,
    db: AsyncSession,
    redis: Any = None,
) -> None:
    """드리프트 항목의 `current_price_krw`를 실시간 시세로 갱신한다 (in-place).

    `analyze_rebalancing()`이 채운 `current_price_krw`는 계좌 동기화 시점의 DB 스냅샷 값이라
    자동실행·원클릭실행 시점에는 이미 낡았을 수 있다. 수동 실행 모달(`/stocks/prices-batch`)과
    동일하게 `price_service.fetch_prices_batch()`로 실시간 시세를 조회해 지정가 산정에 반영한다.
    조회 실패 종목은 기존 값을 그대로 둔다(폴백).

    `analyze_rebalancing()`은 분석 시점에 유효 가격을 못 구하면(보유수량 0 + 캐시된 가격도 없음)
    `shares_to_trade`를 None으로 남긴다 — 이 경우 여기서 실시간 가격을 새로 확보하면 동일한 공식으로
    `shares_to_trade`도 함께 재계산한다. 그러지 않으면 `build_rebalancing_orders()`가 이 항목을
    "거래수량 없음"으로 영구히 스킵해 실제로는 존재하는 드리프트가 조용히 누락된다.
    """
    from app.services.price_service import fetch_prices_batch

    tickers = [(item.ticker, item.market) for item in items if item.ticker not in _NON_TRADABLE_TICKERS]
    if not tickers:
        return

    try:
        price_map = await fetch_prices_batch(user_id, tickers, db, redis)
    except Exception as exc:
        logger.warning("rebalancing_live_price_refresh_failed", error=str(exc))
        return

    for item in items:
        price = price_map.get(item.ticker)
        if price and price > 0:
            item.current_price_krw = float(price)
            if item.shares_to_trade is None and item.ticker not in _NON_TRADABLE_TICKERS:
                target_qty = math.floor(item.target_value_krw / price)
                item.shares_to_trade = target_qty - (item.current_qty or 0)


def clamp_orders_to_max_value(orders: list[Any], max_order_value_krw: float) -> list[Any]:
    """주문 1건당 거래대금(수량 × 참조가)이 max_order_value_krw를 넘지 않도록 수량을 축소한다.

    AUTO 대기 플랜 생성(`plan_service.generate_pending_plan_for_alert`)의 마지막 단계에서
    호출되는 안전장치 — 드리프트/가격 계산 버그로 비정상적으로 큰 수량이 생성되더라도 계좌
    잔고만큼 무제한 매매되는 것을 막는다. 참조가(`reference_price`)를 모르는 주문(가격 조회
    실패 등)은 검증할 수 없으므로 그대로 통과시킨다 — 기존 동작 유지.
    """
    clamped: list[Any] = []
    for order in orders:
        price = getattr(order, "reference_price", None)
        if not price or price <= 0:
            clamped.append(order)
            continue

        max_qty = int(max_order_value_krw // price)
        if order.quantity <= max_qty:
            clamped.append(order)
            continue

        if max_qty <= 0:
            logger.warning(
                "auto_order_value_cap_skipped",
                ticker=order.ticker,
                side=order.side,
                requested_qty=order.quantity,
                reference_price=price,
                max_order_value_krw=max_order_value_krw,
            )
            continue

        logger.warning(
            "auto_order_value_cap_clamped",
            ticker=order.ticker,
            side=order.side,
            requested_qty=order.quantity,
            clamped_qty=max_qty,
            reference_price=price,
            max_order_value_krw=max_order_value_krw,
        )
        clamped.append(order.model_copy(update={"quantity": max_qty}))

    return clamped


def is_market_signal_blocking_auto_mode(
    market_condition_mode: str, composite_level: str, data_freshness: str = "LIVE"
) -> bool:
    """AUTO 모드에서 시장 신호 등급이 `market_condition_mode` 게이트를 위반하는지 판정한다.

    드리프트 알림 체크(`rebalancing/alert_check.py`), AUTO 플랜 생성 job
    (`jobs/rebalancing_auto_execution.py`), 원클릭 실행(`api/v1/rebalancing_execution.py`)이
    동일한 판정 로직을 공유하는 단일화된 순수 함수 — 로깅은 각 호출부 책임으로 남긴다.

    `data_freshness == "STALE"`(시장 신호를 신뢰할 수 있을 만큼 조회하지 못한 상태 —
    FRED_API_KEY 미설정, 전면 장애 등)이면 CAUTIOUS/STRICT에서 composite_level과 무관하게
    차단한다. "판단 불가"를 "GREEN(안전)"으로 오인해 실행을 통과시키는 것을 막기 위함 —
    DISABLED는 애초에 시장 신호를 보지 않으므로 영향받지 않는다.
    """
    if market_condition_mode == "DISABLED":
        return False
    if data_freshness == "STALE":
        return True
    return (market_condition_mode == "CAUTIOUS" and composite_level == "RED") or (
        market_condition_mode == "STRICT" and composite_level in ("YELLOW", "RED")
    )


def is_tax_impact_blocking_auto_mode(
    gate_mode: str, estimated_tax_krw: float, max_tax_impact_krw: float | None
) -> bool:
    """AUTO 모드에서 매도로 인한 추정 양도세가 `tax_impact_gate_mode` 게이트를 위반하는지 판정한다.

    `market_condition_mode`/`is_market_signal_blocking_auto_mode`와 대칭인 순수 함수.
    `ENABLED`인데 상한액이 아직 설정되지 않았으면(예: 마이그레이션 직후 기본값) 안전하게 통과시킨다 —
    "설정 안 함"을 "무제한 차단"으로 오인해 AUTO를 예기치 않게 멈추는 것을 막기 위함.
    """
    if gate_mode != "ENABLED":
        return False
    if max_tax_impact_krw is None:
        return False
    return estimated_tax_krw > max_tax_impact_krw


def _flatten_account_tax_types(ticker_account_map: dict[str, list]) -> dict[str, str]:
    """ticker_account_map에 등장하는 모든 계좌의 account_id → tax_type 맵을 구성한다.

    buy_account_id의 tax_type 조회용 — 매수 대상 계좌가 현재 어떤 종목이라도 보유하고 있어야
    맵에 등장하므로, 아무것도 보유하지 않은 신규 계좌는 GENERAL로 취급된다(보수적 기본값).
    """
    result: dict[str, str] = {}
    for accounts in ticker_account_map.values():
        for a in accounts:
            result[a.account_id] = getattr(a, "tax_type", "GENERAL")
    return result


def build_rebalancing_orders(
    drifting: list,
    ticker_account_map: dict[str, list],
    strategy: str,
    order_type: Literal["MARKET", "LIMIT"],
    buy_account_id: str,
    alert_id: str | None = None,
) -> list[Any]:
    """드리프트 항목 목록으로부터 실행 주문 목록을 생성한다.

    매도 주문은 `ticker_account_map`을 사용해 실제 종목을 보유한 브로커 연동 계좌(들)로
    분산 생성하고, 매수 주문은 `buy_account_id` 단일 계좌로 생성한다.
    AUTO 자동실행(`_execute_auto_rebalancing`)과 원클릭 실행(`quick_execute_rebalancing`)이
    공유하는 주문 생성 로직 — 두 경로가 서로 다른 동작을 하지 않도록 여기서 단일화한다.
    """
    from app.schemas.rebalancing import ExecutionOrderItem

    ticker_account_map = ticker_account_map or {}
    account_tax_type_map = _flatten_account_tax_types(ticker_account_map)
    orders: list[ExecutionOrderItem] = []
    for item in drifting:
        if item.ticker in _NON_TRADABLE_TICKERS or item.shares_to_trade is None:
            logger.info(
                "rebalancing_auto_item_skipped",
                alert_id=alert_id,
                ticker=item.ticker,
                reason="cash_or_no_shares_to_trade",
            )
            continue
        qty = abs(int(item.shares_to_trade))
        if qty <= 0:
            logger.info(
                "rebalancing_auto_item_skipped",
                alert_id=alert_id,
                ticker=item.ticker,
                reason="zero_qty",
                shares_to_trade=item.shares_to_trade,
            )
            continue
        side = "BUY" if item.diff_krw > 0 else "SELL"
        if strategy == "BUY_ONLY" and side == "SELL":
            logger.info(
                "rebalancing_auto_item_skipped",
                alert_id=alert_id,
                ticker=item.ticker,
                reason="buy_only_strategy",
            )
            continue

        # LIMIT 주문 시 현재가를 지정가로 사용 (None이면 MARKET으로 fallback)
        effective_order_type = order_type
        current_price = getattr(item, "current_price_krw", None)
        reference_price: float | None = float(current_price) if current_price and current_price > 0 else None
        limit_price: float | None = None
        if order_type == "LIMIT":
            if reference_price is not None:
                limit_price = reference_price
            else:
                effective_order_type = "MARKET"

        if side == "SELL":
            orders.extend(
                _build_sell_orders(item, qty, ticker_account_map, effective_order_type, limit_price, reference_price)
            )
            continue

        # ISA/연금저축/IRP 계좌는 해외 개별 종목을 직접 매수할 수 없다 — 실행 불가능한 주문 생성 방지.
        buy_account_tax_type = account_tax_type_map.get(buy_account_id, "GENERAL")
        if item.market in _OVERSEAS_MARKETS and buy_account_tax_type in _TAX_DEFERRED_TYPES:
            logger.info(
                "rebalancing_auto_item_skipped",
                alert_id=alert_id,
                ticker=item.ticker,
                reason="overseas_not_allowed_in_tax_deferred_account",
            )
            continue

        orders.append(
            ExecutionOrderItem(
                ticker=item.ticker,
                name=item.name,
                market=item.market,
                side=side,
                quantity=qty,
                account_id=buy_account_id,
                order_type=effective_order_type,
                limit_price=limit_price,
                reference_price=reference_price,
            )
        )

    return orders
