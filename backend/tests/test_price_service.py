"""price_service 단위 테스트 — Yahoo Finance 우선순위 체인 검증."""

import pytest

from app.services.yahoo_price import to_yf_symbol as _to_yahoo_symbol

# ── Yahoo 심볼 변환 테스트 ──────────────────────────────────


class TestToYahooSymbol:
    """_to_yahoo_symbol: 시장별 티커 변환 로직."""

    @pytest.mark.parametrize(
        ("ticker", "market", "expected"),
        [
            ("005930", "KOSPI", "005930.KS"),
            ("5930", "KOSPI", "005930.KS"),  # zero-padding
            ("5930", "KRX", "005930.KS"),
            ("035720", "KOSDAQ", "035720.KQ"),
            ("35720", "KOSDAQ", "035720.KQ"),  # zero-padding
            ("AAPL", "NYSE", "AAPL"),  # 해외: 그대로
            ("TSLA", "NASDAQ", "TSLA"),
            ("NVDA", "nasdaq", "NVDA"),  # 소문자 market도 처리
        ],
    )
    def test_symbol_conversion(self, ticker, market, expected):
        assert _to_yahoo_symbol(ticker, market) == expected


# ── fetch_current_price 우선순위 체인 테스트 ────────────────


class TestFetchCurrentPrice:
    """Yahoo 실패 → KIS → LS 순서로 fallback 되는지 검증."""

    @pytest.mark.asyncio
    async def test_returns_yahoo_price_when_available(self, mock_db, mock_cache, override_settings):
        """Yahoo Finance 가격 조회 성공 시 바로 반환."""
        import uuid
        from unittest.mock import AsyncMock, patch

        user_id = uuid.uuid4()

        with (
            patch("app.services.price_service.domestic_price_fallback", new=AsyncMock(return_value=None)),
            patch("app.services.price_service._sync_yahoo_price", return_value=75000.0),
            patch("asyncio.get_event_loop") as mock_loop,
        ):
            mock_executor = AsyncMock(return_value=75000.0)
            mock_loop.return_value.run_in_executor = mock_executor

            from app.services.price_service import fetch_current_price

            # DB 조회 없이 Yahoo가 성공하면 DB 없어도 됨
            # (실제 내부 구현상 DB 조회 후 KIS/LS 체인이므로 mock 필요)
            mock_db.scalar.return_value = None  # UserSettings 없음 → KIS/LS skip

            price = await fetch_current_price(user_id, "005930", "KOSPI", mock_db, mock_cache)
            # Yahoo가 성공했으므로 75000 반환
            assert price == 75000.0

    @pytest.mark.asyncio
    async def test_returns_none_when_all_providers_fail(self, mock_db, mock_cache, override_settings):
        """모든 provider 실패 시 None 반환 (예외 없음)."""
        import uuid
        from unittest.mock import AsyncMock, patch

        user_id = uuid.uuid4()
        mock_db.scalar.return_value = None  # UserSettings 없음

        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=None)

            from app.services.price_service import fetch_current_price

            price = await fetch_current_price(user_id, "UNKNOWN", "NYSE", mock_db, mock_cache)
            assert price is None


# ── 배치 조회 테스트 ────────────────────────────────────────


class TestFetchPricesBatch:
    """fetch_prices_batch: 여러 종목 일괄 조회."""

    @pytest.mark.asyncio
    async def test_empty_tickers_returns_empty(self, mock_db, mock_cache, override_settings):
        """빈 목록 입력 시 빈 딕셔너리 반환."""
        import uuid

        from app.services.price_service import fetch_prices_batch

        result = await fetch_prices_batch(uuid.uuid4(), [], mock_db, mock_cache)
        assert result == {}

    @pytest.mark.asyncio
    async def test_yahoo_circuit_open_returns_empty(self, mock_db, mock_cache, override_settings):
        """Yahoo 서킷 OPEN 상태이면 price_map이 빈 dict로 시작."""
        import uuid
        from unittest.mock import AsyncMock, patch

        user_id = uuid.uuid4()
        mock_db.scalar = AsyncMock(return_value=None)

        with patch("app.services.price_service.yahoo_circuit") as mock_circuit:
            mock_circuit.is_available.return_value = False

            from app.services.price_service import fetch_prices_batch

            result = await fetch_prices_batch(user_id, [("AAPL", "NASDAQ")], mock_db, mock_cache)

        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_yahoo_returns_prices(self, mock_db, mock_cache, override_settings):
        """Yahoo 배치 조회 성공 시 price_map 반환."""
        import uuid
        from unittest.mock import AsyncMock, patch

        user_id = uuid.uuid4()
        mock_db.scalar = AsyncMock(return_value=None)

        with (
            patch("app.services.price_service.yahoo_circuit") as mock_circuit,
            patch("app.services.price_service._yfinance_sem"),
        ):
            mock_circuit.is_available.return_value = True

            loop_mock = AsyncMock()
            loop_mock.run_in_executor = AsyncMock(return_value={"AAPL": 180.0})

            with patch("asyncio.get_running_loop", return_value=loop_mock):
                from app.services.price_service import fetch_prices_batch

                result = await fetch_prices_batch(user_id, [("AAPL", "NASDAQ")], mock_db, mock_cache)

        assert result.get("AAPL") == 180.0

    @pytest.mark.asyncio
    async def test_domestic_ticker_filled_by_naver_skips_yahoo_call(self, mock_db, mock_cache, override_settings):
        """국내 종목이 Naver로 채워지면 해당 티커는 Yahoo 배치 대상에서 제외된다."""
        import uuid
        from unittest.mock import AsyncMock, patch

        user_id = uuid.uuid4()
        mock_db.scalar = AsyncMock(return_value=None)

        with (
            patch("app.services.price_service.sync_naver_price", return_value=286000.0),
            patch("app.services.price_service._sync_yahoo_batch") as mock_yahoo_batch,
        ):
            from app.services.price_service import fetch_prices_batch

            result = await fetch_prices_batch(user_id, [("005930", "KOSPI")], mock_db, mock_cache)

        assert result.get("005930") == 286000.0
        mock_yahoo_batch.assert_not_called()


class TestReadCachedPricesMalformedEntry:
    """_read_cached_prices: 캐시에 float으로 파싱 불가능한 값(예: 다른 엔드포인트가 저장한
    JSON dict)이 섞여 있어도 전체 요청이 크래시하지 않고 해당 티커만 건너뛰어야 한다 — 과거
    stocks.py와 current_price_key를 공유해 float(cached)가 JSON 문자열을 파싱하려다 크래시하던
    회귀 방지."""

    @pytest.mark.asyncio
    async def test_skips_malformed_entry_and_returns_valid_ones(self, mock_cache, override_settings):
        from unittest.mock import AsyncMock

        from app.services.price_service import _read_cached_prices

        mock_cache.mget = AsyncMock(
            return_value=[
                '{"price_krw": 15525.0, "price_usd": null, "usd_rate": null}',
                "75000.0",
            ]
        )

        result = await _read_cached_prices(mock_cache, [("402970", "KOSPI"), ("005930", "KOSPI")])

        assert result == {"005930": 75000.0}


# ── fetch_prices_batch_krw: 해외 종목 원시 USD 가격 → KRW 환산 ─────


class TestFetchPricesBatchKrw:
    """fetch_prices_batch_krw: fetch_prices_batch()의 원시 가격(해외는 USD)을 KRW로 환산.

    QLD 397,071주 버그(리밸런싱 매수 수량이 환율 배수만큼 부풀려짐) 회귀 방지 —
    overview_enrichment.py/order_builder.py가 이 헬퍼로 KRW 환산 후 값을 써야 한다.
    """

    @pytest.mark.asyncio
    async def test_overseas_ticker_multiplied_by_usd_rate(self, mock_db, mock_cache, override_settings):
        import uuid
        from unittest.mock import AsyncMock, patch

        user_id = uuid.uuid4()

        with (
            patch(
                "app.services.price_service.fetch_prices_batch",
                new=AsyncMock(return_value={"QLD": 95.0}),
            ),
            patch(
                "app.services.price_service.get_usd_krw_rate",
                new=AsyncMock(return_value=1385.0),
            ),
        ):
            from app.services.price_service import fetch_prices_batch_krw

            result = await fetch_prices_batch_krw(user_id, [("QLD", "NASDAQ")], mock_db, mock_cache)

        assert result == {"QLD": pytest.approx(95.0 * 1385.0)}

    @pytest.mark.asyncio
    async def test_domestic_only_skips_rate_lookup(self, mock_db, mock_cache, override_settings):
        """국내 종목만 있으면 환율 조회 자체를 생략하고 원시 가격을 그대로 반환한다."""
        import uuid
        from unittest.mock import AsyncMock, patch

        user_id = uuid.uuid4()

        with (
            patch(
                "app.services.price_service.fetch_prices_batch",
                new=AsyncMock(return_value={"005930": 75000.0}),
            ),
            patch("app.services.price_service.get_usd_krw_rate") as mock_rate,
        ):
            from app.services.price_service import fetch_prices_batch_krw

            result = await fetch_prices_batch_krw(user_id, [("005930", "KOSPI")], mock_db, mock_cache)

        assert result == {"005930": 75000.0}
        mock_rate.assert_not_called()

    @pytest.mark.asyncio
    async def test_mixed_domestic_and_overseas_only_converts_overseas(self, mock_db, mock_cache, override_settings):
        """국내+해외 혼합 시 국내 종목 가격은 그대로, 해외 종목만 환율이 곱해진다."""
        import uuid
        from unittest.mock import AsyncMock, patch

        user_id = uuid.uuid4()

        with (
            patch(
                "app.services.price_service.fetch_prices_batch",
                new=AsyncMock(return_value={"005930": 75000.0, "QLD": 95.0}),
            ),
            patch(
                "app.services.price_service.get_usd_krw_rate",
                new=AsyncMock(return_value=1385.0),
            ),
        ):
            from app.services.price_service import fetch_prices_batch_krw

            result = await fetch_prices_batch_krw(
                user_id, [("005930", "KOSPI"), ("QLD", "NASDAQ")], mock_db, mock_cache
            )

        assert result["005930"] == 75000.0
        assert result["QLD"] == pytest.approx(95.0 * 1385.0)


# ── get_historical_returns ────────────────────────────────────


class TestGetHistoricalReturns:
    @pytest.mark.asyncio
    async def test_empty_tickers_returns_empty(self, override_settings):
        from app.services.price_service import get_historical_returns

        result = await get_historical_returns([])
        assert result == {}

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached(self, override_settings):
        import json
        from unittest.mock import AsyncMock

        cache = AsyncMock()
        cached_data = {"cumulative_pct": 120.0, "annual_pct": 8.5}
        cache.mget = AsyncMock(return_value=[json.dumps(cached_data).encode()])

        from app.services.price_service import get_historical_returns

        result = await get_historical_returns([("AAPL", "NASDAQ")], cache=cache)

        assert ("AAPL", "NASDAQ") in result
        assert result[("AAPL", "NASDAQ")]["cumulative_pct"] == 120.0

    @pytest.mark.asyncio
    async def test_circuit_open_returns_empty_for_overseas(self, override_settings):
        """회로 OPEN + 해외 종목(대체 소스 없음)이면 빈 결과."""
        from unittest.mock import patch

        with patch("app.services.price_service.yahoo_circuit") as mock_circuit:
            mock_circuit.is_available.return_value = False

            from app.services.price_service import get_historical_returns

            result = await get_historical_returns([("AAPL", "NASDAQ")])

        assert result == {}

    @pytest.mark.asyncio
    async def test_circuit_open_falls_back_to_pykrx_for_domestic(self, override_settings):
        """회로 OPEN이어도 국내 종목은 pykrx로 보완된다."""
        from unittest.mock import AsyncMock, patch

        pykrx_data = {("005930", "KOSPI"): {"cumulative_return_pct": 50.0, "cagr_pct": 5.0, "actual_years": 10.0}}

        with (
            patch("app.services.price_service.yahoo_circuit") as mock_circuit,
        ):
            mock_circuit.is_available.return_value = False

            loop_mock = AsyncMock()
            loop_mock.run_in_executor = AsyncMock(return_value=pykrx_data)

            with patch("asyncio.get_running_loop", return_value=loop_mock):
                from app.services.price_service import get_historical_returns

                result = await get_historical_returns([("005930", "KOSPI")])

        assert result == pykrx_data

    @pytest.mark.asyncio
    async def test_yahoo_returns_result(self, override_settings):
        """Yahoo Finance batch 결과 반환 시 return_map에 저장."""
        from unittest.mock import AsyncMock, patch

        batch_data = {("AAPL", "NASDAQ"): {"cumulative_pct": 200.0, "annual_pct": 10.0}}

        with (
            patch("app.services.price_service.yahoo_circuit") as mock_circuit,
            patch("app.services.price_service._yfinance_sem"),
        ):
            mock_circuit.is_available.return_value = True

            loop_mock = AsyncMock()
            loop_mock.run_in_executor = AsyncMock(return_value=batch_data)

            with patch("asyncio.get_running_loop", return_value=loop_mock):
                from app.services.price_service import get_historical_returns

                result = await get_historical_returns([("AAPL", "NASDAQ")])

        assert ("AAPL", "NASDAQ") in result

    @pytest.mark.asyncio
    async def test_yahoo_partial_miss_backfilled_by_pykrx(self, override_settings):
        """Yahoo batch가 국내 종목을 못 채우면 pykrx로 보완한다."""
        from unittest.mock import AsyncMock, patch

        with (
            patch("app.services.price_service.yahoo_circuit") as mock_circuit,
            patch("app.services.price_service._yfinance_sem"),
            patch(
                "app.services.price_service._sync_calc_returns_batch",
                return_value={},
            ),
            patch(
                "app.services.price_service._sync_pykrx_returns_batch",
                return_value={
                    ("005930", "KOSPI"): {"cumulative_return_pct": 30.0, "cagr_pct": 3.0, "actual_years": 10.0}
                },
            ),
        ):
            mock_circuit.is_available.return_value = True

            loop_mock = AsyncMock()

            async def _run_in_executor(_executor, func):
                return func()

            loop_mock.run_in_executor = _run_in_executor

            with patch("asyncio.get_running_loop", return_value=loop_mock):
                from app.services.price_service import get_historical_returns

                result = await get_historical_returns([("005930", "KOSPI")])

        assert ("005930", "KOSPI") in result


# ── fetch_current_price cache hit ─────────────────────────────


class TestFetchCurrentPriceCacheHit:
    @pytest.mark.asyncio
    async def test_returns_cached_price(self, mock_db, override_settings):
        import uuid
        from unittest.mock import AsyncMock

        user_id = uuid.uuid4()
        cache = AsyncMock()
        cache.get = AsyncMock(return_value=b"75000.0")

        from app.services.price_service import fetch_current_price

        price = await fetch_current_price(user_id, "005930", "KOSPI", mock_db, cache)

        assert price == 75000.0


# ── domestic_price_fallback: 국내 종목 Naver→pykrx 폴백 ────────


class TestDomesticPriceFallback:
    @pytest.mark.asyncio
    async def test_naver_success_skips_pykrx(self, override_settings):
        import asyncio
        from unittest.mock import patch

        with (
            patch("app.services.price_service.sync_naver_price", return_value=286000.0),
            patch("app.services.price_service.sync_pykrx_price") as mock_pykrx,
        ):
            from app.services.price_service import domestic_price_fallback

            loop = asyncio.get_running_loop()
            price = await domestic_price_fallback("005930", loop)

        assert price == 286000.0
        mock_pykrx.assert_not_called()

    @pytest.mark.asyncio
    async def test_naver_fails_falls_back_to_pykrx(self, override_settings):
        import asyncio
        from unittest.mock import patch

        with (
            patch("app.services.price_service.sync_naver_price", return_value=None),
            patch("app.services.price_service.sync_pykrx_price", return_value=284000.0),
        ):
            from app.services.price_service import domestic_price_fallback

            loop = asyncio.get_running_loop()
            price = await domestic_price_fallback("005930", loop)

        assert price == 284000.0

    @pytest.mark.asyncio
    async def test_both_sources_fail_returns_none(self, override_settings):
        import asyncio
        from unittest.mock import patch

        with (
            patch("app.services.price_service.sync_naver_price", return_value=None),
            patch("app.services.price_service.sync_pykrx_price", return_value=None),
        ):
            from app.services.price_service import domestic_price_fallback

            loop = asyncio.get_running_loop()
            price = await domestic_price_fallback("005930", loop)

        assert price is None


class TestFetchCurrentPriceDomesticPriority:
    """국내 종목은 Naver/pykrx가 성공하면 Yahoo를 호출하지 않아야 한다."""

    @pytest.mark.asyncio
    async def test_domestic_naver_success_skips_yahoo(self, mock_db, mock_cache, override_settings):
        import uuid
        from unittest.mock import patch

        user_id = uuid.uuid4()
        mock_db.scalar.return_value = None

        with (
            patch("app.services.price_service.sync_naver_price", return_value=286000.0),
            patch("app.services.price_service._sync_yahoo_price") as mock_yahoo,
        ):
            from app.services.price_service import fetch_current_price

            price = await fetch_current_price(user_id, "005930", "KOSPI", mock_db, mock_cache)

        assert price == 286000.0
        mock_yahoo.assert_not_called()

    @pytest.mark.asyncio
    async def test_overseas_ticker_skips_domestic_fallback(self, mock_db, mock_cache, override_settings):
        """해외 종목은 국내 폴백(Naver/pykrx)을 거치지 않고 바로 Yahoo로 간다."""
        import uuid
        from unittest.mock import patch

        user_id = uuid.uuid4()
        mock_db.scalar.return_value = None

        with (
            patch("app.services.price_service.domestic_price_fallback") as mock_domestic,
            patch("app.services.price_service._sync_yahoo_price", return_value=180.0),
        ):
            from app.services.price_service import fetch_current_price

            price = await fetch_current_price(user_id, "AAPL", "NASDAQ", mock_db, mock_cache)

        assert price == 180.0
        mock_domestic.assert_not_called()
