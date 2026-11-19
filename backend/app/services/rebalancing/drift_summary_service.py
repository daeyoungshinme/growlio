"""포트폴리오별 비중 이탈 요약 — `/rebalancing/drift-summary`와 홈 "지금 할 일"(action_items_service)이 공유한다.

진단 탭 "언제 할지"(plans/136): 이탈 판정에 마지막 리밸런싱·다음 예정일·매도 비용 추정·시점 판정을 붙인다.
모두 이미 읽은 overview·분석·알림 행과 DB 조회만 쓴다(외부 시세·증권사 호출 없음).
"""

from __future__ import annotations

import uuid
from datetime import date

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import RebalancingAlert
from app.schemas.rebalancing import PortfolioDriftSummary
from app.services._settings_queries import get_settings_row
from app.services.alerts.calculator import upcoming_schedule_date
from app.services.market_signal.market_signal_service import get_last_composite_level, get_market_signal
from app.services.portfolio._portfolio_queries import (
    alert_drift_thresholds,
    get_active_alerts_by_portfolio,
    get_last_rebalanced_at,
    get_linked_portfolios,
)
from app.services.portfolio.portfolio_service import build_portfolio_overview
from app.services.rebalancing.diagnosis_service import estimate_sell_costs, fetch_composite_signal
from app.services.rebalancing.drift_rule import drift_progress
from app.services.rebalancing.order_builder import is_market_signal_blocking_auto_mode, tactical_regime_for_gate
from app.services.rebalancing.service import analyze_rebalancing, summarize_drift
from app.services.rebalancing.timing_verdict import decide_timing
from app.utils.cache_keys import CacheStoreType
from app.utils.kst import today_kst

logger = structlog.get_logger()

_SCHEDULE_TRIGGERS = ("SCHEDULE_ONLY", "BOTH")


async def _market_levels(db: AsyncSession, cache: CacheStoreType) -> tuple[str | None, bool]:
    """(확정 등급, STALE 여부) — 읽기 전용. 확정 등급은 자동 실행 게이트가 쓰는 값(durable)을 그대로 읽는다.

    `get_confirmed_composite_level`은 확정 후보를 기록(쓰기)하므로 조회 경로에서 부르지 않는다. 확정 기록이
    아직 없으면 즉시 등급으로 대신한다. 시장 신호 조회 실패는 (None, True) — GREEN으로 지어내지 않는다.
    """
    try:
        raw = await get_market_signal(cache)
    except Exception as e:
        logger.warning("drift_summary_market_signal_failed", error=str(e))
        return None, True
    stale = raw.get("data_freshness") == "STALE"
    try:
        confirmed = await get_last_composite_level(db)
    except Exception as e:
        logger.warning("drift_summary_confirmed_level_failed", error=str(e))
        confirmed = None
    return confirmed or raw.get("composite_level"), stale


def _next_schedule(alerts: list[RebalancingAlert], today: date) -> tuple[date | None, str | None]:
    """스케줄 알림 중 가장 가까운 다음 실행·발송일과 그 주기."""
    best: tuple[date, str] | None = None
    for alert in alerts:
        if alert.trigger_condition not in _SCHEDULE_TRIGGERS:
            continue
        d = upcoming_schedule_date(alert, today)
        if d is not None and (best is None or d < best[0]):
            best = (d, alert.schedule_type)
    return (best[0], best[1]) if best else (None, None)


async def _blocked_gate_mode(
    alerts: list[RebalancingAlert], db: AsyncSession, confirmed_level: str | None, stale: bool
) -> str | None:
    """이 포트폴리오의 AUTO 알림 중 지금 시장 게이트에 막힌 것의 `market_condition_mode`(없으면 None).

    자동 실행과 같은 판정 함수(`is_market_signal_blocking_auto_mode`)를 쓴다 — 화면이 "지금 실행"이라 하는데
    자동 실행은 보류되는 어긋남을 막는다.
    """
    for alert in alerts:
        if alert.mode != "AUTO" or alert.market_condition_mode == "DISABLED":
            continue
        regime = await tactical_regime_for_gate(alert, db)
        if is_market_signal_blocking_auto_mode(
            alert.market_condition_mode, confirmed_level or "GREEN", "STALE" if stale else "LIVE", regime
        ):
            return alert.market_condition_mode
    return None


async def get_drift_summaries(
    user_id: uuid.UUID, db: AsyncSession, cache: CacheStoreType = None
) -> list[PortfolioDriftSummary]:
    """모든 포트폴리오의 비중 이탈 현황 (배당·수익률 외부 API 미사용)."""
    portfolios = await get_linked_portfolios(db, user_id)
    if not portfolios:
        return []

    alerts_by_portfolio = await get_active_alerts_by_portfolio(db, user_id)
    try:
        last_rebalanced = await get_last_rebalanced_at(db, user_id)
    except Exception as e:
        logger.warning("drift_summary_last_rebalanced_failed", error=str(e))
        last_rebalanced = {}

    # 시장상황/리스크는 유저 단위 신호이므로 포트폴리오 루프 밖에서 1회만 조회한다.
    has_composite_signal = False
    composite_reason: str | None = None
    try:
        settings_row = await get_settings_row(db, user_id)
        enable_composite_signals = settings_row.composite_signal_alerts_enabled if settings_row else True
        if enable_composite_signals:
            has_composite_signal, composite_reason = await fetch_composite_signal(user_id, db, cache)
    except Exception as e:
        logger.warning("drift_summary_composite_signal_failed", error=str(e))

    confirmed_level, market_stale = await _market_levels(db, cache)
    today = today_kst()

    # NOTE: build_portfolio_overview는 요청-스코프 AsyncSession(db)으로 DB를 조회하므로
    # 포트폴리오 루프를 asyncio.gather로 동시 실행할 수 없다 (SQLAlchemy AsyncSession은
    # 동일 세션에 대한 동시 작업을 지원하지 않음). 별도 세션(AsyncSessionLocal)을 열어
    # 우회하는 방법은 FastAPI의 get_db dependency-override 기반 테스트 목킹과 충돌하므로
    # (실제 DB 연결 시도) 채택하지 않았다 — 순차 실행 유지, 콜드 캐시 시나리오는
    # 1.2(캐시 스레딩)/1.5(single-flight 락)로 완화한다.
    summaries: list[PortfolioDriftSummary] = []
    pending_ids = [p.id for p in portfolios]
    by_id = {p.id: p for p in portfolios}
    for portfolio_id in pending_ids:
        portfolio = by_id.get(portfolio_id)
        if portfolio is None:
            continue
        try:
            portfolio_account_ids = getattr(portfolio, "account_ids", None)
            effective_ids = [uuid.UUID(aid) for aid in portfolio_account_ids] if portfolio_account_ids else None
            overview = await build_portfolio_overview(user_id, db, account_ids=effective_ids, cache=cache)
            alerts = alerts_by_portfolio.get(str(portfolio.id), [])
            threshold, relative = alert_drift_thresholds(alerts)
            analysis = analyze_rebalancing(portfolio, overview, include_implicit_cash=True)
            summary = summarize_drift(portfolio, analysis, threshold, relative)
            summary.has_composite_signal = has_composite_signal
            summary.composite_reason = composite_reason
            summary.has_alert_configured = bool(alerts)
            summary.last_rebalanced_at = last_rebalanced.get(str(portfolio.id))
            summary.next_scheduled_date, summary.schedule_type = _next_schedule(alerts, today)

            overseas_tax = 0.0
            if summary.needs_rebalancing:
                costs = estimate_sell_costs(analysis, overview)
                overseas_tax = costs.overseas_tax
                summary.estimated_trade_krw = round(costs.sell_notional, 0)
                summary.estimated_cost_krw = round(costs.fee + costs.overseas_tax, 0)
                summary.estimated_overseas_gain_krw = round(costs.overseas_gain, 0)

            verdict = decide_timing(
                needs_rebalancing=summary.needs_rebalancing,
                drift_progress=drift_progress(analysis.items, threshold, relative),
                max_drift_pct=summary.max_drift_pct,
                threshold_pct=threshold,
                relative_threshold_pct=relative,
                confirmed_level=confirmed_level,
                market_stale=market_stale,
                gate_blocked_mode=(
                    await _blocked_gate_mode(alerts, db, confirmed_level, market_stale)
                    if summary.needs_rebalancing
                    else None
                ),
                estimated_overseas_tax_krw=overseas_tax,
            )
            summary.timing = verdict.timing
            summary.timing_reason = verdict.reason
            summaries.append(summary)
        except Exception as e:
            logger.warning(
                "drift_summary_failed",
                portfolio_id=str(portfolio_id),
                error=str(e),
                exc_type=type(e).__name__,
            )
            # DB 오류로 트랜잭션이 aborted면 뒤 포트폴리오가 전부 PendingRollbackError로 빠진다.
            # rollback은 루프의 Portfolio 객체를 expire시키므로(async lazy load 불가) 다시 읽는다.
            try:
                await db.rollback()
                by_id = {p.id: p for p in await get_linked_portfolios(db, user_id)}
                alerts_by_portfolio = await get_active_alerts_by_portfolio(db, user_id)
            except Exception:
                logger.warning("drift_summary_recover_failed", user_id=str(user_id))
                break

    return summaries
