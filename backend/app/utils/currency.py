"""USD/KRW 환율 캐싱 유틸리티."""

from __future__ import annotations

import asyncio
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


async def cache_usd_krw_rate(cache: CacheStore | None, rate: float) -> None:
    """USD/KRW 환율을 캐싱."""
    if cache is None or rate <= 0:
        return
    await cache.setex(_USD_KRW_KEY, settings.cache_ttl_seconds, str(rate))


async def fetch_usd_krw(cache: CacheStore | None, *, force_refresh: bool = False) -> float:
    """USD/KRW 환율 단일 진입점.

    force_refresh=False: 캐시 조회 → 미적중 시 settings fallback.
    force_refresh=True:  yfinance로 실시간 조회 → 캐시 갱신 → 실패 시 캐시/fallback.
    """
    if not force_refresh:
        return await get_usd_krw_rate(cache)

    from app.services.yahoo_price import _sync_usdkrw  # 순환 import 방지

    loop = asyncio.get_running_loop()
    fetched = await loop.run_in_executor(None, _sync_usdkrw)
    if fetched:
        await cache_usd_krw_rate(cache, fetched)
        return fetched
    return await get_usd_krw_rate(cache)
