"""AUTO 리밸런싱 대기 플랜 생성 — 드리프트 분석 → 게이트 판정 → BUY/SELL leg 생성.

`plan_service.py`(구 단일 파일, 1025줄)에서 분리된 서브모듈. 계획 생성은
rebalancing/order_builder.py의 build_rebalancing_orders/refresh_live_prices를 재사용한다.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from typing import Any, Literal, cast

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.alert import RebalancingAlert
from app.models.portfolio import Portfolio
from app.models.rebalancing_plan import RebalancingPlan, RebalancingPlanItem, RebalancingPlanLeg
from app.services.rebalancing.order_builder import (
    build_rebalancing_orders,
    clamp_orders_to_max_value,
    filter_drifting_items,
    is_daily_value_cap_blocking_auto_mode,
    is_tax_impact_blocking_auto_mode,
    market_group,
    refresh_live_prices,
    split_orders_by_market,
)

logger = structlog.get_logger()

_KST = timezone(timedelta(hours=9))


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


@dataclass(frozen=True)
class DailyValueCapBlocked:
    """AUTO 계획 생성이 유저 단위 하루 합산 거래대금 상한으로 차단됐을 때 반환하는 sentinel."""

    today_total_krw: float
    attempted_value_krw: float
    cap_krw: float


@dataclass(frozen=True)
class PlanGenerationInProgress:
    """동시에 들어온 다른 계획 생성 요청이 이미 처리 중이라 유저 단위 락을 획득하지 못했을 때 반환하는 sentinel.

    AUTO 스케줄러 job과 수동 "지금 실행"이 같은 유저에 대해 거의 동시에 호출되는 경우에만 발생한다
    (하루 합산 거래한도의 check-then-act 레이스를 막기 위한 `inproc_lock` 직렬화, `build_pending_plan_for_alert`
    참고). 흔치 않은 경합이므로 재시도 안내만 하면 충분 — 별도 알림 발송은 하지 않는다.
    """


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


async def sum_today_auto_plan_value_krw(user_id: uuid.UUID, db: AsyncSession) -> float:
    """오늘(KST) 이 유저의 AUTO 대기 플랜 중 자금이 이동했거나 이동할 leg의 총 거래대금(KRW)을 합산한다.

    PENDING(대기중, 곧 실행될 수 있음)/EXECUTED(이미 실행됨) leg만 포함 — CANCELED/REJECTED/
    EXPIRED/FAILED는 자금이 이동하지 않(았)으므로 하루 합산 상한 계산에서 제외한다.
    """
    today_start_kst = datetime.now(tz=_KST).replace(hour=0, minute=0, second=0, microsecond=0)
    today_start_utc = today_start_kst.astimezone(UTC)

    total = await db.scalar(
        select(func.coalesce(func.sum(RebalancingPlanItem.quantity * RebalancingPlanItem.reference_price), 0))
        .select_from(RebalancingPlanItem)
        .join(RebalancingPlanLeg, RebalancingPlanLeg.id == RebalancingPlanItem.leg_id)
        .join(RebalancingPlan, RebalancingPlan.id == RebalancingPlanLeg.plan_id)
        .where(
            RebalancingPlan.user_id == user_id,
            RebalancingPlan.created_at >= today_start_utc,
            RebalancingPlanLeg.status.in_(["PENDING", "EXECUTED"]),
        )
    )
    return float(total or 0)


async def get_alert_ids_with_pending_plan(alert_ids: list[uuid.UUID], db: AsyncSession) -> set[uuid.UUID]:
    """여러 알림 중 PENDING 상태 leg가 있는 알림 id 집합을 한 번의 쿼리로 조회한다.

    `has_pending_plan_for_alert()`를 alert마다 개별 호출하면 AUTO 알림 수만큼 DB
    round-trip이 발생하는 N+1이 되므로(rebalancing_auto_execution.py 루프 전용),
    루프 시작 전 한 번에 조회해 멤버십 체크로 대체한다.
    """
    if not alert_ids:
        return set()
    result = await db.execute(
        select(RebalancingPlan.alert_id)
        .join(RebalancingPlanLeg, RebalancingPlanLeg.plan_id == RebalancingPlan.id)
        .where(RebalancingPlan.alert_id.in_(alert_ids), RebalancingPlanLeg.status == "PENDING")
        .distinct()
    )
    return {alert_id for alert_id in result.scalars().all() if alert_id is not None}


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
    from app.utils.market_hours import korean_market_close_datetime, us_market_close_datetime

    strategy = cast(str, strategy_override or getattr(alert, "strategy", "BUY_ONLY"))
    order_type = order_type_override or cast(Literal["MARKET", "LIMIT"], getattr(alert, "order_type", "MARKET"))
    account_id = account_id_override or alert.account_id

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
) -> (
    tuple[RebalancingPlan, list[tuple[str, str]], list[tuple[str, str]]]
    | None
    | TaxGateBlocked
    | DailyValueCapBlocked
    | PlanGenerationInProgress
):
    """알림 설정 기준으로 드리프트 분석 후 대기 플랜을 생성한다.

    AUTO 스케줄러 job과 수동 "지금 테스트 실행" 모두 이 함수로 플랜을 생성해 두 경로가
    동일한 계획 생성 로직(및 이메일 발송 파이프라인)을 공유하도록 한다.
    반환: (plan, buy_tokens, sell_tokens) | None(드리프트 없음) | TaxGateBlocked(세금영향 게이트 차단)
    | DailyValueCapBlocked(하루 합산 거래한도 게이트 차단) | PlanGenerationInProgress(동시 요청 락 획득 실패).
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

    # 게이트 판정(세금영향·하루합산한도) 이전에 라이브 시세로 갱신 — analysis.items와 drifting은
    # 같은 객체를 참조하므로 여기서 갱신하면 아래 _build_tax_preview(analysis, ...)에도 반영된다.
    await refresh_live_prices(drifting, alert.user_id, db, cache)

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

    from app.core.cache_store import get_cache_store
    from app.models.user import UserSettings
    from app.utils.inproc_lock import inproc_lock

    # 하루 합산 거래한도 체크(조회→비교→플랜생성)는 AUTO 잡과 수동 "지금 실행"이 거의 동시에
    # 호출될 수 있어 유저 단위 락으로 직렬화한다 — 락 없이는 두 호출이 같은 "오늘 누적액"을
    # 읽고 둘 다 통과해 한도를 최대 2배 초과할 수 있다.
    lock_cache = cache or await get_cache_store()
    async with inproc_lock(lock_cache, f"rebalancing_plan_gen:{alert.user_id}", ttl=60) as acquired:
        if not acquired:
            logger.info("rebalancing_plan_generation_lock_busy", alert_id=str(alert.id))
            return PlanGenerationInProgress()

        daily_cap_krw = await db.scalar(
            select(UserSettings.auto_rebalancing_daily_value_cap_krw).where(UserSettings.user_id == alert.user_id)
        )
        if daily_cap_krw is not None:
            attempted_value_krw = sum(abs(item.diff_krw) for item in drifting)
            today_total_krw = await sum_today_auto_plan_value_krw(alert.user_id, db)
            if is_daily_value_cap_blocking_auto_mode(today_total_krw, attempted_value_krw, float(daily_cap_krw)):
                logger.info(
                    "rebalancing_plan_blocked_daily_value_cap",
                    alert_id=str(alert.id),
                    today_total_krw=today_total_krw,
                    attempted_value_krw=attempted_value_krw,
                    cap_krw=float(daily_cap_krw),
                )
                return DailyValueCapBlocked(
                    today_total_krw=today_total_krw,
                    attempted_value_krw=attempted_value_krw,
                    cap_krw=float(daily_cap_krw),
                )

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
