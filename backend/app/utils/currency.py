"""USD/KRW 환율 캐싱 유틸리티."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import settings
from app.utils.cache_keys import USD_KRW_RATE as _USD_KRW_KEY

if TYPE_CHECKING:
    from app.core.cache_store import CacheStore


async def get_usd_krw_rate(cache: CacheStore | None, fallback_rate: float | None = None) -> float:
    """캐시에서 USD/KRW 환율 조회. 캐시 미적중 시 config fallback 반환."""
    rate = fallback_rate if fallback_rate is not None else settings.usd_krw_fallback_rate
    if cache is None:
        return rate
    cached = await cache.get(_USD_KRW_KEY)
    if cached:
        return float(cached)
    return rate


async def get_live_or_cached_usd_krw(cache: CacheStore | None) -> tuple[float, bool]:
    """(환율, 실값 여부). 캐시 미스면 실시간 조회해 캐시하고, 그것도 실패하면 (fallback, False).

    결과를 장시간 캐시하는 계산(종목별 배당 요약 24h 등)은 fallback 환율이 그대로 굳지 않도록
    실값 여부로 TTL을 줄여야 한다.
    """
    if cache is not None:
        cached = await cache.get(_USD_KRW_KEY)
        if cached:
            return float(cached), True
    from app.services.market_data.yahoo_price import fetch_usdkrw  # 순환 import 방지

    fetched = await fetch_usdkrw()
    if fetched:
        await cache_usd_krw_rate(cache, fetched)
        return fetched, True
    return settings.usd_krw_fallback_rate, False


async def cache_usd_krw_rate(cache: CacheStore | None, rate: float) -> None:
    """USD/KRW 환율을 캐싱."""
    if cache is None or rate <= 0:
        return
    await cache.setex(_USD_KRW_KEY, settings.cache_ttl_seconds, str(rate))


async def fetch_usd_krw(cache: CacheStore | None, *, force_refresh: bool = False, allow_fallback: bool = True) -> float:
    """USD/KRW 환율 단일 진입점.

    force_refresh=False: 캐시 조회 → 미적중 시 settings fallback.
    force_refresh=True:  yfinance로 실시간 조회 → 캐시 갱신 → 실패 시 캐시/fallback.
    allow_fallback=False: 실시간·캐시 모두 없으면 settings fallback 대신 0.0 — 환율로 알림 발동·판정을
        하는 호출처용(고정 fallback 1300원이 실환율로 쓰이면 BELOW 알림이 거짓 발동한다).
    """
    if force_refresh:
        from app.services.market_data.yahoo_price import fetch_usdkrw  # 순환 import 방지

        fetched = await fetch_usdkrw()
        if fetched:
            await cache_usd_krw_rate(cache, fetched)
            return fetched
    if allow_fallback:
        return await get_usd_krw_rate(cache)
    if cache is not None and (cached := await cache.get(_USD_KRW_KEY)):
        return float(cached)
    return 0.0
