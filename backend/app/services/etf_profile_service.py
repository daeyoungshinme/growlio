"""ETF 기본 정보(총보수·기초지수·운용사) 조회 — 추천 후보 비교(`etf_overlap_service.py`)용.

소스:
- 국내 ETF: Naver 모바일 `etfAnalysis`(배당·추종지역 판별이 이미 쓰는 같은 응답) — `totalFee`(총보수 %),
  `etfBaseIndex`(기초지수명), `issuerName`(운용사), `chaseErrorRate`(추적오차 %).
- 해외 ETF: yfinance `.info` — `netExpenseRatio`(순보수 %, 없으면 `annualReportExpenseRatio`),
  `fundFamily`(운용사), `longName`(기초지수명이 이름에 드러나는 경우가 많아 지수 판별 보조로 사용).

두 소스 모두 **퍼센트 단위**로 값을 준다(예: TIGER 미국S&P500 `totalFee=0.0068`, SPY `netExpenseRatio=0.0945`).

ETF가 아닌 종목(개별주)·데이터 없음은 `None` 프로필로 확정하고 짧게 캐싱한다. 네트워크 오류는 캐싱하지
않고 이번 요청에서만 `None`으로 둔다 — 참고 정보라 조회 실패가 비교 기능 자체를 막지 않는다(fail-soft).
"""

from __future__ import annotations

import asyncio
from typing import Any, TypedDict

import structlog

from app.constants import CASH_EQUIVALENT_MARKET, DOMESTIC_MARKETS
from app.services.dividend.sync_sources import fetch_naver_etf_analysis
from app.services.goal_candidate_service import looks_like_korean_etf
from app.services.market_data_fetcher import fetch_yf_info
from app.services.yahoo_price import run_yf_bounded, to_yf_symbol
from app.utils.cache_keys import (
    TTL_ETF_PROFILE,
    TTL_ETF_PROFILE_MISSING,
    CacheStoreType,
    etf_profile_key,
    get_cached_json,
    set_cached_json,
)

logger = structlog.get_logger()

_NAVER_FETCH_CONCURRENCY = 6
_FETCH_DEADLINE_SECONDS = 20.0
"""프로필 조회 전체 상한 — Naver 최대 20건 × (10초 타임아웃 + 재시도)가 엔드포인트를 붙잡지 않게 한다.
초과하면 그때까지 받은 프로필만 쓰고 나머지는 None(캐싱 안 함 → 다음 요청에 재시도)."""


class EtfProfile(TypedDict):
    ter_pct: float | None  # 연 총보수(%)
    base_index: str | None  # 기초지수명(국내: Naver etfBaseIndex, 해외: 없음)
    issuer: str | None  # 운용사
    long_name: str | None  # 정식 명칭(해외 ETF의 지수 판별 보조)
    tracking_error_pct: float | None  # 추적오차(%, 국내만)


def _as_float(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f >= 0 else None


def parse_naver_etf_profile(data: dict) -> EtfProfile | None:
    """Naver `etfAnalysis` 응답 → 프로필. 핵심 필드가 모두 없으면 None(ETF 데이터 아님)."""
    ter = _as_float(data.get("totalFee"))
    base_index = (data.get("etfBaseIndex") or "").strip() or None
    issuer = (data.get("issuerName") or "").strip() or None
    if ter is None and base_index is None and issuer is None:
        return None
    return EtfProfile(
        ter_pct=ter,
        base_index=base_index,
        issuer=issuer,
        long_name=(data.get("itemName") or "").strip() or None,
        tracking_error_pct=_as_float(data.get("chaseErrorRate")),
    )


def parse_yahoo_etf_profile(info: dict) -> EtfProfile | None:
    """yfinance `.info` → 프로필. ETF가 아니면 None."""
    if info.get("quoteType") != "ETF":
        return None
    ter = _as_float(info.get("netExpenseRatio"))
    if ter is None:
        ter = _as_float(info.get("annualReportExpenseRatio"))
    return EtfProfile(
        ter_pct=ter,
        base_index=None,
        issuer=(info.get("fundFamily") or "").strip() or None,
        long_name=(info.get("longName") or "").strip() or None,
        tracking_error_pct=None,
    )


def _sync_naver_profile(ticker: str) -> EtfProfile | None:
    """네트워크 오류는 그대로 raise한다(호출측이 캐싱하지 않도록) — 파싱 결과 없음만 None."""
    return parse_naver_etf_profile(fetch_naver_etf_analysis(ticker))


async def get_etf_profiles(
    cache: CacheStoreType, items: list[tuple[str, str, str]]
) -> dict[tuple[str, str], EtfProfile | None]:
    """(ticker, name, market) 목록의 ETF 프로필을 조회한다. 키는 (ticker, market).

    국내 개별주(ETF로 보이지 않는 종목)와 합성 현금성 자산은 조회하지 않고 None으로 둔다.
    ticker+market 단위 전역 캐시(`TTL_ETF_PROFILE` 7일 — 보수·기초지수는 사실상 불변)를 공유한다.
    """
    result: dict[tuple[str, str], EtfProfile | None] = {}
    domestic: list[tuple[str, str]] = []
    overseas: list[tuple[str, str]] = []

    for ticker, name, market in items:
        key = (ticker, market)
        if key in result:
            continue
        result[key] = None
        if market.upper() == CASH_EQUIVALENT_MARKET:
            continue
        cached = await get_cached_json(cache, etf_profile_key(ticker, market))
        if cached is not None:
            result[key] = cached.get("profile")
            continue
        if market.upper() in DOMESTIC_MARKETS:
            if looks_like_korean_etf({"ticker": ticker, "name": name, "market": market}):
                domestic.append(key)
        else:
            overseas.append(key)

    loop = asyncio.get_running_loop()
    sem = asyncio.Semaphore(_NAVER_FETCH_CONCURRENCY)

    async def _fetch_domestic(ticker: str, market: str) -> None:
        try:
            async with sem:
                profile = await loop.run_in_executor(None, _sync_naver_profile, ticker)
        except Exception as e:
            logger.warning("etf_profile_naver_failed", ticker=ticker, error=str(e))
            return
        await _store(ticker, market, profile)

    async def _store(ticker: str, market: str, profile: EtfProfile | None, *, definitive: bool = False) -> None:
        """`definitive`: 소스가 "ETF 아님"을 명시한 경우(Yahoo quoteType) — 프로필과 같은 장기 TTL로 캐싱한다."""
        result[(ticker, market)] = profile
        ttl = TTL_ETF_PROFILE if profile is not None or definitive else TTL_ETF_PROFILE_MISSING
        await set_cached_json(cache, etf_profile_key(ticker, market), {"profile": profile}, ttl)

    async def _fetch_overseas() -> None:
        if not overseas:
            return
        symbol_to_key = {to_yf_symbol(t, m): (t, m) for t, m in overseas}
        info_map = await run_yf_bounded(fetch_yf_info, list(symbol_to_key))
        for symbol, (t, m) in symbol_to_key.items():
            info = info_map.get(symbol)
            if not info:
                # 빈 응답은 조회 실패(서킷브레이커·네트워크)와 구분되지 않으므로 캐싱하지 않는다.
                continue
            await _store(t, m, parse_yahoo_etf_profile(info), definitive=bool(info.get("quoteType")))

    try:
        await asyncio.wait_for(
            asyncio.gather(_fetch_overseas(), *[_fetch_domestic(t, m) for t, m in domestic]),
            timeout=_FETCH_DEADLINE_SECONDS,
        )
    except TimeoutError:
        logger.warning("etf_profile_fetch_deadline", domestic=len(domestic), overseas=len(overseas))
    return result
