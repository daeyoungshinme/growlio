"""포트폴리오별 비중 이탈 요약 — `/rebalancing/drift-summary`와 홈 "지금 할 일"(action_items_service)이 공유한다."""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.rebalancing import PortfolioDriftSummary
from app.services._portfolio_queries import get_active_alert_thresholds, get_linked_portfolios
from app.services._settings_queries import get_settings_row
from app.services.portfolio_service import build_portfolio_overview
from app.services.rebalancing.diagnosis_service import check_composite_signal, fetch_market_and_risk_signal
from app.services.rebalancing.service import compute_portfolio_drift_summary
from app.utils.cache_keys import CacheStoreType

logger = structlog.get_logger()


async def get_drift_summaries(
    user_id: uuid.UUID, db: AsyncSession, cache: CacheStoreType = None
) -> list[PortfolioDriftSummary]:
    """모든 포트폴리오의 비중 이탈 현황 (배당·수익률 외부 API 미사용)."""
    portfolios = await get_linked_portfolios(db, user_id)
    if not portfolios:
        return []

    alert_by_portfolio = await get_active_alert_thresholds(db, user_id)

    # 시장상황/리스크는 유저 단위 신호이므로 포트폴리오 루프 밖에서 1회만 조회한다.
    has_composite_signal = False
    composite_reason: str | None = None
    try:
        settings_row = await get_settings_row(db, user_id)
        enable_composite_signals = settings_row.composite_signal_alerts_enabled if settings_row else True
        if enable_composite_signals:
            market_level, risk = await fetch_market_and_risk_signal(user_id, db, cache)
            has_composite_signal, composite_reason = check_composite_signal(
                market_level,
                bool(risk.get("data_available")),
                risk.get("diversification_score"),
                risk.get("top_holding_weight_pct"),
                risk.get("annualized_volatility_pct"),
            )
    except Exception as e:
        logger.warning("drift_summary_composite_signal_failed", error=str(e))

    # NOTE: build_portfolio_overview는 요청-스코프 AsyncSession(db)으로 DB를 조회하므로
    # 포트폴리오 루프를 asyncio.gather로 동시 실행할 수 없다 (SQLAlchemy AsyncSession은
    # 동일 세션에 대한 동시 작업을 지원하지 않음). 별도 세션(AsyncSessionLocal)을 열어
    # 우회하는 방법은 FastAPI의 get_db dependency-override 기반 테스트 목킹과 충돌하므로
    # (실제 DB 연결 시도) 채택하지 않았다 — 순차 실행 유지, 콜드 캐시 시나리오는
    # 1.2(캐시 스레딩)/1.5(single-flight 락)로 완화한다.
    summaries: list[PortfolioDriftSummary] = []
    for portfolio in portfolios:
        try:
            portfolio_account_ids = getattr(portfolio, "account_ids", None)
            effective_ids = [uuid.UUID(aid) for aid in portfolio_account_ids] if portfolio_account_ids else None
            overview = await build_portfolio_overview(user_id, db, account_ids=effective_ids, cache=cache)
            threshold = alert_by_portfolio.get(str(portfolio.id), 5.0)
            summary = compute_portfolio_drift_summary(portfolio, overview, threshold)
            summary.has_composite_signal = has_composite_signal
            summary.composite_reason = composite_reason
            summary.has_alert_configured = str(portfolio.id) in alert_by_portfolio
            summaries.append(summary)
        except Exception as e:
            logger.error(
                "drift_summary_failed",
                portfolio_id=str(portfolio.id),
                error=str(e),
                exc_type=type(e).__name__,
            )

    return summaries
