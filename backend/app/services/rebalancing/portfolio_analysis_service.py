"""리밸런싱 분석 파이프라인 — `GET /rebalancing/portfolios/{id}/analyze`.

overview → 배당 → 과거 수익률 → 현재가 보강 → `analyze_rebalancing` → 진단 컨텍스트 순으로 계산하고,
계좌 범위·예수금 덮어쓰기별로 캐시한다.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, cast

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import is_non_tradable
from app.models.portfolio import Portfolio
from app.schemas.rebalancing import RebalancingAnalysis
from app.schemas.service_dtypes import DividendMapEntry, ReturnsMapEntry
from app.services._settings_queries import get_settings_row
from app.services.dividend.orchestrator import get_ticker_dividend_summary
from app.services.market_data.price_service import get_historical_returns
from app.services.portfolio.portfolio_service import build_portfolio_overview
from app.services.rebalancing.diagnosis_service import build_diagnosis_context
from app.services.rebalancing.overview_enrichment import collect_dividend_map, enrich_overview_with_prices
from app.services.rebalancing.service import _item_attr, analyze_rebalancing
from app.utils.cache_keys import (
    TTL_REBALANCING_ANALYSIS,
    get_cached_json,
    portfolio_overview_acct_suffix,
    rebalancing_analysis_key,
    set_cached_json,
)

logger = structlog.get_logger()


def _with_deposit_override(overview: dict, deposit_krw_override: float) -> dict:
    """예수금을 사용자가 입력한 값으로 바꾸고 총자산도 그 차이만큼 맞춘다."""
    delta = deposit_krw_override - float(overview.get("total_deposit_krw") or 0)
    return {
        **overview,
        "total_deposit_krw": deposit_krw_override,
        "total_assets_krw": float(overview.get("total_assets_krw", 0)) + delta,
    }


async def analyze_portfolio_rebalancing(
    db: AsyncSession,
    cache: Any,
    user_id: uuid.UUID,
    portfolio: Portfolio,
    account_ids: list[uuid.UUID] | None,
    deposit_krw_override: float | None,
) -> RebalancingAnalysis:
    """현재 자산과 목표 포트폴리오를 비교한 리밸런싱 제안. account_ids가 None이면 포트폴리오 연동 계좌 기준.

    `portfolio.items`·`portfolio.linked_accounts`가 로드돼 있어야 한다.
    """
    portfolio_acct_ids = [uuid.UUID(aid) for aid in portfolio.account_ids] if portfolio.account_ids else None
    effective_ids = account_ids if account_ids is not None else portfolio_acct_ids

    cache_key = rebalancing_analysis_key(
        user_id, portfolio.id, portfolio_overview_acct_suffix(effective_ids), deposit_krw_override
    )
    cached = await get_cached_json(cache, cache_key)
    if cached is not None:
        return RebalancingAnalysis.model_validate(cached)

    # 같은 AsyncSession을 쓰는 호출은 동시 실행 불가(SQLAlchemy) — 순차 실행한다.
    overview = await build_portfolio_overview(user_id, db, account_ids=effective_ids, cache=cache)
    base_dividend_items = await get_ticker_dividend_summary(user_id, db, account_ids=effective_ids)
    base_dividend_map = {(item["ticker"], item["market"]): item for item in base_dividend_items if item.get("ticker")}

    target_tickers = [
        (str(_item_attr(raw_item, "ticker")), str(_item_attr(raw_item, "market")))
        for raw_item in portfolio.items
        if not is_non_tradable(str(_item_attr(raw_item, "ticker")), str(_item_attr(raw_item, "market")))
    ]
    current_tickers = [
        (p["ticker"], p["market"])
        for p in overview.get("all_positions", [])
        if p.get("ticker") and p.get("ticker") != "CASH"
    ]

    # 과거 수익률은 세션을 쓰지 않으니 병렬로 돌리고, 세션을 쓰는 두 호출은 순차 실행한다.
    returns_task = asyncio.create_task(
        get_historical_returns(list(set(target_tickers) | set(current_tickers)), cache=cache)
    )
    try:
        dividend_map = await collect_dividend_map(user_id, db, cache, portfolio, base_dividend_map)
        overview = await enrich_overview_with_prices(portfolio, overview, user_id, db, cache)
    except BaseException:
        returns_task.cancel()
        raise
    returns_map = await returns_task

    if deposit_krw_override is not None:
        overview = _with_deposit_override(overview, deposit_krw_override)

    # 알림·대기 계획·진단 요약과 같은 분석 기준 — TOTAL_ASSETS면 목표 밖 예수금도 이탈 항목으로 본다(plans/63 P1-3)
    analysis = analyze_rebalancing(
        portfolio,
        overview,
        cast(dict[tuple[str, str], DividendMapEntry], dividend_map),
        cast(dict[tuple[str, str], ReturnsMapEntry], returns_map),
        include_implicit_cash=True,
    )

    try:
        settings_row = await get_settings_row(db, user_id)
        enable_composite_signals = settings_row.composite_signal_alerts_enabled if settings_row else True
        analysis.diagnosis_context = await build_diagnosis_context(
            user_id,
            db,
            cache,
            analysis,
            overview,
            enable_composite_signals=enable_composite_signals,
            settings_row=settings_row,
        )
    except Exception as e:
        logger.warning("diagnosis_context_build_failed", portfolio_id=str(portfolio.id), error=str(e))
        analysis.diagnosis_context = None

    await set_cached_json(cache, cache_key, analysis.model_dump(mode="json"), TTL_REBALANCING_ANALYSIS)
    return analysis
