"""QQQ/SPY 전술 배분 API — 매크로+차트 국면 조회·전략 설정·제안 비중 적용·규칙 백테스트.

자동 주문은 없다. `/apply`는 포트폴리오 목표 비중만 바꾸고, 실제 주문은 기존 리밸런싱 실행 화면에서 한다.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.cache_store import get_cache_store
from app.limiter import limiter
from app.models.portfolio import Portfolio
from app.models.tactical import TacticalStrategy
from app.models.user import User
from app.services import tactical_allocation_service as tactical
from app.services.tactical_tilt import DEFAULT_TILT_SHIFT_PCT, MAX_TILT_SHIFT_PCT
from app.utils.cache_keys import invalidate_rebalancing_analysis_cache, invalidate_user_caches, portfolio_list_key
from app.utils.kst import today_kst

router = APIRouter(prefix="/tactical", tags=["tactical"])
logger = structlog.get_logger()


class TacticalStrategyUpsert(BaseModel):
    notify_enabled: bool = True
    regime_weights: dict[str, dict[str, float]] | None = None  # None이면 기본 비중표
    # 나스닥/S&P 틸트 이동폭(%p) — 0이면 틸트 끔
    tilt_shift_pct: float = Field(DEFAULT_TILT_SHIFT_PCT, ge=0, le=MAX_TILT_SHIFT_PCT)

    @field_validator("regime_weights")
    @classmethod
    def _validate_weights(cls, v: dict[str, dict[str, float]] | None) -> dict[str, dict[str, float]] | None:
        return None if v is None else tactical.validate_regime_weights(v)


async def _portfolio_or_404(portfolio_id: uuid.UUID, user: User, db: AsyncSession) -> Portfolio:
    portfolio = await tactical.get_owned_portfolio(portfolio_id, user.id, db)
    if portfolio is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="포트폴리오를 찾을 수 없습니다")
    return portfolio


async def _status(
    portfolio: Portfolio, strategy: TacticalStrategy | None, db: AsyncSession, *, advance: bool
) -> dict[str, Any]:
    cache = await get_cache_store()
    market = await tactical.evaluate_market(cache, db)
    if advance and strategy is not None:
        today = today_kst()
        regime_changed = tactical.advance_regime(strategy, market, today)
        tilt_changed = tactical.advance_tilt(strategy, market, today)
        if regime_changed or tilt_changed:
            await db.commit()
    return await tactical.build_status(portfolio, strategy, market)


@router.get("/{portfolio_id}")
@limiter.limit("30/minute")
async def get_tactical_status(
    request: Request,
    portfolio_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """현재 국면(관측·확정), 매크로 등급, QQQ/SPY/DIA 차트 지표, 제안 비중과 현재 목표 비중을 반환한다."""
    portfolio = await _portfolio_or_404(portfolio_id, current_user, db)
    strategy = await tactical.get_strategy(portfolio_id, current_user.id, db)
    # 서버가 잠들어 일일 점검 job이 못 돈 날도 앱을 열면 국면 확정이 진행되도록 조회 시에도 갱신한다
    return await _status(portfolio, strategy, db, advance=True)


@router.put("/{portfolio_id}")
@limiter.limit("20/minute")
async def upsert_tactical_strategy(
    request: Request,
    portfolio_id: uuid.UUID,
    body: TacticalStrategyUpsert,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """전략 사용 시작/설정 변경. 최초 생성 시 현재 관측 국면을 바로 확정 국면으로 삼는다(알림 없음)."""
    portfolio = await _portfolio_or_404(portfolio_id, current_user, db)
    strategy = await tactical.get_strategy(portfolio_id, current_user.id, db)
    if strategy is None:
        strategy = TacticalStrategy(user_id=current_user.id, portfolio_id=portfolio_id)
        db.add(strategy)
    strategy.notify_enabled = body.notify_enabled
    strategy.regime_weights = body.regime_weights
    strategy.tilt_shift_pct = Decimal(str(body.tilt_shift_pct))

    cache = await get_cache_store()
    market = await tactical.evaluate_market(cache, db)
    today = today_kst()
    tactical.advance_regime(strategy, market, today)
    tactical.advance_tilt(strategy, market, today)
    if strategy.notified_regime is None:
        strategy.notified_regime = strategy.last_regime  # 사용 시작 시점 국면은 알릴 필요 없음
    await db.commit()
    return await tactical.build_status(portfolio, strategy, market)


@router.delete("/{portfolio_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("20/minute")
async def delete_tactical_strategy(
    request: Request,
    portfolio_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """전략 사용 중지(포트폴리오 목표 비중은 그대로 둔다)."""
    strategy = await tactical.get_strategy(portfolio_id, current_user.id, db)
    if strategy is not None:
        await db.delete(strategy)
        await db.commit()


@router.post("/{portfolio_id}/apply")
@limiter.limit("10/minute")
async def apply_tactical_weights(
    request: Request,
    portfolio_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """확정 국면의 제안 비중을 포트폴리오 목표 비중으로 저장한다 — 주문은 내지 않는다."""
    portfolio = await _portfolio_or_404(portfolio_id, current_user, db)
    strategy = await tactical.get_strategy(portfolio_id, current_user.id, db)
    if strategy is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="전술 배분을 먼저 켜주세요.")
    regime = strategy.last_regime
    if regime not in tactical.REGIMES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="아직 국면이 확정되지 않았습니다. 잠시 후 다시 시도해주세요."
        )

    await tactical.apply_regime_to_portfolio(portfolio, strategy, regime, db)
    strategy.notified_regime = strategy.last_regime  # 이미 반영했으니 같은 국면으로 다시 알릴 필요 없음
    await db.commit()

    cache = await get_cache_store()
    await invalidate_user_caches(cache, portfolio_list_key(current_user.id))
    await invalidate_rebalancing_analysis_cache(cache, current_user.id, portfolio_id)

    db.expire(portfolio)
    refreshed = await _portfolio_or_404(portfolio_id, current_user, db)
    return await _status(refreshed, strategy, db, advance=False)


@router.get("/{portfolio_id}/backtest")
@limiter.limit("6/minute")
async def backtest_tactical_rules(
    request: Request,
    portfolio_id: uuid.UUID,
    years: int = Query(10, ge=3, le=20),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """이 포트폴리오의 국면별 비중표·틸트 이동폭으로 과거 규칙을 재현한 백테스트(SPY·QQQ·DIA 단순보유와 비교)."""
    from app.services.tactical_backtest import run_tactical_backtest

    await _portfolio_or_404(portfolio_id, current_user, db)
    strategy = await tactical.get_strategy(portfolio_id, current_user.id, db)
    try:
        return await run_tactical_backtest(
            tactical.resolve_weights(strategy),
            years,
            await get_cache_store(),
            tilt_shift_pct=tactical.tilt_shift_of(strategy),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
