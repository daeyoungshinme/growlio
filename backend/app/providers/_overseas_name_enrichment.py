"""해외 포지션 종목명 영문 통일 헬퍼.

KIS/키움 브로커가 반환하는 해외 종목명은 한글(예: "QQQ 인베스코 ETF")인 반면 수동입력은
Yahoo Finance 검색을 거쳐 대부분 영문으로 저장된다. 병합 화면에서 같은 종목이 계좌 순서에
따라 한글/영문이 뒤섞여 보이는 문제를 막기 위해, 동기화 시점에 티커 기준으로 영문 캐노니컬
이름을 조회해 덮어쓴다. 조회 실패 시 브로커 원본 이름으로 폴백한다.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from app.services.stock_search_service import resolve_english_name
from app.utils.cache_keys import TTL_OVERSEAS_STOCK_NAME, overseas_stock_name_key

if TYPE_CHECKING:
    import redis.asyncio as aioredis


async def enrich_overseas_names(positions: list[dict], redis: aioredis.Redis) -> list[dict]:
    """해외 포지션 리스트의 name을 영문 캐노니컬 이름으로 교체한 새 리스트를 반환한다."""
    tickers = {p["ticker"] for p in positions}
    name_map: dict[str, str] = {}
    uncached: list[str] = []

    for ticker in tickers:
        cached = await redis.get(overseas_stock_name_key(ticker))
        if cached:
            name_map[ticker] = cached.decode() if isinstance(cached, bytes) else cached
        else:
            uncached.append(ticker)

    if uncached:
        resolved = await asyncio.gather(*(resolve_english_name(t) for t in uncached))
        for ticker, name in zip(uncached, resolved, strict=True):
            if name:
                name_map[ticker] = name
                await redis.setex(overseas_stock_name_key(ticker), TTL_OVERSEAS_STOCK_NAME, name)

    return [{**p, "name": name_map.get(p["ticker"], p["name"])} for p in positions]
