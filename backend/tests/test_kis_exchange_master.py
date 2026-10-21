"""KIS 아멕스 종목마스터 기반 NYSE Arca ETF 거래소 보정 (SPY·VOO·SCHD가 Yahoo PCX→"NYSE"로 저장되는 문제)."""

from __future__ import annotations

import io
import json
import zipfile
from unittest.mock import AsyncMock

import pytest
from pytest_httpx import HTTPXMock

from app.core.cache_store import CacheStore
from app.kis import exchange_master
from app.kis.constants import KIS_AMEX_MASTER_URL
from app.schemas.rebalancing import ExecutionOrderItem

# 실제 AMSMST.COD 행 형태(탭 구분, 거래소명은 cp949)
_MASTER_ROWS = (
    "US\t23\tAMS\t아멕스\tSPY\tAMSSPY\tSS SPDR S&P 500 TRUST\tSTATE STREET SPDR S&P 500 ETF\t3\tUSD\n"
    "US\t23\tAMS\t아멕스\tVOO\tAMSVOO\tVANGUARD S&P 500\tVANGUARD INDEX FUNDS S&P 500 ETF USD\t3\tUSD\n"
    "US\t23\tAMS\t아멕스\tSCHD\tAMSSCHD\tSCHWAB US DIVIDEND\tSCHWAB US DIVIDEND EQUITY ETF\t3\tUSD\n"
).encode("cp949")


def _master_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("AMSMST.COD", _MASTER_ROWS)
    return buf.getvalue()


def test_parse_master_symbols_reads_symbol_column():
    assert exchange_master.parse_master_symbols(_MASTER_ROWS + b"\nbroken-line\n") == {"SPY", "VOO", "SCHD"}


@pytest.mark.asyncio
async def test_downloads_once_then_serves_from_cache(httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=KIS_AMEX_MASTER_URL, content=_master_zip())
    cache = CacheStore()

    assert await exchange_master.resolve_kis_overseas_market("SPY", "NYSE", cache) == "AMEX"
    assert await exchange_master.resolve_kis_overseas_market("voo", "nyse", cache) == "AMEX"
    # 진짜 NYSE 상장 종목·다른 시장은 그대로
    assert await exchange_master.resolve_kis_overseas_market("KO", "NYSE", cache) == "NYSE"
    assert await exchange_master.resolve_kis_overseas_market("QQQ", "NASDAQ", cache) == "NASDAQ"

    assert len(httpx_mock.get_requests()) == 1


@pytest.mark.asyncio
async def test_download_failure_keeps_stored_market(httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=KIS_AMEX_MASTER_URL, status_code=503)

    assert await exchange_master.resolve_kis_overseas_market("SPY", "NYSE", CacheStore()) == "NYSE"


@pytest.mark.asyncio
async def test_non_nyse_market_skips_master_lookup(monkeypatch):
    download = AsyncMock()
    monkeypatch.setattr(exchange_master, "_download_amex_master", download)

    assert await exchange_master.resolve_kis_overseas_market("005930", "KOSPI", None) == "KOSPI"
    download.assert_not_awaited()


def _order(ticker: str, market: str, side: str = "BUY") -> ExecutionOrderItem:
    return ExecutionOrderItem(
        ticker=ticker,
        name=ticker,
        market=market,
        side=side,
        quantity=1,
        account_id="acc",
    )


@pytest.mark.asyncio
async def test_kis_execution_normalizes_arca_etf_markets():
    from app.services.rebalancing import execution_service

    cache = CacheStore()
    from app.utils.cache_keys import kis_amex_master_key

    await cache.setex(kis_amex_master_key(), 60, json.dumps(["SPY", "VOO"]))

    orders = [_order("SPY", "NYSE", "SELL"), _order("KO", "NYSE"), _order("QQQ", "NASDAQ"), _order("VOO", "NYSE")]
    normalized = await execution_service._normalize_kis_overseas_markets(orders, cache)

    assert [o.market for o in normalized] == ["AMEX", "NYSE", "NASDAQ", "AMEX"]
    assert orders[0].market == "NYSE"  # 원본 불변


@pytest.mark.asyncio
async def test_overseas_quote_uses_3_letter_excd(httpx_mock: HTTPXMock, monkeypatch):
    from app.kis import client as kis_client
    from app.kis.overseas_quote import get_overseas_price

    monkeypatch.setattr(kis_client._rate_limiter, "acquire", AsyncMock())
    httpx_mock.add_response(json={"rt_cd": "0", "output": {"last": "700.5", "rate": "1400"}})

    result = await get_overseas_price("k", "s", "t", "SPY", "AMEX", is_mock=False)

    request = httpx_mock.get_requests()[0]
    assert request.url.params["EXCD"] == "AMS"
    assert result["price_usd"] == 700.5
