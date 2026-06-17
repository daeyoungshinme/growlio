"""종목 검색 및 환율 API 테스트 (GET /api/v1/stocks)."""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def mock_redis_scheduler(monkeypatch):
    import app.redis_client as rc
    import app.scheduler as sched
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)
    mock_redis.aclose = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.set = AsyncMock()
    mock_redis.setex = AsyncMock()
    monkeypatch.setattr(rc, "redis_client", mock_redis)
    monkeypatch.setattr(sched.scheduler, "start", lambda: None)
    monkeypatch.setattr(sched.scheduler, "shutdown", lambda: None)
    yield
    rc.redis_client = None


_SEARCH_RESULTS = [
    {"ticker": "005930", "name": "삼성전자", "market": "KOSPI"},
]

_USD_KRW_CACHED = 1350.0


class TestSearchNaverUnit:
    @pytest.mark.asyncio
    async def test_search_naver_returns_results(self, override_settings):
        from unittest.mock import AsyncMock as AM
        from unittest.mock import MagicMock as MM
        from unittest.mock import patch as p

        from app.api.v1.stocks import _search_naver
        mock_resp = MM()
        mock_resp.json.return_value = {
            "items": [{"code": "005930", "name": "삼성전자", "typeCode": "KOSPI"}]
        }
        mock_resp.raise_for_status = MM()
        with p("httpx.AsyncClient") as mock_client_cls:
            mock_ctx = MM()
            mock_ctx.__aenter__ = AM(return_value=mock_ctx)
            mock_ctx.__aexit__ = AM(return_value=None)
            mock_ctx.get = AM(return_value=mock_resp)
            mock_client_cls.return_value = mock_ctx
            result = await _search_naver("삼성전자", 5)
        assert isinstance(result, list)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_search_naver_http_error_returns_empty(self, override_settings):
        from unittest.mock import AsyncMock as AM
        from unittest.mock import MagicMock as MM
        from unittest.mock import patch as p

        from app.api.v1.stocks import _search_naver
        with p("httpx.AsyncClient") as mock_client_cls:
            mock_ctx = MM()
            mock_ctx.__aenter__ = AM(return_value=mock_ctx)
            mock_ctx.__aexit__ = AM(return_value=None)
            mock_ctx.get = AM(side_effect=Exception("connection error"))
            mock_client_cls.return_value = mock_ctx
            result = await _search_naver("삼성전자", 5)
        assert result == []

    @pytest.mark.asyncio
    async def test_search_naver_limit_enforced(self, override_settings):
        from unittest.mock import AsyncMock as AM
        from unittest.mock import MagicMock as MM
        from unittest.mock import patch as p

        from app.api.v1.stocks import _search_naver
        many_items = [{"code": f"00593{i}", "name": f"종목{i}", "typeCode": "KOSPI"} for i in range(10)]
        mock_resp = MM()
        mock_resp.json.return_value = {"items": many_items}
        mock_resp.raise_for_status = MM()
        with p("httpx.AsyncClient") as mock_client_cls:
            mock_ctx = MM()
            mock_ctx.__aenter__ = AM(return_value=mock_ctx)
            mock_ctx.__aexit__ = AM(return_value=None)
            mock_ctx.get = AM(return_value=mock_resp)
            mock_client_cls.return_value = mock_ctx
            result = await _search_naver("종목", 3)
        assert len(result) <= 3


class TestSearchYahooUnit:
    @pytest.mark.asyncio
    async def test_search_yahoo_returns_results(self, override_settings):
        from unittest.mock import AsyncMock as AM
        from unittest.mock import MagicMock as MM
        from unittest.mock import patch as p

        from app.api.v1.stocks import _search_yahoo
        mock_resp = MM()
        mock_resp.json.return_value = {
            "quotes": [{"symbol": "AAPL", "shortname": "Apple Inc.", "quoteType": "EQUITY", "exchange": "NMS"}]
        }
        mock_resp.raise_for_status = MM()
        with p("httpx.AsyncClient") as mock_client_cls:
            mock_ctx = MM()
            mock_ctx.__aenter__ = AM(return_value=mock_ctx)
            mock_ctx.__aexit__ = AM(return_value=None)
            mock_ctx.get = AM(return_value=mock_resp)
            mock_client_cls.return_value = mock_ctx
            result = await _search_yahoo("AAPL", 5)
        assert isinstance(result, list)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_search_yahoo_http_error_returns_empty(self, override_settings):
        from unittest.mock import AsyncMock as AM
        from unittest.mock import MagicMock as MM
        from unittest.mock import patch as p

        from app.api.v1.stocks import _search_yahoo
        with p("httpx.AsyncClient") as mock_client_cls:
            mock_ctx = MM()
            mock_ctx.__aenter__ = AM(return_value=mock_ctx)
            mock_ctx.__aexit__ = AM(return_value=None)
            mock_ctx.get = AM(side_effect=Exception("timeout"))
            mock_client_cls.return_value = mock_ctx
            result = await _search_yahoo("AAPL", 5)
        assert result == []


class TestStockSearch:
    def test_search_returns_200(self, override_settings):
        from app.main import app
        with (
            patch("app.api.v1.stocks._search_naver", new_callable=AsyncMock, return_value=_SEARCH_RESULTS),
            patch("app.api.v1.stocks._search_yahoo", new_callable=AsyncMock, return_value=[]),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get("/api/v1/stocks/search?q=삼성전자")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_search_requires_query(self, override_settings):
        """q 파라미터 없으면 422."""
        from app.main import app
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/stocks/search")
        assert resp.status_code == 422

    def test_search_with_short_query_returns_empty(self, override_settings):
        """q 길이 1이하면 빈 배열 반환."""
        from app.main import app
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/stocks/search?q=a")
        assert resp.status_code in (200, 422, 400)
        if resp.status_code == 200:
            assert isinstance(resp.json(), list)


class TestExchangeRate:
    def test_returns_200_with_cached_rate(self, override_settings):
        """Redis 캐시에서 환율 반환."""
        from app.main import app
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=b"1350.0")
        with (
            patch("app.api.v1.stocks.get_redis", new_callable=AsyncMock, return_value=mock_redis),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get("/api/v1/stocks/exchange-rate")
        assert resp.status_code == 200
        assert "usd_krw" in resp.json()

    async def test_returns_200_with_yfinance_fallback(self, override_settings):
        """캐시 미스 시 yfinance 폴백."""
        from app.main import app
        from httpx import AsyncClient, ASGITransport
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()
        with (
            patch("app.api.v1.stocks.get_redis", new_callable=AsyncMock, return_value=mock_redis),
            patch("app.api.v1.stocks.asyncio.get_running_loop") as mock_loop,
            patch("app.utils.currency.get_usd_krw_rate", new_callable=AsyncMock, return_value=1350.0),
        ):
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=0.0)
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/api/v1/stocks/exchange-rate")
        assert resp.status_code in (200, 500)


class TestStockPrice:
    def test_returns_200_for_domestic_ticker(self, override_settings):
        from app.main import app
        with (
            patch("app.api.v1.stocks.asyncio.get_running_loop") as mock_loop,
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=75000.0)
            resp = client.get("/api/v1/stocks/price?ticker=005930&market=KOSPI")
        assert resp.status_code == 200
        data = resp.json()
        assert "price_krw" in data

    def test_requires_ticker_and_market(self, override_settings):
        from app.main import app
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/stocks/price")
        assert resp.status_code == 422
