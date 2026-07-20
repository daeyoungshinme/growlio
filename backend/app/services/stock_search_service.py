"""종목명·티커 검색 — 네이버 금융(한글)/Yahoo Finance(영문·티커) 연동."""

import re

import httpx
import structlog

from app.services.recommendation_universe import guess_asset_class, resolve_index_region

logger = structlog.get_logger()

EXCHANGE_TO_MARKET: dict[str, str] = {
    "KSC": "KOSPI",
    "KOE": "KOSDAQ",
    "NMS": "NASDAQ",
    "NGM": "NASDAQ",
    "NCM": "NASDAQ",
    "NYQ": "NYSE",
    "PCX": "NYSE",
    "ASE": "AMEX",
}

_KOREAN_RE = re.compile(r"[가-힣]")


def _has_korean(text: str) -> bool:
    return bool(_KOREAN_RE.search(text))


async def _search_naver(q: str, limit: int) -> list[dict]:
    """네이버 금융 자동완성 — 한글 종목명 검색용."""
    url = "https://ac.stock.naver.com/ac"
    params = {"q": q, "target": "stock,index"}
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        logger.warning("naver_search_failed", q=q, error=str(e))
        return []

    results = []
    for item in data.get("items", []):
        type_code = item.get("typeCode", "")
        market = type_code if type_code in ("KOSPI", "KOSDAQ") else type_code
        ticker = item.get("code", "")
        name = item.get("name", "")
        results.append(
            {
                "ticker": ticker,
                "name": name,
                "market": market,
                "exchange": type_code,
                "asset_class": guess_asset_class(name),
                "index_region": resolve_index_region(ticker, market, None),
            }
        )
        if len(results) >= limit:
            break
    return results


async def _search_yahoo(q: str, limit: int) -> list[dict]:
    """Yahoo Finance 검색 — 영문명·티커 검색용."""
    url = "https://query1.finance.yahoo.com/v1/finance/search"
    params: dict[str, str | int] = {"q": q, "quotesCount": limit, "newsCount": 0, "listsCount": 0}
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(url, params=params, headers=headers)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        logger.warning("yahoo_search_failed", q=q, error=str(e))
        return []

    results = []
    for item in data.get("quotes", []):
        if item.get("quoteType") not in ("EQUITY", "ETF"):
            continue
        exchange = item.get("exchange", "")
        market = EXCHANGE_TO_MARKET.get(exchange, exchange)
        symbol: str = item.get("symbol", "")
        ticker = symbol.removesuffix(".KS").removesuffix(".KQ")
        name = item.get("shortname") or item.get("longname") or symbol
        results.append(
            {
                "ticker": ticker,
                "name": name,
                "market": market,
                "exchange": exchange,
                "asset_class": guess_asset_class(name),
                "index_region": resolve_index_region(ticker, market, None),
            }
        )
        if len(results) >= limit:
            break
    return results


async def resolve_english_name(ticker: str) -> str | None:
    """티커로 Yahoo Finance를 조회해 영문 캐노니컬 종목명을 반환한다. 정확히 일치하는 결과가
    없으면 None (브로커 원본 이름으로 폴백하도록 호출부에서 처리)."""
    results = await _search_yahoo(ticker, limit=5)
    for r in results:
        if r["ticker"].upper() == ticker.upper():
            return r["name"]
    return None
