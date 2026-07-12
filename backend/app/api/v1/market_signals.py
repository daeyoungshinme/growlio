"""시장 위험 신호 API — VIX, 장단기 금리차, Fear & Greed Index 복합 조회."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, Request

from app.api.deps import get_current_user
from app.limiter import limiter
from app.models.user import User
from app.redis_client import get_redis
from app.services.market_signal_service import get_market_signal

router = APIRouter(prefix="/market-signals", tags=["market_signals"])
logger = structlog.get_logger()


@router.get("")
@limiter.limit("30/minute")
async def get_market_signal_endpoint(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> dict:
    """복합 시장 위험 신호(GREEN/YELLOW/RED)와 개별 지표 값을 반환한다.

    - composite_level: GREEN | YELLOW | RED
    - signals.vix: VIX 최신값 + 위험 레벨
    - signals.yield_curve: 10Y-2Y 스프레드 + 커브 상태
    - signals.fear_greed: Fear & Greed Index 0-100
    - signals.high_yield_spread: 하이일드 채권 스프레드 + 신용 경색 레벨
    - signals.dollar_index: 달러 인덱스 20일선 이격도 + 레벨
    - signals.rate_cut_expectation: 2Y-FEDFUNDS 스프레드 기반 금리인하 기대 레벨
    - signals.exchange_rate: 원/달러 환율(DEXKOUS) 20일선 이격도 + 레벨 (예측치 아님, 참고 지표)
    - fear_greed_contrarian_buy: F&G 25 이하 시 역발상 매수 기회 플래그
    - data_freshness: LIVE | CACHED | PARTIAL | STALE
    """
    redis = await get_redis()
    return await get_market_signal(redis)
