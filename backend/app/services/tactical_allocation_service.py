"""QQQ/SPY 전술 배분 — 매크로 복합신호 + 차트 추세로 국면을 판정해 목표 비중을 제안한다.

비중 자산은 QQQ·SPY·DIA(다우)·QLD·SSO(나스닥·S&P 2배)·현금. DIA·QLD·SSO는 비중표에만 쓰이는 선택 자산이고(기본 0%)
국면 판정에는 넣지 않는다 — DIA는 SPY와 상관이 0.95를 넘어 새 정보가 거의 없고, 레버리지 ETF는 기초지수(QQQ·SPY)
신호와 같으며, 판정 규칙은 백테스트로 검증된 QQQ/SPY 기준을 유지한다.

제안 비중 = 국면 비중표 → 나스닥/S&P 틸트(`tactical_tilt`, 월 1회) → 눌림목 현금 투입(`tactical_dip`, 공격 국면만).

판정 규칙(순서대로):
1. SPY·QQQ 추세가 모두 UNKNOWN(시세 조회 실패)이면 판정 불가 → 기존 확정 국면 유지
2. 매크로 RED 이거나 SPY 추세 DOWN → RISK_OFF
3. SPY·QQQ 추세가 모두 UP 이고 매크로 GREEN(STALE 아님) → RISK_ON
   (직전 확정 국면이 RISK_ON이면 매크로 YELLOW여도 RISK_ON 유지 — 아래 히스테리시스)
4. 그 외 → NEUTRAL

공격 국면 히스테리시스: 진입은 매크로 GREEN이 필요하지만, 이미 공격 국면이면 YELLOW까지는 유지한다(RED·SPY 하락은
즉시 이탈 대상). 경계값 근처에서 GREEN↔YELLOW가 오갈 때마다 공격↔중립이 뒤집히던 왕복이 백테스트 전환 횟수의
절반 이상을 차지해 도입했다(10년 88→39회, CAGR·샤프 동반 개선 — 비대칭 확정일수·최소 유지기간은 회복 구간
재진입을 늦춰 오히려 성과가 나빠 채택하지 않음).

국면 확정(`step_confirmation`): 같은 새 국면이 서로 다른 KST 날짜에 2번 관측돼야 바뀐다. 매크로 등급 자체에도
2연속 확인 히스테리시스가 있으므로 이중 완충이다. 자동 주문은 하지 않는다 — 제안 비중을 포트폴리오 목표에
적용(`apply_regime_to_portfolio`)한 뒤 기존 리밸런싱 실행 화면에서 사용자가 직접 확인·실행한다.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any, Literal, NamedTuple

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.portfolio import Portfolio, PortfolioItem
from app.models.tactical import TacticalStrategy
from app.services.tactical_dip import ACTIVE_REGIMES as DIP_ACTIVE_REGIMES
from app.services.tactical_dip import DEFAULT_DIP_SHIFT_PCT, advance_dip_level, apply_dip, dip_reasons
from app.services.tactical_hints import transition_hints
from app.services.tactical_tilt import (
    DEFAULT_TILT_SHIFT_PCT,
    apply_tilt,
    classify_tilt,
    get_tilt_inputs,
    is_new_month,
    tilt_reasons,
)
from app.services.technical_indicators import TechnicalSnapshot, TrendState
from app.services.technical_signal_service import get_technical_signals
from app.utils.kst import today_kst

if TYPE_CHECKING:
    from app.core.cache_store import CacheStore

logger = structlog.get_logger()

Regime = Literal["RISK_ON", "NEUTRAL", "RISK_OFF"]
REGIMES: tuple[Regime, ...] = ("RISK_ON", "NEUTRAL", "RISK_OFF")
REGIME_LABELS: dict[str, str] = {"RISK_ON": "공격", "NEUTRAL": "중립", "RISK_OFF": "방어"}

TACTICAL_ASSETS: tuple[str, ...] = ("QQQ", "SPY", "DIA", "QLD", "SSO", "CASH")
# 0%면 비중 문구에서 생략하는 선택 자산(기본 비중표에 없음)
OPTIONAL_ASSETS = frozenset({"DIA", "QLD", "SSO"})
LEVERAGED_ASSETS = frozenset({"QLD", "SSO"})
# 포트폴리오 항목 저장 형식 — 프론트 종목검색 저장값과 동일(NYSE Arca 상장 ETF는 Yahoo PCX→"NYSE";
# KIS 주문 시 kis/exchange_master가 AMS 종목마스터로 AMEX 보정)
_ASSET_META: dict[str, tuple[str, str]] = {
    "QQQ": ("Invesco QQQ Trust", "NASDAQ"),
    "SPY": ("SPDR S&P 500 ETF Trust", "NYSE"),
    "DIA": ("SPDR Dow Jones Industrial Average ETF Trust", "NYSE"),
    "QLD": ("ProShares Ultra QQQ", "NYSE"),
    "SSO": ("ProShares Ultra S&P500", "NYSE"),
    "CASH": ("현금", "KRW"),
}

DEFAULT_REGIME_WEIGHTS: dict[str, dict[str, float]] = {
    "RISK_ON": {"QQQ": 50.0, "SPY": 40.0, "DIA": 0.0, "QLD": 0.0, "SSO": 0.0, "CASH": 10.0},
    "NEUTRAL": {"QQQ": 30.0, "SPY": 40.0, "DIA": 0.0, "QLD": 0.0, "SSO": 0.0, "CASH": 30.0},
    "RISK_OFF": {"QQQ": 10.0, "SPY": 30.0, "DIA": 0.0, "QLD": 0.0, "SSO": 0.0, "CASH": 60.0},
}

_TREND_LABELS: dict[TrendState, str] = {"UP": "상승", "NEUTRAL": "혼조", "DOWN": "하락", "UNKNOWN": "확인 불가"}
_MACRO_LABELS = {"GREEN": "안정", "YELLOW": "주의", "RED": "위험"}


def classify_regime(
    macro_level: str, macro_freshness: str, trends: dict[str, TrendState], prev: str | None = None
) -> tuple[Regime | None, list[str]]:
    """(국면 또는 판정불가 None, 판정 근거 문장 목록). `prev`는 직전 확정 국면(공격 국면 유지 판정용)."""
    spy = trends.get("SPY", "UNKNOWN")
    qqq = trends.get("QQQ", "UNKNOWN")
    macro_stale = macro_freshness == "STALE"
    reasons = [
        f"매크로 신호: {_MACRO_LABELS.get(macro_level, macro_level)}" + (" (데이터 지연)" if macro_stale else ""),
        f"SPY 추세: {_TREND_LABELS[spy]} · QQQ 추세: {_TREND_LABELS[qqq]}",
    ]
    if spy == "UNKNOWN" and qqq == "UNKNOWN":
        reasons.append("시세를 받지 못해 국면을 판정하지 않았습니다.")
        return None, reasons
    if (macro_level == "RED" and not macro_stale) or spy == "DOWN":
        return "RISK_OFF", reasons
    if spy == "UP" and qqq == "UP":
        if macro_level == "GREEN" and not macro_stale:
            return "RISK_ON", reasons
        if prev == "RISK_ON" and macro_level in ("GREEN", "YELLOW"):
            reasons.append("공격 국면 진입 이후 추세가 유지돼 공격 국면을 이어가요(매크로 위험 시 전환).")
            return "RISK_ON", reasons
    return "NEUTRAL", reasons


class ConfirmState(NamedTuple):
    """확정 상태 — 국면·틸트가 같은 규칙(`step_confirmation`)을 쓴다."""

    current: str | None
    pending: str | None
    pending_since: date | None


def step_confirmation(state: ConfirmState, observed: str | None, today: date) -> tuple[ConfirmState, bool]:
    """같은 새 값이 서로 다른 날짜에 2번 관측되면 확정한다. (새 상태, 확정값 변경 여부 — 최초 확정 포함).

    실시간은 KST 날짜, 백테스트는 거래일 날짜로 호출한다. 같은 날 반복 조회는 확정을 앞당기지 않는다.
    """
    if observed is None:
        return state, False
    if state.current is None:
        return ConfirmState(observed, None, None), True
    if observed == state.current:
        return ConfirmState(state.current, None, None), False
    if observed == state.pending and state.pending_since is not None and today > state.pending_since:
        return ConfirmState(observed, None, None), True
    if observed != state.pending:
        return ConfirmState(state.current, observed, today), False
    return state, False


def advance_regime(strategy: TacticalStrategy, market: dict[str, Any], today: date) -> bool:
    """시장 관측(`evaluate_market`)으로 확정 상태를 갱신한다. 확정 국면이 바뀌었으면 True(최초 확정 포함)."""
    observed, _ = observed_for(market, strategy.last_regime)
    state = ConfirmState(strategy.last_regime, strategy.pending_regime, strategy.pending_first_seen)
    new, changed = step_confirmation(state, observed, today)
    strategy.pending_regime = new.pending
    strategy.pending_first_seen = new.pending_since
    if changed:
        strategy.last_regime = new.current
        strategy.last_regime_changed_at = datetime.now(UTC)
        # 이전 국면의 분할 적용은 새 국면 제안과 무관 — 새 국면은 처음부터 다시 적용한다
        strategy.partial_regime = None
        strategy.partial_applied_on = None
    return changed


def advance_tilt(strategy: TacticalStrategy, market: dict[str, Any], today: date) -> bool:
    """그 달 첫 점검일에만 틸트를 갱신한다(입력 일부 결측이면 이번 점검은 건너뛰고 다음 점검에서 재시도).

    상태가 바뀌었으면(판정일 기록 포함) True — 호출부 커밋 판단용.
    """
    if not market.get("tilt_inputs_complete") or not is_new_month(strategy.tilt_evaluated_on, today):
        return False
    strategy.last_tilt = market["observed_tilt"]
    strategy.tilt_evaluated_on = today
    return True


def advance_dip(strategy: TacticalStrategy, market: dict[str, Any]) -> bool:
    """확정 국면 갱신 뒤 호출 — 눌림목 투입 단계를 갱신한다. 바뀌었으면 True(호출부 커밋 판단용).

    투입을 끈 전략(이동폭 0)도 단계는 추적한다 — 나중에 켰을 때 진행 중인 웅덩이를 바로 반영하도록.
    """
    prev = strategy.dip_level or 0
    new = advance_dip_level(prev, market.get("qqq_pullback_stage"), strategy.last_regime)
    if new == prev:
        return False
    strategy.dip_level = new
    return True


def dip_shift_of(strategy: TacticalStrategy | None) -> float:
    if strategy is None or strategy.dip_shift_pct is None:
        return DEFAULT_DIP_SHIFT_PCT
    return float(strategy.dip_shift_pct)


def effective_dip_level(strategy: TacticalStrategy | None, regime: str | None) -> int:
    """제안 비중에 쓸 투입 단계 — 전략이 없으면(미리보기)·공격 국면이 아니면 투입하지 않는다."""
    if strategy is None or regime not in DIP_ACTIVE_REGIMES:
        return 0
    return strategy.dip_level or 0


def tilt_shift_of(strategy: TacticalStrategy | None) -> float:
    # 새로 만든 객체는 flush 전까지 server_default가 채워지지 않아 None일 수 있다
    if strategy is None or strategy.tilt_shift_pct is None:
        return DEFAULT_TILT_SHIFT_PCT
    return float(strategy.tilt_shift_pct)


def effective_tilt(strategy: TacticalStrategy | None, market: dict[str, Any]) -> str:
    """제안 비중에 쓸 틸트 — 전략이 있으면 월 1회 확정값(아직 없으면 균형), 없으면 오늘 판정(미리보기)."""
    if strategy is None:
        return market.get("observed_tilt", "BALANCED")
    return strategy.last_tilt or "BALANCED"


def _tilted_weights(strategy: TacticalStrategy | None, regime: str, market: dict[str, Any]) -> dict[str, float]:
    return apply_tilt(resolve_weights(strategy)[regime], effective_tilt(strategy, market), tilt_shift_of(strategy))


def proposed_weights_for(strategy: TacticalStrategy | None, regime: str, market: dict[str, Any]) -> dict[str, float]:
    tilted = _tilted_weights(strategy, regime, market)
    return apply_dip(tilted, effective_dip_level(strategy, regime), dip_shift_of(strategy))


def dip_deployed_for(strategy: TacticalStrategy | None, regime: str | None, market: dict[str, Any]) -> float:
    """제안 비중에 실제로 들어간 웅덩이 투입량(%p) — 명목 투입량(`dip_amount`)이 현금 비중을 넘으면 현금까지만."""
    if regime is None:
        return 0.0
    tilted = _tilted_weights(strategy, regime, market)
    proposed = apply_dip(tilted, effective_dip_level(strategy, regime), dip_shift_of(strategy))
    return round(tilted.get("CASH", 0.0) - proposed.get("CASH", 0.0), 1)


def validate_regime_weights(raw: dict[str, Any]) -> dict[str, dict[str, float]]:
    """국면별 비중표 검증 — 3개 국면 모두, 자산은 TACTICAL_ASSETS(누락은 0), 각 0~100, 합계 100."""
    if set(raw) != set(REGIMES):
        raise ValueError("공격·중립·방어 3개 국면의 비중을 모두 입력해야 합니다.")
    result: dict[str, dict[str, float]] = {}
    for regime in REGIMES:
        weights = raw[regime]
        if not isinstance(weights, dict) or not weights or not set(weights) <= set(TACTICAL_ASSETS):
            raise ValueError("비중 자산은 QQQ·SPY·DIA·QLD·SSO·CASH만 사용할 수 있습니다.")
        cleaned = {k: float(v) for k, v in weights.items()}
        if any(v < 0 or v > 100 for v in cleaned.values()):
            raise ValueError("각 비중은 0~100 사이여야 합니다.")
        if abs(sum(cleaned.values()) - 100.0) > 0.01:
            raise ValueError(f"{REGIME_LABELS[regime]} 국면 비중 합계가 100이어야 합니다.")
        result[regime] = {a: cleaned.get(a, 0.0) for a in TACTICAL_ASSETS}
    return result


def resolve_weights(strategy: TacticalStrategy | None) -> dict[str, dict[str, float]]:
    if strategy is not None and strategy.regime_weights:
        try:
            return validate_regime_weights(strategy.regime_weights)
        except (ValueError, TypeError):
            logger.warning("tactical_invalid_stored_weights", strategy_id=str(strategy.id))
    return DEFAULT_REGIME_WEIGHTS


def format_weights(weights: dict[str, float]) -> str:
    return " · ".join(
        f"{'현금' if a == 'CASH' else a} {weights.get(a, 0):g}%"
        for a in TACTICAL_ASSETS
        if a not in OPTIONAL_ASSETS or weights.get(a, 0) > 0
    )


async def evaluate_market(cache: CacheStore | None, db: AsyncSession) -> dict[str, Any]:
    """유저 무관 공통 입력(매크로 확정 등급 + 차트 지표)과 관측 국면."""
    from app.services.market_signal_service import get_confirmed_composite_level

    try:
        macro_level, freshness = await get_confirmed_composite_level(cache, db)
    except Exception as exc:
        logger.warning("tactical_macro_fetch_failed", error=str(exc))
        macro_level, freshness = "GREEN", "STALE"
    technicals: dict[str, TechnicalSnapshot] = await get_technical_signals(cache)
    trends = {t: s["trend"] for t, s in technicals.items()}
    qqq_snap = technicals.get("QQQ")
    qqq_stage = qqq_snap.get("pullback_stage", "UNKNOWN") if qqq_snap else "UNKNOWN"
    observed, reasons = classify_regime(macro_level, freshness, trends)
    # 공격 국면 유지(히스테리시스)는 전략별 직전 확정 국면에 달려 있어 두 경우를 모두 계산해 둔다
    observed_on, reasons_on = classify_regime(macro_level, freshness, trends, prev="RISK_ON")
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
        "tilt_inputs": tilt_inputs,
        "tilt_inputs_complete": all(v is not None for v in tilt_inputs.values()),
        "observed_tilt": observed_tilt,
        "tilt_reasons": tilt_reasons(tilt_inputs, observed_tilt),
        "qqq_pullback_stage": qqq_stage,
    }


def observed_for(market: dict[str, Any], prev: str | None) -> tuple[Regime | None, list[str]]:
    """직전 확정 국면을 반영한 관측 국면과 근거."""
    if prev == "RISK_ON" and "observed_if_risk_on" in market:
        return market["observed_if_risk_on"], market["reasons_if_risk_on"]
    return market["observed_regime"], market["reasons"]


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


def _current_weights(portfolio: Portfolio) -> dict[str, float]:
    return {item.ticker: float(item.weight) for item in portfolio.items}


def is_tactical_managed(portfolio: Portfolio) -> bool:
    """포트폴리오가 전술 자산(TACTICAL_ASSETS)만으로 구성됐는지 — 아니면 적용 시 다른 종목이 지워진다는 경고 대상."""
    return all(item.ticker in TACTICAL_ASSETS for item in portfolio.items)


async def build_status(
    portfolio: Portfolio,
    strategy: TacticalStrategy | None,
    market: dict[str, Any],
) -> dict[str, Any]:
    weights_table = resolve_weights(strategy)
    confirmed = strategy.last_regime if strategy else None
    observed, reasons = observed_for(market, confirmed)
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
            effective, market["macro_level"], market["macro_freshness"], market["technicals"]
        ),
        "current_weights": _current_weights(portfolio),
        "portfolio_compatible": is_tactical_managed(portfolio),
    }


def interpolate_weights(current: dict[str, float], target: dict[str, float], fraction: float) -> dict[str, float]:
    """현재 목표에서 제안 비중 쪽으로 `fraction`만큼 이동(0.1%p 단위). 반올림 오차는 현금이 흡수한다."""
    out = {a: round(current.get(a, 0.0) + (target.get(a, 0.0) - current.get(a, 0.0)) * fraction, 1) for a in target}
    out["CASH"] = round(100.0 - sum(v for a, v in out.items() if a != "CASH"), 1)
    return out


async def apply_regime_to_portfolio(
    portfolio: Portfolio, strategy: TacticalStrategy, regime: Regime, db: AsyncSession, fraction: float = 1.0
) -> dict[str, float]:
    """포트폴리오 목표 비중을 제안 비중(국면+틸트+웅덩이)으로 교체한다(전술 자산 외 기존 종목은 삭제). 커밋은 호출부.

    `fraction<1`이면 현재 목표에서 제안 쪽으로 그만큼만 옮긴다(분할 적용 — 전술 자산만으로 구성된 포트폴리오인지는
    호출부가 확인). 이때는 "적용 완료" 대신 분할 적용 진행 상태(`partial_regime`)를 기록해 화면에
    "나머지 적용"이 남는다.
    """
    weights = proposed_weights_for(strategy, regime, {})
    if fraction < 1:
        weights = interpolate_weights(_current_weights(portfolio), weights, fraction)
    await db.execute(delete(PortfolioItem).where(PortfolioItem.portfolio_id == portfolio.id))
    for idx, asset in enumerate(a for a in TACTICAL_ASSETS if weights.get(a, 0) > 0):
        name, market = _ASSET_META[asset]
        db.add(
            PortfolioItem(
                portfolio_id=portfolio.id,
                ticker=asset,
                name=name,
                market=market,
                weight=weights[asset],
                sort_order=idx,
            )
        )
    if fraction >= 1:
        strategy.applied_regime = regime
        strategy.notified_dip_level = strategy.dip_level or 0
        strategy.partial_regime = None
        strategy.partial_applied_on = None
    else:
        strategy.partial_regime = regime
        strategy.partial_applied_on = today_kst()
    return weights
