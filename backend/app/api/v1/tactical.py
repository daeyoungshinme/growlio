"""나스닥100/S&P500 전술 배분 API — 매크로+차트 국면 조회·전략 설정·제안 비중 적용·규칙 백테스트.

자동 주문은 없다. `/apply`는 포트폴리오 목표 비중만 바꾸고, 실제 주문은 기존 리밸런싱 실행 화면에서 한다.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.cache_store import get_cache_store
from app.core.database import release_read_connection
from app.limiter import limiter
from app.models.portfolio import Portfolio
from app.models.tactical import TacticalStrategy
from app.models.user import User
from app.schemas.tactical import TacticalApplyRequest, TacticalStrategyUpsert
from app.services.tactical import tactical_allocation_service as tactical
from app.utils.cache_invalidation import invalidate_rebalancing_analysis_cache, invalidate_user_caches
from app.utils.cache_keys import insights_key, portfolio_list_key
from app.utils.kst import today_kst

router = APIRouter(prefix="/tactical", tags=["tactical"])


async def _status(
    portfolio: Portfolio, strategy: TacticalStrategy | None, db: AsyncSession, *, advance: bool
) -> dict[str, Any]:
    # 시장 신호·차트 지표(외부 조회) 동안 커넥션을 쥐지 않게 — 포트폴리오·전략은 이미 읽었고
    # expire_on_commit=False라 그대로 쓰며, 국면 갱신 commit은 새 트랜잭션에서 한다(plans/125 A6)
    await release_read_connection(db)
    market = await tactical.evaluate_market(await get_cache_store(), db)
    if advance and strategy is not None and tactical.advance_strategy(strategy, market, today_kst()):
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
    portfolio = await tactical.get_owned_portfolio(portfolio_id, current_user.id, db)
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
    portfolio = await tactical.get_owned_portfolio(portfolio_id, current_user.id, db)
    strategy, market = await tactical.save_strategy(portfolio_id, current_user.id, body, await get_cache_store(), db)
    return await tactical.build_status(portfolio, strategy, market)


@router.delete("/{portfolio_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("20/minute")
async def delete_tactical_strategy(
    request: Request,
    portfolio_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """전략 사용 중지(포트폴리오 목표 비중은 그대로 둔다). 전술 연동 자동매수는 일반 모드로 되돌린다."""
    await tactical.disable_strategy(portfolio_id, current_user.id, db)


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

    분할 적용 규칙 등 검증은 `tactical.check_apply_allowed`가 한다.
    """
    portfolio = await tactical.get_owned_portfolio(portfolio_id, current_user.id, db)
    fraction = body.fraction if body else 1.0
    expected_regime = body.expected_regime if body else None
    strategy, regime = tactical.check_apply_allowed(
        portfolio, await tactical.get_strategy(portfolio_id, current_user.id, db), fraction, expected_regime
    )

    # 그룹 제안은 오래 걸릴 수 있어 락 밖에서 구하고, 항목을 교체하기 직전에 잠그고 다시 읽어 판정한다 —
    # 그 사이 저장된 편집을 옛 값으로 덮어쓰거나 동시 적용이 겹쳐 비중 합이 200%가 되지 않게(plans/110 A4)
    cache = await get_cache_store()
    suggestions = (
        await tactical.group_suggestions_for(portfolio, current_user.id, db, cache)
        if tactical.needs_group_suggestions(portfolio, strategy, regime, fraction)
        else None
    )
    portfolio = await tactical.get_owned_portfolio(portfolio_id, current_user.id, db, lock=True)
    strategy, regime = tactical.check_apply_allowed(
        portfolio, await tactical.get_strategy(portfolio_id, current_user.id, db, lock=True), fraction, expected_regime
    )
    await tactical.apply_regime_to_portfolio(
        portfolio, strategy, regime, db, fraction=fraction, group_suggestions=suggestions
    )
    strategy.notified_regime = strategy.last_regime  # 이미 반영했으니 같은 국면으로 다시 알릴 필요 없음
    await db.commit()

    # 홈 인사이트의 리밸런싱 기회도 목표 비중을 읽는다 — 포트폴리오 수정 경로와 같이 비운다 (plans/99 A2)
    await invalidate_user_caches(cache, portfolio_list_key(current_user.id), insights_key(current_user.id))
    await invalidate_rebalancing_analysis_cache(cache, current_user.id, portfolio_id)

    db.expire(portfolio)
    refreshed = await tactical.get_owned_portfolio(portfolio_id, current_user.id, db)
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
    from app.services.tactical.tactical_backtest import run_tactical_backtest

    await tactical.get_owned_portfolio(portfolio_id, current_user.id, db)
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
