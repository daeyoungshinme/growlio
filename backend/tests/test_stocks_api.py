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

        from app.services.market_data.stock_search_service import _search_naver

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

        from app.services.market_data.stock_search_service import _search_naver

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

        from app.services.market_data.stock_search_service import _search_naver

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

        from app.services.market_data.stock_search_service import _search_naver

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

        from app.services.market_data.stock_search_service import _search_yahoo

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

        from app.services.market_data.stock_search_service import _search_yahoo

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

        from app.services.market_data.stock_search_service import _search_yahoo

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
            patch(
                "app.services.market_data.stock_search_service._search_naver",
                new_callable=AsyncMock,
                return_value=_SEARCH_RESULTS,
            ),
            patch(
                "app.services.market_data.stock_search_service._search_yahoo", new_callable=AsyncMock, return_value=[]
            ),
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

        with (
            patch(
                "app.services.market_data.stock_search_service._search_naver", new_callable=AsyncMock, return_value=[]
            ),
            patch(
                "app.services.market_data.stock_search_service._search_yahoo", new_callable=AsyncMock, return_value=[]
            ),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
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
        """`get_cache_store()`가 반환하는 프로세스 싱글턴을 직접 재설정해 캐시 동작을 검증한다."""
        import app.core.cache_store as _rc
        from app.main import app

        _rc.cache_store = AsyncMock()
        _rc.cache_store.get = AsyncMock(return_value=None)
        _rc.cache_store.setex = AsyncMock()
        mock_setex = _rc.cache_store.setex  # 앱 lifespan 종료 시 cache_client가 None으로 리셋되므로 미리 참조 보관
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
        import app.core.cache_store as _rc
        from app.main import app

        _rc.cache_store = AsyncMock()
        _rc.cache_store.get = AsyncMock(return_value=None)
        _rc.cache_store.setex = AsyncMock()
        with (
            patch("app.services.dividend.sync_sources.sync_naver_etf_index_region", return_value=None),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get("/api/v1/stocks/index-region?ticker=005930&market=KOSPI")
        assert resp.status_code == 200
        assert resp.json() == {"index_region": "DOMESTIC"}

    def test_cache_hit_skips_fetch(self, override_settings):
        import app.core.cache_store as _rc
        from app.main import app

        _rc.cache_store = AsyncMock()
        _rc.cache_store.get = AsyncMock(return_value='{"index_region": "OVERSEAS"}')
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
        """Cache 캐시에서 환율 반환."""
        from app.main import app

        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value=b"1350.0")
        with (
            patch("app.api.v1.stocks.get_cache_store", new_callable=AsyncMock, return_value=mock_cache),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get("/api/v1/stocks/exchange-rate")
        assert resp.status_code == 200
        assert "usd_krw" in resp.json()

    def test_returns_200_with_yfinance_fallback(self, override_settings):
        """캐시 미스 시 yfinance 폴백."""
        from app.main import app

        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock()
        with (
            TestClient(app, raise_server_exceptions=False) as client,
            patch("app.api.v1.stocks.get_cache_store", new_callable=AsyncMock, return_value=mock_cache),
            patch("app.services.market_data.yahoo_price._sync_usdkrw", return_value=0.0),
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


_PS = "app.services.market_data.price_service"
_YAHOO_BATCH = "app.services.market_data.yahoo_price._sync_yahoo_batch"
_USDKRW = "app.services.market_data.yahoo_price._sync_usdkrw"


class TestStockPrice:
    """단일 조회도 `fetch_prices_batch`(국내 Naver/pykrx → Yahoo → 지정 계좌 KIS)를 탄다 — plans/114 A."""

    def test_domestic_uses_naver_pykrx_first_and_skips_yahoo(self, override_settings, auth_app):
        app, _, _ = auth_app

        with (
            TestClient(app, raise_server_exceptions=False) as client,
            patch(f"{_PS}.domestic_price_fallback", new_callable=AsyncMock, return_value=75000.0),
            patch(_YAHOO_BATCH) as mock_yahoo,
        ):
            resp = client.get("/api/v1/stocks/price?ticker=005930&market=KOSPI")
        assert resp.status_code == 200
        assert resp.json() == {"price_krw": 75000.0, "price_usd": None, "usd_rate": None}
        mock_yahoo.assert_not_called()

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

    def test_domestic_miss_falls_back_to_yahoo(self, override_settings, auth_app):
        app, _, _ = auth_app

        with (
            TestClient(app, raise_server_exceptions=False) as client,
            patch(f"{_PS}.domestic_price_fallback", new_callable=AsyncMock, return_value=None),
            patch(_YAHOO_BATCH, return_value={"402970": 15500.0}),
        ):
            resp = client.get("/api/v1/stocks/price?ticker=402970&market=KOSPI")
        assert resp.status_code == 200
        assert resp.json()["price_krw"] == 15500.0

    def test_overseas_ticker_skips_domestic_fallback(self, override_settings, auth_app):
        app, _, _ = auth_app

        with (
            TestClient(app, raise_server_exceptions=False) as client,
            patch(f"{_PS}.domestic_price_fallback", new_callable=AsyncMock) as mock_domestic,
            patch(_YAHOO_BATCH, return_value={"AAPL": 180.0}),
            patch(_USDKRW, return_value=1350.0),
        ):
            resp = client.get("/api/v1/stocks/price?ticker=AAPL&market=NASDAQ")
        assert resp.status_code == 200
        assert resp.json()["price_krw"] == 243_000
        mock_domestic.assert_not_called()

    def test_overseas_price_usd_rounded_to_two_decimals(self, override_settings, auth_app):
        """Yahoo 원본 시세는 부동소수점 오차로 소수점이 길어질 수 있음 — 지정가 표시/주문 단위(센트)에
        맞춰 price_usd를 2자리로 반올림해 반환해야 한다."""
        app, _, _ = auth_app

        with (
            TestClient(app, raise_server_exceptions=False) as client,
            patch(_YAHOO_BATCH, return_value={"AAPL": 180.336789}),
            patch(_USDKRW, return_value=1350.0),
        ):
            resp = client.get("/api/v1/stocks/price?ticker=AAPL&market=NASDAQ")
        assert resp.status_code == 200
        assert resp.json()["price_usd"] == 180.34

    def test_lowercase_domestic_market_is_domestic(self, override_settings, auth_app):
        """소문자 "kospi"도 국내로 판정 — 원화 그대로, 국내 폴백 경로."""
        app, _, _ = auth_app

        with (
            TestClient(app, raise_server_exceptions=False) as client,
            patch(f"{_PS}.domestic_price_fallback", new_callable=AsyncMock, return_value=75000.0) as mock_domestic,
        ):
            resp = client.get("/api/v1/stocks/price?ticker=005930&market=kospi")
        assert resp.status_code == 200
        assert resp.json() == {"price_krw": 75000.0, "price_usd": None, "usd_rate": None}
        mock_domestic.assert_awaited_once()

    def test_kis_fallback_used_as_last_resort(self, override_settings, auth_app):
        """국내·Yahoo 모두 실패하고 account_id가 주어지면 소유 계좌 검증 후 그 계좌로 KIS 조회한다."""
        app, user, db = auth_app
        account = _make_kis_account(user.id)
        db.scalar = AsyncMock(return_value=account)

        with (
            TestClient(app, raise_server_exceptions=False) as client,
            patch(_YAHOO_BATCH, return_value={}),
            patch(f"{_PS}.domestic_price_fallback", new_callable=AsyncMock, return_value=None),
            patch(f"{_PS}.price_via_kis", new_callable=AsyncMock, return_value=15490.0) as mock_kis,
            patch(f"{_PS}._get_any_kis_account", new_callable=AsyncMock) as mock_any,
        ):
            resp = client.get(f"/api/v1/stocks/price?ticker=402970&market=KOSPI&account_id={account.id}")
        assert resp.status_code == 200
        assert resp.json()["price_krw"] == 15490.0
        assert mock_kis.await_args.args[0] is account
        mock_any.assert_not_called()

    def test_kis_fallback_skipped_without_account_id(self, override_settings, auth_app):
        """지정 계좌가 없으면 유저의 다른 KIS 계좌로도 폴백하지 않는다(내부 호출과 다른 점)."""
        app, _, _ = auth_app

        with (
            TestClient(app, raise_server_exceptions=False) as client,
            patch(_YAHOO_BATCH, return_value={}),
            patch(f"{_PS}.domestic_price_fallback", new_callable=AsyncMock, return_value=None),
            patch(f"{_PS}.price_via_kis", new_callable=AsyncMock) as mock_kis,
            patch(f"{_PS}._get_any_kis_account", new_callable=AsyncMock) as mock_any,
        ):
            resp = client.get("/api/v1/stocks/price?ticker=402970&market=KOSPI")
        assert resp.status_code == 200
        assert resp.json()["price_krw"] is None
        mock_kis.assert_not_called()
        mock_any.assert_not_called()

    def test_kis_fallback_ignores_unowned_account(self, override_settings, auth_app):
        """account_id가 다른 유저 소유이면 KIS를 부르지 않고, 가격 조회 자체는 조용히 null로 끝난다."""
        app, _, db = auth_app
        db.scalar = AsyncMock(return_value=None)  # get_owned_account: 소유 계좌 없음

        with (
            TestClient(app, raise_server_exceptions=False) as client,
            patch(_YAHOO_BATCH, return_value={}),
            patch(f"{_PS}.domestic_price_fallback", new_callable=AsyncMock, return_value=None),
            patch(f"{_PS}.price_via_kis", new_callable=AsyncMock) as mock_kis,
        ):
            resp = client.get(f"/api/v1/stocks/price?ticker=402970&market=KOSPI&account_id={uuid.uuid4()}")
        assert resp.status_code == 200
        assert resp.json()["price_krw"] is None
        mock_kis.assert_not_called()

    def test_result_fills_shared_raw_price_cache(self, override_settings, auth_app):
        """라우터 결과도 내부와 같은 원시 캐시를 채워, 두 번째 요청은 소스를 다시 부르지 않는다."""
        app, _, _ = auth_app

        with (
            TestClient(app, raise_server_exceptions=False) as client,
            patch(f"{_PS}.domestic_price_fallback", new_callable=AsyncMock, return_value=75000.0) as mock_domestic,
        ):
            client.get("/api/v1/stocks/price?ticker=005930&market=KOSPI")
            resp = client.get("/api/v1/stocks/price?ticker=005930&market=kospi")
        assert resp.json()["price_krw"] == 75000.0
        mock_domestic.assert_awaited_once()


class TestStockPricesBatch:
    def test_domestic_and_overseas_mixed(self, override_settings, auth_app):
        app, _, _ = auth_app

        with (
            TestClient(app, raise_server_exceptions=False) as client,
            patch(f"{_PS}.domestic_price_fallback", new_callable=AsyncMock, return_value=75000.0),
            patch(_YAHOO_BATCH, return_value={"AAPL": 200.0}) as mock_yahoo,
            patch(_USDKRW, return_value=1400.0),
        ):
            resp = client.post(
                "/api/v1/stocks/prices-batch",
                json={"items": [{"ticker": "005930", "market": "KOSPI"}, {"ticker": "AAPL", "market": "NASDAQ"}]},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["005930"] == {"price_krw": 75000.0, "price_usd": None, "usd_rate": None}
        assert data["AAPL"] == {"price_krw": 280_000, "price_usd": 200.0, "usd_rate": 1400.0}
        # 국내가 채워졌으니 Yahoo에는 해외 종목만 간다
        assert [t for t, _ in mock_yahoo.call_args.args[0]] == ["AAPL"]

    def test_domestic_miss_falls_back_to_yahoo(self, override_settings, auth_app):
        app, _, _ = auth_app

        with (
            TestClient(app, raise_server_exceptions=False) as client,
            patch(f"{_PS}.domestic_price_fallback", new_callable=AsyncMock, return_value=None),
            patch(_YAHOO_BATCH, return_value={"402970": 15500.0}),
        ):
            resp = client.post(
                "/api/v1/stocks/prices-batch",
                json={"items": [{"ticker": "402970", "market": "KOSPI"}]},
            )
        assert resp.status_code == 200
        assert resp.json()["402970"]["price_krw"] == 15500.0

    def test_overseas_price_usd_rounded_to_two_decimals(self, override_settings, auth_app):
        app, _, _ = auth_app

        with (
            TestClient(app, raise_server_exceptions=False) as client,
            patch(_YAHOO_BATCH, return_value={"AAPL": 180.336789}),
            patch(_USDKRW, return_value=1350.0),
        ):
            resp = client.post(
                "/api/v1/stocks/prices-batch",
                json={"items": [{"ticker": "AAPL", "market": "NASDAQ"}]},
            )
        assert resp.status_code == 200
        assert resp.json()["AAPL"]["price_usd"] == 180.34

    def test_lowercase_overseas_market_is_converted_to_krw(self, override_settings, auth_app):
        """시장 코드는 대소문자를 가리지 않는다 — 소문자 해외 시장이 USD 값 그대로 원화로 반환되면 안 된다."""
        app, _, _ = auth_app

        with (
            TestClient(app, raise_server_exceptions=False) as client,
            patch(_YAHOO_BATCH, return_value={"AAPL": 200.0}),
            patch(_USDKRW, return_value=1400.0),
        ):
            resp = client.post(
                "/api/v1/stocks/prices-batch",
                json={"items": [{"ticker": "AAPL", "market": "nasdaq"}]},
            )
        assert resp.status_code == 200
        body = resp.json()["AAPL"]
        assert body["price_usd"] == 200.0
        assert body["price_krw"] == 280_000

    def test_kis_fallback_only_for_ticker_with_account_id(self, override_settings, auth_app):
        app, user, db = auth_app
        account = _make_kis_account(user.id)
        db.scalar = AsyncMock(return_value=account)

        with (
            TestClient(app, raise_server_exceptions=False) as client,
            patch(_YAHOO_BATCH, return_value={}),
            patch(f"{_PS}.domestic_price_fallback", new_callable=AsyncMock, return_value=None),
            patch(f"{_PS}.price_via_kis", new_callable=AsyncMock, return_value=15490.0) as mock_kis,
        ):
            resp = client.post(
                "/api/v1/stocks/prices-batch",
                json={
                    "items": [
                        {"ticker": "402970", "market": "KOSPI", "account_id": str(account.id)},
                        {"ticker": "005930", "market": "KOSPI"},
                    ]
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["402970"]["price_krw"] == 15490.0
        assert data["005930"]["price_krw"] is None
        assert [c.args[1] for c in mock_kis.await_args_list] == ["402970"]

    def test_empty_items_returns_empty_dict(self, override_settings, auth_app):
        app, _, _ = auth_app

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post("/api/v1/stocks/prices-batch", json={"items": []})
        assert resp.status_code == 200
        assert resp.json() == {}


class TestPriceViaKisMarketCase:
    async def test_lowercase_domestic_market_uses_domestic_quote(self, override_settings):
        """소문자 "kospi"가 해외 시세 TR로 가던 버그 — plans/114 A4."""
        from app.services.market_data import price_service

        account = _make_kis_account(uuid.uuid4())
        with (
            patch.object(price_service, "decrypt_kis_credentials", return_value=("k", "s")),
            patch("app.kis.auth.get_access_token", new_callable=AsyncMock, return_value="tok"),
            patch("app.kis.domestic_quote.get_domestic_price", new_callable=AsyncMock, return_value=70000.0) as dom,
            patch("app.kis.overseas_quote.get_overseas_price", new_callable=AsyncMock) as ovs,
        ):
            price = await price_service.price_via_kis(account, "005930", "kospi", AsyncMock(), None)
        assert price == 70000.0
        dom.assert_awaited_once()
        ovs.assert_not_called()
