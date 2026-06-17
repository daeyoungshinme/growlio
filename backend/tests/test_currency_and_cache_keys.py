"""utils/currency.py 및 utils/cache_keys.py 단위 테스트."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from redis.exceptions import RedisError

from app.utils.cache_keys import (
    alloc_history_key,
    backtest_key,
    correlation_key,
    current_price_key,
    dart_disclosures_key,
    dividend_info_key,
    dividend_months_key,
    dividend_summary_key,
    dividend_ticker_summary_key,
    economic_indicator_calendar_key,
    economic_indicator_latest_key,
    has_overseas_key,
    invalidate_user_caches,
    monthly_trend_key,
    ob_state_key,
    portfolio_list_key,
    portfolio_overview_key,
    portfolio_overview_lite_key,
    price_return_key,
)
from app.utils.currency import cache_usd_krw_rate, get_usd_krw_rate

# ── cache_keys ───────────────────────────────────────────────────────────────


class TestCacheKeyBuilders:
    def test_current_price_key(self, override_settings):
        assert current_price_key("AAPL", "NASDAQ") == "test:price:current:AAPL:NASDAQ"

    def test_price_return_key(self, override_settings):
        assert price_return_key(3, "AAPL", "NASDAQ") == "test:return:3y:AAPL:NASDAQ"

    def test_monthly_trend_key(self, override_settings):
        uid = uuid.uuid4()
        key = monthly_trend_key(uid)
        assert str(uid) in key
        assert key.startswith("test:monthly_trend:")

    def test_dividend_ticker_summary_key(self, override_settings):
        uid = uuid.uuid4()
        key = dividend_ticker_summary_key(uid, 2024)
        assert "2024" in key
        assert str(uid) in key

    def test_dividend_months_key(self, override_settings):
        key = dividend_months_key("005930", "KOSPI")
        assert "005930" in key
        assert "KOSPI" in key

    def test_dividend_info_key(self, override_settings):
        key = dividend_info_key("AAPL", "NASDAQ")
        assert "AAPL" in key

    def test_backtest_key(self, override_settings):
        uid = uuid.uuid4()
        key = backtest_key(uid, "abc123")
        assert "abc123" in key

    def test_correlation_key(self, override_settings):
        uid = uuid.uuid4()
        key = correlation_key(uid, "hash42")
        assert "hash42" in key

    def test_dart_disclosures_key(self, override_settings):
        uid = uuid.uuid4()
        key = dart_disclosures_key(uid, 7)
        assert "7" in key

    def test_alloc_history_key(self, override_settings):
        uid = uuid.uuid4()
        key = alloc_history_key(uid, 12)
        assert "12" in key

    def test_ob_state_key(self, override_settings):
        key = ob_state_key("random_state_xyz")
        assert "random_state_xyz" in key

    def test_has_overseas_key(self, override_settings):
        key = has_overseas_key(42)
        assert "42" in key

    def test_dividend_summary_key(self, override_settings):
        uid = uuid.uuid4()
        key = dividend_summary_key(uid)
        assert str(uid) in key

    def test_portfolio_overview_key(self, override_settings):
        uid = uuid.uuid4()
        key = portfolio_overview_key(uid)
        assert str(uid) in key

    def test_portfolio_overview_lite_key(self, override_settings):
        uid = uuid.uuid4()
        key = portfolio_overview_lite_key(uid)
        assert "lite" in key

    def test_portfolio_list_key(self, override_settings):
        uid = uuid.uuid4()
        key = portfolio_list_key(uid)
        assert str(uid) in key

    def test_economic_indicator_latest_key(self, override_settings):
        key = economic_indicator_latest_key("GDP")
        assert "GDP" in key

    def test_economic_indicator_calendar_key(self, override_settings):
        key = economic_indicator_calendar_key()
        assert "calendar" in key or "economic" in key


class TestInvalidateUserCaches:
    @pytest.mark.asyncio
    async def test_calls_redis_delete(self, override_settings):
        redis = AsyncMock()
        await invalidate_user_caches(redis, "key1", "key2")
        redis.delete.assert_called_once_with("key1", "key2")

    @pytest.mark.asyncio
    async def test_suppresses_redis_error(self, override_settings):
        redis = AsyncMock()
        redis.delete.side_effect = RedisError("fail")
        await invalidate_user_caches(redis, "key1")  # should not raise


# ── currency ─────────────────────────────────────────────────────────────────


class TestGetUsdKrwRate:
    @pytest.mark.asyncio
    async def test_returns_fallback_when_redis_is_none(self, override_settings):
        rate = await get_usd_krw_rate(None)
        assert rate > 0

    @pytest.mark.asyncio
    async def test_returns_cached_value_when_available(self, override_settings):
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=b"1350.5")
        rate = await get_usd_krw_rate(redis)
        assert rate == pytest.approx(1350.5)

    @pytest.mark.asyncio
    async def test_returns_fallback_when_cache_miss(self, override_settings):
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        rate = await get_usd_krw_rate(redis, fallback_rate=1300.0)
        assert rate == pytest.approx(1300.0)

    @pytest.mark.asyncio
    async def test_suppresses_redis_error_and_returns_fallback(self, override_settings):
        redis = AsyncMock()
        redis.get = AsyncMock(side_effect=RedisError("connection error"))
        rate = await get_usd_krw_rate(redis, fallback_rate=1400.0)
        assert rate == pytest.approx(1400.0)

    @pytest.mark.asyncio
    async def test_custom_fallback_rate_used(self, override_settings):
        rate = await get_usd_krw_rate(None, fallback_rate=1200.0)
        assert rate == pytest.approx(1200.0)


class TestCacheUsdKrwRate:
    @pytest.mark.asyncio
    async def test_stores_rate_in_redis(self, override_settings):
        redis = AsyncMock()
        await cache_usd_krw_rate(redis, 1350.0)
        redis.setex.assert_called_once()
        args = redis.setex.call_args[0]
        assert "1350.0" in args

    @pytest.mark.asyncio
    async def test_does_nothing_when_redis_none(self, override_settings):
        await cache_usd_krw_rate(None, 1350.0)  # should not raise

    @pytest.mark.asyncio
    async def test_does_nothing_when_rate_zero(self, override_settings):
        redis = AsyncMock()
        await cache_usd_krw_rate(redis, 0)
        redis.setex.assert_not_called()

    @pytest.mark.asyncio
    async def test_suppresses_redis_error(self, override_settings):
        redis = AsyncMock()
        redis.setex.side_effect = RedisError("fail")
        await cache_usd_krw_rate(redis, 1350.0)  # should not raise


# ── fetch_usd_krw (force_refresh) ────────────────────────────


class TestFetchUsdKrw:
    @pytest.mark.asyncio
    async def test_no_force_refresh_returns_cache(self, override_settings):
        from app.utils.currency import fetch_usd_krw

        redis = AsyncMock()
        redis.get = AsyncMock(return_value=b"1350.0")

        rate = await fetch_usd_krw(redis, force_refresh=False)
        assert rate == pytest.approx(1350.0)

    @pytest.mark.asyncio
    async def test_force_refresh_returns_fetched(self, override_settings):
        from app.utils.currency import fetch_usd_krw

        redis = AsyncMock()
        redis.setex = AsyncMock()

        with patch("app.services.yahoo_price._sync_usdkrw", return_value=1380.0):
            loop_mock = AsyncMock()
            loop_mock.run_in_executor = AsyncMock(return_value=1380.0)

            with patch("asyncio.get_running_loop", return_value=loop_mock):
                rate = await fetch_usd_krw(redis, force_refresh=True)

        assert rate == pytest.approx(1380.0)
        redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_force_refresh_fallback_when_fetch_fails(self, override_settings):
        from app.utils.currency import fetch_usd_krw

        redis = AsyncMock()
        redis.get = AsyncMock(return_value=b"1300.0")

        loop_mock = AsyncMock()
        loop_mock.run_in_executor = AsyncMock(return_value=None)

        with patch("asyncio.get_running_loop", return_value=loop_mock):
            rate = await fetch_usd_krw(redis, force_refresh=True)

        assert rate == pytest.approx(1300.0)


# ── redis_lock ────────────────────────────────────────────────


class TestRedisLock:
    @pytest.mark.asyncio
    async def test_lock_acquired_yields_true_and_releases(self, override_settings):
        """락 획득 성공 시 True yield 후 해제."""
        import uuid as _uuid_mod

        from app.utils.redis_lock import redis_lock

        fixed_id = _uuid_mod.UUID("12345678-1234-5678-1234-567812345678")
        fixed_str = str(fixed_id)

        redis = AsyncMock()
        redis.set = AsyncMock(return_value=True)
        redis.get = AsyncMock(return_value=fixed_str)
        redis.delete = AsyncMock()

        with patch("app.utils.redis_lock.uuid.uuid4", return_value=fixed_id):
            async with redis_lock(redis, "test:lock:key") as acquired:
                assert acquired is True

        redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_lock_not_acquired_yields_false(self, override_settings):
        """락 획득 실패 시 False yield."""
        from app.utils.redis_lock import redis_lock

        redis = AsyncMock()
        redis.set = AsyncMock(return_value=None)

        async with redis_lock(redis, "test:lock:key") as acquired:
            assert acquired is False

        redis.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_lock_not_released_if_stolen(self, override_settings):
        """락 값이 다를 경우 (다른 프로세스가 재획득) 삭제하지 않는다."""
        from app.utils.redis_lock import redis_lock

        redis = AsyncMock()
        redis.set = AsyncMock(return_value=True)
        redis.get = AsyncMock(return_value="different-value")
        redis.delete = AsyncMock()

        async with redis_lock(redis, "test:lock:key") as acquired:
            assert acquired is True

        redis.delete.assert_not_called()
