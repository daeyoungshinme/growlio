"""price_service 단위 테스트 — Yahoo Finance 우선순위 체인 검증."""

import pytest

from app.services.yahoo_price import _to_yahoo_symbol


# ── Yahoo 심볼 변환 테스트 ──────────────────────────────────

class TestToYahooSymbol:
    """_to_yahoo_symbol: 시장별 티커 변환 로직."""

    @pytest.mark.parametrize("ticker,market,expected", [
        ("005930", "KOSPI", "005930.KS"),
        ("5930", "KOSPI", "005930.KS"),   # zero-padding
        ("5930", "KRX", "005930.KS"),
        ("035720", "KOSDAQ", "035720.KQ"),
        ("35720", "KOSDAQ", "035720.KQ"),  # zero-padding
        ("AAPL", "NYSE", "AAPL"),           # 해외: 그대로
        ("TSLA", "NASDAQ", "TSLA"),
        ("NVDA", "nasdaq", "NVDA"),         # 소문자 market도 처리
    ])
    def test_symbol_conversion(self, ticker, market, expected):
        assert _to_yahoo_symbol(ticker, market) == expected


# ── fetch_current_price 우선순위 체인 테스트 ────────────────

class TestFetchCurrentPrice:
    """Yahoo 실패 → KIS → LS 순서로 fallback 되는지 검증."""

    @pytest.mark.asyncio
    async def test_returns_yahoo_price_when_available(self, mock_db, mock_redis, override_settings):
        """Yahoo Finance 가격 조회 성공 시 바로 반환."""
        from unittest.mock import AsyncMock, patch

        import uuid
        user_id = uuid.uuid4()

        with patch("app.services.price_service._sync_yahoo_price", return_value=75000.0):
            with patch("asyncio.get_event_loop") as mock_loop:
                mock_executor = AsyncMock(return_value=75000.0)
                mock_loop.return_value.run_in_executor = mock_executor

                from app.services.price_service import fetch_current_price
                # DB 조회 없이 Yahoo가 성공하면 DB 없어도 됨
                # (실제 내부 구현상 DB 조회 후 KIS/LS 체인이므로 mock 필요)
                mock_db.scalar.return_value = None  # UserSettings 없음 → KIS/LS skip

                price = await fetch_current_price(user_id, "005930", "KOSPI", mock_db, mock_redis)
                # Yahoo가 성공했으므로 75000 반환
                assert price == 75000.0

    @pytest.mark.asyncio
    async def test_returns_none_when_all_providers_fail(self, mock_db, mock_redis, override_settings):
        """모든 provider 실패 시 None 반환 (예외 없음)."""
        import uuid
        from unittest.mock import AsyncMock, patch

        user_id = uuid.uuid4()
        mock_db.scalar.return_value = None  # UserSettings 없음

        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=None)

            from app.services.price_service import fetch_current_price
            price = await fetch_current_price(user_id, "UNKNOWN", "NYSE", mock_db, mock_redis)
            assert price is None


# ── 배치 조회 테스트 ────────────────────────────────────────

class TestFetchPricesBatch:
    """fetch_prices_batch: 여러 종목 일괄 조회."""

    @pytest.mark.asyncio
    async def test_empty_tickers_returns_empty(self, mock_db, mock_redis, override_settings):
        """빈 목록 입력 시 빈 딕셔너리 반환."""
        import uuid
        from app.services.price_service import fetch_prices_batch

        result = await fetch_prices_batch(uuid.uuid4(), [], mock_db, mock_redis)
        assert result == {}

    @pytest.mark.asyncio
    async def test_yahoo_circuit_open_returns_empty(self, mock_db, mock_redis, override_settings):
        """Yahoo 서킷 OPEN 상태이면 price_map이 빈 dict로 시작."""
        import uuid
        from unittest.mock import patch, AsyncMock, MagicMock

        user_id = uuid.uuid4()
        mock_db.scalar = AsyncMock(return_value=None)

        with patch("app.services.price_service.yahoo_circuit") as mock_circuit:
            mock_circuit.is_available.return_value = False

            from app.services.price_service import fetch_prices_batch
            result = await fetch_prices_batch(user_id, [("AAPL", "NASDAQ")], mock_db, mock_redis)

        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_yahoo_returns_prices(self, mock_db, mock_redis, override_settings):
        """Yahoo 배치 조회 성공 시 price_map 반환."""
        import uuid
        from unittest.mock import patch, AsyncMock

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
                result = await fetch_prices_batch(
                    user_id, [("AAPL", "NASDAQ")], mock_db, mock_redis
                )

        assert result.get("AAPL") == 180.0


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
        from unittest.mock import AsyncMock, patch

        redis = AsyncMock()
        cached_data = {"cumulative_pct": 120.0, "annual_pct": 8.5}
        redis.get = AsyncMock(return_value=json.dumps(cached_data).encode())

        from app.services.price_service import get_historical_returns
        result = await get_historical_returns([("AAPL", "NASDAQ")], redis=redis)

        assert ("AAPL", "NASDAQ") in result
        assert result[("AAPL", "NASDAQ")]["cumulative_pct"] == 120.0

    @pytest.mark.asyncio
    async def test_circuit_open_returns_empty(self, override_settings):
        from unittest.mock import patch, AsyncMock

        with patch("app.services.price_service.yahoo_circuit") as mock_circuit:
            mock_circuit.is_available.return_value = False

            from app.services.price_service import get_historical_returns
            result = await get_historical_returns([("AAPL", "NASDAQ")])

        assert result == {}

    @pytest.mark.asyncio
    async def test_yahoo_returns_result(self, override_settings):
        """Yahoo Finance 결과 반환 시 return_map에 저장."""
        from unittest.mock import patch, AsyncMock

        ret_data = {"cumulative_pct": 200.0, "annual_pct": 10.0}

        with (
            patch("app.services.price_service.yahoo_circuit") as mock_circuit,
            patch("app.services.price_service._yfinance_sem"),
        ):
            mock_circuit.is_available.return_value = True

            loop_mock = AsyncMock()
            loop_mock.run_in_executor = AsyncMock(return_value=ret_data)

            with patch("asyncio.get_running_loop", return_value=loop_mock):
                from app.services.price_service import get_historical_returns
                result = await get_historical_returns([("AAPL", "NASDAQ")])

        assert ("AAPL", "NASDAQ") in result


# ── fetch_current_price cache hit ─────────────────────────────

class TestFetchCurrentPriceCacheHit:
    @pytest.mark.asyncio
    async def test_returns_cached_price(self, mock_db, override_settings):
        import uuid
        from unittest.mock import AsyncMock

        user_id = uuid.uuid4()
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=b"75000.0")

        from app.services.price_service import fetch_current_price
        price = await fetch_current_price(user_id, "005930", "KOSPI", mock_db, redis)

        assert price == 75000.0
