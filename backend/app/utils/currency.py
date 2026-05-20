"""USD/KRW 환율 Redis 캐싱 유틸리티."""
from __future__ import annotations

from app.config import settings

_REDIS_USD_KRW_KEY = "usd_krw_rate"


async def get_usd_krw_rate(redis, fallback_rate: float | None = None) -> float:
    """Redis 캐시에서 USD/KRW 환율 조회. 캐시 미적중 시 config fallback 반환."""
    rate = fallback_rate if fallback_rate is not None else settings.usd_krw_fallback_rate
    if redis is None:
        return rate
    try:
        cached = await redis.get(_REDIS_USD_KRW_KEY)
        if cached:
            return float(cached)
    except Exception:
        pass
    return rate


async def cache_usd_krw_rate(redis, rate: float) -> None:
    """USD/KRW 환율을 Redis에 캐싱."""
    import contextlib

    if redis is None or rate <= 0:
        return
    with contextlib.suppress(Exception):
        await redis.setex(_REDIS_USD_KRW_KEY, settings.redis_cache_ttl_seconds, str(rate))
