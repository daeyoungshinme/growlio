"""리밸런싱 분석 및 브로커 잔고 API."""

import asyncio
import uuid
from typing import cast

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db
from app.core.cache_store import get_cache_store
from app.limiter import limiter
from app.models.portfolio import Portfolio
from app.models.user import User
from app.schemas.rebalancing import (
    CandidateOverlapResponse,
    CompositeSignalStatus,
    GoalRecommendation,
    HorizonRecommendationResponse,
    KisBalanceResponse,
    PortfolioDriftSummary,
    PortfolioExpectedMetrics,
    RebalancingAnalysis,
)
from app.schemas.rebalancing.goal import CandidateOverlapRequest
from app.schemas.service_dtypes import DividendMapEntry, ReturnsMapEntry
from app.services._account_queries import active_broker_accounts_stmt, get_account_including_inactive
from app.services._settings_queries import get_or_create_settings, get_settings_row
from app.services.dividend.orchestrator import get_ticker_dividend_summary
from app.services.etf_overlap_service import analyze_candidate_overlap_for_user
from app.services.goal_age_recommendation_service import get_age_based_recommendation
from app.services.goal_candidate_service import existing_items_from_positions
from app.services.goal_horizon_recommendation_service import get_horizon_recommendations
from app.services.goal_recommendation_service import (
    compute_portfolio_expected_metrics,
    get_goal_recommendation,
)
from app.services.portfolio_service import build_portfolio_overview
from app.services.position_aggregator import query_latest_position_map
from app.services.price_service import get_historical_returns
from app.services.rebalancing.broker_balance_service import fetch_broker_balance
from app.services.rebalancing.diagnosis_service import (
    build_diagnosis_context,
    check_composite_signal,
    fetch_market_and_risk_signal,
)
from app.services.rebalancing.drift_summary_service import get_drift_summaries
from app.services.rebalancing.overview_enrichment import collect_dividend_map, enrich_overview_with_prices
from app.services.rebalancing.service import (
    _item_attr,
    analyze_rebalancing,
)
from app.utils.cache_keys import (
    TTL_REBALANCING_ANALYSIS,
    get_cached_json,
    portfolio_overview_acct_suffix,
    rebalancing_analysis_key,
    set_cached_json,
)

router = APIRouter(prefix="/rebalancing", tags=["rebalancing"])
logger = structlog.get_logger()


@router.get("/portfolios/{portfolio_id}/analyze", response_model=RebalancingAnalysis)
@limiter.limit("5/minute")
async def analyze_portfolio(
    request: Request,
    portfolio_id: uuid.UUID,
    account_ids: list[uuid.UUID] | None = Query(default=None),
    deposit_krw_override: float | None = Query(default=None, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    cache=Depends(get_cache_store),
):
    """현재 자산과 목표 포트폴리오를 비교해 리밸런싱 제안을 반환한다."""
    portfolio = await db.scalar(
        select(Portfolio)
        .options(
            selectinload(Portfolio.linked_accounts),
            selectinload(Portfolio.items),
        )
        .where(
            Portfolio.id == portfolio_id,
            Portfolio.user_id == current_user.id,
        )
    )
    if not portfolio:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="포트폴리오를 찾을 수 없습니다")

    portfolio_acct_ids = [uuid.UUID(aid) for aid in portfolio.account_ids] if portfolio.account_ids else None
    effective_ids = account_ids if account_ids is not None else portfolio_acct_ids

    cache_key = rebalancing_analysis_key(
        current_user.id, portfolio_id, portfolio_overview_acct_suffix(effective_ids), deposit_krw_override
    )
    cached = await get_cached_json(cache, cache_key)
    if cached is not None:
        return RebalancingAnalysis.model_validate(cached)

    overview, base_dividend_items = await asyncio.gather(
        build_portfolio_overview(current_user.id, db, account_ids=effective_ids, cache=cache),
        get_ticker_dividend_summary(current_user.id, db, account_ids=effective_ids),
    )
    base_dividend_map = {(item["ticker"], item["market"]): item for item in base_dividend_items if item.get("ticker")}

    target_tickers = [
        (str(_item_attr(raw_item, "ticker")), str(_item_attr(raw_item, "market")))
        for raw_item in portfolio.items
        if str(_item_attr(raw_item, "ticker")) != "CASH" and str(_item_attr(raw_item, "market")) != "KR_PROPERTY"
    ]
    current_tickers = [
        (p["ticker"], p["market"])
        for p in overview.get("all_positions", [])
        if p.get("ticker") and p.get("ticker") != "CASH"
    ]

    dividend_map, returns_map, overview = await asyncio.gather(
        collect_dividend_map(current_user.id, db, cache, portfolio, base_dividend_map),
        get_historical_returns(list(set(target_tickers) | set(current_tickers)), cache=cache),
        enrich_overview_with_prices(portfolio, overview, current_user.id, db, cache),
    )

    if deposit_krw_override is not None:
        old_deposit = float(overview.get("total_deposit_krw") or 0)
        delta = deposit_krw_override - old_deposit
        overview = {
            **overview,
            "total_deposit_krw": deposit_krw_override,
            "total_assets_krw": float(overview.get("total_assets_krw", 0)) + delta,
        }

    analysis = analyze_rebalancing(
        portfolio,
        overview,
        cast(dict[tuple[str, str], DividendMapEntry], dividend_map),
        cast(dict[tuple[str, str], ReturnsMapEntry], returns_map),
    )

    try:
        settings_row = await get_settings_row(db, current_user.id)
        enable_composite_signals = settings_row.composite_signal_alerts_enabled if settings_row else True
        analysis.diagnosis_context = await build_diagnosis_context(
            current_user.id,
            db,
            cache,
            analysis,
            overview,
            enable_composite_signals=enable_composite_signals,
            settings_row=settings_row,
        )
    except Exception as e:
        logger.warning("diagnosis_context_build_failed", portfolio_id=str(portfolio_id), error=str(e))
        analysis.diagnosis_context = None

    await set_cached_json(cache, cache_key, analysis.model_dump(mode="json"), TTL_REBALANCING_ANALYSIS)
    return analysis


@router.get("/goal-recommendation", response_model=GoalRecommendation)
@limiter.limit("5/minute")
async def get_overall_goal_recommendation_endpoint(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    cache=Depends(get_cache_store),
):
    """전체 계좌(전체 투자현황) 기준으로 목표 역산 추천을 반환한다 (자동 적용 아님)."""
    overview = await build_portfolio_overview(current_user.id, db, cache=cache)
    settings_row = await get_settings_row(db, current_user.id)

    # 부동산은 목표 역산 추천 MVO 엔진의 후보에 포함되지 않으므로(성장 미모델링) 필요
    # 수익률 역산의 원금(base_krw)에서 제외 — 그렇지 않으면 부동산 추가만으로 필요
    # 수익률이 부당하게 낮아지거나 "이미 달성"으로 잘못 판정된다.
    real_estate_krw = next(
        (item["amount_krw"] for item in overview.get("asset_type_allocation", []) if item.get("type") == "REAL_ESTATE"),
        0.0,
    )
    base_krw = float(overview.get("total_assets_krw", 0)) - real_estate_krw
    pos_map = await query_latest_position_map(current_user.id, db, include_name=True)
    existing_items = existing_items_from_positions(pos_map)
    return await get_goal_recommendation(cache, base_krw, existing_items, settings_row, db)


@router.get("/goal-recommendation/by-horizon", response_model=HorizonRecommendationResponse)
@limiter.limit("5/minute")
async def get_horizon_goal_recommendation_endpoint(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    cache=Depends(get_cache_store),
):
    """계좌에 태그된 투자기간(단기/중기/장기)별로 리스크 성향이 다른 추천을 반환한다 (자동 적용 아님).

    목표금액/목표연도 설정과 무관하게 동작한다 — `/goal-recommendation`(전체 자산 기준 목표 역산)과는
    별개의 기능이며, 두 엔드포인트 모두 그대로 유지된다.
    """
    settings_row = await get_or_create_settings(db, current_user.id)
    return await get_horizon_recommendations(cache, db, current_user.id, settings_row)


@router.get("/goal-recommendation/by-age", response_model=GoalRecommendation)
@limiter.limit("5/minute")
async def get_age_based_goal_recommendation_endpoint(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    cache=Depends(get_cache_store),
):
    """사용자가 직접 선택한 연령대에 맞는 리스크 성향 + 주식비중으로 추천을 반환한다
    (자동 적용 아님). `UserSettings.age_group` 미설정 시 `is_configured=False`로 안내 문구만 반환한다.

    목표금액/목표연도 역산은 하지 않는다 — `/goal-recommendation/by-horizon`과 동일하게 나이
    구간에서 유도한 리스크 성향/주식비중 상하한만으로 결과를 결정한다.
    """
    settings_row = await get_or_create_settings(db, current_user.id)
    return await get_age_based_recommendation(cache, db, current_user.id, settings_row)


@router.post("/candidates/overlap", response_model=CandidateOverlapResponse)
@limiter.limit("10/minute")
async def analyze_candidate_overlap_endpoint(
    request: Request,
    body: CandidateOverlapRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    cache=Depends(get_cache_store),
):
    """후보 ETF ↔ 보유 종목·다른 후보 간 중복(같은 지수/사실상 같은 움직임)과 총보수를 비교한다.

    정보 제공 전용 — 후보 목록·추천 비중을 바꾸지 않는다. `candidates`를 생략하면 저장된 후보 목록을,
    후보 관리 모달은 저장 전 편집 중 목록을 보낸다. 후보를 한 번도 등록하지 않았으면(시딩 전) 빈 결과.
    """
    draft = (
        [c.model_dump(mode="json", exclude_none=True) for c in body.candidates] if body.candidates is not None else None
    )
    return await analyze_candidate_overlap_for_user(cache, db, current_user.id, draft)


@router.get("/portfolios/{portfolio_id}/expected-metrics", response_model=PortfolioExpectedMetrics)
@limiter.limit("10/minute")
async def get_portfolio_expected_metrics_endpoint(
    request: Request,
    portfolio_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    cache=Depends(get_cache_store),
):
    """포트폴리오의 현재 목표 비중에 대한 기대수익률/배당수익률/변동성 — "추천 비중 적용 전
    비교 미리보기"에서 추천 비중의 같은 지표와 나란히 보여주기 위한 온디맨드 조회(캐싱 없음,
    확인 모달을 열 때만 호출)."""
    portfolio = await db.scalar(
        select(Portfolio)
        .options(selectinload(Portfolio.items))
        .where(Portfolio.id == portfolio_id, Portfolio.user_id == current_user.id)
    )
    if not portfolio:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="포트폴리오를 찾을 수 없습니다")

    items = [
        (
            str(_item_attr(i, "ticker")),
            str(_item_attr(i, "market")),
            str(_item_attr(i, "name")),
            float(_item_attr(i, "weight")),
        )
        for i in portfolio.items
        if str(_item_attr(i, "ticker")) not in ("CASH",) and str(_item_attr(i, "market")) != "KR_PROPERTY"
    ]

    settings_row = await get_settings_row(db, current_user.id)
    cagr_lookback_years = int(getattr(settings_row, "goal_cagr_lookback_years", None) or 10)

    return await compute_portfolio_expected_metrics(cache, items, cagr_lookback_years=cagr_lookback_years)


@router.get("/broker-balance/{account_id}", response_model=KisBalanceResponse)
@limiter.limit("10/minute")
async def get_broker_account_balance(
    request: Request,
    account_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    cache=Depends(get_cache_store),
):
    """KIS/키움/토스 계좌의 실시간 보유 종목 잔고를 조회한다 (비활성 계좌 포함)."""
    account = await get_account_including_inactive(db, account_id, current_user.id)
    if not account:
        logger.warning(
            "broker_balance_account_not_found",
            account_id=str(account_id),
            user_id=str(current_user.id),
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="계좌를 찾을 수 없습니다")
    if account.asset_type not in ("STOCK_KIS", "STOCK_KIWOOM", "STOCK_TOSS"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="KIS/키움/토스 계좌만 잔고 조회가 가능합니다",
        )

    await db.commit()  # 브로커 조회(느린 외부 HTTP 호출) 전 요청 DB 커넥션 풀 슬롯을 미리 반환
    try:
        return await fetch_broker_balance(account, cache)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/broker-balance-all", response_model=list[KisBalanceResponse])
@limiter.limit("5/minute")
async def get_all_broker_balances(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    cache=Depends(get_cache_store),
):
    """연동된 모든 활성 KIS/키움/토스 계좌의 실시간 잔고를 병렬로 조회한다."""
    acc_result = await db.execute(active_broker_accounts_stmt(current_user.id))
    accounts = acc_result.scalars().all()

    if not accounts:
        return []

    await db.commit()  # 브로커 조회(느린 외부 HTTP 호출) 전 요청 DB 커넥션 풀 슬롯을 미리 반환
    tasks = [fetch_broker_balance(acc, cache) for acc in accounts]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    return [
        r
        if not isinstance(r, Exception)
        else KisBalanceResponse(
            account_id=str(acc.id),
            account_name=acc.name,
            is_mock=acc.is_mock_mode,
            positions=[],
            deposit_krw=0.0,
            error=str(r),
        )
        for acc, r in zip(accounts, results, strict=False)
    ]


@router.get("/drift-summary", response_model=list[PortfolioDriftSummary])
@limiter.limit("10/minute")
async def get_drift_summary(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    cache=Depends(get_cache_store),
):
    """모든 포트폴리오의 비중 이탈 현황을 빠르게 반환한다 (배당·수익률 외부 API 미사용)."""
    return await get_drift_summaries(current_user.id, db, cache)


@router.get("/composite-signal", response_model=CompositeSignalStatus)
@limiter.limit("30/minute")
async def get_composite_signal_status(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    cache=Depends(get_cache_store),
):
    """진단탭 상단 배너 전용 — 포트폴리오 컨텍스트 없이 유저 단위 복합신호(시장/리스크) 상태만 반환."""
    settings_row = await get_settings_row(db, current_user.id)
    enabled = settings_row.composite_signal_alerts_enabled if settings_row else True

    triggered = False
    reason: str | None = None
    if enabled:
        try:
            market_level, risk = await fetch_market_and_risk_signal(current_user.id, db, cache)
            triggered, reason = check_composite_signal(
                market_level,
                bool(risk.get("data_available")),
                risk.get("diversification_score"),
                risk.get("top_holding_weight_pct"),
                risk.get("annualized_volatility_pct"),
            )
        except Exception as e:
            logger.warning("composite_signal_status_failed", error=str(e))

    return CompositeSignalStatus(enabled=enabled, triggered=triggered, reason=reason)
