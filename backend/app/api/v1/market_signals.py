"""시장 위험 신호 API — VIX, 미국 금리 커브, 하이일드 스프레드 등 복합 조회."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.cache_store import get_cache_store
from app.limiter import limiter
from app.models.user import User
from app.schemas.market_signal import MarketOutlook
from app.services.market_signal.market_outlook import build_market_outlook
from app.services.market_signal.market_signal_service import get_last_composite_level, get_market_signal
from app.services.market_signal.technical_signal_service import get_technical_signals

router = APIRouter(prefix="/market-signals", tags=["market_signals"])
logger = structlog.get_logger()


@router.get("")
@limiter.limit("30/minute")
async def get_market_signal_endpoint(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """복합 시장 위험 신호(GREEN/YELLOW/RED)와 개별 지표 값을 반환한다.

    - composite_level: GREEN | YELLOW | RED
    - signals.vix: VIX 최신값 + 위험 레벨
    - signals.us_rate_curve: 10Y-2Y 스프레드 + 2Y-FEDFUNDS 스프레드를 병합한 "미국 금리 커브" 신호
      (둘 다 Fed 정책금리 경로 기대를 반영해 이중계상 방지 목적으로 병합, sub_score는 worst-case)
    - signals.high_yield_spread: 하이일드 채권 스프레드 + 신용 경색 레벨
    - signals.dollar_index: 달러 인덱스 20일선 이격도 + 레벨
    - signals.exchange_rate: 원/달러 환율(DEXKOUS) 20일선 이격도 + 레벨 (예측치 아님, 참고 지표)
    - signals.oil_price: WTI 현물유가(DCOILWTICO) 20일선 이격도 + 레벨 (급등/급락 모두 위험 신호)
    - data_freshness: LIVE | CACHED | PARTIAL | STALE
    - confirmed_level: AUTO 실행 게이트가 쓰는 연속 확인된 등급(아직 없으면 null). 표시용 composite_level은
      즉시 반영되고 confirmed는 연속 확인 후 반영돼 둘이 잠시 다를 수 있다 — 배너가 이를 함께 보여 준다.
      확인 단계를 전진시키지 않도록 저장된 값만 읽는다(전진은 스케줄러 job 담당).
    """
    cache = await get_cache_store()
    signal = await get_market_signal(cache)
    # 캐시된 dict는 사용자 간 공유되므로 복사본에 덧붙인다
    return {**signal, "confirmed_level": await get_last_composite_level(db)}


@router.get("/outlook", response_model=MarketOutlook)
@limiter.limit("30/minute")
async def get_market_outlook_endpoint(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> dict:
    """시장 종합 판단 — 즉시 매크로 등급 × 나스닥100·S&P500·다우 추세(plans/137 B).

    **표시 전용** — 자동 실행 게이트·전술 국면은 이 판단을 쓰지 않는다. 두 입력 모두 서버 캐시를 공유하므로
    배너·전술 탭과 같은 값을 본다. 한쪽 조회가 실패하면 나머지만으로 판단한다.
    """
    cache = await get_cache_store()
    signal: dict = {}
    technicals: dict = {}
    try:
        signal = await get_market_signal(cache)
    except Exception as e:
        logger.warning("market_outlook_signal_failed", error=str(e))
    try:
        technicals = dict(await get_technical_signals(cache))
    except Exception as e:
        logger.warning("market_outlook_technicals_failed", error=str(e))
    return build_market_outlook(signal, technicals)
