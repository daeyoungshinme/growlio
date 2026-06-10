"""AI 시황 분석 및 포트폴리오 추천 서비스.

yfinance로 시장 지수·섹터 데이터를 수집하고 Google Gemini API로 분석을 생성한다.
결과는 Redis에 1시간 캐시되며, force_refresh=True 시 즉시 재생성한다.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from datetime import UTC, datetime

import structlog
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.ai_analysis import (
    AIAnalysisResponse,
    AIAnalysisResult,
    ExchangeRateInfo,
    MarketIndexItem,
    SectorInfo,
)
from app.services.portfolio_service import build_portfolio_overview
from app.utils.cache_keys import TTL_AI_ANALYSIS, ai_analysis_key
from app.utils.circuit_breaker import yahoo_circuit

logger = structlog.get_logger()

_yfinance_sem = asyncio.Semaphore(3)

_INDICES = {
    "KOSPI": "^KS11",
    "KOSDAQ": "^KQ11",
    "S&P500": "^GSPC",
    "NASDAQ": "^IXIC",
}

_SECTORS = {
    "Technology": "XLK",
    "Healthcare": "XLV",
    "Finance": "XLF",
    "Energy": "XLE",
    "Consumer": "XLY",
    "Industrial": "XLI",
}

_EMPTY_MARKET_DATA: dict = {
    "indices": [],
    "sectors": [],
    "usd_krw": {"usd_krw": None, "change_pct": None},
}


def _sync_fetch_market_data() -> dict:
    """yfinance로 시장 지수·섹터 ETF·USD/KRW 데이터를 수집한다. 동기 함수 — run_in_executor 전용."""
    import yfinance as yf

    all_symbols = list(_INDICES.values()) + list(_SECTORS.values()) + ["USDKRW=X"]
    try:
        hist = yf.download(all_symbols, period="5d", auto_adjust=True, progress=False)
        has_close = isinstance(hist.columns, object) and "Close" in hist
        close = hist.get("Close", hist) if has_close else hist
    except Exception as e:
        logger.warning("market_data_fetch_failed", error=str(e))
        return _EMPTY_MARKET_DATA

    def _change_pct(symbol: str) -> float | None:
        try:
            col = close[symbol].dropna()
            if len(col) >= 2:
                return round((float(col.iloc[-1]) / float(col.iloc[-2]) - 1) * 100, 2)
        except Exception:
            pass
        return None

    def _week_change_pct(symbol: str) -> float | None:
        try:
            col = close[symbol].dropna()
            if len(col) >= 2:
                return round((float(col.iloc[-1]) / float(col.iloc[0]) - 1) * 100, 2)
        except Exception:
            pass
        return None

    def _price(symbol: str) -> float | None:
        try:
            col = close[symbol].dropna()
            if not col.empty:
                return round(float(col.iloc[-1]), 2)
        except Exception:
            pass
        return None

    indices = [
        {
            "symbol": symbol,
            "name": name,
            "price": _price(symbol),
            "change_pct": _change_pct(symbol),
            "week_change_pct": _week_change_pct(symbol),
        }
        for name, symbol in _INDICES.items()
    ]

    sectors = [
        {
            "sector": sector,
            "etf_ticker": etf,
            "change_pct": _change_pct(etf),
        }
        for sector, etf in _SECTORS.items()
    ]

    usd_krw_price = _price("USDKRW=X")
    usd_krw_change = _change_pct("USDKRW=X")

    return {
        "indices": indices,
        "sectors": sectors,
        "usd_krw": {"usd_krw": usd_krw_price, "change_pct": usd_krw_change},
    }


def _build_safe_portfolio_context(overview: dict) -> str:
    """포트폴리오 데이터를 JSON 직렬화해 프롬프트 인젝션을 방지한다."""
    safe = [
        {
            "ticker": str(p.get("ticker", ""))[:20],
            "name": str(p.get("name", ""))[:50],
            "market": str(p.get("market", ""))[:10],
            "weight_pct": round(float(p.get("weight_in_stock", 0)), 2),
            "pnl_pct": round(float(p.get("pnl_pct", 0)), 2),
            "value_krw": int(p.get("value_krw", 0)),
        }
        for p in overview.get("all_positions", [])[:50]
    ]
    summary = {
        "total_assets_krw": int(overview.get("total_assets_krw", 0)),
        "total_stock_krw": int(overview.get("total_stock_krw", 0)),
        "stock_return_pct": round(float(overview.get("stock_return_pct", 0)), 2),
        "positions": safe,
    }
    return json.dumps(summary, ensure_ascii=False)


async def _call_gemini_analysis(
    market_data: dict,
    portfolio_context: str,
    api_key: str,
) -> AIAnalysisResult:
    """Google Gemini API로 구조화된 포트폴리오 분석을 생성한다."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=AIAnalysisResult,
        system_instruction=(
            "당신은 전문 투자 분석가입니다. "
            "주어진 시장 데이터와 포트폴리오를 객관적으로 분석하세요. "
            "본 분석은 참고용이며 투자를 권유하지 않습니다. "
            "모든 응답은 한국어로 작성하세요."
        ),
    )

    market_json = json.dumps(market_data, ensure_ascii=False)
    prompt = (
        "## 현재 시장 데이터\n"
        f"```json\n{market_json}\n```\n\n"
        "## 사용자 보유 포트폴리오\n"
        f"```json\n{portfolio_context}\n```\n\n"
        "위 데이터를 바탕으로 다음을 분석하세요:\n"
        "1. 현재 시황 종합 요약 (2-3문장)\n"
        "2. 포트폴리오 리스크 진단 (집중도, 섹터 편향)\n"
        "3. 구체적 액션 추천 (최대 5개, 우선순위 포함)\n"
        "4. 대안 포트폴리오 3종 (보수적/중립적/공격적, 각 3-5종목)"
    )

    response = await client.aio.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
        config=config,
    )
    return AIAnalysisResult.model_validate_json(response.text)


def _make_error(msg: str) -> AIAnalysisResponse:
    return AIAnalysisResponse(
        status="error",
        cached_at=None,
        market_indices=[],
        exchange_rate=ExchangeRateInfo(usd_krw=None, change_pct=None),
        sector_performance=[],
        analysis=None,
        error_message=msg,
    )


async def _collect_market_data() -> dict:
    """서킷브레이커를 적용해 yfinance 시장 데이터를 수집한다. 실패 시 빈 dict 반환."""
    if not yahoo_circuit.is_available():
        return dict(_EMPTY_MARKET_DATA)
    try:
        loop = asyncio.get_running_loop()
        async with _yfinance_sem:
            fetched = await loop.run_in_executor(None, _sync_fetch_market_data)
        if fetched.get("indices"):
            yahoo_circuit.record_success()
            return fetched
        yahoo_circuit.record_failure()
    except Exception as e:
        yahoo_circuit.record_failure()
        logger.warning("market_data_fetch_error", error=str(e))
    return dict(_EMPTY_MARKET_DATA)


async def _run_gemini_analysis(
    market_data: dict,
    portfolio_context: str,
    api_key: str,
    user_id: uuid.UUID,
) -> tuple[AIAnalysisResult | None, str | None]:
    """Gemini API를 호출해 분석 결과를 반환한다. 에러 시 (None, 메시지) 반환."""
    from google.genai import errors as genai_errors

    last_err: Exception | None = None
    for attempt in range(2):
        try:
            analysis = await _call_gemini_analysis(market_data, portfolio_context, api_key)
            return analysis, None
        except Exception as e:
            if isinstance(e, genai_errors.ClientError):
                status = getattr(e, "status_code", None) or getattr(e, "code", None)
                if status == 429:
                    return None, "AI API 요청 한도를 초과했습니다. 잠시 후 다시 시도해주세요."
                if status == 403:
                    return None, "AI API 인증 오류입니다. GOOGLE_API_KEY를 확인해주세요."
            last_err = e
            if attempt == 0:
                await asyncio.sleep(1)

    logger.error("gemini_analysis_failed", user_id=str(user_id), error=str(last_err))
    return None, "AI 분석 중 오류가 발생했습니다."


async def get_ai_analysis(
    user_id: uuid.UUID,
    db: AsyncSession,
    redis,
    force_refresh: bool = False,
) -> AIAnalysisResponse:
    """AI 시황 분석 결과를 반환한다. Redis TTL 1시간 캐시 적용."""
    from app.config import settings

    if not settings.google_api_key:
        return _make_error(
            "AI 분석 기능이 설정되지 않았습니다. GOOGLE_API_KEY를 설정해주세요."
        )

    cache_key = ai_analysis_key(user_id)

    if not force_refresh and redis:
        with contextlib.suppress(RedisError):
            cached = await redis.get(cache_key)
            if cached:
                return AIAnalysisResponse.model_validate_json(cached)

    market_data = await _collect_market_data()

    try:
        overview = await build_portfolio_overview(user_id, db, redis=redis)
    except Exception as e:
        logger.error("portfolio_overview_failed", user_id=str(user_id), error=str(e))
        return _make_error("포트폴리오 데이터를 조회하지 못했습니다.")

    portfolio_context = _build_safe_portfolio_context(overview)
    analysis, err_msg = await _run_gemini_analysis(
        market_data, portfolio_context, settings.google_api_key, user_id
    )
    if err_msg:
        error_result = _make_error(err_msg)
        # 429 에러는 5분 캐시 → 이후 요청이 Gemini를 반복 호출하지 않도록 방지
        if redis and "한도를 초과" in err_msg:
            with contextlib.suppress(RedisError):
                await redis.setex(cache_key, 300, error_result.model_dump_json())
        return error_result

    result = AIAnalysisResponse(
        status="ready",
        cached_at=datetime.now(UTC),
        market_indices=[MarketIndexItem(**i) for i in market_data.get("indices", [])],
        exchange_rate=ExchangeRateInfo(
            **market_data.get("usd_krw", {"usd_krw": None, "change_pct": None})
        ),
        sector_performance=[SectorInfo(**s) for s in market_data.get("sectors", [])],
        analysis=analysis,
        error_message=None,
    )

    if redis:
        with contextlib.suppress(RedisError):
            await redis.setex(cache_key, TTL_AI_ANALYSIS, result.model_dump_json())

    return result
