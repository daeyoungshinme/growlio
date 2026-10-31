"""규칙 기반 포트폴리오 인사이트 & 진단 서비스."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass
from enum import StrEnum

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.job_runner import report_handled_failure
from app.services.portfolio.asset_aggregator import get_dashboard_summary
from app.services.tax.tax_service import get_overseas_positions_detail, get_tax_summary
from app.utils.cache_keys import (
    TTL_INSIGHTS,
    TTL_MARKET_SIGNAL_DEGRADED,
    CacheStoreType,
    get_cached_json,
    insights_key,
    set_cached_json,
)
from app.utils.kst import today_kst

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# 타입 정의
# ---------------------------------------------------------------------------


class InsightSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ALERT = "ALERT"


class InsightType(StrEnum):
    CONCENTRATION = "CONCENTRATION"
    REBALANCING_OPPORTUNITY = "REBALANCING_OPPORTUNITY"
    TAX_LOSS_HARVEST = "TAX_LOSS_HARVEST"


@dataclass
class Insight:
    type: str
    severity: str
    title: str
    detail: str
    action_label: str | None = None
    action_url: str | None = None
    metric_value: float | None = None


# ---------------------------------------------------------------------------
# 진입점
# ---------------------------------------------------------------------------


async def generate_insights(
    user_id: uuid.UUID,
    db: AsyncSession,
    cache: CacheStoreType = None,
    force_refresh: bool = False,
) -> list[dict]:
    """모든 체커를 병렬 실행하고 인사이트 목록을 반환한다 (1h 캐시)."""
    if not force_refresh:
        cached = await get_cached_json(cache, insights_key(user_id))
        if cached is not None:
            return cached

    # 일부가 실패한 목록을 1시간 캐싱하면 그동안 인사이트가 빠진 채 보인다 — 실패가 있으면 짧게만 둔다 (plans/99 A3)
    degraded = False
    try:
        dashboard = await get_dashboard_summary(user_id, db, cache)
    except Exception as e:
        report_handled_failure("insight_dashboard_summary_failed", e, user_id=str(user_id))
        dashboard = {}
        degraded = True

    def _mark_degraded() -> None:
        nonlocal degraded
        degraded = True

    # 체커들이 같은 AsyncSession을 쓰므로 순차 실행한다(동시 사용 불가). 체커 하나의 실패는 나머지에 영향 없음.
    checkers = (
        lambda: _check_concentration(dashboard),
        lambda: _check_rebalancing_opportunity(user_id, db, cache, on_partial_failure=_mark_degraded),
        lambda: _check_tax_loss_harvest(user_id, db),
    )
    insights: list[Insight] = []
    for run_checker in checkers:
        try:
            insights.extend(await run_checker())
        except Exception as res:
            report_handled_failure("insight_checker_failed", res, user_id=str(user_id))
            degraded = True
            # 뒤 체커가 aborted 트랜잭션에서 실패하지 않게 되돌린다(체커는 ORM 객체를 새로 읽는다)
            try:
                await db.rollback()
            except Exception:
                logger.warning("insight_checker_rollback_failed")

    # 심각도 순 정렬: ALERT → WARNING → INFO
    _severity_order = {InsightSeverity.ALERT: 0, InsightSeverity.WARNING: 1, InsightSeverity.INFO: 2}
    insights.sort(key=lambda i: _severity_order.get(InsightSeverity(i.severity), 9))

    data = [asdict(i) for i in insights]

    await set_cached_json(cache, insights_key(user_id), data, TTL_MARKET_SIGNAL_DEGRADED if degraded else TTL_INSIGHTS)
    return data


# ---------------------------------------------------------------------------
# 체커 1: 집중도
# ---------------------------------------------------------------------------


async def _check_concentration(dashboard: dict) -> list[Insight]:
    """단일 종목/유형 집중도 > 30% 경고."""
    insights: list[Insight] = []
    total = float(dashboard.get("total_assets_krw") or 0)
    if total <= 0:
        return insights

    allocation = dashboard.get("asset_allocation") or []
    for item in allocation:
        pct = float(item.get("pct") or 0)
        asset_type = item.get("type", "")
        if pct >= 40:
            insights.append(
                Insight(
                    type=InsightType.CONCENTRATION,
                    severity=InsightSeverity.ALERT,
                    title="자산 집중도 위험",
                    detail=f"{asset_type} 비중이 {pct:.1f}%로 40%를 초과합니다. 분산 투자를 검토하세요.",
                    action_label="자산 현황 보기",
                    action_url="/assets",
                    metric_value=round(pct, 1),
                )
            )
        elif pct >= 30:
            insights.append(
                Insight(
                    type=InsightType.CONCENTRATION,
                    severity=InsightSeverity.WARNING,
                    title="자산 집중도 주의",
                    detail=f"{asset_type} 비중이 {pct:.1f}%로 30%를 초과합니다.",
                    action_label="자산 현황 보기",
                    action_url="/assets",
                    metric_value=round(pct, 1),
                )
            )
    return insights


# ---------------------------------------------------------------------------
# 체커 2: 리밸런싱 기회
# ---------------------------------------------------------------------------


async def _check_rebalancing_opportunity(
    user_id: uuid.UUID,
    db: AsyncSession,
    cache: CacheStoreType = None,
    *,
    on_partial_failure: Callable[[], None] | None = None,
) -> list[Insight]:
    """저장된 포트폴리오 중 드리프트 > 5%인 항목이 있을 때 알림.

    포트폴리오 하나가 실패하면 건너뛰고 `on_partial_failure`를 부른다 — 호출자가 불완전한 목록을 짧게만 캐싱한다.
    """
    from app.models.portfolio import Portfolio
    from app.services.portfolio.portfolio_service import build_portfolio_overview
    from app.services.rebalancing.service import compute_portfolio_drift_summary

    async def _load_portfolios() -> dict[uuid.UUID, Portfolio]:
        result = await db.execute(
            select(Portfolio)
            .where(Portfolio.user_id == user_id)
            .options(
                selectinload(Portfolio.items),
                selectinload(Portfolio.linked_accounts),
            )
        )
        return {p.id: p for p in result.scalars().all()}

    by_id = await _load_portfolios()
    if not by_id:
        return []

    insights: list[Insight] = []
    for pf_id in list(by_id):
        pf = by_id.get(pf_id)
        if pf is None:
            continue
        items = pf.items
        if not items:
            continue

        # 포트폴리오별 계좌 필터 적용 (None이면 전체 계좌)
        raw_ids = pf.account_ids
        account_ids = [uuid.UUID(aid) for aid in raw_ids] if raw_ids else None

        try:
            overview = await build_portfolio_overview(user_id, db, account_ids=account_ids, cache=cache)
        except Exception as e:  # 포트폴리오 단위 실패는 건너뛰고 나머지 계속
            report_handled_failure("insight_portfolio_overview_failed", e, portfolio_id=str(pf_id))
            if on_partial_failure is not None:
                on_partial_failure()
            # aborted 트랜잭션을 되돌리고, rollback이 expire시킨 Portfolio 객체를 다시 읽는다
            try:
                await db.rollback()
                by_id = await _load_portfolios()
            except Exception:
                logger.warning("insight_portfolio_recover_failed", user_id=str(user_id))
                break
            continue

        # 드리프트는 알림·진단과 같은 단일 판정(기준 자산·지수 그룹 합산 포함)으로 구한다 — 예전엔 여기서
        # 티커 단위로 따로 계산해 지수 그룹(VOO+SPY)의 멤버 보유분이 빠져 거짓 "리밸런싱 필요"가 떴다(plans/77 B1)
        max_drift = compute_portfolio_drift_summary(pf, overview).max_drift_pct

        if max_drift >= 10:
            insights.append(
                Insight(
                    type=InsightType.REBALANCING_OPPORTUNITY,
                    severity=InsightSeverity.ALERT,
                    title="리밸런싱 필요",
                    detail=f"포트폴리오 '{pf.name}' 최대 드리프트가 {max_drift:.1f}%p입니다. 리밸런싱이 필요합니다.",
                    action_label="리밸런싱 분석",
                    action_url=f"/rebalancing?rtab=포트폴리오&portfolioId={pf.id}",
                    metric_value=round(max_drift, 1),
                )
            )
        elif max_drift >= 5:
            insights.append(
                Insight(
                    type=InsightType.REBALANCING_OPPORTUNITY,
                    severity=InsightSeverity.WARNING,
                    title="리밸런싱 권장",
                    detail=f"포트폴리오 '{pf.name}' 최대 드리프트가 {max_drift:.1f}%p입니다.",
                    action_label="리밸런싱 분석",
                    action_url=f"/rebalancing?rtab=포트폴리오&portfolioId={pf.id}",
                    metric_value=round(max_drift, 1),
                )
            )

    # ALERT 우선, 없으면 WARNING 1개
    alerts = [i for i in insights if i.severity == InsightSeverity.ALERT]
    return alerts[:1] or insights[:1]


# ---------------------------------------------------------------------------
# 체커 3: Tax-Loss Harvesting
# ---------------------------------------------------------------------------


async def _check_tax_loss_harvest(
    user_id: uuid.UUID,
    db: AsyncSession,
) -> list[Insight]:
    """해외 손실 종목이 있고 과세 이익도 있을 때 절세 기회 알림.

    손실 수확 후보·절세액은 절세 탭·지금 할 일과 같은 `get_tax_summary`의 `harvesting_recommendations`를
    쓴다 — 따로 계산하면 기본공제·손익통산 기준이 달라 화면마다 절세액이 어긋났다(plans/90 C4)."""
    positions = await get_overseas_positions_detail(user_id, db)
    if not any(p["unrealized_pnl_krw"] < 0 for p in positions):
        return []

    summary = await get_tax_summary(user_id, today_kst().year, db, overseas_positions=positions)
    loss_positions = summary.get("harvesting_recommendations", [])
    tax_saved = sum(float(p["tax_saved_krw"]) for p in loss_positions)

    if tax_saved < 50_000:
        return []

    loss_tickers = ", ".join(p["ticker"] for p in loss_positions[:3])
    suffix = f" 외 {len(loss_positions) - 3}개" if len(loss_positions) > 3 else ""

    return [
        Insight(
            type=InsightType.TAX_LOSS_HARVEST,
            severity=InsightSeverity.INFO,
            title="절세 기회: 손실 수확(Tax-Loss Harvesting)",
            detail=(
                f"{loss_tickers}{suffix} 매도 시 최대 {tax_saved:,.0f}원 절세 가능합니다. "
                "세금 상세 페이지에서 확인하세요."
            ),
            action_label="세금 계획 보기",
            action_url="/invest-plan?tab=절세",
            metric_value=round(tax_saved, 0),
        )
    ]
