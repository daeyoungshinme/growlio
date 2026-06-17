"""규칙 기반 포트폴리오 인사이트 & 진단 서비스."""
from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from dataclasses import asdict, dataclass
from enum import StrEnum

import structlog
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.services.asset_aggregator import get_dashboard_summary
from app.services.tax_service import (
    _get_rates,
    get_overseas_positions_detail,
)
from app.utils.cache_keys import RedisType

logger = structlog.get_logger()

TTL_INSIGHTS = 3600  # 1시간


def insights_key(user_id: uuid.UUID) -> str:
    return f"insights:{user_id}"


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
    redis: RedisType = None,
    force_refresh: bool = False,
) -> list[dict]:
    """모든 체커를 병렬 실행하고 인사이트 목록을 반환한다 (Redis 1h 캐시)."""
    if redis and not force_refresh:
        with contextlib.suppress(RedisError):
            cached = await redis.get(insights_key(user_id))
            if cached:
                return json.loads(cached)

    try:
        dashboard = await get_dashboard_summary(user_id, db, redis)
    except Exception:
        dashboard = {}

    results = await asyncio.gather(
        _check_concentration(dashboard),
        _check_rebalancing_opportunity(user_id, db),
        _check_tax_loss_harvest(user_id, db),
        return_exceptions=True,
    )

    insights: list[Insight] = []
    for res in results:
        if isinstance(res, BaseException):
            logger.warning("insight_checker_failed", error=str(res))
        elif isinstance(res, list):
            insights.extend(res)

    # 심각도 순 정렬: ALERT → WARNING → INFO
    _severity_order = {InsightSeverity.ALERT: 0, InsightSeverity.WARNING: 1, InsightSeverity.INFO: 2}
    insights.sort(key=lambda i: _severity_order.get(InsightSeverity(i.severity), 9))

    data = [asdict(i) for i in insights]

    if redis:
        with contextlib.suppress(RedisError):
            await redis.setex(insights_key(user_id), TTL_INSIGHTS, json.dumps(data))

    return data


async def get_insights_summary(
    user_id: uuid.UUID,
    db: AsyncSession,
    redis: RedisType = None,
) -> dict[str, int]:
    """심각도별 인사이트 개수 (대시보드 뱃지용)."""
    insights = await generate_insights(user_id, db, redis)
    summary: dict[str, int] = {
        InsightSeverity.ALERT: 0,
        InsightSeverity.WARNING: 0,
        InsightSeverity.INFO: 0,
    }
    for i in insights:
        sev = i.get("severity", InsightSeverity.INFO)
        if sev in summary:
            summary[sev] += 1
    return summary


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
            insights.append(Insight(
                type=InsightType.CONCENTRATION,
                severity=InsightSeverity.ALERT,
                title="자산 집중도 위험",
                detail=f"{asset_type} 비중이 {pct:.1f}%로 40%를 초과합니다. 분산 투자를 검토하세요.",
                action_label="자산 현황 보기",
                action_url="/assets",
                metric_value=round(pct, 1),
            ))
        elif pct >= 30:
            insights.append(Insight(
                type=InsightType.CONCENTRATION,
                severity=InsightSeverity.WARNING,
                title="자산 집중도 주의",
                detail=f"{asset_type} 비중이 {pct:.1f}%로 30%를 초과합니다.",
                action_label="자산 현황 보기",
                action_url="/assets",
                metric_value=round(pct, 1),
            ))
    return insights


# ---------------------------------------------------------------------------
# 체커 2: 리밸런싱 기회
# ---------------------------------------------------------------------------

async def _check_rebalancing_opportunity(
    user_id: uuid.UUID,
    db: AsyncSession,
) -> list[Insight]:
    """저장된 포트폴리오 중 드리프트 > 5%인 항목이 있을 때 알림."""
    from app.models.portfolio import Portfolio
    from app.services.portfolio_service import build_portfolio_overview

    result = await db.execute(
        select(Portfolio)
        .where(Portfolio.user_id == user_id)
        .options(
            selectinload(Portfolio.items),
            selectinload(Portfolio.linked_accounts),
        )
    )
    portfolios = result.scalars().all()
    if not portfolios:
        return []

    insights: list[Insight] = []
    for pf in portfolios:
        items = pf.items
        if not items:
            continue

        # 포트폴리오별 계좌 필터 적용 (None이면 전체 계좌)
        raw_ids = pf.account_ids
        account_ids = [uuid.UUID(aid) for aid in raw_ids] if raw_ids else None

        try:
            overview = await build_portfolio_overview(user_id, db, account_ids=account_ids)
        except Exception:
            continue

        # base_type에 따라 드리프트 분모 결정
        if pf.base_type == "TOTAL_ASSETS":
            base_krw = float(overview.get("total_assets_krw") or 0)
        else:  # STOCK_ONLY (기본값)
            base_krw = float(overview.get("total_stock_krw") or 0)

        if base_krw <= 0:
            continue

        all_positions = overview.get("all_positions", [])
        pos_map: dict[tuple[str, str], float] = {}
        for p in all_positions:
            key = (p.get("ticker", ""), p.get("market", ""))
            pos_map[key] = pos_map.get(key, 0) + float(p.get("value_krw", 0))

        max_drift = 0.0
        for item in items:
            target_w = float(item.weight)
            cur_val = pos_map.get((item.ticker, item.market), 0.0)
            cur_w = cur_val / base_krw * 100
            max_drift = max(max_drift, abs(target_w - cur_w))

        if max_drift >= 10:
            insights.append(Insight(
                type=InsightType.REBALANCING_OPPORTUNITY,
                severity=InsightSeverity.ALERT,
                title="리밸런싱 필요",
                detail=f"포트폴리오 '{pf.name}' 최대 드리프트가 {max_drift:.1f}%p입니다. 리밸런싱이 필요합니다.",
                action_label="리밸런싱 분석",
                action_url=f"/portfolio?tab=포트폴리오 분석&portfolioId={pf.id}",
                metric_value=round(max_drift, 1),
            ))
        elif max_drift >= 5:
            insights.append(Insight(
                type=InsightType.REBALANCING_OPPORTUNITY,
                severity=InsightSeverity.WARNING,
                title="리밸런싱 권장",
                detail=f"포트폴리오 '{pf.name}' 최대 드리프트가 {max_drift:.1f}%p입니다.",
                action_label="리밸런싱 분석",
                action_url=f"/portfolio?tab=포트폴리오 분석&portfolioId={pf.id}",
                metric_value=round(max_drift, 1),
            ))

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
    """해외 손실 종목이 있고 과세 이익도 있을 때 절세 기회 알림."""
    positions = await get_overseas_positions_detail(user_id, db)
    if not positions:
        return []

    total_gain = sum(p["unrealized_pnl_krw"] for p in positions if p["unrealized_pnl_krw"] > 0)
    loss_positions = [p for p in positions if p["unrealized_pnl_krw"] < 0]

    if not loss_positions or total_gain <= 0:
        return []

    from datetime import date
    rates = _get_rates(date.today().year)

    # 연 250만원 기본 공제 적용 — 공제 후 과세 이익이 없으면 절세 불필요
    taxable_gain = max(0.0, total_gain - rates["overseas_deduction"])
    if taxable_gain <= 0:
        return []

    # 절세액 큰 순(손실 큰 순)으로 정렬
    loss_positions.sort(key=lambda p: p["unrealized_pnl_krw"])

    total_loss = sum(abs(p["unrealized_pnl_krw"]) for p in loss_positions)
    offsettable = min(total_loss, taxable_gain)
    tax_saved = offsettable * rates["overseas_gain"]

    if tax_saved < 50_000:
        return []

    loss_tickers = ", ".join(p["ticker"] for p in loss_positions[:3])
    suffix = f" 외 {len(loss_positions) - 3}개" if len(loss_positions) > 3 else ""

    return [Insight(
        type=InsightType.TAX_LOSS_HARVEST,
        severity=InsightSeverity.INFO,
        title="절세 기회: 손실 수확(Tax-Loss Harvesting)",
        detail=(
            f"{loss_tickers}{suffix} 매도 시 최대 {tax_saved:,.0f}원 절세 가능합니다. "
            "세금 상세 페이지에서 확인하세요."
        ),
        action_label="세금 계획 보기",
        action_url="/portfolio?tab=analysis",
        metric_value=round(tax_saved, 0),
    )]


# ---------------------------------------------------------------------------
# 캐시 무효화 헬퍼
# ---------------------------------------------------------------------------

async def invalidate_insights_cache(user_id: uuid.UUID, redis: RedisType) -> None:
    if redis is None:
        return
    with contextlib.suppress(RedisError):
        await redis.delete(insights_key(user_id))
