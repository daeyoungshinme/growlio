"""price_service 단위 테스트 — Yahoo Finance 우선순위 체인 검증."""

import pytest

from app.services.market_data.yahoo_price import to_yf_symbol as _to_yahoo_symbol

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


# ── 배치 조회 테스트 ────────────────────────────────────────


class TestFetchPricesBatch:
    """fetch_prices_batch: 여러 종목 일괄 조회."""

    @pytest.mark.asyncio
    async def test_empty_tickers_returns_empty(self, mock_db, mock_cache, override_settings):
        """빈 목록 입력 시 빈 딕셔너리 반환."""
        import uuid

        from app.services.market_data.price_service import fetch_prices_batch

        result = await fetch_prices_batch(uuid.uuid4(), [], mock_db, mock_cache)
        assert result == {}

    @pytest.mark.asyncio
    async def test_yahoo_circuit_open_returns_empty(self, mock_db, mock_cache, override_settings):
        """Yahoo 서킷 OPEN 상태이면 price_map이 빈 dict로 시작."""
        import uuid
        from unittest.mock import AsyncMock, patch

        user_id = uuid.uuid4()
        mock_db.scalar = AsyncMock(return_value=None)

        with patch("app.services.market_data.yahoo_price.yahoo_circuit") as mock_circuit:
            mock_circuit.is_available.return_value = False

            from app.services.market_data.price_service import fetch_prices_batch

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
            patch("app.services.market_data.yahoo_price.yahoo_circuit") as mock_circuit,
        ):
            mock_circuit.is_available.return_value = True

            loop_mock = AsyncMock()
            loop_mock.run_in_executor = AsyncMock(return_value={"AAPL": 180.0})

            with patch("asyncio.get_running_loop", return_value=loop_mock):
                from app.services.market_data.price_service import fetch_prices_batch

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
            patch("app.services.market_data.price_service.sync_naver_price", return_value=286000.0),
            patch("app.services.market_data.yahoo_price._sync_yahoo_batch") as mock_yahoo_batch,
        ):
            from app.services.market_data.price_service import fetch_prices_batch

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

        from app.services.market_data.price_service import _read_cached_prices

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
                "app.services.market_data.price_service.fetch_prices_batch",
                new=AsyncMock(return_value={"QLD": 95.0}),
            ),
            patch(
                "app.services.market_data.price_service.get_usd_krw_rate",
                new=AsyncMock(return_value=1385.0),
            ),
        ):
            from app.services.market_data.price_service import fetch_prices_batch_krw

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
                "app.services.market_data.price_service.fetch_prices_batch",
                new=AsyncMock(return_value={"005930": 75000.0}),
            ),
            patch("app.services.market_data.price_service.get_usd_krw_rate") as mock_rate,
        ):
            from app.services.market_data.price_service import fetch_prices_batch_krw

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
                "app.services.market_data.price_service.fetch_prices_batch",
                new=AsyncMock(return_value={"005930": 75000.0, "QLD": 95.0}),
            ),
            patch(
                "app.services.market_data.price_service.get_usd_krw_rate",
                new=AsyncMock(return_value=1385.0),
            ),
        ):
            from app.services.market_data.price_service import fetch_prices_batch_krw

            result = await fetch_prices_batch_krw(
                user_id, [("005930", "KOSPI"), ("QLD", "NASDAQ")], mock_db, mock_cache
            )

        assert result["005930"] == 75000.0
        assert result["QLD"] == pytest.approx(95.0 * 1385.0)


# ── get_historical_returns ────────────────────────────────────


class TestGetHistoricalReturns:
    @pytest.mark.asyncio
    async def test_empty_tickers_returns_empty(self, override_settings):
        from app.services.market_data.price_service import get_historical_returns

        result = await get_historical_returns([])
        assert result == {}

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached(self, override_settings):
        import json
        from unittest.mock import AsyncMock

        cache = AsyncMock()
        cached_data = {"cumulative_pct": 120.0, "annual_pct": 8.5}
        cache.mget = AsyncMock(return_value=[json.dumps(cached_data).encode()])

        from app.services.market_data.price_service import get_historical_returns

        result = await get_historical_returns([("AAPL", "NASDAQ")], cache=cache)

        assert ("AAPL", "NASDAQ") in result
        assert result[("AAPL", "NASDAQ")]["cumulative_pct"] == 120.0

    @pytest.mark.asyncio
    async def test_circuit_open_returns_empty_for_overseas(self, override_settings):
        """회로 OPEN + 해외 종목(대체 소스 없음)이면 빈 결과."""
        from unittest.mock import patch

        with patch("app.services.market_data.yahoo_price.yahoo_circuit") as mock_circuit:
            mock_circuit.is_available.return_value = False

            from app.services.market_data.price_service import get_historical_returns

            result = await get_historical_returns([("AAPL", "NASDAQ")])

        assert result == {}

    @pytest.mark.asyncio
    async def test_circuit_open_falls_back_to_pykrx_for_domestic(self, override_settings):
        """회로 OPEN이어도 국내 종목은 pykrx로 보완된다."""
        from unittest.mock import AsyncMock, patch

        pykrx_data = {("005930", "KOSPI"): {"cumulative_return_pct": 50.0, "cagr_pct": 5.0, "actual_years": 10.0}}

        with (
            patch("app.services.market_data.yahoo_price.yahoo_circuit") as mock_circuit,
        ):
            mock_circuit.is_available.return_value = False

            loop_mock = AsyncMock()
            loop_mock.run_in_executor = AsyncMock(return_value=pykrx_data)

            with patch("asyncio.get_running_loop", return_value=loop_mock):
                from app.services.market_data.price_service import get_historical_returns

                result = await get_historical_returns([("005930", "KOSPI")])

        assert result == pykrx_data

    @pytest.mark.asyncio
    async def test_yahoo_returns_result(self, override_settings):
        """Yahoo Finance batch 결과 반환 시 return_map에 저장."""
        from unittest.mock import AsyncMock, patch

        batch_data = {("AAPL", "NASDAQ"): {"cumulative_pct": 200.0, "annual_pct": 10.0}}

        with (
            patch("app.services.market_data.yahoo_price.yahoo_circuit") as mock_circuit,
        ):
            mock_circuit.is_available.return_value = True

            loop_mock = AsyncMock()
            loop_mock.run_in_executor = AsyncMock(return_value=batch_data)

            with patch("asyncio.get_running_loop", return_value=loop_mock):
                from app.services.market_data.price_service import get_historical_returns

                result = await get_historical_returns([("AAPL", "NASDAQ")])

        assert ("AAPL", "NASDAQ") in result

    @pytest.mark.asyncio
    async def test_yahoo_partial_miss_backfilled_by_pykrx(self, override_settings):
        """Yahoo batch가 국내 종목을 못 채우면 pykrx로 보완한다."""
        from unittest.mock import AsyncMock, patch

        with (
            patch("app.services.market_data.yahoo_price.yahoo_circuit") as mock_circuit,
            patch(
                "app.services.market_data.yahoo_price._sync_calc_returns_batch",
                return_value={},
            ),
            patch(
                "app.services.market_data.price_service._sync_pykrx_returns_batch",
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
                from app.services.market_data.price_service import get_historical_returns

                result = await get_historical_returns([("005930", "KOSPI")])

        assert ("005930", "KOSPI") in result


# ── domestic_price_fallback: 국내 종목 Naver→pykrx 폴백 ────────


class TestDomesticPriceFallback:
    @pytest.mark.asyncio
    async def test_naver_success_skips_pykrx(self, override_settings):
        import asyncio
        from unittest.mock import patch

        with (
            patch("app.services.market_data.price_service.sync_naver_price", return_value=286000.0),
            patch("app.services.market_data.price_service.sync_pykrx_price") as mock_pykrx,
        ):
            from app.services.market_data.price_service import domestic_price_fallback

            loop = asyncio.get_running_loop()
            price = await domestic_price_fallback("005930", loop)

        assert price == 286000.0
        mock_pykrx.assert_not_called()

    @pytest.mark.asyncio
    async def test_naver_fails_falls_back_to_pykrx(self, override_settings):
        import asyncio
        from unittest.mock import patch

        with (
            patch("app.services.market_data.price_service.sync_naver_price", return_value=None),
            patch("app.services.market_data.price_service.sync_pykrx_price", return_value=284000.0),
        ):
            from app.services.market_data.price_service import domestic_price_fallback

            loop = asyncio.get_running_loop()
            price = await domestic_price_fallback("005930", loop)

        assert price == 284000.0

    @pytest.mark.asyncio
    async def test_both_sources_fail_returns_none(self, override_settings):
        import asyncio
        from unittest.mock import patch

        with (
            patch("app.services.market_data.price_service.sync_naver_price", return_value=None),
            patch("app.services.market_data.price_service.sync_pykrx_price", return_value=None),
        ):
            from app.services.market_data.price_service import domestic_price_fallback

            loop = asyncio.get_running_loop()
            price = await domestic_price_fallback("005930", loop)

        assert price is None


class TestPriceMissCache:
    """공개 소스가 모두 실패한 현재가·기간 수익률은 10분 동안 다시 조회하지 않는다(plans/151 A2)."""

    @pytest.mark.asyncio
    async def test_current_price_miss_is_cached_and_skips_public_sources(self, mock_db, override_settings):
        import uuid
        from unittest.mock import AsyncMock, patch

        from app.core.cache_store import CacheStore
        from app.services.market_data.price_service import fetch_prices_batch

        cache = CacheStore()
        mock_db.scalar = AsyncMock(return_value=None)  # KIS 계좌 없음
        ps = "app.services.market_data.price_service"
        # 같은 국내 묶음의 다른 종목은 받았으니 소스는 살아 있다 → 이 종목만 미스로 기록
        with (
            patch(
                f"{ps}.domestic_price_fallback",
                new_callable=AsyncMock,
                side_effect=lambda t, _loop: 70000.0 if t == "005930" else None,
            ) as domestic,
            patch(f"{ps}.fetch_yahoo_batch", new_callable=AsyncMock, return_value={}) as yahoo,
        ):
            first = await fetch_prices_batch(uuid.uuid4(), [("999999", "KOSPI"), ("005930", "KOSPI")], mock_db, cache)
            second = await fetch_prices_batch(uuid.uuid4(), [("999999", "KOSPI")], mock_db, cache)

        assert first == {"005930": 70000.0}
        assert second == {}
        assert domestic.await_count == 2  # 두 번째 호출은 국내 소스를 건너뛴다
        assert yahoo.await_args_list[1].args[0] == []  # 두 번째는 Yahoo 대상에서도 빠진다

    @pytest.mark.asyncio
    async def test_whole_batch_failure_is_not_cached_as_miss(self, mock_db, override_settings):
        """묶음 전체가 비면 소스 장애(서킷 열림)일 수 있다 — 2분짜리 장애를 10분 미스로 늘리지 않는다."""
        import uuid
        from unittest.mock import AsyncMock, patch

        from app.core.cache_store import CacheStore
        from app.services.market_data.price_service import fetch_prices_batch

        cache = CacheStore()
        mock_db.scalar = AsyncMock(return_value=None)
        ps = "app.services.market_data.price_service"
        with (
            patch(f"{ps}.domestic_price_fallback", new_callable=AsyncMock, return_value=None),
            patch(f"{ps}.fetch_yahoo_batch", new_callable=AsyncMock, side_effect=[{}, {"QQQ": 500.0}]) as yahoo,
        ):
            first = await fetch_prices_batch(uuid.uuid4(), [("QQQ", "NASDAQ")], mock_db, cache)
            second = await fetch_prices_batch(uuid.uuid4(), [("QQQ", "NASDAQ")], mock_db, cache)

        assert first == {}
        assert second == {"QQQ": 500.0}
        assert yahoo.await_args_list[1].args[0] == [("QQQ", "NASDAQ")]

    def test_confirmed_misses_per_source_group(self):
        from app.services.market_data.price_service import confirmed_misses

        targets = [("005930", "KOSPI"), ("999999", "KOSPI"), ("QQQ", "NASDAQ"), ("ZZZZ", "NASDAQ")]
        found = {"005930"}
        # 국내는 성공 종목이 있어 실패분 기록, 해외는 전부 실패(Yahoo 장애일 수 있음)라 기록 안 함
        assert confirmed_misses(targets, lambda tm: tm[0] in found) == [("999999", "KOSPI")]

    @pytest.mark.asyncio
    async def test_current_price_miss_still_tries_kis(self, mock_db, override_settings):
        """KIS 폴백은 계좌마다 결과가 달라 실패 표식이 있어도 시도한다."""
        import uuid
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.core.cache_store import CacheStore
        from app.services.market_data.price_service import fetch_prices_batch

        cache = CacheStore()
        account = MagicMock()
        ps = "app.services.market_data.price_service"
        with (
            patch(f"{ps}.domestic_price_fallback", new_callable=AsyncMock, return_value=None) as domestic,
            patch(f"{ps}.fetch_yahoo_batch", new_callable=AsyncMock, return_value={}),
            patch(f"{ps}._fetch_fallback", new_callable=AsyncMock, side_effect=[None, 1234.0]) as kis,
        ):
            await fetch_prices_batch(uuid.uuid4(), [("999999", "KOSPI")], mock_db, cache, {"999999": account})
            result = await fetch_prices_batch(uuid.uuid4(), [("999999", "KOSPI")], mock_db, cache, {"999999": account})

        assert result == {"999999": 1234.0}
        assert domestic.await_count == 2  # 묶음 전체 실패는 미스로 기록하지 않는다(소스 장애일 수 있음)
        assert kis.await_count == 2

    @pytest.mark.asyncio
    async def test_historical_return_miss_is_cached(self, override_settings):
        from unittest.mock import AsyncMock, patch

        from app.core.cache_store import CacheStore
        from app.services.market_data.price_service import get_historical_returns

        cache = CacheStore()
        ps = "app.services.market_data.price_service"
        qqq = {"cumulative_return_pct": 10.0}
        with patch(
            f"{ps}.fetch_yahoo_returns_batch",
            new_callable=AsyncMock,
            side_effect=[{("QQQ", "NASDAQ"): qqq}, {}],
        ) as yahoo:
            first = await get_historical_returns([("ZZZZ", "NASDAQ"), ("QQQ", "NASDAQ")], cache=cache)
            second = await get_historical_returns([("ZZZZ", "NASDAQ"), ("QQQ", "NASDAQ")], cache=cache)

        assert first == {("QQQ", "NASDAQ"): qqq}
        assert second == {("QQQ", "NASDAQ"): qqq}
        assert yahoo.await_count == 1  # ZZZZ는 미스, QQQ는 수익률 캐시

    @pytest.mark.asyncio
    async def test_historical_return_whole_batch_failure_not_cached(self, override_settings):
        from unittest.mock import AsyncMock, patch

        from app.core.cache_store import CacheStore
        from app.services.market_data.price_service import get_historical_returns

        cache = CacheStore()
        ps = "app.services.market_data.price_service"
        with patch(f"{ps}.fetch_yahoo_returns_batch", new_callable=AsyncMock, return_value={}) as yahoo:
            await get_historical_returns([("ZZZZ", "NASDAQ")], cache=cache)
            await get_historical_returns([("ZZZZ", "NASDAQ")], cache=cache)

        assert yahoo.await_count == 2
