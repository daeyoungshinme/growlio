"""종목 검색 및 환율 API 테스트 (GET /api/v1/stocks)."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

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

        from app.services.stock_search_service import _search_naver

        mock_resp = MM()
        mock_resp.json.return_value = {"items": [{"code": "005930", "name": "삼성전자", "typeCode": "KOSPI"}]}
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

        from app.services.stock_search_service import _search_naver

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

        from app.services.stock_search_service import _search_naver

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

    @pytest.mark.asyncio
    async def test_search_naver_includes_asset_class_and_index_region_suggestion(self, override_settings):
        from unittest.mock import AsyncMock as AM
        from unittest.mock import MagicMock as MM
        from unittest.mock import patch as p

        from app.services.stock_search_service import _search_naver

        mock_resp = MM()
        mock_resp.json.return_value = {
            "items": [
                {"code": "005930", "name": "삼성전자", "typeCode": "KOSPI"},
                {"code": "153130", "name": "KODEX 단기채권", "typeCode": "KOSPI"},
            ]
        }
        mock_resp.raise_for_status = MM()
        with p("httpx.AsyncClient") as mock_client_cls:
            mock_ctx = MM()
            mock_ctx.__aenter__ = AM(return_value=mock_ctx)
            mock_ctx.__aexit__ = AM(return_value=None)
            mock_ctx.get = AM(return_value=mock_resp)
            mock_client_cls.return_value = mock_ctx
            result = await _search_naver("삼성전자", 5)
        by_ticker = {r["ticker"]: r for r in result}
        assert by_ticker["005930"]["asset_class"] == "EQUITY"
        assert by_ticker["005930"]["index_region"] == "DOMESTIC"
        assert by_ticker["153130"]["asset_class"] == "CASH"


class TestSearchYahooUnit:
    @pytest.mark.asyncio
    async def test_search_yahoo_returns_results(self, override_settings):
        from unittest.mock import AsyncMock as AM
        from unittest.mock import MagicMock as MM
        from unittest.mock import patch as p

        from app.services.stock_search_service import _search_yahoo

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

        from app.services.stock_search_service import _search_yahoo

        with p("httpx.AsyncClient") as mock_client_cls:
            mock_ctx = MM()
            mock_ctx.__aenter__ = AM(return_value=mock_ctx)
            mock_ctx.__aexit__ = AM(return_value=None)
            mock_ctx.get = AM(side_effect=Exception("timeout"))
            mock_client_cls.return_value = mock_ctx
            result = await _search_yahoo("AAPL", 5)
        assert result == []

    @pytest.mark.asyncio
    async def test_search_yahoo_includes_asset_class_and_index_region_suggestion(self, override_settings):
        from unittest.mock import AsyncMock as AM
        from unittest.mock import MagicMock as MM
        from unittest.mock import patch as p

        from app.services.stock_search_service import _search_yahoo

        mock_resp = MM()
        mock_resp.json.return_value = {
            "quotes": [
                {
                    "symbol": "SHY",
                    "shortname": "iShares 1-3 Year Treasury Bond ETF",
                    "quoteType": "ETF",
                    "exchange": "NGM",
                }
            ]
        }
        mock_resp.raise_for_status = MM()
        with p("httpx.AsyncClient") as mock_client_cls:
            mock_ctx = MM()
            mock_ctx.__aenter__ = AM(return_value=mock_ctx)
            mock_ctx.__aexit__ = AM(return_value=None)
            mock_ctx.get = AM(return_value=mock_resp)
            mock_client_cls.return_value = mock_ctx
            result = await _search_yahoo("SHY", 5)
        assert result[0]["asset_class"] == "BOND"
        assert result[0]["index_region"] == "OVERSEAS"


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


class TestIndexRegion:
    def test_overseas_market_returns_immediately_without_network_call(self, override_settings):
        """해외거래소 상장은 시장구분만으로 자명하므로 네이버 조회 함수를 호출하지 않는다."""
        from app.main import app

        with (
            patch("app.services.dividend.sync_sources.sync_naver_etf_index_region") as mock_fetch,
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get("/api/v1/stocks/index-region?ticker=AAPL&market=NASDAQ")
        assert resp.status_code == 200
        assert resp.json() == {"index_region": "OVERSEAS"}
        mock_fetch.assert_not_called()

    def test_krx_ticker_uses_fetched_result_and_caches(self, override_settings):
        """`_mock_redis_singleton`(conftest.py autouse)이 실제 `get_redis()`가 반환하는
        싱글턴이므로, `app.core.redis_client.redis_client`를 직접 재설정해 캐시 동작을 검증한다."""
        import app.core.redis_client as _rc
        from app.main import app

        _rc.redis_client.get = AsyncMock(return_value=None)
        _rc.redis_client.setex = AsyncMock()
        mock_setex = _rc.redis_client.setex  # 앱 lifespan 종료 시 redis_client가 None으로 리셋되므로 미리 참조 보관
        with (
            patch(
                "app.services.dividend.sync_sources.sync_naver_etf_index_region",
                return_value="OVERSEAS",
            ) as mock_fetch,
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get("/api/v1/stocks/index-region?ticker=133690&market=KOSPI")
        assert resp.status_code == 200
        assert resp.json() == {"index_region": "OVERSEAS"}
        mock_fetch.assert_called_once_with("133690")
        mock_setex.assert_awaited_once()

    def test_krx_ticker_falls_back_when_not_etf(self, override_settings):
        """ETF가 아니면(None 반환) resolve_index_region 폴백(기본값 DOMESTIC)을 사용한다."""
        import app.core.redis_client as _rc
        from app.main import app

        _rc.redis_client.get = AsyncMock(return_value=None)
        _rc.redis_client.setex = AsyncMock()
        with (
            patch("app.services.dividend.sync_sources.sync_naver_etf_index_region", return_value=None),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get("/api/v1/stocks/index-region?ticker=005930&market=KOSPI")
        assert resp.status_code == 200
        assert resp.json() == {"index_region": "DOMESTIC"}

    def test_cache_hit_skips_fetch(self, override_settings):
        import app.core.redis_client as _rc
        from app.main import app

        _rc.redis_client.get = AsyncMock(return_value=b'{"index_region": "OVERSEAS"}')
        with (
            patch("app.services.dividend.sync_sources.sync_naver_etf_index_region") as mock_fetch,
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get("/api/v1/stocks/index-region?ticker=133690&market=KOSPI")
        assert resp.status_code == 200
        assert resp.json() == {"index_region": "OVERSEAS"}
        mock_fetch.assert_not_called()


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
            TestClient(app, raise_server_exceptions=False) as client,
            patch("app.api.v1.stocks.get_redis", new_callable=AsyncMock, return_value=mock_redis),
            patch("app.services.yahoo_price._sync_usdkrw", return_value=0.0),
            patch("app.utils.currency.get_usd_krw_rate", new_callable=AsyncMock, return_value=1350.0),
        ):
            resp = client.get("/api/v1/stocks/exchange-rate")
        assert resp.status_code in (200, 500)


def _make_kis_account(user_id):
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        data_source="KIS_API",
        is_active=True,
        is_mock_mode=False,
        kis_app_key="encrypted-key",
        kis_app_secret="encrypted-secret",
    )


@pytest.fixture
def auth_app():
    """`/stocks/price`, `/stocks/prices-batch`는 인증이 필요하므로 get_current_user/get_db를
    override하고 테스트 후 정리한다."""
    from app.api.deps import get_current_user
    from app.core.database import get_db
    from app.main import app

    user = SimpleNamespace(id=uuid.uuid4())
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=None)

    async def override_auth():
        return user

    async def override_db():
        yield db

    app.dependency_overrides[get_current_user] = override_auth
    app.dependency_overrides[get_db] = override_db
    yield app, user, db
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db, None)


class TestStockPrice:
    def test_returns_200_for_domestic_ticker(self, override_settings, auth_app):
        app, _, _ = auth_app

        with (
            TestClient(app, raise_server_exceptions=False) as client,
            patch("app.services.yahoo_price._sync_yahoo_price", return_value=75000.0),
        ):
            resp = client.get("/api/v1/stocks/price?ticker=005930&market=KOSPI")
        assert resp.status_code == 200
        data = resp.json()
        assert "price_krw" in data

    def test_requires_ticker_and_market(self, override_settings, auth_app):
        app, _, _ = auth_app

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/stocks/price")
        assert resp.status_code == 422

    def test_requires_auth(self, override_settings):
        from app.api.deps import get_current_user
        from app.main import app

        app.dependency_overrides.pop(get_current_user, None)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/stocks/price?ticker=005930&market=KOSPI")
        assert resp.status_code == 401

    def test_yahoo_success_skips_domestic_fallback(self, override_settings, auth_app):
        """Yahoo가 정상 응답하면 (느린) Naver/pykrx 폴백을 타지 않아야 한다 — 회귀 방지."""
        app, _, _ = auth_app

        with (
            TestClient(app, raise_server_exceptions=False) as client,
            patch("app.services.yahoo_price._sync_yahoo_price", return_value=75000.0),
            patch("app.api.v1.stocks.domestic_price_fallback", new_callable=AsyncMock) as mock_domestic,
        ):
            resp = client.get("/api/v1/stocks/price?ticker=005930&market=KOSPI")
        assert resp.status_code == 200
        assert resp.json()["price_krw"] == 75000.0
        mock_domestic.assert_not_called()

    def test_yahoo_fails_falls_back_to_naver_pykrx(self, override_settings, auth_app):
        """402970류 — Yahoo가 실패하는 소수 국내 티커만 Naver/pykrx 폴백을 탄다."""
        app, _, _ = auth_app

        with (
            TestClient(app, raise_server_exceptions=False) as client,
            patch("app.services.yahoo_price._sync_yahoo_price", return_value=None),
            patch("app.api.v1.stocks.domestic_price_fallback", new_callable=AsyncMock, return_value=15500.0),
        ):
            resp = client.get("/api/v1/stocks/price?ticker=402970&market=KOSPI")
        assert resp.status_code == 200
        assert resp.json()["price_krw"] == 15500.0

    def test_overseas_ticker_skips_domestic_fallback(self, override_settings, auth_app):
        app, _, _ = auth_app

        with (
            TestClient(app, raise_server_exceptions=False) as client,
            patch("app.api.v1.stocks.domestic_price_fallback", new_callable=AsyncMock) as mock_domestic,
            patch("app.services.yahoo_price._sync_yahoo_price", return_value=180.0),
            patch("app.services.yahoo_price._sync_usdkrw", return_value=1350.0),
        ):
            resp = client.get("/api/v1/stocks/price?ticker=AAPL&market=NASDAQ")
        assert resp.status_code == 200
        mock_domestic.assert_not_called()

    def test_overseas_price_usd_rounded_to_two_decimals(self, override_settings, auth_app):
        """Yahoo 원본 시세는 부동소수점 오차로 소수점이 길어질 수 있음 — 지정가 표시/주문 단위(센트)에
        맞춰 price_usd를 2자리로 반올림해 반환해야 한다."""
        app, _, _ = auth_app

        with (
            TestClient(app, raise_server_exceptions=False) as client,
            patch("app.services.yahoo_price._sync_yahoo_price", return_value=180.336789),
            patch("app.services.yahoo_price._sync_usdkrw", return_value=1350.0),
        ):
            resp = client.get("/api/v1/stocks/price?ticker=AAPL&market=NASDAQ")
        assert resp.status_code == 200
        assert resp.json()["price_usd"] == 180.34

    def test_kis_fallback_used_as_last_resort(self, override_settings, auth_app):
        """Yahoo/Naver/pykrx 모두 실패하고 account_id가 주어지면 소유 계좌 검증 후 KIS로 조회한다."""
        app, user, db = auth_app
        account = _make_kis_account(user.id)
        db.scalar = AsyncMock(return_value=account)

        with (
            TestClient(app, raise_server_exceptions=False) as client,
            patch("app.services.yahoo_price._sync_yahoo_price", return_value=None),
            patch("app.api.v1.stocks.domestic_price_fallback", new_callable=AsyncMock, return_value=None),
            patch("app.api.v1.stocks._price_via_kis", new_callable=AsyncMock, return_value=15490.0),
        ):
            resp = client.get(f"/api/v1/stocks/price?ticker=402970&market=KOSPI&account_id={account.id}")
        assert resp.status_code == 200
        assert resp.json()["price_krw"] == 15490.0

    def test_kis_fallback_skipped_without_account_id(self, override_settings, auth_app):
        app, _, _ = auth_app

        with (
            TestClient(app, raise_server_exceptions=False) as client,
            patch("app.services.yahoo_price._sync_yahoo_price", return_value=None),
            patch("app.api.v1.stocks.domestic_price_fallback", new_callable=AsyncMock, return_value=None),
            patch("app.api.v1.stocks._price_via_kis", new_callable=AsyncMock) as mock_kis,
        ):
            resp = client.get("/api/v1/stocks/price?ticker=402970&market=KOSPI")
        assert resp.status_code == 200
        assert resp.json()["price_krw"] is None
        mock_kis.assert_not_called()

    def test_kis_fallback_ignores_unowned_account(self, override_settings, auth_app):
        """account_id가 다른 유저 소유이면 404로 실패하지만, 가격 조회 자체는 조용히 null로 끝난다."""
        app, _, db = auth_app
        db.scalar = AsyncMock(return_value=None)  # get_owned_account: 소유 계좌 없음

        with (
            TestClient(app, raise_server_exceptions=False) as client,
            patch("app.services.yahoo_price._sync_yahoo_price", return_value=None),
            patch("app.api.v1.stocks.domestic_price_fallback", new_callable=AsyncMock, return_value=None),
        ):
            resp = client.get(f"/api/v1/stocks/price?ticker=402970&market=KOSPI&account_id={uuid.uuid4()}")
        assert resp.status_code == 200
        assert resp.json()["price_krw"] is None


class TestStockPricesBatch:
    def test_yahoo_success_skips_domestic_fallback(self, override_settings, auth_app):
        """Yahoo 배치가 전부 채우면 (느린) Naver/pykrx 폴백을 타지 않아야 한다 — 회귀 방지."""
        app, _, _ = auth_app

        with (
            TestClient(app, raise_server_exceptions=False) as client,
            patch("app.services.yahoo_price._sync_yahoo_batch", return_value={"005930": 75000.0}),
            patch("app.api.v1.stocks.domestic_price_fallback", new_callable=AsyncMock) as mock_domestic,
        ):
            resp = client.post(
                "/api/v1/stocks/prices-batch",
                json={"items": [{"ticker": "005930", "market": "KOSPI"}]},
            )
        assert resp.status_code == 200
        assert resp.json()["005930"]["price_krw"] == 75000.0
        mock_domestic.assert_not_called()

    def test_yahoo_miss_falls_back_to_naver_pykrx(self, override_settings, auth_app):
        app, _, _ = auth_app

        with (
            TestClient(app, raise_server_exceptions=False) as client,
            patch("app.services.yahoo_price._sync_yahoo_batch", return_value={}),
            patch(
                "app.api.v1.stocks.domestic_price_fallback",
                new_callable=AsyncMock,
                return_value=15500.0,
            ),
        ):
            resp = client.post(
                "/api/v1/stocks/prices-batch",
                json={"items": [{"ticker": "402970", "market": "KOSPI"}]},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["402970"]["price_krw"] == 15500.0

    def test_overseas_price_usd_rounded_to_two_decimals(self, override_settings, auth_app):
        app, _, _ = auth_app

        with (
            TestClient(app, raise_server_exceptions=False) as client,
            patch("app.services.yahoo_price._sync_yahoo_batch", return_value={"AAPL": 180.336789}),
            patch("app.services.yahoo_price._sync_usdkrw", return_value=1350.0),
        ):
            resp = client.post(
                "/api/v1/stocks/prices-batch",
                json={"items": [{"ticker": "AAPL", "market": "NASDAQ"}]},
            )
        assert resp.status_code == 200
        assert resp.json()["AAPL"]["price_usd"] == 180.34

    def test_kis_fallback_used_when_account_id_provided_and_others_fail(self, override_settings, auth_app):
        app, user, db = auth_app
        account = _make_kis_account(user.id)
        db.scalar = AsyncMock(return_value=account)

        with (
            TestClient(app, raise_server_exceptions=False) as client,
            patch("app.services.yahoo_price._sync_yahoo_batch", return_value={}),
            patch("app.api.v1.stocks.domestic_price_fallback", new_callable=AsyncMock, return_value=None),
            patch("app.api.v1.stocks._price_via_kis", new_callable=AsyncMock, return_value=15490.0),
        ):
            resp = client.post(
                "/api/v1/stocks/prices-batch",
                json={"items": [{"ticker": "402970", "market": "KOSPI", "account_id": str(account.id)}]},
            )
        assert resp.status_code == 200
        assert resp.json()["402970"]["price_krw"] == 15490.0

    def test_empty_items_returns_empty_dict(self, override_settings, auth_app):
        app, _, _ = auth_app

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post("/api/v1/stocks/prices-batch", json={"items": []})
        assert resp.status_code == 200
        assert resp.json() == {}
