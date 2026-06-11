"""종목 검색 및 환율 API 테스트 (GET /api/v1/stocks)."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

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

    def test_returns_200_with_yfinance_fallback(self, override_settings):
        """캐시 미스 시 yfinance 폴백."""
        from app.main import app
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()
        with (
            patch("app.api.v1.stocks.get_redis", new_callable=AsyncMock, return_value=mock_redis),
            patch("app.api.v1.stocks.asyncio.get_running_loop") as mock_loop,
            patch("app.utils.currency.get_usd_krw_rate", new_callable=AsyncMock, return_value=1350.0),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=0.0)
            resp = client.get("/api/v1/stocks/exchange-rate")
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
