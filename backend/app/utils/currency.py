"""USD/KRW 환율 캐싱 유틸리티."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import settings
from app.exceptions import ProviderApiError, ServiceUnavailableError
from app.utils.cache_keys import USD_KRW_RATE as _USD_KRW_KEY

if TYPE_CHECKING:
    from app.core.cache_store import CacheStore

_PLAUSIBLE_USD_KRW_MIN = 500.0
_PLAUSIBLE_USD_KRW_MAX = 3000.0


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


async def refresh_usd_krw(cache: CacheStore | None) -> tuple[float, bool]:
    """실시간 조회를 먼저 시도하는 (환율, 실값 여부). 실패하면 캐시, 그것도 없으면 (fallback, False).

    **새로 조회한 값만 캐시한다.** fallback 1300은 타당성 범위를 통과하므로 전역 캐시에 쓰면 이후 모든 경로가 실환율로
    믿게 되고, 옛 캐시를 다시 쓰면 장애 내내 TTL이 연장된다(plans/110 A1).
    """
    from app.services.market_data.yahoo_price import fetch_usdkrw  # 순환 import 방지

    fetched = await fetch_usdkrw()
    if fetched:
        await cache_usd_krw_rate(cache, fetched)
        return fetched, True
    if cache is not None and (cached := await cache.get(_USD_KRW_KEY)):
        return float(cached), True
    return settings.usd_krw_fallback_rate, False


async def require_live_usd_krw(cache: CacheStore | None, *, force_refresh: bool = False) -> float:
    """영구 기록(거래 행·스냅샷)에 쓸 환율 — 실값이 없으면 fallback으로 저장하지 않고 503으로 거부한다."""
    rate = await fetch_usd_krw(cache, force_refresh=force_refresh, allow_fallback=False)
    if rate:
        return rate
    rate, is_live = await get_live_or_cached_usd_krw(cache)
    if not is_live:
        raise ServiceUnavailableError("환율을 확인할 수 없어 달러 금액을 반영하지 못했어요. 잠시 후 다시 시도해주세요.")
    return rate


async def sync_usd_krw_rate(cache: CacheStore | None, *, needs_usd: bool) -> float:
    """브로커 동기화용 환율. 달러 자산이 있는데 실환율이 없으면 동기화를 실패시켜 기존 데이터를 보존한다.

    fallback으로 진행하면 그날 스냅샷이 1300 기준으로 굳고, 월말이면 그 달의 대표값이 된다(plans/110 A7).
    달러 자산이 없으면 환율을 쓰지 않으므로 그대로 진행한다.
    """
    rate, is_live = await get_live_or_cached_usd_krw(cache)
    if needs_usd and not is_live:
        raise ProviderApiError(
            "환율을 확인할 수 없어 해외 자산 동기화를 미뤘어요. 잠시 후 다시 시도하세요.", http_status=503
        )
    return rate


async def cache_usd_krw_rate(cache: CacheStore | None, rate: float) -> None:
    """USD/KRW 환율을 캐싱. 범위를 벗어난 값(등락률 등 다른 필드를 잘못 읽은 값)은 버린다 — 전역 캐시라 한 번
    들어가면 환산·환율 알림·환전 계획이 모두 그 값을 실환율로 쓴다(plans/99 A1)."""
    if cache is None or not _PLAUSIBLE_USD_KRW_MIN < rate < _PLAUSIBLE_USD_KRW_MAX:
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
