"""AUTO 리밸런싱 2단계 플랜(계획 생성 → 매수 대기/매도 승인 → 실행) 서비스.

계획 생성은 rebalancing/order_builder.py의 build_rebalancing_orders/refresh_live_prices를
재사용한다. 매수는 대기시간 경과 후 자동 실행(취소 가능), 매도는 이메일 승인 필요(당일
장마감 미응답 시 자동 만료)라는 leg별 독립 생명주기를 관리한다.
"""

from __future__ import annotations

import contextlib
import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, cast

import structlog
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models.alert import RebalancingAlert
from app.models.asset import AssetAccount
from app.models.portfolio import Portfolio
from app.models.rebalancing_plan import RebalancingPlan, RebalancingPlanItem, RebalancingPlanLeg
from app.services.alerts.alert_service import save_alert_history
from app.services.rebalancing.order_builder import (
    build_rebalancing_orders,
    clamp_orders_to_max_value,
    filter_drifting_items,
    is_tax_impact_blocking_auto_mode,
    market_group,
    refresh_live_prices,
    split_orders_by_market,
)

logger = structlog.get_logger()


@dataclass(frozen=True)
class TaxGateBlocked:
    """`build_pending_plan_for_alert`가 세금영향 게이트로 차단됐을 때 반환하는 sentinel.

    알림 발송에 필요한 추정치를 함께 실어 나른다."""

    estimated_tax_krw: float
    max_tax_impact_krw: float


@dataclass(frozen=True)
class MarketSignalGateBlocked:
    """AUTO 계획 생성이 시장신호 게이트로 차단됐을 때 알림에 필요한 컨텍스트를 실어 나르는 sentinel."""

    composite_level: str
    market_condition_mode: str
    data_freshness: str


def _generate_token() -> tuple[str, str]:
    """(원문 토큰, SHA-256 해시) 반환 — DB에는 해시만 저장한다."""
    raw = secrets.token_urlsafe(32)
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    return raw, hashed


def _coerce_overseas_market_orders_to_limit(orders: list, alert_id: str | None = None) -> list:
    """AUTO 플랜의 해외 MARKET 주문을 LIMIT으로 강제 변환한다.

    `place_overseas_order()`는 실계좌 시장가 주문이 거래소별로 코드가 상이해 mock 모드
    밖에서는 불안정하다(app/kis/order.py의 docstring 경고 참고). AUTO는 무인 실행이라 이
    리스크를 감수할 수 없으므로 최근 참고가(reference_price)를 지정가로 강제한다 — 참고가가
    없으면(가격 조회 실패 등) 안전하게 건너뛴다. 사람이 직접 확인 후 실행하는 원클릭 실행
    경로(`build_rebalancing_orders`의 다른 호출부)는 이 보정 대상이 아니다.
    """
    coerced: list = []
    for order in orders:
        if market_group(order.market) != "US" or order.order_type != "MARKET":
            coerced.append(order)
            continue
        if not order.reference_price or order.reference_price <= 0:
            logger.warning(
                "rebalancing_auto_overseas_market_order_skipped",
                alert_id=alert_id,
                ticker=order.ticker,
                reason="no_reference_price",
            )
            continue
        coerced.append(order.model_copy(update={"order_type": "LIMIT", "limit_price": order.reference_price}))
    return coerced


def _build_plan_leg(
    plan: RebalancingPlan,
    side: str,
    market: str,
    orders: list,
    deadline_at: datetime,
) -> tuple[RebalancingPlanLeg, str]:
    """지정된 side/market 주문 그룹으로 leg를 생성하고 (leg, 원문 토큰)을 반환한다."""
    raw, hashed = _generate_token()
    leg = RebalancingPlanLeg(
        plan=plan,
        side=side,
        market=market,
        status="PENDING",
        deadline_at=deadline_at,
        action_token_hash=hashed,
    )
    leg.items = [_order_to_item(o) for o in orders]
    return leg, raw


def _order_to_item(order) -> RebalancingPlanItem:
    return RebalancingPlanItem(
        ticker=order.ticker,
        name=order.name,
        market=order.market,
        quantity=order.quantity,
        account_id=order.account_id,
        order_type=order.order_type,
        limit_price=order.limit_price,
        reference_price=order.reference_price,
    )


async def has_pending_plan_for_alert(alert_id: uuid.UUID, db: AsyncSession) -> bool:
    """이 알림에 대해 아직 PENDING 상태인 leg가 있는지 확인한다 (중복 플랜 생성 방지)."""
    result = await db.execute(
        select(RebalancingPlanLeg.id)
        .join(RebalancingPlan, RebalancingPlan.id == RebalancingPlanLeg.plan_id)
        .where(RebalancingPlan.alert_id == alert_id, RebalancingPlanLeg.status == "PENDING")
        .limit(1)
    )
    return result.first() is not None


async def generate_pending_plan_for_alert(
    alert: RebalancingAlert,
    portfolio: Portfolio,
    drifting: list,
    db: AsyncSession,
    ticker_account_map: dict[str, list] | None,
    composite_level: str,
    strategy_override: str | None = None,
    order_type_override: Literal["MARKET", "LIMIT"] | None = None,
    account_id_override: uuid.UUID | None = None,
) -> tuple[RebalancingPlan | None, list[tuple[str, str]], list[tuple[str, str]]]:
    """드리프트 항목으로부터 BUY/SELL leg를 가진 대기 플랜을 생성한다 (실행하지 않음).

    `*_override` 파라미터는 저장된 `alert` 설정 대신 사용할 값 — 화면에서 저장하지 않고
    바로 테스트할 때 쓰인다. `alert` 객체 자체는 절대 mutate하지 않는다.

    국내(KR)/해외(US) 주문이 섞여 있으면 side당 최대 2개(KR/US) leg로 분리한다 — 두 시장은
    개장시간이 달라 하나의 leg로 묶으면 마감/실행 시각을 leg 단위로만 판단할 수 없다.

    반환: (plan, buy_tokens, sell_tokens). 각 tokens는 [(market, raw_token), ...] 형태로
    비어있는 side는 빈 리스트. 실행할 주문이 전혀 없으면 (None, [], []).
    """
    from app.core.cache_store import get_cache_store
    from app.utils.market_hours import korean_market_close_datetime, us_market_close_datetime

    strategy = cast(str, strategy_override or getattr(alert, "strategy", "BUY_ONLY"))
    order_type = order_type_override or cast(Literal["MARKET", "LIMIT"], getattr(alert, "order_type", "MARKET"))
    account_id = account_id_override or alert.account_id

    cache = await get_cache_store()
    await refresh_live_prices(drifting, alert.user_id, db, cache)

    orders = build_rebalancing_orders(
        drifting, ticker_account_map or {}, strategy, order_type, str(account_id), alert_id=str(alert.id)
    )
    orders = clamp_orders_to_max_value(orders, settings.auto_rebalancing_max_order_value_krw)
    orders = _coerce_overseas_market_orders_to_limit(orders, alert_id=str(alert.id))
    if not orders:
        return None, [], []

    buy_kr, buy_us = split_orders_by_market([o for o in orders if o.side == "BUY"])
    sell_kr, sell_us = split_orders_by_market([o for o in orders if o.side == "SELL"])

    now = datetime.now(tz=UTC)
    plan = RebalancingPlan(
        user_id=alert.user_id,
        portfolio_id=portfolio.id,
        alert_id=alert.id,
        account_id=account_id,
        strategy=strategy,
        order_type=order_type,
        composite_level_at_plan=composite_level,
    )
    db.add(plan)

    buy_tokens: list[tuple[str, str]] = []
    sell_tokens: list[tuple[str, str]] = []

    buy_wait_minutes = getattr(alert, "buy_wait_minutes", 10)
    buy_deadline = now + timedelta(minutes=buy_wait_minutes)
    for mkt, group in (("KR", buy_kr), ("US", buy_us)):
        if not group:
            continue
        leg, token = _build_plan_leg(plan, "BUY", mkt, group, buy_deadline)
        db.add(leg)
        db.add_all(leg.items)
        buy_tokens.append((mkt, token))

    sell_deadlines = {
        "KR": korean_market_close_datetime().astimezone(UTC),
        "US": us_market_close_datetime().astimezone(UTC),
    }
    for mkt, group in (("KR", sell_kr), ("US", sell_us)):
        if not group:
            continue
        leg, token = _build_plan_leg(plan, "SELL", mkt, group, sell_deadlines[mkt])
        db.add(leg)
        db.add_all(leg.items)
        sell_tokens.append((mkt, token))

    await db.commit()
    # attribute_names=["legs"]로 명시 refresh해 실제 DB에 반영된 leg/item 수를 다시 조회한다 —
    # buy_items/sell_items(생성 의도)와 persisted_*_items(실제 저장치)가 다르면 저장 누락을 의미한다.
    await db.refresh(plan, attribute_names=["legs"])
    persisted_buy = sum(len(leg.items) for leg in plan.legs if leg.side == "BUY")
    persisted_sell = sum(len(leg.items) for leg in plan.legs if leg.side == "SELL")
    logger.info(
        "rebalancing_plan_generated",
        plan_id=str(plan.id),
        alert_id=str(alert.id),
        buy_items=len(buy_kr) + len(buy_us),
        sell_items=len(sell_kr) + len(sell_us),
        buy_legs=[mkt for mkt, _ in buy_tokens],
        sell_legs=[mkt for mkt, _ in sell_tokens],
        persisted_buy_items=persisted_buy,
        persisted_sell_items=persisted_sell,
    )
    return plan, buy_tokens, sell_tokens


async def build_pending_plan_for_alert(
    alert: RebalancingAlert,
    portfolio: Portfolio,
    db: AsyncSession,
    composite_level: str,
    strategy_override: str | None = None,
    order_type_override: Literal["MARKET", "LIMIT"] | None = None,
    account_id_override: uuid.UUID | None = None,
    cache: Any = None,
) -> tuple[RebalancingPlan, list[tuple[str, str]], list[tuple[str, str]]] | None | TaxGateBlocked:
    """알림 설정 기준으로 드리프트 분석 후 대기 플랜을 생성한다.

    AUTO 스케줄러 job과 수동 "지금 테스트 실행" 모두 이 함수로 플랜을 생성해 두 경로가
    동일한 계획 생성 로직(및 이메일 발송 파이프라인)을 공유하도록 한다.
    반환: (plan, buy_tokens, sell_tokens) | None(드리프트 없음) | TaxGateBlocked(세금영향 게이트 차단).
    buy_tokens/sell_tokens는 [(market, raw_token), ...] — KR/US leg가 각각 있으면 최대 2개.
    """
    from app.services.portfolio_service import build_portfolio_overview
    from app.services.rebalancing.alert_scope import resolve_effective_account_ids
    from app.services.rebalancing.service import analyze_rebalancing

    effective_account_ids = resolve_effective_account_ids(alert, portfolio)

    overview = await build_portfolio_overview(alert.user_id, db, account_ids=effective_account_ids, cache=cache)
    analysis = analyze_rebalancing(portfolio, overview, include_implicit_cash=True)

    threshold = float(alert.threshold_pct)
    drifting = filter_drifting_items(analysis.items, threshold)

    if not drifting:
        logger.info("rebalancing_plan_no_drift", alert_id=str(alert.id))
        return None

    tax_gate_mode = getattr(alert, "tax_impact_gate_mode", "DISABLED")
    max_tax_impact_krw = getattr(alert, "max_tax_impact_krw", None)
    if tax_gate_mode == "ENABLED" and max_tax_impact_krw is not None:
        from app.services.rebalancing.diagnosis_service import _build_tax_preview

        _total_gain, estimated_tax_krw, _fee, _notes, _items = _build_tax_preview(analysis, overview)
        if is_tax_impact_blocking_auto_mode(tax_gate_mode, estimated_tax_krw, max_tax_impact_krw):
            logger.info(
                "rebalancing_plan_blocked_tax_impact",
                alert_id=str(alert.id),
                estimated_tax_krw=estimated_tax_krw,
                max_tax_impact_krw=max_tax_impact_krw,
            )
            return TaxGateBlocked(estimated_tax_krw=estimated_tax_krw, max_tax_impact_krw=float(max_tax_impact_krw))

    plan, buy_tokens, sell_tokens = await generate_pending_plan_for_alert(
        alert,
        portfolio,
        drifting,
        db,
        analysis.ticker_account_map,
        composite_level,
        strategy_override=strategy_override,
        order_type_override=order_type_override,
        account_id_override=account_id_override,
    )
    if plan is None:
        return None

    alert.last_triggered_at = plan.created_at
    return plan, buy_tokens, sell_tokens


async def notify_plan_generated(
    plan: RebalancingPlan,
    alert: RebalancingAlert,
    portfolio: Portfolio,
    buy_tokens: list[tuple[str, str]],
    sell_tokens: list[tuple[str, str]],
    email: str | None,
    fcm_token: str | None,
    composite_level: str,
    db: AsyncSession,
    note: str | None = None,
) -> bool:
    """플랜 생성 후 계획 안내 이메일/푸시 발송 + 알림 이력 저장. 반환: 이메일 발송 성공 여부.

    `buy_tokens`/`sell_tokens`는 [(market, raw_token), ...] — KR/US leg가 각각 있으면 최대 2개.
    """
    from app.models.asset import AssetAccount
    from app.services.email_service import send_rebalancing_plan_pending_email
    from app.services.push_service import send_push_to_user

    await db.refresh(plan, attribute_names=["legs"])
    buy_token_map = dict(buy_tokens)
    sell_token_map = dict(sell_tokens)
    buy_legs = [leg for leg in plan.legs if leg.side == "BUY"]
    sell_legs = [leg for leg in plan.legs if leg.side == "SELL"]
    # 이메일 링크용 원문 토큰은 해시만 저장되므로(action_token_hash) leg 객체엔 없다 — 전달받은
    # market→token 맵을 leg의 transient 속성으로 실어 email_service._to_section()이 읽게 한다.
    for leg in buy_legs:
        leg.token = buy_token_map.get(leg.market)
    for leg in sell_legs:
        leg.token = sell_token_map.get(leg.market)

    buy_count = sum(len(leg.items) for leg in buy_legs)
    sell_count = sum(len(leg.items) for leg in sell_legs)

    account_name = None
    if plan.account_id:
        account_name = await db.scalar(select(AssetAccount.name).where(AssetAccount.id == plan.account_id))

    email_sent = False
    if email and (buy_legs or sell_legs):
        try:
            await send_rebalancing_plan_pending_email(
                to_email=email,
                portfolio_name=portfolio.name,
                account_name=account_name,
                buy_legs=buy_legs,
                sell_legs=sell_legs,
            )
            email_sent = True
        except Exception as exc:
            logger.error("rebalancing_plan_pending_email_failed", alert_id=str(alert.id), error=str(exc))

    push_body = f"매수 {buy_count}건"
    if sell_count:
        push_body += f", 매도 승인대기 {sell_count}건"
    try:
        await send_push_to_user(
            user_id=alert.user_id,
            title=f"리밸런싱 자동화 플랜 생성 — {portfolio.name}",
            body=push_body,
            fcm_token=fcm_token,
            data={"type": "REBALANCING_PLAN_PENDING", "portfolio_id": str(portfolio.id)},
        )
    except Exception as exc:
        logger.error("rebalancing_plan_pending_push_failed", alert_id=str(alert.id), error=str(exc))

    history_note = f", {note}" if note else ""
    await save_alert_history(
        db,
        alert.user_id,
        "REBALANCING",
        (
            f"리밸런싱 자동화 플랜 생성: {portfolio.name} — 매수 {buy_count}건"
            + (f", 매도 승인대기 {sell_count}건" if sell_count else "")
            + f" [시장신호: {composite_level}{history_note}]"
        ),
    )
    return email_sent


async def notify_tax_gate_blocked(
    alert: RebalancingAlert,
    portfolio: Portfolio,
    blocked: TaxGateBlocked,
    email: str | None,
    fcm_token: str | None,
    db: AsyncSession,
) -> None:
    """세금영향 게이트로 계획 생성이 보류됐음을 알린다 — 같은 알림에 대해 하루 1회만 발송(dedup).

    dedup 플래그는 재시작에도 유지돼야 하므로(콜드스타트 후 오탐 방지) Postgres 기반
    durable_state를 사용한다.
    """
    from app.services.email_service import send_tax_impact_gate_blocked_email
    from app.services.push_service import send_push_to_user
    from app.utils.cache_keys import TTL_TAX_IMPACT_GATE_ALERT_SENT, tax_impact_gate_alert_sent_key
    from app.utils.durable_state import get_durable, set_durable

    today = datetime.now(tz=UTC).date().isoformat()
    dedup_key = tax_impact_gate_alert_sent_key(alert.id, today)
    if await get_durable(db, dedup_key):
        return

    if email:
        try:
            await send_tax_impact_gate_blocked_email(
                email, portfolio.name, blocked.estimated_tax_krw, blocked.max_tax_impact_krw
            )
        except Exception as exc:
            logger.error("tax_impact_gate_blocked_email_error", alert_id=str(alert.id), error=str(exc))

    push_body = f"세금영향 상한 초과로 이번 계획을 만들지 않았습니다 (추정 양도세 {blocked.estimated_tax_krw:,.0f}원)."
    with contextlib.suppress(Exception):
        await send_push_to_user(
            user_id=alert.user_id,
            title=f"리밸런싱 자동화 보류 — {portfolio.name}",
            body=push_body,
            fcm_token=fcm_token,
            data={"type": "REBALANCING_TAX_GATE_BLOCKED", "portfolio_id": str(portfolio.id)},
        )

    history_message = (
        f"리밸런싱 자동화 보류(세금영향 상한 초과): {portfolio.name} — 추정 양도세 {blocked.estimated_tax_krw:,.0f}원"
    )
    await save_alert_history(db, alert.user_id, "REBALANCING", history_message)
    await db.commit()

    await set_durable(db, dedup_key, "1", ttl=TTL_TAX_IMPACT_GATE_ALERT_SENT)


async def notify_market_signal_gate_blocked(
    alert: RebalancingAlert,
    portfolio: Portfolio,
    blocked: MarketSignalGateBlocked,
    email: str | None,
    fcm_token: str | None,
    db: AsyncSession,
) -> None:
    """시장신호 게이트로 계획 생성이 보류됐음을 알린다 — 같은 알림에 대해 하루 1회만 발송(dedup).

    dedup 플래그는 재시작에도 유지돼야 하므로(콜드스타트 후 오탐 방지) Postgres 기반
    durable_state를 사용한다.
    """
    from app.services.email_service import send_market_signal_gate_blocked_email
    from app.services.push_service import send_push_to_user
    from app.utils.cache_keys import TTL_MARKET_SIGNAL_GATE_ALERT_SENT, market_signal_gate_alert_sent_key
    from app.utils.durable_state import get_durable, set_durable

    today = datetime.now(tz=UTC).date().isoformat()
    dedup_key = market_signal_gate_alert_sent_key(alert.id, today)
    if await get_durable(db, dedup_key):
        return

    if email:
        try:
            await send_market_signal_gate_blocked_email(
                email, portfolio.name, blocked.composite_level, blocked.market_condition_mode
            )
        except Exception as exc:
            logger.error("market_signal_gate_blocked_email_error", alert_id=str(alert.id), error=str(exc))

    push_body = f"시장신호 게이트({blocked.composite_level})로 이번 계획을 만들지 않았습니다."
    with contextlib.suppress(Exception):
        await send_push_to_user(
            user_id=alert.user_id,
            title=f"리밸런싱 자동화 보류 — {portfolio.name}",
            body=push_body,
            fcm_token=fcm_token,
            data={"type": "REBALANCING_MARKET_GATE_BLOCKED", "portfolio_id": str(portfolio.id)},
        )

    history_message = f"리밸런싱 자동화 보류(시장신호 게이트): {portfolio.name} — 현재 신호 {blocked.composite_level}"
    await save_alert_history(db, alert.user_id, "REBALANCING", history_message)
    await db.commit()

    await set_durable(db, dedup_key, "1", ttl=TTL_MARKET_SIGNAL_GATE_ALERT_SENT)


async def get_plan_leg_by_token(
    raw_token: str, expected_side: Literal["BUY", "SELL"] | None, db: AsyncSession
) -> RebalancingPlanLeg | None:
    """토큰 해시 매치로 leg를 조회한다. 읽기 전용 — DB를 변경하지 않는다."""
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    leg = await db.scalar(
        select(RebalancingPlanLeg)
        .options(selectinload(RebalancingPlanLeg.items), selectinload(RebalancingPlanLeg.plan))
        .where(RebalancingPlanLeg.action_token_hash == token_hash)
    )
    if leg is None:
        return None
    if expected_side is not None and leg.side != expected_side:
        return None
    return leg


async def _lock_and_claim(leg_id: uuid.UUID, db: AsyncSession) -> RebalancingPlanLeg:
    """leg를 FOR UPDATE로 잠그고 PENDING/미소비 상태를 확인한 뒤 토큰을 즉시 소비 처리한다.

    상태(status)는 아직 바꾸지 않고 token_consumed_at만 먼저 커밋해, 이후 실제 실행(수 초 소요될
    수 있는 브로커 API 호출) 도중 들어오는 중복 요청도 이 시점 이후로는 확실히 차단한다.
    """
    locked = await db.scalar(select(RebalancingPlanLeg).where(RebalancingPlanLeg.id == leg_id).with_for_update())
    if locked is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="계획을 찾을 수 없습니다")
    if locked.status != "PENDING" or locked.token_consumed_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="이미 처리되었거나 만료된 계획입니다")
    locked.token_consumed_at = datetime.now(tz=UTC)
    await db.commit()
    await db.refresh(locked)
    return locked


async def cancel_buy_leg(leg: RebalancingPlanLeg, db: AsyncSession, decided_by: str) -> None:
    locked = await _lock_and_claim(leg.id, db)
    locked.status = "CANCELED"
    locked.decided_at = datetime.now(tz=UTC)
    locked.decided_by = decided_by
    plan = await db.get(RebalancingPlan, locked.plan_id)
    if plan:
        await save_alert_history(db, plan.user_id, "REBALANCING", "리밸런싱 자동화 매수 대기 취소")
    await db.commit()


async def reject_sell_leg(leg: RebalancingPlanLeg, db: AsyncSession, decided_by: str) -> None:
    locked = await _lock_and_claim(leg.id, db)
    locked.status = "REJECTED"
    locked.decided_at = datetime.now(tz=UTC)
    locked.decided_by = decided_by
    plan = await db.get(RebalancingPlan, locked.plan_id)
    if plan:
        await save_alert_history(db, plan.user_id, "REBALANCING", "리밸런싱 자동화 매도 계획 거부")
    await db.commit()


async def _rebuild_orders_from_items(
    items: list[RebalancingPlanItem],
    side: str,
    user_id: uuid.UUID,
    db: AsyncSession,
    cache,
) -> list:
    """플랜 아이템으로부터 실행 주문을 재구성한다.

    수량은 계획 생성 시점 값을 그대로 사용(재계산 안 함). LIMIT 주문만 실행 직전 가격을 다시
    조회해 limit_price를 갱신한다 — 그 사이 대기시간 동안 벌어진 가격 변동을 반영하기 위함.
    """
    from app.schemas.rebalancing import ExecutionOrderItem
    from app.services.price_service import fetch_prices_batch

    limit_tickers = [(item.ticker, item.market or "") for item in items if item.order_type == "LIMIT" and item.ticker]
    price_map: dict[str, float] = {}
    if limit_tickers:
        try:
            price_map = await fetch_prices_batch(user_id, limit_tickers, db, cache)
        except Exception as exc:
            logger.warning("rebalancing_plan_limit_price_refresh_failed", error=str(exc))

    orders: list[ExecutionOrderItem] = []
    for item in items:
        limit_price = float(item.limit_price) if item.limit_price is not None else None
        if item.order_type == "LIMIT":
            fresh = price_map.get(item.ticker or "")
            if fresh and fresh > 0:
                limit_price = float(fresh)
        orders.append(
            ExecutionOrderItem(
                ticker=item.ticker or "",
                name=item.name or item.ticker or "",
                market=item.market or "",
                side=side,
                quantity=item.quantity,
                account_id=item.account_id,
                order_type=item.order_type,
                limit_price=limit_price,
                reference_price=float(item.reference_price) if item.reference_price is not None else None,
            )
        )
    return orders


async def _send_leg_execution_email(plan: RebalancingPlan, execution_id: uuid.UUID, db: AsyncSession) -> None:
    """leg 실행 완료 후 결과 이메일/푸시 발송 (기존 실행완료 템플릿 재사용)."""
    from app.models.asset import RebalancingExecution
    from app.models.user import User, UserSettings
    from app.services.email_service import send_rebalancing_execution_email
    from app.services.push_service import send_push_to_user

    exec_result = await db.scalar(
        select(RebalancingExecution)
        .options(selectinload(RebalancingExecution.result_items))
        .where(RebalancingExecution.id == execution_id)
    )
    if exec_result is None:
        return

    row = await db.execute(
        select(Portfolio.name, User.email, UserSettings.notification_email, UserSettings.fcm_token)
        .select_from(User)
        .outerjoin(Portfolio, Portfolio.id == plan.portfolio_id)
        .outerjoin(UserSettings, UserSettings.user_id == User.id)
        .where(User.id == plan.user_id)
    )
    info = row.first()
    if info is None:
        return
    portfolio_name, user_email, notification_email, fcm_token = info
    portfolio_name = portfolio_name or "포트폴리오"
    email = notification_email or user_email

    if email:
        try:
            await send_rebalancing_execution_email(
                to_email=email,
                portfolio_name=portfolio_name,
                executed_at=exec_result.executed_at,
                result_items=exec_result.result_items,
                total_success=exec_result.total_success,
                total_fail=exec_result.total_fail,
                total_skipped=exec_result.total_skipped,
            )
        except Exception as exc:
            logger.error("rebalancing_plan_execution_email_failed", execution_id=str(execution_id), error=str(exc))

    with contextlib.suppress(Exception):
        await send_push_to_user(
            user_id=plan.user_id,
            title=f"리밸런싱 자동 실행 완료 — {portfolio_name}",
            body=(
                f"{exec_result.total_success}건 완료"
                + (f", {exec_result.total_fail}건 실패" if exec_result.total_fail else "")
            ),
            fcm_token=fcm_token,
            data={"type": "REBALANCING_EXECUTED", "portfolio_id": str(plan.portfolio_id or "")},
        )


async def _notify_leg_execution_failed(plan: RebalancingPlan, side: str, error_message: str, db: AsyncSession) -> None:
    """leg 실행 자체가 예외로 실패했을 때(개별 종목 실패가 아닌 전체 실패) 이메일/푸시로 알린다.

    개별 종목 주문 실패는 `_send_leg_execution_email`의 완료 리포트(total_fail)로 이미 안내되지만,
    leg 실행 자체가 예외를 던진 경우(자격증명 오류, 브로커 토큰 발급 실패 등)는 실행 리포트가
    아예 생성되지 않아 사용자가 이력 탭을 직접 열어보지 않으면 알 방법이 없었다 — 그 공백을 메운다.
    """
    from app.models.user import User, UserSettings
    from app.services.email_service import send_rebalancing_plan_execution_failed_email
    from app.services.push_service import send_push_to_user

    row = await db.execute(
        select(Portfolio.name, User.email, UserSettings.notification_email, UserSettings.fcm_token)
        .select_from(User)
        .outerjoin(Portfolio, Portfolio.id == plan.portfolio_id)
        .outerjoin(UserSettings, UserSettings.user_id == User.id)
        .where(User.id == plan.user_id)
    )
    info = row.first()
    if info is None:
        return
    portfolio_name, user_email, notification_email, fcm_token = info
    portfolio_name = portfolio_name or "포트폴리오"
    email = notification_email or user_email

    if email:
        try:
            await send_rebalancing_plan_execution_failed_email(email, portfolio_name, side, error_message)
        except Exception as exc:
            logger.error("rebalancing_plan_execution_failed_email_error", plan_id=str(plan.id), error=str(exc))

    with contextlib.suppress(Exception):
        side_label = "매수" if side == "BUY" else "매도"
        await send_push_to_user(
            user_id=plan.user_id,
            title=f"리밸런싱 자동화 {side_label} 실행 실패 — {portfolio_name}",
            body="이번 계획은 체결되지 않았습니다. 앱에서 확인해주세요.",
            fcm_token=fcm_token,
            data={"type": "REBALANCING_PLAN_EXECUTION_FAILED", "portfolio_id": str(plan.portfolio_id or "")},
        )


async def _execute_leg(
    locked: RebalancingPlanLeg, plan: RebalancingPlan, db: AsyncSession, cache, decided_by: str
) -> uuid.UUID | None:
    """잠긴(claim된) leg의 아이템으로 실제 주문을 실행하고 상태를 최종 반영한다."""
    from app.services.rebalancing.execution_service import execute_rebalancing

    await db.refresh(locked, attribute_names=["items"])
    orders = await _rebuild_orders_from_items(locked.items, locked.side, plan.user_id, db, cache)

    try:
        _results, execution_id = await execute_rebalancing(
            user_id=plan.user_id,
            account_id=plan.account_id,
            orders=orders,
            db=db,
            cache=cache,
            portfolio_id=plan.portfolio_id,
            triggered_by="AUTO",
            strategy=plan.strategy,
        )
    except Exception as exc:
        logger.error("rebalancing_plan_leg_execute_failed", leg_id=str(locked.id), error=str(exc))
        locked.status = "FAILED"
        locked.error_message = str(exc)
        locked.decided_at = datetime.now(tz=UTC)
        locked.decided_by = decided_by
        await save_alert_history(
            db, plan.user_id, "REBALANCING", f"리밸런싱 자동화 {'매수' if locked.side == 'BUY' else '매도'} 실행 실패"
        )
        await db.commit()
        await _notify_leg_execution_failed(plan, locked.side, str(exc), db)
        return None

    locked.status = "EXECUTED"
    locked.execution_id = execution_id
    locked.decided_at = datetime.now(tz=UTC)
    locked.decided_by = decided_by
    await db.commit()
    return execution_id


async def _approve_leg_now(
    leg: RebalancingPlanLeg, db: AsyncSession, cache, decided_by: str, expected_side: Literal["BUY", "SELL"]
) -> uuid.UUID | None:
    """PENDING leg를 잠그고 즉시 실행한다 — BUY/SELL 공용 (앱에서 대기시간을 건너뛰고 즉시 체결할 때 사용)."""
    locked = await _lock_and_claim(leg.id, db)
    if locked.side != expected_side:
        label = "매도" if expected_side == "SELL" else "매수"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{label} 계획이 아닙니다")
    plan = await db.get(RebalancingPlan, locked.plan_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="계획을 찾을 수 없습니다")

    execution_id = await _execute_leg(locked, plan, db, cache, decided_by)
    if execution_id:
        await _send_leg_execution_email(plan, execution_id, db)
    return execution_id


async def approve_sell_leg(leg: RebalancingPlanLeg, db: AsyncSession, cache, decided_by: str) -> uuid.UUID | None:
    return await _approve_leg_now(leg, db, cache, decided_by, expected_side="SELL")


async def approve_buy_leg(leg: RebalancingPlanLeg, db: AsyncSession, cache, decided_by: str) -> uuid.UUID | None:
    """대기중인 매수 leg를 앱에서 즉시 실행한다 — 대기시간(buy_wait_minutes) 경과를 기다리지 않고 바로 체결."""
    return await _approve_leg_now(leg, db, cache, decided_by, expected_side="BUY")


async def execute_due_buy_legs(db: AsyncSession, cache) -> int:
    """대기시간이 지난 PENDING BUY leg를 실행한다. 대기 중 장마감을 넘겼으면 EXPIRED 처리(익일 이월 안 함).

    실행 직전 시장 신호 게이트를 다시 확인한다 — 계획 생성 시점엔 안전했더라도 대기시간(수 분~수십 분)
    동안 시장 상황이 악화될 수 있어서다(계획 생성 시점 1회만 확인하던 기존 동작의 공백). 차단되면
    leg는 PENDING으로 남아 다음 tick(1분 간격)에 재시도되고, 장마감까지 계속 막히면 위 EXPIRED 처리로
    자연 정리된다 — 별도 알림 없이 조용히 보류(계획 생성 자체를 건너뛰는 시장신호 게이트와 동일한 정책).
    """
    from app.models.alert import RebalancingAlert
    from app.services.rebalancing.order_builder import is_market_signal_blocking_auto_mode
    from app.utils.market_hours import is_korean_market_open, is_us_market_open

    now = datetime.now(tz=UTC)
    result = await db.execute(
        select(RebalancingPlanLeg.id).where(
            RebalancingPlanLeg.side == "BUY",
            RebalancingPlanLeg.status == "PENDING",
            RebalancingPlanLeg.deadline_at <= now,
        )
    )
    due_leg_ids = [row[0] for row in result.all()]
    if not due_leg_ids:
        return 0

    from app.services.market_signal_service import get_market_signal_for_auto_gate

    composite_level, data_freshness = await get_market_signal_for_auto_gate(cache)

    processed = 0
    for leg_id in due_leg_ids:
        locked = await db.scalar(select(RebalancingPlanLeg).where(RebalancingPlanLeg.id == leg_id).with_for_update())
        if locked is None or locked.status != "PENDING":
            continue

        market_open = is_korean_market_open() if locked.market == "KR" else is_us_market_open()
        if not market_open:
            locked.status = "EXPIRED"
            locked.error_message = "market_closed_before_execution"
            locked.decided_at = now
            locked.decided_by = "SYSTEM_AUTO"
            await db.commit()
            processed += 1
            continue

        plan = await db.get(RebalancingPlan, locked.plan_id)
        if plan is None:
            continue

        plan_alert_id = getattr(plan, "alert_id", None)
        alert = await db.get(RebalancingAlert, plan_alert_id) if plan_alert_id else None
        market_mode = getattr(alert, "market_condition_mode", "DISABLED")
        if is_market_signal_blocking_auto_mode(market_mode, composite_level, data_freshness):
            logger.info(
                "rebalancing_plan_buy_execution_skipped_market_signal",
                leg_id=str(locked.id),
                composite_level=composite_level,
                data_freshness=data_freshness,
            )
            continue

        locked.token_consumed_at = now
        await db.commit()

        execution_id = await _execute_leg(locked, plan, db, cache, "SYSTEM_AUTO")
        if execution_id:
            await _send_leg_execution_email(plan, execution_id, db)
        processed += 1

    return processed


async def expire_due_sell_legs(db: AsyncSession) -> int:
    """당일 장마감 시각이 지난 PENDING SELL leg를 EXPIRED로 마감한다."""
    now = datetime.now(tz=UTC)
    result = await db.execute(
        select(RebalancingPlanLeg.id).where(
            RebalancingPlanLeg.side == "SELL",
            RebalancingPlanLeg.status == "PENDING",
            RebalancingPlanLeg.deadline_at <= now,
        )
    )
    due_leg_ids = [row[0] for row in result.all()]

    processed = 0
    for leg_id in due_leg_ids:
        locked = await db.scalar(select(RebalancingPlanLeg).where(RebalancingPlanLeg.id == leg_id).with_for_update())
        if locked is None or locked.status != "PENDING":
            continue
        locked.status = "EXPIRED"
        locked.decided_at = now
        locked.decided_by = "SYSTEM_EXPIRY"
        plan = await db.get(RebalancingPlan, locked.plan_id)
        if plan:
            await save_alert_history(db, plan.user_id, "REBALANCING", "리밸런싱 자동화 매도 승인 만료 (장마감 미응답)")
        await db.commit()
        processed += 1

    return processed


async def list_recent_plan_legs(user_id: uuid.UUID, db: AsyncSession, limit: int = 30):
    """EXECUTED 제외(이미 실행 이력에 노출됨) 최근 leg 목록을 (leg, plan, portfolio_name, account_name) 튜플로 반환."""
    result = await db.execute(
        select(RebalancingPlanLeg, RebalancingPlan, Portfolio.name, AssetAccount.name)
        .join(RebalancingPlan, RebalancingPlan.id == RebalancingPlanLeg.plan_id)
        .outerjoin(Portfolio, Portfolio.id == RebalancingPlan.portfolio_id)
        .outerjoin(AssetAccount, AssetAccount.id == RebalancingPlan.account_id)
        .options(selectinload(RebalancingPlanLeg.items))
        .where(RebalancingPlan.user_id == user_id, RebalancingPlanLeg.status != "EXECUTED")
        .order_by(RebalancingPlanLeg.created_at.desc())
        .limit(limit)
    )
    return result.all()
