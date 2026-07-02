"""배당 데이터 멀티소스 조회 체인.

Naver Finance → yfinance → KIS ETF API → pykrx → FinanceDataReader → KIS 일반 → DART → 정적 폴백
"""

from __future__ import annotations

import asyncio
import json
from functools import partial

import structlog
from redis.asyncio import Redis as AioRedis

from app.constants import DOMESTIC_MARKETS
from app.kis.domestic_quote import get_domestic_dividend_info, get_domestic_etf_dividend_info
from app.services.dart_service import fetch_dart_dividend
from app.services.dividend_constants import (
    KNOWN_DIVIDEND_INFO,
    KNOWN_DIVIDEND_SCHEDULES,
    is_korean_etf,
)
from app.services.dividend_sync_sources import (
    sync_fdr_etf_dividend_info,
    sync_fetch_dividend_months,
    sync_naver_etf_dividend_info,
    sync_naver_stock_dividend_info,
    sync_pykrx_etf_dividend_info,
    sync_yahoo_dividend_info,
)
from app.services.yahoo_price import to_yf_symbol as _to_yahoo_symbol
from app.utils.cache_keys import (
    TTL_DIVIDEND_INFO,
    TTL_DIVIDEND_MONTHS,
    dividend_info_key,
    dividend_months_key,
)
from app.utils.circuit_breaker import fdr_circuit, naver_circuit

logger = structlog.get_logger()


# ── 개별 소스 fetcher (try/except 캡슐화) ────────────────────────

_EMPTY_DIV: dict = {"dps": 0, "dividend_yield": 0}
_EMPTY_DIV_WITH_MONTHS: dict = {"dps": 0, "dividend_yield": 0, "dividend_months": []}


async def _try_source(coro, log_key: str, ticker: str, fallback: dict | None = None) -> dict:
    """코루틴을 실행하고 예외 발생 시 fallback dict를 반환하는 공통 래퍼."""
    try:
        return await coro
    except Exception as e:
        logger.warning(log_key, ticker=ticker, error=str(e))
        return fallback if fallback is not None else _EMPTY_DIV


async def _try_naver(ticker: str, is_etf: bool, loop: asyncio.AbstractEventLoop) -> dict:
    """Naver Finance 조회. 실패 시 빈 결과 반환."""
    fn = sync_naver_etf_dividend_info if is_etf else sync_naver_stock_dividend_info
    return await _try_source(
        naver_circuit.call(loop.run_in_executor, None, partial(fn, ticker)),
        "naver_dividend_circuit_skipped",
        ticker,
        _EMPTY_DIV_WITH_MONTHS,
    )


async def _try_kis_etf(ticker: str, kis_creds: dict) -> dict:
    """KIS ETF 전용 배당 조회. 실패 시 빈 결과 반환."""
    return await _try_source(
        get_domestic_etf_dividend_info(
            app_key=kis_creds["app_key"],
            app_secret=kis_creds["app_secret"],
            access_token=kis_creds["access_token"],
            ticker=ticker,
            is_mock=kis_creds["is_mock"],
        ),
        "kis_etf_dividend_fallback_failed",
        ticker,
    )


async def _try_fdr(ticker: str, loop: asyncio.AbstractEventLoop) -> dict:
    """FinanceDataReader ETF 배당 조회. 실패 시 빈 결과 반환."""
    return await _try_source(
        fdr_circuit.call(loop.run_in_executor, None, partial(sync_fdr_etf_dividend_info, ticker)),
        "fdr_dividend_circuit_skipped",
        ticker,
    )


async def _try_kis_general(ticker: str, kis_creds: dict) -> dict:
    """KIS 일반주식 배당 조회. 실패 시 빈 결과 반환."""
    return await _try_source(
        get_domestic_dividend_info(
            app_key=kis_creds["app_key"],
            app_secret=kis_creds["app_secret"],
            access_token=kis_creds["access_token"],
            ticker=ticker,
            is_mock=kis_creds["is_mock"],
        ),
        "kis_dividend_fallback_failed",
        ticker,
    )


def _merge_source(src: dict, dps: float, yield_decimal: float) -> tuple[float, float]:
    """소스 결과를 현재값에 병합. 기존값이 0일 때만 덮어쓴다."""
    new_dps = src["dps"] if src.get("dps", 0) > 0 and dps == 0.0 else dps
    new_yield = src["dividend_yield"] if src.get("dividend_yield", 0) > 0 and yield_decimal == 0.0 else yield_decimal
    return new_dps, new_yield


# ── 국내 종목 fallback 체인 ──────────────────────────────────────


async def _fetch_dart_and_static(
    ticker: str,
    market: str,
    dart_key: str,
    dps: float,
    yield_decimal: float,
) -> tuple[float, float]:
    """DART 조회 및 정적 폴백 — 마지막 수단.

    DPS가 0이면 yield 유무와 무관하게 DART를 시도한다.
    Naver는 yield만 반환하고 DPS를 주지 않으므로, DPS가 0인 채로
    DART를 건너뛰면 수량 기반 배당금 계산이 불가능해진다.
    """
    if dps == 0.0:
        dart = await fetch_dart_dividend(ticker, api_key=dart_key)
        if dart:
            if dps == 0.0:
                dps = dart["dps"]
            if yield_decimal == 0.0:
                yield_decimal = dart["dividend_yield"]
    if dps == 0.0 and yield_decimal == 0.0:
        known_info = KNOWN_DIVIDEND_INFO.get((ticker, market.upper()))
        if known_info:
            dps, yield_decimal = known_info
            logger.info("known_dividend_info_used", ticker=ticker, market=market)
        elif len(ticker) == 6 and ticker[-1] == "5":
            # 우선주(마지막 자리 5)에 대한 데이터가 없으면 보통주(마지막 자리 0) 폴백
            common_ticker = ticker[:-1] + "0"
            common_info = KNOWN_DIVIDEND_INFO.get((common_ticker, market.upper()))
            if common_info:
                dps, yield_decimal = common_info
                logger.info(
                    "preferred_stock_fallback_to_common",
                    preferred=ticker,
                    common=common_ticker,
                    market=market,
                )
    return dps, yield_decimal


async def _fetch_korean_fallbacks(
    ticker: str,
    market: str,
    is_etf: bool,
    loop: asyncio.AbstractEventLoop,
    dps: float,
    yield_decimal: float,
    kis_creds: dict | None,
    dart_key: str,
) -> tuple[float, float]:
    """국내 종목 fallback 체인: KIS ETF → pykrx → FDR → KIS 일반 → DART → 정적."""
    if is_etf and (dps == 0.0 or yield_decimal == 0.0) and kis_creds:
        prev_dps = dps
        dps, yield_decimal = _merge_source(await _try_kis_etf(ticker, kis_creds), dps, yield_decimal)
        if dps != prev_dps:
            logger.info("kis_etf_dividend_fallback_used", ticker=ticker)

    if dps == 0.0 or yield_decimal == 0.0:
        pykrx = await loop.run_in_executor(None, partial(sync_pykrx_etf_dividend_info, ticker))
        dps, yield_decimal = _merge_source(pykrx, dps, yield_decimal)

    if is_etf and (dps == 0.0 or yield_decimal == 0.0):
        dps, yield_decimal = _merge_source(await _try_fdr(ticker, loop), dps, yield_decimal)

    if (dps == 0.0 or yield_decimal == 0.0) and kis_creds:
        prev_dps = dps
        dps, yield_decimal = _merge_source(await _try_kis_general(ticker, kis_creds), dps, yield_decimal)
        if dps != prev_dps:
            logger.info("kis_dividend_fallback_used", ticker=ticker)

    return await _fetch_dart_and_static(ticker, market, dart_key, dps, yield_decimal)


# ── 네트워크 소스 체인 (sem 내부) ──────────────────────────────────


async def _fetch_from_network(
    ticker: str,
    market: str,
    is_korean: bool,
    is_etf: bool,
    yahoo_sym: str,
    loop: asyncio.AbstractEventLoop,
    dps: float,
    yield_decimal: float,
    months: list[int],
    need_months_fetch: bool,
    kis_creds: dict | None,
    dart_key: str,
) -> tuple[float, float, str | None, list[int], bool]:
    """네트워크 소스 전체 체인. (yield_decimal, dps, ex_div_date, months, need_months_fetch) 반환."""
    ex_dividend_date = None

    if is_korean:
        naver_info = await _try_naver(ticker, is_etf, loop)
        dps, yield_decimal = _merge_source(naver_info, dps, yield_decimal)
        if need_months_fetch and naver_info["dividend_months"]:
            months = naver_info["dividend_months"]
            need_months_fetch = False
        if naver_info.get("dps", 0) > 0 or naver_info.get("dividend_yield", 0) > 0:
            logger.debug("naver_dividend_used", ticker=ticker)

    if dps == 0.0 or yield_decimal == 0.0:
        info = await loop.run_in_executor(None, partial(sync_yahoo_dividend_info, yahoo_sym))
        prev_dps, prev_yield = dps, yield_decimal
        dps, yield_decimal = _merge_source(info, dps, yield_decimal)
        if dps != prev_dps or yield_decimal != prev_yield:
            logger.debug("yahoo_dividend_used", ticker=ticker)
        ex_dividend_date = info.get("ex_dividend_date")

        if is_korean:
            dps, yield_decimal = await _fetch_korean_fallbacks(
                ticker, market, is_etf, loop, dps, yield_decimal, kis_creds, dart_key
            )

        if need_months_fetch:
            months = await loop.run_in_executor(None, partial(sync_fetch_dividend_months, yahoo_sym))

    return yield_decimal, dps, ex_dividend_date, months, need_months_fetch


# ── 공개 API ────────────────────────────────────────────────────


async def fetch_ticker_dividend_info(
    ticker: str,
    market: str,
    redis: AioRedis,
    sem: asyncio.Semaphore,
    kis_creds: dict | None,
    dart_key: str,
    overrides: dict[tuple[str, str], list[int]],
) -> tuple[float, float, list[int], str | None]:
    """배당 수익률, DPS, 배당월, 배당락일을 멀티소스 폴백 체인으로 조회한다.

    Returns: (yield_decimal, dps, months, ex_dividend_date)
    소스 우선순위: Naver → yfinance → KIS ETF → pykrx → FDR → KIS 일반 → DART → 정적 폴백
    """
    loop = asyncio.get_running_loop()
    is_korean = market.upper() in DOMESTIC_MARKETS
    is_etf = is_korean_etf(ticker, market)
    yahoo_sym = _to_yahoo_symbol(ticker, market)
    yield_decimal = 0.0
    dps = 0.0
    ex_dividend_date = None

    # 배당월: override > 정적 스케줄 > Redis 캐시 > 네트워크
    override_months = overrides.get((ticker, market))
    if override_months is not None:
        months: list[int] = override_months
        need_months_fetch = False
    else:
        known = KNOWN_DIVIDEND_SCHEDULES.get((ticker, market.upper()))
        months = known if known is not None else []
        need_months_fetch = known is None

    months_cache_key = dividend_months_key(ticker, market)
    info_cache_key = dividend_info_key(ticker, market)

    if need_months_fetch:
        cached_months = await redis.get(months_cache_key)
        if cached_months:
            try:
                months = json.loads(cached_months)
                need_months_fetch = False
            except (json.JSONDecodeError, TypeError):
                await redis.delete(months_cache_key)

    cached_info = await redis.get(info_cache_key)
    if cached_info:
        try:
            cached = json.loads(cached_info)
            dps = cached["dps"] if dps == 0.0 else dps
            yield_decimal = cached["yield_decimal"] if yield_decimal == 0.0 else yield_decimal
        except (json.JSONDecodeError, TypeError, KeyError):
            await redis.delete(info_cache_key)

    if dps > 0 and yield_decimal > 0 and not need_months_fetch:
        return yield_decimal, dps, months, ex_dividend_date

    async with sem:
        yield_decimal, dps, ex_dividend_date, months, need_months_fetch = await _fetch_from_network(
            ticker,
            market,
            is_korean,
            is_etf,
            yahoo_sym,
            loop,
            dps,
            yield_decimal,
            months,
            need_months_fetch,
            kis_creds,
            dart_key,
        )

    if need_months_fetch:
        await redis.setex(months_cache_key, TTL_DIVIDEND_MONTHS, json.dumps(months))

    if dps > 0 or yield_decimal > 0:
        await redis.setex(info_cache_key, TTL_DIVIDEND_INFO, json.dumps({"dps": dps, "yield_decimal": yield_decimal}))
    else:
        logger.warning("dividend_all_sources_failed", ticker=ticker, market=market)

    return yield_decimal, dps, months, ex_dividend_date
