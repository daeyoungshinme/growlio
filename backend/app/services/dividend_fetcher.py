"""배당 데이터 멀티소스 조회 체인.

Naver Finance → yfinance → KIS ETF API → pykrx → FinanceDataReader → KIS 일반 → DART → 정적 폴백
"""

from __future__ import annotations

import asyncio
import json
from functools import partial

import structlog
from redis.asyncio import Redis as AioRedis

from app.kis.domestic_quote import get_domestic_dividend_info, get_domestic_etf_dividend_info
from app.services.dart_service import fetch_dart_dividend
from app.services.dividend_constants import (
    KNOWN_DIVIDEND_INFO,
    KNOWN_DIVIDEND_SCHEDULES,
    is_korean_etf,
)
from app.services.dividend_providers import (
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
    is_korean = market.upper() in ("KOSPI", "KOSDAQ", "KRX")
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
        if known is not None:
            months = known
            need_months_fetch = False
        else:
            months = []
            need_months_fetch = True

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
            if dps == 0.0:
                dps = cached["dps"]
            if yield_decimal == 0.0:
                yield_decimal = cached["yield_decimal"]
        except (json.JSONDecodeError, TypeError, KeyError):
            await redis.delete(info_cache_key)

    # 캐시에서 모든 필요한 데이터를 확보한 경우 네트워크 소스 체인 생략
    if dps > 0 and yield_decimal > 0 and not need_months_fetch:
        return yield_decimal, dps, months, ex_dividend_date

    async with sem:
        # 0순위: Naver Finance (국내 종목 전용, 인증 불필요)
        if is_korean:
            fn = sync_naver_etf_dividend_info if is_etf else sync_naver_stock_dividend_info
            try:
                naver_info = await naver_circuit.call(
                    loop.run_in_executor, None, partial(fn, ticker)
                )
            except Exception as _naver_exc:
                logger.warning("naver_dividend_circuit_skipped", ticker=ticker, error=str(_naver_exc))
                naver_info = {"dps": 0, "dividend_yield": 0, "dividend_months": []}
            if naver_info["dps"] > 0 and dps == 0.0:
                dps = naver_info["dps"]
            if naver_info["dividend_yield"] > 0 and yield_decimal == 0.0:
                yield_decimal = naver_info["dividend_yield"]
            if need_months_fetch and naver_info["dividend_months"]:
                months = naver_info["dividend_months"]
                need_months_fetch = False
            if naver_info["dps"] > 0 or naver_info["dividend_yield"] > 0:
                logger.debug("naver_dividend_used", ticker=ticker)

        if dps == 0.0 or yield_decimal == 0.0:
            # 1순위: yfinance (국내/해외 공통)
            info = await loop.run_in_executor(None, partial(sync_yahoo_dividend_info, yahoo_sym))
            yahoo_contributed = False
            if info["dividend_yield"] > 0 and yield_decimal == 0.0:
                yield_decimal = info["dividend_yield"]
                yahoo_contributed = True
            if info["dps"] > 0 and dps == 0.0:
                dps = info["dps"]
                yahoo_contributed = True
            if yahoo_contributed:
                logger.debug("yahoo_dividend_used", ticker=ticker)
            ex_dividend_date = info.get("ex_dividend_date")

            # 2순위 (ETF): KIS ETF 전용 API (FHPET01010000) — 실시간 분배율
            if is_korean and is_etf and (dps == 0.0 or yield_decimal == 0.0) and kis_creds:
                try:
                    kis_etf = await get_domestic_etf_dividend_info(
                        app_key=kis_creds["app_key"],
                        app_secret=kis_creds["app_secret"],
                        access_token=kis_creds["access_token"],
                        ticker=ticker,
                        is_mock=kis_creds["is_mock"],
                    )
                    if kis_etf["dps"] > 0 and dps == 0.0:
                        dps = kis_etf["dps"]
                        logger.info("kis_etf_dividend_fallback_used", ticker=ticker)
                    if kis_etf["dividend_yield"] > 0 and yield_decimal == 0.0:
                        yield_decimal = kis_etf["dividend_yield"]
                except Exception as e:
                    logger.warning("kis_etf_dividend_fallback_failed", ticker=ticker, error=str(e))

            # 3순위: pykrx (국내 — 연간 DPS 합산 방식)
            if is_korean and (dps == 0.0 or yield_decimal == 0.0):
                pykrx = await loop.run_in_executor(None, partial(sync_pykrx_etf_dividend_info, ticker))
                if pykrx["dps"] > 0 and dps == 0.0:
                    dps = pykrx["dps"]
                if pykrx["dividend_yield"] > 0 and yield_decimal == 0.0:
                    yield_decimal = pykrx["dividend_yield"]

            # 3.5순위: FinanceDataReader ETF (국내 ETF — pykrx 실패 시 fallback)
            if is_korean and is_etf and (dps == 0.0 or yield_decimal == 0.0):
                try:
                    fdr = await fdr_circuit.call(
                        loop.run_in_executor, None, partial(sync_fdr_etf_dividend_info, ticker)
                    )
                except Exception as _fdr_exc:
                    logger.warning("fdr_dividend_circuit_skipped", ticker=ticker, error=str(_fdr_exc))
                    fdr = {"dps": 0, "dividend_yield": 0}
                if fdr["dps"] > 0 and dps == 0.0:
                    dps = fdr["dps"]
                if fdr["dividend_yield"] > 0 and yield_decimal == 0.0:
                    yield_decimal = fdr["dividend_yield"]

            # 4순위: KIS API 일반주식 (ETF 아닌 종목 또는 위 소스 모두 실패 시)
            if is_korean and (dps == 0.0 or yield_decimal == 0.0) and kis_creds:
                try:
                    kis_info = await get_domestic_dividend_info(
                        app_key=kis_creds["app_key"],
                        app_secret=kis_creds["app_secret"],
                        access_token=kis_creds["access_token"],
                        ticker=ticker,
                        is_mock=kis_creds["is_mock"],
                    )
                    if kis_info["dps"] > 0 and dps == 0.0:
                        dps = kis_info["dps"]
                        logger.info("kis_dividend_fallback_used", ticker=ticker)
                    if kis_info["dividend_yield"] > 0 and yield_decimal == 0.0:
                        yield_decimal = kis_info["dividend_yield"]
                except Exception as e:
                    logger.warning("kis_dividend_fallback_failed", ticker=ticker, error=str(e))

            # 5순위: DART (국내 종목이고 여전히 데이터 없을 때)
            if is_korean and yield_decimal == 0.0:
                dart = await fetch_dart_dividend(ticker, api_key=dart_key)
                if dart:
                    yield_decimal = dart["dividend_yield"]
                    if dps == 0.0:
                        dps = dart["dps"]

            # 6순위: 정적 폴백 (위 소스 모두 실패 시)
            if is_korean and dps == 0.0 and yield_decimal == 0.0:
                known_info = KNOWN_DIVIDEND_INFO.get((ticker, market.upper()))
                if known_info:
                    dps, yield_decimal = known_info
                    logger.info("known_dividend_info_used", ticker=ticker, market=market)

            if need_months_fetch:
                months = await loop.run_in_executor(None, partial(sync_fetch_dividend_months, yahoo_sym))

    if need_months_fetch:
        await redis.setex(months_cache_key, TTL_DIVIDEND_MONTHS, json.dumps(months))

    if dps > 0 or yield_decimal > 0:
        await redis.setex(info_cache_key, TTL_DIVIDEND_INFO, json.dumps({"dps": dps, "yield_decimal": yield_decimal}))
    else:
        logger.warning("dividend_all_sources_failed", ticker=ticker, market=market)

    return yield_decimal, dps, months, ex_dividend_date
