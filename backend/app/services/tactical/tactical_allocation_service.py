"""전술 배분 서비스 — 시장 관측(`evaluate_market`), 전략 조회·저장·해제, 상태 응답, 제안 비중 적용(DB 쓰기).

국면 판정·제안 비중 규칙은 `tactical_regime`, 적용 계획(그룹 재구성·분할 보간·할 일 판정)은 `tactical_apply`에 있다.
이 파일은 두 모듈의 심볼을 재노출한다 — `from ...tactical_allocation_service import X`·`patch.object(tactical, ...)`
호출부는 그대로 유효하다. 단 서브모듈 안의 함수 간 호출을 가로채려면 그 서브모듈 경로를 patch해야 한다.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import RebalancingAlert
from app.models.portfolio import Portfolio, PortfolioItem
from app.models.tactical import TacticalStrategy
from app.services.market_signal.technical_indicators import TechnicalSnapshot
from app.services.market_signal.technical_signal_service import get_technical_signals
from app.services.tactical.tactical_apply import (
    _current_weights,
    _GroupSpec,
    _MemberSpec,
    _new_item,
    _plan_groups,
    _weights_to_apply,
    check_apply_allowed,
    current_groups,
    interpolate_weights,
    is_tactical_managed,
    needs_group_suggestions,
    pending_action,
    tactical_asset_of,
)
from app.services.tactical.tactical_dip import dip_reasons
from app.services.tactical.tactical_hints import transition_hints
from app.services.tactical.tactical_regime import (
    ASSET_GROUP_KEYS,
    ASSET_LABELS,
    DEFAULT_REGIME_WEIGHTS,
    LEVERAGED_ASSETS,
    OPTIONAL_ASSETS,
    REGIME_LABELS,
    REGIMES,
    TACTICAL_ASSETS,
    ConfirmState,
    Regime,
    advance_dip,
    advance_regime,
    advance_tilt,
    classify_regime,
    dip_deployed_for,
    dip_shift_of,
    effective_dip_level,
    effective_tilt,
    format_weights,
    observed_for,
    proposed_weights_for,
    resolve_weights,
    step_confirmation,
    tilt_shift_of,
    uses_macro,
    validate_regime_weights,
)
from app.services.tactical.tactical_tilt import classify_tilt, get_tilt_inputs, tilt_reasons
from app.utils.kst import today_kst

if TYPE_CHECKING:
    from app.core.cache_store import CacheStore
    from app.schemas.portfolio import IndexGroupSuggestion
    from app.schemas.tactical import TacticalStrategyUpsert

__all__ = [
    "ASSET_GROUP_KEYS",
    "ASSET_LABELS",
    "DEFAULT_REGIME_WEIGHTS",
    "LEVERAGED_ASSETS",
    "OPTIONAL_ASSETS",
    "REGIMES",
    "REGIME_LABELS",
    "TACTICAL_ASSETS",
    "ConfirmState",
    "Regime",
    "_GroupSpec",
    "_MemberSpec",
    "_current_weights",
    "_new_item",
    "_plan_groups",
    "_weights_to_apply",
    "advance_dip",
    "advance_regime",
    "advance_tilt",
    "apply_regime_to_portfolio",
    "build_status",
    "check_apply_allowed",
    "classify_regime",
    "current_groups",
    "dip_deployed_for",
    "dip_shift_of",
    "disable_strategy",
    "effective_dip_level",
    "effective_tilt",
    "evaluate_market",
    "format_weights",
    "get_owned_portfolio",
    "get_strategy",
    "interpolate_weights",
    "is_tactical_managed",
    "list_strategies",
    "needs_group_suggestions",
    "observed_for",
    "pending_action",
    "proposed_weights_for",
    "resolve_weights",
    "save_strategy",
    "step_confirmation",
    "tactical_asset_of",
    "tilt_shift_of",
    "uses_macro",
    "validate_regime_weights",
]


async def evaluate_market(cache: CacheStore | None, db: AsyncSession) -> dict[str, Any]:
    """유저 무관 공통 입력(매크로 확정 등급 + 차트 지표)과 관측 국면."""
    from app.services.market_signal.market_signal_service import get_confirmed_composite_level

    # 실패하면 내부에서 (GREEN, STALE)로 폴백한다
    macro_level, freshness = await get_confirmed_composite_level(cache, db)
    technicals: dict[str, TechnicalSnapshot] = await get_technical_signals(cache)
    trends = {t: s["trend"] for t, s in technicals.items()}
    qqq_snap = technicals.get("QQQ")
    qqq_stage = qqq_snap.get("pullback_stage", "UNKNOWN") if qqq_snap else "UNKNOWN"
    observed, reasons = classify_regime(macro_level, freshness, trends)
    # 공격 국면 유지(히스테리시스)는 전략별 직전 확정 국면에 달려 있어 두 경우를 모두 계산해 둔다
    observed_on, reasons_on = classify_regime(macro_level, freshness, trends, prev="RISK_ON")
    # 매크로를 끈 전략용 — 매크로가 GREEN 고정이라 공격 유지 히스테리시스와 무관(prev 불필요)
    observed_nm, reasons_nm = classify_regime(macro_level, freshness, trends, use_macro=False)
    tilt_inputs = await get_tilt_inputs(cache)
    observed_tilt = classify_tilt(tilt_inputs["real_yield_change_pp"], tilt_inputs["relative_strength_pct"])
    return {
        "macro_level": macro_level,
        "macro_freshness": freshness,
        "technicals": technicals,
        "observed_regime": observed,
        "reasons": reasons,
        "observed_if_risk_on": observed_on,
        "reasons_if_risk_on": reasons_on,
        "observed_no_macro": observed_nm,
        "reasons_no_macro": reasons_nm,
        "tilt_inputs": tilt_inputs,
        "tilt_inputs_complete": all(v is not None for v in tilt_inputs.values()),
        "observed_tilt": observed_tilt,
        "tilt_reasons": tilt_reasons(tilt_inputs, observed_tilt),
        "qqq_pullback_stage": qqq_stage,
    }


async def get_owned_portfolio(portfolio_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession) -> Portfolio | None:
    from sqlalchemy.orm import selectinload

    result = await db.execute(
        select(Portfolio)
        .options(selectinload(Portfolio.items))
        .where(Portfolio.id == portfolio_id, Portfolio.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def get_strategy(portfolio_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession) -> TacticalStrategy | None:
    result = await db.execute(
        select(TacticalStrategy).where(
            TacticalStrategy.portfolio_id == portfolio_id, TacticalStrategy.user_id == user_id
        )
    )
    return result.scalar_one_or_none()


async def list_strategies(user_id: uuid.UUID, db: AsyncSession) -> list[TacticalStrategy]:
    """사용자가 전술 배분을 켠 포트폴리오들의 전략 — 목표 조정 › 전술의 기본 선택·"(전술 켜짐)" 표시용."""
    result = await db.execute(
        select(TacticalStrategy).where(TacticalStrategy.user_id == user_id).order_by(TacticalStrategy.created_at)
    )
    return list(result.scalars().all())


async def save_strategy(
    portfolio_id: uuid.UUID,
    user_id: uuid.UUID,
    body: TacticalStrategyUpsert,
    cache: CacheStore | None,
    db: AsyncSession,
) -> tuple[TacticalStrategy, dict[str, Any]]:
    """전략 사용 시작/설정 변경 후 커밋. 최초 생성 시 현재 관측 국면을 바로 확정 국면으로 삼는다(알림 없음).

    상태 응답을 다시 계산하지 않도록 판정에 쓴 시장 지표를 함께 돌려준다.
    """
    strategy = await get_strategy(portfolio_id, user_id, db)
    if strategy is None:
        strategy = TacticalStrategy(user_id=user_id, portfolio_id=portfolio_id)
        db.add(strategy)
    strategy.notify_enabled = body.notify_enabled
    strategy.regime_weights = body.regime_weights
    strategy.tilt_shift_pct = Decimal(str(body.tilt_shift_pct))
    strategy.dip_shift_pct = Decimal(str(body.dip_shift_pct))
    strategy.use_macro = body.use_macro

    market = await evaluate_market(cache, db)
    today = today_kst()
    advance_regime(strategy, market, today)
    advance_tilt(strategy, market, today)
    advance_dip(strategy, market)
    if strategy.notified_regime is None:
        strategy.notified_regime = strategy.last_regime  # 사용 시작 시점 국면은 알릴 필요 없음
        strategy.notified_dip_level = strategy.dip_level or 0  # 진행 중인 웅덩이도 마찬가지
    await db.commit()
    return strategy, market


async def disable_strategy(portfolio_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession) -> None:
    """전략 사용 중지(포트폴리오 목표 비중은 그대로 둔다).

    이 포트폴리오의 자동매수가 전술 연동(`market_condition_mode="TACTICAL"`)이면 일반 모드(DISABLED)로 되돌린다 —
    국면이 없으면 게이트가 늘 통과라 연동 표시만 남아 오해를 부른다. 적립식 여부와 상관없이 TACTICAL인 알림은 모두
    되돌리므로 프론트는 끌 때마다 알림 캐시를 비운다(plans/101 A1).
    """
    strategy = await get_strategy(portfolio_id, user_id, db)
    if strategy is None:
        return
    await db.execute(
        update(RebalancingAlert)
        .where(
            RebalancingAlert.portfolio_id == portfolio_id,
            RebalancingAlert.user_id == user_id,
            RebalancingAlert.market_condition_mode == "TACTICAL",
        )
        .values(market_condition_mode="DISABLED")
    )
    await db.delete(strategy)
    await db.commit()


async def build_status(
    portfolio: Portfolio,
    strategy: TacticalStrategy | None,
    market: dict[str, Any],
) -> dict[str, Any]:
    weights_table = resolve_weights(strategy)
    confirmed = strategy.last_regime if strategy else None
    use_macro = uses_macro(strategy)
    observed, reasons = observed_for(market, confirmed, use_macro)
    effective = confirmed or observed
    dip_level = effective_dip_level(strategy, effective)
    deployed = dip_deployed_for(strategy, effective, market)
    stage = market.get("qqq_pullback_stage", "UNKNOWN")
    partial_active = strategy is not None and confirmed is not None and strategy.partial_regime == confirmed
    return {
        "portfolio_id": str(portfolio.id),
        "portfolio_name": portfolio.name,
        "enabled": strategy is not None,
        "notify_enabled": strategy.notify_enabled if strategy else False,
        "use_macro": use_macro,
        "macro_level": market["macro_level"],
        "macro_freshness": market["macro_freshness"],
        "technicals": market["technicals"],
        "observed_regime": observed,
        "confirmed_regime": confirmed,
        "pending_regime": strategy.pending_regime if strategy else None,
        "regime_changed_at": strategy.last_regime_changed_at.isoformat()
        if strategy and strategy.last_regime_changed_at
        else None,
        "applied_regime": strategy.applied_regime if strategy else None,
        "reasons": reasons,
        "regime_weights": weights_table,
        "is_default_weights": weights_table is DEFAULT_REGIME_WEIGHTS,
        "proposed_weights": proposed_weights_for(strategy, effective, market) if effective else None,
        "tilt_shift_pct": tilt_shift_of(strategy),
        "observed_tilt": market.get("observed_tilt", "BALANCED"),
        "confirmed_tilt": effective_tilt(strategy, market),
        "tilt_evaluated_on": strategy.tilt_evaluated_on.isoformat()
        if strategy and strategy.tilt_evaluated_on
        else None,
        "tilt_inputs": market.get("tilt_inputs"),
        "tilt_reasons": market.get("tilt_reasons", []),
        "dip_shift_pct": dip_shift_of(strategy),
        "dip_level": dip_level,
        "pullback_stage": stage,
        "dip_deployed_pct": deployed,
        "dip_reasons": dip_reasons(stage, dip_level, dip_shift_of(strategy), effective, deployed=deployed),
        "partial_regime": strategy.partial_regime if partial_active and strategy else None,
        "partial_applied_on": strategy.partial_applied_on.isoformat()
        if partial_active and strategy and strategy.partial_applied_on
        else None,
        "transition_hints": transition_hints(
            effective, market["macro_level"], market["macro_freshness"], market["technicals"], use_macro=use_macro
        ),
        "current_weights": _current_weights(portfolio),
        "current_groups": current_groups(portfolio),
        "portfolio_compatible": is_tactical_managed(portfolio),
    }


async def apply_regime_to_portfolio(
    portfolio: Portfolio,
    strategy: TacticalStrategy,
    regime: Regime,
    db: AsyncSession,
    fraction: float = 1.0,
    group_suggestions: dict[str, IndexGroupSuggestion] | None = None,
) -> dict[str, float]:
    """포트폴리오 목표 비중을 제안 비중(국면+틸트+웅덩이)으로 교체한다(전술 자산 외 기존 종목은 삭제). 커밋은 호출부.

    QQQ·SPY·DIA는 지수 그룹 항목으로 저장한다(plans/76) — 기존 그룹은 대표 종목·멤버·국내 대체를 그대로 두고
    비중만 바꾸고, 없으면 `group_suggestions`(그룹 키 → 보유 종목 기반 제안)로 만든다(제안이 없으면 대표 종목만).

    `fraction<1`이면 현재 목표에서 제안 쪽으로 그만큼만 옮긴다(분할 적용 — 전술 자산만으로 구성된 포트폴리오인지는
    호출부가 확인). 이때는 "적용 완료" 대신 분할 적용 진행 상태(`partial_regime`)를 기록해 화면에
    "나머지 적용"이 남는다.
    """
    weights = _weights_to_apply(portfolio, strategy, regime, fraction)
    groups = _plan_groups(portfolio, weights, group_suggestions)
    # 그룹 구성은 위에서 값으로 복사해 뒀다 — 항목을 다시 만들어도(기존 멤버는 FK CASCADE로 삭제) 보존된다
    await db.execute(delete(PortfolioItem).where(PortfolioItem.portfolio_id == portfolio.id))
    for idx, asset in enumerate(a for a in TACTICAL_ASSETS if weights.get(a, 0) > 0):
        db.add(_new_item(portfolio, asset, weights[asset], idx, groups.get(asset)))
    if fraction >= 1:
        strategy.applied_regime = regime
        strategy.notified_dip_level = strategy.dip_level or 0
        strategy.partial_regime = None
        strategy.partial_applied_on = None
    else:
        strategy.partial_regime = regime
        strategy.partial_applied_on = today_kst()
    return weights
