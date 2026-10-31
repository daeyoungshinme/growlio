"""리밸런싱 분석 및 브로커 잔고 API."""

import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db, get_owned_or_404
from app.constants import BROKER_API_ASSET_TYPES, is_non_tradable
from app.core.cache_store import get_cache_store
from app.core.logging import public_error_message
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
from app.services._settings_queries import get_or_create_settings, get_settings_row
from app.services.accounts._account_queries import active_broker_accounts_stmt, get_account_including_inactive
from app.services.etf.etf_overlap_service import analyze_candidate_overlap_for_user
from app.services.goal._goal_recommendation_common import _cagr_lookback_years_from_settings
from app.services.goal.goal_age_recommendation_service import (
    get_age_based_recommendation,
    get_cached_age_based_recommendation,
    get_stale_age_based_recommendation,
    refresh_age_based_recommendation_in_background,
)
from app.services.goal.goal_horizon_recommendation_service import (
    get_cached_horizon_recommendations,
    get_horizon_recommendations,
    get_stale_horizon_recommendations,
    refresh_horizon_recommendations_in_background,
)
from app.services.goal.goal_recommendation_service import (
    compute_portfolio_expected_metrics,
    get_cached_goal_recommendation,
    get_overall_goal_recommendation_for_user,
    get_stale_goal_recommendation,
    refresh_goal_recommendation_in_background,
)
from app.services.rebalancing.broker_balance_service import fetch_broker_balance
from app.services.rebalancing.diagnosis_service import (
    fetch_composite_signal,
)
from app.services.rebalancing.drift_summary_service import get_drift_summaries
from app.services.rebalancing.portfolio_analysis_service import analyze_portfolio_rebalancing
from app.services.rebalancing.service import (
    _item_attr,
)
from app.utils.cache_keys import (
    get_goal_recommendation_generation,
)

router = APIRouter(prefix="/rebalancing", tags=["rebalancing"])
logger = structlog.get_logger()


@router.get("/portfolios/{portfolio_id}/analyze", response_model=RebalancingAnalysis)
@limiter.limit("5/minute")
async def analyze_portfolio(
    request: Request,
    portfolio_id: uuid.UUID,
    account_ids: list[uuid.UUID] | None = Query(default=None, max_length=50),
    deposit_krw_override: float | None = Query(default=None, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    cache=Depends(get_cache_store),
):
    """현재 자산과 목표 포트폴리오를 비교해 리밸런싱 제안을 반환한다."""
    portfolio = await get_owned_or_404(
        db,
        Portfolio,
        portfolio_id,
        current_user.id,
        "포트폴리오를 찾을 수 없습니다",
        options=(selectinload(Portfolio.linked_accounts), selectinload(Portfolio.items)),
    )
    return await analyze_portfolio_rebalancing(db, cache, current_user.id, portfolio, account_ids, deposit_krw_override)


async def _serve_recommendation[R](
    background_tasks: BackgroundTasks,
    user_id: uuid.UUID,
    cache: Any,
    get_cached: Callable[[Any, uuid.UUID, str], Awaitable[R | None]],
    get_stale: Callable[[Any, uuid.UUID, str], Awaitable[R | None]],
    refresh_in_background: Callable[[uuid.UUID, Any], Awaitable[None]],
    compute: Callable[[str], Awaitable[R]],
) -> R:
    """추천 3종 공통: 캐시 → (만료됐으면) 마지막 정상 결과 + 응답 뒤 재계산 → 계산.

    캐시 세대는 설정을 읽기 전에 잡는다 — 계산 중 설정이 저장되면 결과가 옛 세대 키로만 가게(plans/88).
    1시간 키가 만료됐어도 마지막 정상 결과가 있으면 바로 돌려준다(plans/66·90 C6).
    """
    gen = await get_goal_recommendation_generation(cache, user_id)
    cached = await get_cached(cache, user_id, gen)
    if cached is not None:
        return cached
    stale = await get_stale(cache, user_id, gen)
    if stale is not None:
        background_tasks.add_task(refresh_in_background, user_id, cache)
        return stale
    return await compute(gen)


@router.get("/goal-recommendation", response_model=GoalRecommendation)
@limiter.limit("5/minute")
async def get_overall_goal_recommendation_endpoint(
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    cache=Depends(get_cache_store),
):
    """전체 계좌(전체 투자현황) 기준으로 목표 역산 추천을 반환한다 (자동 적용 아님)."""
    started = time.perf_counter()

    async def compute(gen: str):
        # 캐시 히트면 이 계산(overview·포지션 조회)을 건너뛴다
        result = await get_overall_goal_recommendation_for_user(current_user.id, db, cache, gen)
        logger.info("goal_recommendation_cold_request", total_ms=round((time.perf_counter() - started) * 1000))
        return result

    return await _serve_recommendation(
        background_tasks,
        current_user.id,
        cache,
        get_cached_goal_recommendation,
        get_stale_goal_recommendation,
        refresh_goal_recommendation_in_background,
        compute,
    )


@router.get("/goal-recommendation/by-horizon", response_model=HorizonRecommendationResponse)
@limiter.limit("5/minute")
async def get_horizon_goal_recommendation_endpoint(
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    cache=Depends(get_cache_store),
):
    """계좌에 태그된 투자기간(단기/중기/장기)별로 리스크 성향이 다른 추천을 반환한다 (자동 적용 아님).

    목표금액/목표연도 설정과 무관하게 동작한다 — `/goal-recommendation`(전체 자산 기준 목표 역산)과는
    별개의 기능이며, 두 엔드포인트 모두 그대로 유지된다.
    """

    async def compute(gen: str):
        settings_row = await get_or_create_settings(db, current_user.id)
        return await get_horizon_recommendations(cache, db, current_user.id, settings_row, gen=gen)

    return await _serve_recommendation(
        background_tasks,
        current_user.id,
        cache,
        get_cached_horizon_recommendations,
        get_stale_horizon_recommendations,
        refresh_horizon_recommendations_in_background,
        compute,
    )


@router.get("/goal-recommendation/by-age", response_model=GoalRecommendation)
@limiter.limit("5/minute")
async def get_age_based_goal_recommendation_endpoint(
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    cache=Depends(get_cache_store),
):
    """사용자가 직접 선택한 연령대에 맞는 리스크 성향 + 주식비중으로 추천을 반환한다
    (자동 적용 아님). `UserSettings.age_group` 미설정 시 `is_configured=False`로 안내 문구만 반환한다.

    목표금액/목표연도 역산은 하지 않는다 — `/goal-recommendation/by-horizon`과 동일하게 나이
    구간에서 유도한 리스크 성향/주식비중 상하한만으로 결과를 결정한다.
    """

    async def compute(gen: str):
        settings_row = await get_or_create_settings(db, current_user.id)
        return await get_age_based_recommendation(cache, db, current_user.id, settings_row, gen=gen)

    return await _serve_recommendation(
        background_tasks,
        current_user.id,
        cache,
        get_cached_age_based_recommendation,
        get_stale_age_based_recommendation,
        refresh_age_based_recommendation_in_background,
        compute,
    )


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
    portfolio = await get_owned_or_404(
        db,
        Portfolio,
        portfolio_id,
        current_user.id,
        "포트폴리오를 찾을 수 없습니다",
        options=(selectinload(Portfolio.items),),
    )

    items = [
        (
            str(_item_attr(i, "ticker")),
            str(_item_attr(i, "market")),
            str(_item_attr(i, "name")),
            float(_item_attr(i, "weight")),
        )
        for i in portfolio.items
        if not is_non_tradable(str(_item_attr(i, "ticker")), str(_item_attr(i, "market")))
    ]

    settings_row = await get_settings_row(db, current_user.id)
    cagr_lookback_years = _cagr_lookback_years_from_settings(settings_row)

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
    if account.asset_type not in BROKER_API_ASSET_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="KIS/키움/토스 계좌만 잔고 조회가 가능합니다",
        )

    await db.commit()  # 브로커 조회(느린 외부 HTTP 호출) 전 요청 DB 커넥션 풀 슬롯을 미리 반환
    try:
        return await fetch_broker_balance(account, cache)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=public_error_message(e)) from e


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
            error=public_error_message(r),
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
            triggered, reason = await fetch_composite_signal(current_user.id, db, cache)
        except Exception as e:
            logger.warning("composite_signal_status_failed", error=str(e))

    return CompositeSignalStatus(enabled=enabled, triggered=triggered, reason=reason)
