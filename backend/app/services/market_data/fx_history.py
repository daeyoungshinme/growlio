"""지난 날짜의 USD/KRW 환율 — 수기 해외 거래 기록을 거래일 환율로 원화 환산할 때 쓴다 (plans/156).

Yahoo `USDKRW=X` 일봉 종가 중 그 날짜 이하 가장 최근 값(주말·휴일이면 직전 거래일)을 돌려준다. 장중
값이 아니라 그날 종가라 "대략"의 환산이다. 오늘·미래 날짜는 다루지 않는다 — 호출부가 실시간 환율을 쓴다.
"""

from __future__ import annotations

from datetime import date, timedelta

import structlog

from app.utils.cache_keys import (
    TTL_USD_KRW_ON_DATE,
    TTL_USD_KRW_ON_DATE_RECENT,
    CacheStoreType,
    get_cached_json,
    set_cached_json,
    usd_krw_on_date_key,
)
from app.utils.kst import today_kst

logger = structlog.get_logger()

_FX_SYMBOL = "USDKRW=X"
# 연휴(설·추석·연말)가 겹쳐도 직전 거래일 종가가 들어오도록 넉넉히
_LOOKBACK_DAYS = 10
# 이보다 최근 날짜는 확정값으로 보지 않는다 — `USDKRW=X` 일봉 날짜는 KST와 어긋나 KST 새벽의 "어제" 일봉은 아직
# 장중이고, Yahoo가 하루 늦으면 전날 종가가 그날 값으로 온다. 7일 캐시하면 그 값이 굳는다(plans/157 A3)
_SETTLED_AFTER_DAYS = 4


def _sync_close_on_or_before(day: date) -> tuple[float, date] | None:
    from app.services.market_data.market_data_fetcher import fetch_yf_close_series

    # yfinance의 end는 배타적이다 — 그날 종가를 포함하려면 하루 뒤까지
    series = fetch_yf_close_series([_FX_SYMBOL], day - timedelta(days=_LOOKBACK_DAYS), day + timedelta(days=1)).get(
        _FX_SYMBOL
    )
    if series is None:
        return None
    series = series.dropna()
    candidates = [(idx.date(), float(value)) for idx, value in series.items() if idx.date() <= day and value > 0]
    if not candidates:
        return None
    rate_day, rate = max(candidates)
    return rate, rate_day


async def fetch_usd_krw_on(day: date, cache: CacheStoreType) -> tuple[float, date] | None:
    """(환율, 실제 종가 날짜). 조회 실패면 None — 호출부가 현재 환율로 대신하고 그 사실을 알린다."""
    key = usd_krw_on_date_key(day)
    cached = await get_cached_json(cache, key)
    if isinstance(cached, dict) and cached.get("rate"):
        return float(cached["rate"]), date.fromisoformat(cached["date"])

    from app.services.market_data.yahoo_price import run_yf_bounded

    try:
        found = await run_yf_bounded(_sync_close_on_or_before, day)
    except Exception as e:
        logger.warning("usd_krw_on_date_fetch_failed", day=day.isoformat(), error=str(e))
        return None
    if found is None:
        logger.warning("usd_krw_on_date_missing", day=day.isoformat())
        return None
    rate, rate_day = found
    settled = day <= today_kst() - timedelta(days=_SETTLED_AFTER_DAYS)
    ttl = TTL_USD_KRW_ON_DATE if settled else TTL_USD_KRW_ON_DATE_RECENT
    await set_cached_json(cache, key, {"rate": rate, "date": rate_day.isoformat()}, ttl)
    return rate, rate_day
