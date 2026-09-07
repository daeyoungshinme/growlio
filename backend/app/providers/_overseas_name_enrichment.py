"""해외 포지션 메타데이터(영문명·상장 시장) 보강 헬퍼.

두 가지 불일치를 동기화 시점에 바로잡는다:

1. **종목명 한/영 혼재** — KIS/키움/토스가 반환하는 해외 종목명은 한글(예: "QQQ 인베스코
   ETF")인 반면 수동입력은 Yahoo Finance 검색을 거쳐 대부분 영문으로 저장된다.
2. **상장 시장 미확정** — 키움 `ust21070`은 거래소를 신뢰성 있게 주지 않아(`stex_nm`이
   항상 "미국") `"US"` 센티널로 들어온다. 그대로 두면 같은 종목이 계좌마다 다른 market으로
   저장돼 `position_aggregator`의 `"{ticker}-{market}"` 매칭 키가 어긋난다.

티커 기준으로 Yahoo Finance에서 영문 캐노니컬 이름과 시장을 조회해 보강하고 티커당 7일
캐싱한다(회사명·상장 거래소는 사실상 불변). 조회 실패 시 이름은 브로커 원본을, 시장은
NASDAQ을 폴백으로 쓴다 — `"US"` 센티널이 그대로 Position까지 흘러가면 `is_overseas_market()`
이 국내로 오판(주문 실행 경로 오동작)하므로 항상 유효 미국 시장으로 확정한다.

브로커가 이미 확정한 시장(KIS는 거래소별 조회라 NYSE/NASDAQ/AMEX가 정확)은 건드리지 않는다.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from app.services.stock_search_service import resolve_ticker_meta
from app.utils.cache_keys import (
    TTL_OVERSEAS_STOCK_META,
    get_cached_json,
    overseas_stock_meta_key,
    set_cached_json,
)

if TYPE_CHECKING:
    from app.core.cache_store import CacheStore

# 브로커가 해외 상장 시장을 확정하지 못했음을 나타내는 센티널 (키움 balance.py / 토스 balance.py).
UNRESOLVED_MARKET = "US"
_FALLBACK_MARKET = "NASDAQ"
_VALID_US_MARKETS = {"NYSE", "NASDAQ", "AMEX"}


def _needs_market_resolution(market: str | None) -> bool:
    return (market or "").strip().upper() in {"", UNRESOLVED_MARKET}


async def enrich_overseas_positions(positions: list[dict], cache: CacheStore) -> list[dict]:
    """해외 포지션 리스트의 name·market을 보강한 새 리스트를 반환한다.

    - name: 조회 성공 시 영문 캐노니컬 이름으로 교체(실패 시 브로커 원본 유지).
    - market: `_needs_market_resolution`(빈 값 또는 "US" 센티널)인 경우에만 조회 시장으로
      채운다(실패 시 NASDAQ 폴백). 브로커가 확정한 시장은 그대로 둔다.
    """
    tickers = {p["ticker"] for p in positions}
    meta: dict[str, dict[str, str | None]] = {}
    uncached: list[str] = []

    for ticker in tickers:
        cached = await get_cached_json(cache, overseas_stock_meta_key(ticker))
        if cached:
            meta[ticker] = cached
        else:
            uncached.append(ticker)

    if uncached:
        resolved = await asyncio.gather(*(resolve_ticker_meta(t) for t in uncached))
        for ticker, (name, market) in zip(uncached, resolved, strict=True):
            norm_market = market if market in _VALID_US_MARKETS else None
            entry: dict[str, str | None] = {"name": name, "market": norm_market}
            meta[ticker] = entry
            if name or norm_market:
                await set_cached_json(cache, overseas_stock_meta_key(ticker), entry, TTL_OVERSEAS_STOCK_META)

    enriched: list[dict] = []
    for p in positions:
        m = meta.get(p["ticker"], {})
        name = m.get("name") or p["name"]
        if _needs_market_resolution(p.get("market")):
            market = m.get("market") or _FALLBACK_MARKET
        else:
            market = p["market"]
        enriched.append({**p, "name": name, "market": market})
    return enriched
