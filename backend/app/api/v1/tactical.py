"""나스닥100/S&P500 전술 배분 API — 매크로+차트 국면 조회·전략 설정·제안 비중 적용·규칙 백테스트.

자동 주문은 없다. `/apply`는 포트폴리오 목표 비중만 바꾸고, 실제 주문은 기존 리밸런싱 실행 화면에서 한다.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.cache_store import CacheStore, get_cache_store
from app.limiter import limiter
from app.models.alert import RebalancingAlert
from app.models.portfolio import Portfolio, PortfolioAccount
from app.models.tactical import TacticalStrategy
from app.models.user import User
from app.schemas.portfolio import IndexGroupSuggestion
from app.schemas.tactical import TacticalApplyRequest, TacticalStrategyUpsert
from app.services import tactical_allocation_service as tactical
from app.utils.cache_keys import invalidate_rebalancing_analysis_cache, invalidate_user_caches, portfolio_list_key
from app.utils.kst import today_kst

router = APIRouter(prefix="/tactical", tags=["tactical"])
logger = structlog.get_logger()


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
        dip_changed = tactical.advance_dip(strategy, market)
        if regime_changed or tilt_changed or dip_changed:
            await db.commit()
    return await tactical.build_status(portfolio, strategy, market)


@router.get("")
@limiter.limit("30/minute")
async def list_tactical_strategies(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """전술 배분을 켠 포트폴리오 목록 — 저장된 상태만 읽는다(시세 조회·국면 갱신 없음)."""
    strategies = await tactical.list_strategies(current_user.id, db)
    return [
        {
            "portfolio_id": str(s.portfolio_id),
            "confirmed_regime": s.last_regime,
            "notify_enabled": s.notify_enabled,
        }
        for s in strategies
    ]


@router.get("/market")
@limiter.limit("30/minute")
async def get_tactical_market(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """포트폴리오와 무관한 시장 입력(매크로 확정 등급 + 차트 지표) — 진단 탭 "시장 상황" 카드용.

    국면은 전략별 매크로 반영·히스테리시스에 달려 있어 여기서 내보내지 않는다.
    `/{portfolio_id}`보다 먼저 선언해야 "market"이 uuid 파싱으로 422가 나지 않는다.
    """
    market = await tactical.evaluate_market(await get_cache_store(), db)
    return {
        "macro_level": market["macro_level"],
        "macro_freshness": market["macro_freshness"],
        "technicals": market["technicals"],
    }


@router.get("/{portfolio_id}")
@limiter.limit("30/minute")
async def get_tactical_status(
    request: Request,
    portfolio_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """현재 국면(관측·확정), 매크로 등급, QQQ/SPY/DIA 차트 지표(웅덩이 단계 포함), 제안 비중·현재 목표 비중."""
    portfolio = await _portfolio_or_404(portfolio_id, current_user, db)
    strategy = await tactical.get_strategy(portfolio_id, current_user.id, db)
    # 서버가 잠들어 일일 점검 job이 못 돈 날도 앱을 열면 국면 확정이 진행되도록 조회 시에도 갱신한다.
    # 07:40 job과 겹쳐도 안전하다 — 확정 규칙(step_confirmation)이 같은 날·같은 관측에 같은 상태를 내고 알림은
    # job만 notified_regime 비교로 보낸다(조회가 확정해도 다음 job이 놓친 알림을 보냄, plans/62 F2·77 C3 검토)
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
    strategy.dip_shift_pct = Decimal(str(body.dip_shift_pct))
    strategy.use_macro = body.use_macro

    cache = await get_cache_store()
    market = await tactical.evaluate_market(cache, db)
    today = today_kst()
    tactical.advance_regime(strategy, market, today)
    tactical.advance_tilt(strategy, market, today)
    tactical.advance_dip(strategy, market)
    if strategy.notified_regime is None:
        strategy.notified_regime = strategy.last_regime  # 사용 시작 시점 국면은 알릴 필요 없음
        strategy.notified_dip_level = strategy.dip_level or 0  # 진행 중인 웅덩이도 마찬가지
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
    """전략 사용 중지(포트폴리오 목표 비중은 그대로 둔다).

    이 포트폴리오의 자동매수가 전술 연동(`market_condition_mode="TACTICAL"`)이면 일반 모드(DISABLED)로 되돌린다 —
    국면이 없으면 게이트가 늘 통과라 연동 표시만 남아 오해를 부른다.
    """
    strategy = await tactical.get_strategy(portfolio_id, current_user.id, db)
    if strategy is not None:
        await db.execute(
            update(RebalancingAlert)
            .where(
                RebalancingAlert.portfolio_id == portfolio_id,
                RebalancingAlert.user_id == current_user.id,
                RebalancingAlert.market_condition_mode == "TACTICAL",
            )
            .values(market_condition_mode="DISABLED")
        )
        await db.delete(strategy)
        await db.commit()


async def _group_suggestions(
    portfolio: Portfolio, user: User, db: AsyncSession, cache: CacheStore
) -> dict[str, IndexGroupSuggestion] | None:
    """새로 만들 지수 그룹의 멤버·국내 대체 종목 — 포트폴리오 연결 계좌의 보유 종목 기준 제안(plans/76).

    실패해도 적용은 막지 않는다(대표 종목만으로 그룹 생성).
    """
    from app.services.etf.index_exposure_service import get_index_group_suggestions

    try:
        rows = await db.execute(
            select(PortfolioAccount.account_id).where(PortfolioAccount.portfolio_id == portfolio.id)
        )
        account_ids = list(rows.scalars().all()) or None
        result = await get_index_group_suggestions(cache, db, user.id, account_ids)
    except Exception as exc:
        logger.warning("tactical_group_suggestions_failed", portfolio_id=str(portfolio.id), error=str(exc))
        return None
    return {g.key: g for g in result.groups}


@router.post("/{portfolio_id}/apply")
@limiter.limit("10/minute")
async def apply_tactical_weights(
    request: Request,
    portfolio_id: uuid.UUID,
    body: TacticalApplyRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """확정 국면의 제안 비중을 포트폴리오 목표 비중으로 저장한다 — 주문은 내지 않는다.

    `fraction<1`(분할 적용)은 전술 자산만으로 구성된 포트폴리오에서만, 같은 국면에서 한 번만 허용한다 — 다른 종목을
    절반만 줄이는 건 전술 배분이 관리하는 범위가 아니고, 두 번째부터는 나머지 적용(fraction=1)이다.
    """
    portfolio = await _portfolio_or_404(portfolio_id, current_user, db)
    strategy = await tactical.get_strategy(portfolio_id, current_user.id, db)
    if strategy is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="전술 배분을 먼저 켜주세요.")
    regime = strategy.last_regime
    if regime not in tactical.REGIMES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="아직 국면이 확정되지 않았습니다. 잠시 후 다시 시도해주세요."
        )

    fraction = body.fraction if body else 1.0
    if fraction < 1 and not tactical.is_tactical_managed(portfolio):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="전술 자산 외 종목이 있는 포트폴리오는 나눠서 적용할 수 없습니다. 한 번에 적용해주세요.",
        )
    if fraction < 1 and strategy.partial_regime == regime:
        # 현재 목표에서 다시 절반을 보간하면 75%가 된다 — 두 번째는 나머지(전체) 적용만 허용
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="이미 절반을 적용했어요. 나머지를 적용해주세요.",
        )

    cache = await get_cache_store()
    suggestions = (
        await _group_suggestions(portfolio, current_user, db, cache)
        if tactical.needs_group_suggestions(portfolio, strategy, regime, fraction)
        else None
    )
    await tactical.apply_regime_to_portfolio(
        portfolio, strategy, regime, db, fraction=fraction, group_suggestions=suggestions
    )
    strategy.notified_regime = strategy.last_regime  # 이미 반영했으니 같은 국면으로 다시 알릴 필요 없음
    await db.commit()

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
    """이 포트폴리오의 국면별 비중표·틸트·웅덩이 투입폭으로 과거 규칙을 재현한 백테스트(SPY·QQQ·DIA 단순보유와 비교)."""
    from app.services.tactical_backtest import run_tactical_backtest

    await _portfolio_or_404(portfolio_id, current_user, db)
    strategy = await tactical.get_strategy(portfolio_id, current_user.id, db)
    try:
        return await run_tactical_backtest(
            tactical.resolve_weights(strategy),
            years,
            await get_cache_store(),
            tilt_shift_pct=tactical.tilt_shift_of(strategy),
            dip_shift_pct=tactical.dip_shift_of(strategy),
            use_macro=tactical.uses_macro(strategy),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
