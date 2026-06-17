"""dividend_fetcher.py 단위 테스트 — fetch_ticker_dividend_info 폴백 체인."""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.setex = AsyncMock()
    redis.delete = AsyncMock()
    return redis


async def _call_fetcher(ticker, market, redis, kis_creds=None, overrides=None, dart_key="test"):
    """fetch_ticker_dividend_info 호출 헬퍼."""
    from app.services.dividend_fetcher import fetch_ticker_dividend_info
    sem = asyncio.Semaphore(1)
    return await fetch_ticker_dividend_info(
        ticker=ticker,
        market=market,
        redis=redis,
        sem=sem,
        kis_creds=kis_creds,
        dart_key=dart_key,
        overrides=overrides or {},
    )


class TestFetchTickerDividendInfo:
    @pytest.mark.asyncio
    async def test_cache_hit_skips_network(self, mock_redis, override_settings):
        """Redis 캐시에 dps + yield 있으면 네트워크 소스 생략 후 반환."""
        # months cache hit
        mock_redis.get = AsyncMock(side_effect=[
            json.dumps([3, 6, 9, 12]).encode(),  # months cache
            json.dumps({"dps": 500.0, "yield_decimal": 0.025}).encode(),  # info cache
        ])

        with patch("app.services.dividend_fetcher.sync_yahoo_dividend_info") as mock_yahoo:
            result = await _call_fetcher("AAPL", "NASDAQ", mock_redis)

        mock_yahoo.assert_not_called()
        assert result[0] == pytest.approx(0.025)  # yield_decimal
        assert result[1] == pytest.approx(500.0)   # dps

    @pytest.mark.asyncio
    async def test_override_months_used_directly(self, mock_redis, override_settings):
        """overrides에 배당월이 있으면 캐시/네트워크 조회 없이 사용."""
        mock_redis.get = AsyncMock(return_value=None)

        overrides = {("AAPL", "NASDAQ"): [3, 6, 9, 12]}

        with (
            patch("app.services.dividend_fetcher.sync_yahoo_dividend_info",
                  return_value={"dividend_yield": 0.02, "dps": 1.5, "ex_dividend_date": None}),
            patch("app.services.dividend_fetcher.sync_fetch_dividend_months",
                  return_value=[]) as mock_months,
        ):
            loop_mock = MagicMock()
            loop_mock.run_in_executor = AsyncMock(side_effect=lambda _, fn, *args: fn(*args) if callable(fn) else None)

            with patch("asyncio.get_running_loop", return_value=loop_mock):
                result = await _call_fetcher("AAPL", "NASDAQ", mock_redis, overrides=overrides)

        mock_months.assert_not_called()
        assert result[2] == [3, 6, 9, 12]

    @pytest.mark.asyncio
    async def test_foreign_ticker_yahoo_used(self, mock_redis, override_settings):
        """해외 종목은 Yahoo Finance 사용 (Naver 미사용)."""
        mock_redis.get = AsyncMock(return_value=None)

        yahoo_result = {"dividend_yield": 0.015, "dps": 1.0, "ex_dividend_date": None}

        loop_mock = MagicMock()
        async def fake_executor(_, fn, *args):
            if callable(fn):
                return fn(*args)
            return None

        loop_mock.run_in_executor = fake_executor

        with (
            patch("app.services.dividend_fetcher.sync_yahoo_dividend_info", return_value=yahoo_result),
            patch("app.services.dividend_fetcher.sync_naver_stock_dividend_info") as mock_naver,
            patch("app.services.dividend_fetcher.sync_fetch_dividend_months", return_value=[3, 9]),
            patch("asyncio.get_running_loop", return_value=loop_mock),
        ):
            result = await _call_fetcher("AAPL", "NASDAQ", mock_redis)

        mock_naver.assert_not_called()
        assert result[0] == pytest.approx(0.015)

    @pytest.mark.asyncio
    async def test_known_schedule_used_directly(self, mock_redis, override_settings):
        """KNOWN_DIVIDEND_SCHEDULES에 있는 종목은 배당월 직접 사용."""
        from app.services.dividend_constants import KNOWN_DIVIDEND_SCHEDULES

        # Find a ticker in KNOWN_DIVIDEND_SCHEDULES
        if not KNOWN_DIVIDEND_SCHEDULES:
            pytest.skip("KNOWN_DIVIDEND_SCHEDULES is empty")

        known_ticker, known_market = next(iter(KNOWN_DIVIDEND_SCHEDULES.keys()))
        expected_months = KNOWN_DIVIDEND_SCHEDULES[(known_ticker, known_market.upper())]

        mock_redis.get = AsyncMock(return_value=None)

        yahoo_result = {"dividend_yield": 0.02, "dps": 100.0, "ex_dividend_date": None}

        loop_mock = MagicMock()
        async def fake_executor(_, fn, *args):
            if callable(fn):
                return fn(*args)
            return None

        loop_mock.run_in_executor = fake_executor

        with (
            patch("app.services.dividend_fetcher.sync_yahoo_dividend_info", return_value=yahoo_result),
            patch("app.services.dividend_fetcher.sync_fetch_dividend_months", return_value=[]),
            patch("asyncio.get_running_loop", return_value=loop_mock),
        ):
            result = await _call_fetcher(known_ticker, known_market, mock_redis)

        # months from KNOWN_DIVIDEND_SCHEDULES should be used
        assert result[2] == expected_months

    @pytest.mark.asyncio
    async def test_months_cached_in_redis(self, mock_redis, override_settings):
        """배당월 조회 후 Redis에 캐시 저장."""
        mock_redis.get = AsyncMock(return_value=None)

        yahoo_result = {"dividend_yield": 0.02, "dps": 1.5, "ex_dividend_date": None}

        loop_mock = MagicMock()
        async def fake_executor(_, fn, *args):
            if callable(fn):
                return fn(*args)
            return None

        loop_mock.run_in_executor = fake_executor

        with (
            patch("app.services.dividend_fetcher.sync_yahoo_dividend_info", return_value=yahoo_result),
            patch("app.services.dividend_fetcher.sync_fetch_dividend_months", return_value=[3, 9]),
            patch("asyncio.get_running_loop", return_value=loop_mock),
        ):
            await _call_fetcher("AAPL", "NASDAQ", mock_redis)

        mock_redis.setex.assert_called()
