"""시장 위험 신호 API — VIX, 장단기 금리차, Fear & Greed Index 복합 조회."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, Request

from app.api.deps import get_current_user
from app.limiter import limiter
from app.models.user import User
from app.redis_client import get_redis
from app.services.macro_diagnosis_service import get_macro_diagnosis
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
    - fear_greed_contrarian_buy: F&G 25 이하 시 역발상 매수 기회 플래그
    - data_freshness: LIVE | CACHED | PARTIAL | STALE
    """
    redis = await get_redis()
    return await get_market_signal(redis)


@router.get("/macro-diagnosis")
@limiter.limit("20/minute")
async def get_macro_diagnosis_endpoint(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> dict:
    """CPI 추세·기준금리·FOMC 일정을 종합한 거시경제 진단을 반환한다.

    - cpi: CPI 방향성(rising/flat/falling) + 전년비 % + 최신값
    - fed_rate: 현재 기준금리 + 방향(rising/stable/falling) + 고금리 여부
    - fomc: 다음 FOMC 회의 날짜 + 남은 일수
    - implication: 리밸런싱 시사점 (label, growth_bias, message, action)
    - data_freshness: LIVE | PARTIAL | STALE
    """
    redis = await get_redis()
    return await get_macro_diagnosis(redis)
