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
from app.services.goal.goal_candidate_service import looks_like_korean_etf
from app.services.market_data.market_data_fetcher import fetch_yf_info
from app.services.market_data.yahoo_price import run_yf_bounded, to_yf_symbol
from app.utils.cache_keys import (
    TTL_ETF_PROFILE,
    TTL_ETF_PROFILE_MISSING,
    CacheStoreType,
    etf_profile_key,
    get_cached_json,
    set_cached_json,
)
from app.utils.circuit_breaker import yahoo_circuit

logger = structlog.get_logger()

_NAVER_FETCH_CONCURRENCY = 6
_FETCH_DEADLINE_SECONDS = 20.0
"""프로필 조회 전체 상한 — Naver 최대 20건 × (10초 타임아웃 + 재시도)가 엔드포인트를 붙잡지 않게 한다.
초과하면 그때까지 받은 프로필만 쓰고 나머지는 None(캐싱 안 함 → 다음 요청에 재시도)."""
_EMPTY_INFO_STREAK_AS_MISSING = 3
"""Yahoo가 살아 있는 배치에서 이 횟수만큼 연속으로 빈 응답을 준 해외 심볼은 "데이터 없음"으로 확정한다."""


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
    profiles, _unresolved = await get_etf_profiles_with_status(cache, items)
    return profiles


def _empty_streak_key(ticker: str, market: str) -> str:
    return etf_profile_key(ticker, market) + ":empty"


async def _empty_info_confirms_missing(cache: CacheStoreType, ticker: str, market: str, yahoo_alive: bool) -> bool:
    """해외 심볼의 연속 빈 응답 횟수를 세고, `_EMPTY_INFO_STREAK_AS_MISSING`에 닿으면 True("데이터 없음" 확정)."""
    streak_key = _empty_streak_key(ticker, market)
    prev = int((await get_cached_json(cache, streak_key) or {}).get("n", 0))
    if prev == 0 and not yahoo_alive:
        return False  # 첫 빈 응답이 배치 전체 실패와 겹치면 조회 실패와 구분되지 않는다
    if prev + 1 >= _EMPTY_INFO_STREAK_AS_MISSING:
        return True
    await set_cached_json(cache, streak_key, {"n": prev + 1}, TTL_ETF_PROFILE_MISSING)
    return False


async def _resolve_overseas(
    cache: CacheStoreType, overseas: list[tuple[str, str]]
) -> list[tuple[str, str, EtfProfile | None, bool]]:
    """해외 심볼을 Yahoo로 조회해 캐싱할 (ticker, market, profile, definitive) 목록을 돌려준다(미확정은 빠진다)."""
    symbol_to_key = {to_yf_symbol(t, m): (t, m) for t, m in overseas}
    # 서킷이 열려 있으면 fetch_yf_info는 조회 없이 {}를 돌려준다 — 장애 중의 빈 응답은 세지 않는다. 예전엔
    # 첫 빈 응답만 걸러, 이미 한 번 센 정상 ETF가 장애 중 요청 두 번으로 "데이터 없음"에 닿았다(plans/119 B2)
    circuit_open = not yahoo_circuit.is_available()
    info_map = await run_yf_bounded(fetch_yf_info, list(symbol_to_key))
    # 다른 심볼은 응답을 받은 배치에서 빈 응답이 시작돼 연속으로 이어지면 상장폐지·비정상 심볼로 보고
    # "데이터 없음"(1일)으로 캐싱한다. 안 그러면 그런 종목 하나 때문에 겹침 분석이 매 요청 캐시 없이 다시 돈다
    # (plans/118 B2). 한 번의 빈 응답은 일시 실패일 수 있고, 배치 전체가 빈 응답에서 시작한 연속은
    # 조회 실패(서킷브레이커·네트워크)와 구분되지 않으므로 세지 않는다.
    yahoo_alive = any(info_map.get(symbol) for symbol in symbol_to_key)
    out: list[tuple[str, str, EtfProfile | None, bool]] = []
    for symbol, (t, m) in symbol_to_key.items():
        info = info_map.get(symbol)
        if not info:
            if not circuit_open and await _empty_info_confirms_missing(cache, t, m, yahoo_alive):
                out.append((t, m, None, False))
            continue
        if cache is not None:
            # 정상 응답이 오면 "연속" 빈 응답이 끊긴 것이다 — 남겨 두면 띄엄띄엄 난 일시 실패가 합산됐다
            await cache.delete(_empty_streak_key(t, m))
        out.append((t, m, parse_yahoo_etf_profile(info), bool(info.get("quoteType"))))
    return out


async def get_etf_profiles_with_status(
    cache: CacheStoreType, items: list[tuple[str, str, str]]
) -> tuple[dict[tuple[str, str], EtfProfile | None], set[tuple[str, str]]]:
    """`get_etf_profiles`와 같되, 조회 대상이었지만 응답을 받지 못한(네트워크 오류·서킷·데드라인) 키 집합도
    함께 반환한다 — 프로필 None이 "ETF 아님(확정)"인지 "이번엔 모름"인지 호출측이 구분해야 할 때 사용."""
    result: dict[tuple[str, str], EtfProfile | None] = {}
    resolved: set[tuple[str, str]] = set()
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
        resolved.add((ticker, market))
        ttl = TTL_ETF_PROFILE if profile is not None or definitive else TTL_ETF_PROFILE_MISSING
        await set_cached_json(cache, etf_profile_key(ticker, market), {"profile": profile}, ttl)

    async def _fetch_overseas() -> None:
        if not overseas:
            return
        for t, m, profile, definitive in await _resolve_overseas(cache, overseas):
            await _store(t, m, profile, definitive=definitive)

    try:
        await asyncio.wait_for(
            asyncio.gather(_fetch_overseas(), *[_fetch_domestic(t, m) for t, m in domestic]),
            timeout=_FETCH_DEADLINE_SECONDS,
        )
    except TimeoutError:
        logger.warning("etf_profile_fetch_deadline", domestic=len(domestic), overseas=len(overseas))
    return result, {k for k in (*domestic, *overseas) if k not in resolved}
