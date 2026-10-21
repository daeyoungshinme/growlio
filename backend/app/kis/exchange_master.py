"""KIS 해외 종목마스터 기반 상장 거래소 보정.

Yahoo는 NYSE Arca 상장 ETF(SPY·VOO·SCHD 등)를 PCX로 주고 `stock_search_service`가 이를 "NYSE"로
정규화해 PortfolioItem/Position에 저장한다. 키움은 이 종목들을 NYSE로 분류해 그대로 맞지만, KIS는
아멕스(AMS)로 분류하므로 OVRS_EXCG_CD="NYSE"로 보내면 주문이 거부되고, 잔고(AMEX)와 주문(NYSE)의
ticker+market 키가 어긋나 매도 clamp에서 SKIPPED가 된다. KIS 공식 아멕스 마스터 파일로 보정한다.
"""

from __future__ import annotations

import io
import zipfile
from typing import TYPE_CHECKING

import httpx
import structlog

from app.kis.constants import KIS_AMEX_MASTER_URL
from app.utils.cache_keys import TTL_KIS_AMEX_MASTER, get_cached_json, kis_amex_master_key, set_cached_json

if TYPE_CHECKING:
    from app.core.cache_store import CacheStore

logger = structlog.get_logger()

_SYMBOL_FIELD_INDEX = 4  # 탭 구분: 국가, 거래소ID, 거래소코드, 거래소명, 심볼, ...


def parse_master_symbols(raw: bytes) -> frozenset[str]:
    """KIS 해외 종목마스터(.cod, 탭 구분·cp949) 본문에서 심볼 집합을 뽑는다."""
    symbols: set[str] = set()
    for line in raw.splitlines():
        fields = line.split(b"\t")
        if len(fields) > _SYMBOL_FIELD_INDEX:
            symbol = fields[_SYMBOL_FIELD_INDEX].strip().decode("ascii", errors="ignore").upper()
            if symbol:
                symbols.add(symbol)
    return frozenset(symbols)


async def _download_amex_master() -> frozenset[str]:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(KIS_AMEX_MASTER_URL)
        resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        name = zf.namelist()[0]
        return parse_master_symbols(zf.read(name))


async def get_kis_amex_tickers(cache: CacheStore | None) -> frozenset[str]:
    """KIS가 아멕스(AMS)로 분류하는 티커 집합. 다운로드 실패 시 빈 집합(보정 없이 기존 market 유지)."""
    cached = await get_cached_json(cache, kis_amex_master_key())
    if cached:
        return frozenset(cached)
    try:
        symbols = await _download_amex_master()
    except Exception as exc:
        logger.warning("kis_amex_master_download_failed", error=str(exc))
        return frozenset()
    if symbols:
        await set_cached_json(cache, kis_amex_master_key(), sorted(symbols), TTL_KIS_AMEX_MASTER)
    return symbols


async def resolve_kis_overseas_market(ticker: str, market: str, cache: CacheStore | None) -> str:
    """KIS 주문/시세용 상장 시장을 반환한다 — "NYSE"로 저장됐지만 KIS 아멕스 마스터에 있으면 "AMEX"."""
    if market.upper() != "NYSE":
        return market
    if ticker.upper() in await get_kis_amex_tickers(cache):
        return "AMEX"
    return market
