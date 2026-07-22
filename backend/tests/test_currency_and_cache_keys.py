"""utils/currency.py 및 utils/cache_keys.py 단위 테스트."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.utils.cache_keys import (
    alloc_history_key,
    backtest_key,
    composite_alert_sent_key,
    correlation_key,
    current_price_display_key,
    current_price_key,
    dividend_info_key,
    dividend_months_key,
    dividend_summary_key,
    dividend_ticker_summary_key,
    economic_indicator_calendar_key,
    has_overseas_key,
    invalidate_rebalancing_strategy_cache,
    invalidate_user_caches,
    monthly_trend_key,
    portfolio_list_key,
    portfolio_overview_key,
    portfolio_overview_lite_key,
    price_return_key,
    rebalancing_strategy_key,
)
from app.utils.currency import cache_usd_krw_rate, get_usd_krw_rate

# ── cache_keys ───────────────────────────────────────────────────────────────


class TestCacheKeyBuilders:
    def test_current_price_key(self, override_settings):
        assert current_price_key("AAPL", "NASDAQ") == "test:price:current:AAPL:NASDAQ"

    def test_current_price_display_key_differs_from_current_price_key(self, override_settings):
        """price_service.py의 plain float 캐시(current_price_key)와 stocks.py의 JSON 캐시
        (current_price_display_key)는 같은 키를 공유하면 안 된다 — 공유 시 float(cached)가
        JSON 문자열을 파싱하려다 크래시하는 회귀가 있었다."""
        assert current_price_display_key("AAPL", "NASDAQ") != current_price_key("AAPL", "NASDAQ")

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

    def test_alloc_history_key(self, override_settings):
        uid = uuid.uuid4()
        key = alloc_history_key(uid, 12)
        assert "12" in key

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

    def test_economic_indicator_calendar_key(self, override_settings):
        key = economic_indicator_calendar_key()
        assert "calendar" in key or "economic" in key

    def test_composite_alert_sent_key(self, override_settings):
        uid = uuid.uuid4()
        key = composite_alert_sent_key(uid, "2026-07-05")
        assert str(uid) in key
        assert "2026-07-05" in key

    def test_composite_alert_sent_key_differs_by_day(self, override_settings):
        uid = uuid.uuid4()
        assert composite_alert_sent_key(uid, "2026-07-05") != composite_alert_sent_key(uid, "2026-07-06")

    def test_rebalancing_strategy_key(self, override_settings):
        uid = uuid.uuid4()
        key = rebalancing_strategy_key(uid, "portfolio-1", "acct-a_acct-b")
        assert str(uid) in key
        assert "portfolio-1" in key
        assert "acct-a_acct-b" in key


class TestInvalidateRebalancingStrategyCache:
    """실행 후 무효화가 쓰기 시점 acct_suffix 포함 키를 실제로 지우는지 검증 (회귀 방지)."""

    @pytest.mark.asyncio
    async def test_invalidate_deletes_key_written_with_acct_suffix(self, override_settings):
        uid = uuid.uuid4()
        portfolio_id = "portfolio-1"
        written_key = rebalancing_strategy_key(uid, portfolio_id, "acct-a_acct-b")

        cache = AsyncMock()
        cache.scan = AsyncMock(return_value=(0, [written_key]))
        cache.unlink = AsyncMock()

        await invalidate_rebalancing_strategy_cache(cache, uid, portfolio_id)

        cache.scan.assert_called_once()
        _, kwargs = cache.scan.call_args
        pattern = kwargs["match"]
        assert str(uid) in pattern
        assert portfolio_id in pattern
        assert pattern.endswith(":*")
        cache.unlink.assert_called_once_with(written_key)


class TestInvalidateUserCaches:
    @pytest.mark.asyncio
    async def test_calls_cache_delete(self, override_settings):
        cache = AsyncMock()
        await invalidate_user_caches(cache, "key1", "key2")
        cache.delete.assert_called_once_with("key1", "key2")


# ── currency ─────────────────────────────────────────────────────────────────


class TestGetUsdKrwRate:
    @pytest.mark.asyncio
    async def test_returns_fallback_when_cache_is_none(self, override_settings):
        rate = await get_usd_krw_rate(None)
        assert rate > 0

    @pytest.mark.asyncio
    async def test_returns_cached_value_when_available(self, override_settings):
        cache = AsyncMock()
        cache.get = AsyncMock(return_value=b"1350.5")
        rate = await get_usd_krw_rate(cache)
        assert rate == pytest.approx(1350.5)

    @pytest.mark.asyncio
    async def test_returns_fallback_when_cache_miss(self, override_settings):
        cache = AsyncMock()
        cache.get = AsyncMock(return_value=None)
        rate = await get_usd_krw_rate(cache, fallback_rate=1300.0)
        assert rate == pytest.approx(1300.0)

    @pytest.mark.asyncio
    async def test_custom_fallback_rate_used(self, override_settings):
        rate = await get_usd_krw_rate(None, fallback_rate=1200.0)
        assert rate == pytest.approx(1200.0)


class TestCacheUsdKrwRate:
    @pytest.mark.asyncio
    async def test_stores_rate_in_cache(self, override_settings):
        cache = AsyncMock()
        await cache_usd_krw_rate(cache, 1350.0)
        cache.setex.assert_called_once()
        args = cache.setex.call_args[0]
        assert "1350.0" in args

    @pytest.mark.asyncio
    async def test_does_nothing_when_cache_none(self, override_settings):
        await cache_usd_krw_rate(None, 1350.0)  # should not raise

    @pytest.mark.asyncio
    async def test_does_nothing_when_rate_zero(self, override_settings):
        cache = AsyncMock()
        await cache_usd_krw_rate(cache, 0)
        cache.setex.assert_not_called()


# ── fetch_usd_krw (force_refresh) ────────────────────────────


class TestFetchUsdKrw:
    @pytest.mark.asyncio
    async def test_no_force_refresh_returns_cache(self, override_settings):
        from app.utils.currency import fetch_usd_krw

        cache = AsyncMock()
        cache.get = AsyncMock(return_value=b"1350.0")

        rate = await fetch_usd_krw(cache, force_refresh=False)
        assert rate == pytest.approx(1350.0)

    @pytest.mark.asyncio
    async def test_force_refresh_returns_fetched(self, override_settings):
        from app.utils.currency import fetch_usd_krw

        cache = AsyncMock()
        cache.setex = AsyncMock()

        with patch("app.services.yahoo_price._sync_usdkrw", return_value=1380.0):
            loop_mock = AsyncMock()
            loop_mock.run_in_executor = AsyncMock(return_value=1380.0)

            with patch("asyncio.get_running_loop", return_value=loop_mock):
                rate = await fetch_usd_krw(cache, force_refresh=True)

        assert rate == pytest.approx(1380.0)
        cache.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_force_refresh_fallback_when_fetch_fails(self, override_settings):
        from app.utils.currency import fetch_usd_krw

        cache = AsyncMock()
        cache.get = AsyncMock(return_value=b"1300.0")

        loop_mock = AsyncMock()
        loop_mock.run_in_executor = AsyncMock(return_value=None)

        with patch("asyncio.get_running_loop", return_value=loop_mock):
            rate = await fetch_usd_krw(cache, force_refresh=True)

        assert rate == pytest.approx(1300.0)


# ── inproc_lock ────────────────────────────────────────────────


class TestCacheLock:
    @pytest.mark.asyncio
    async def test_lock_acquired_yields_true_and_releases(self, override_settings):
        """락 획득 성공 시 True yield 후 해제."""
        import uuid as _uuid_mod

        from app.utils.inproc_lock import inproc_lock

        fixed_id = _uuid_mod.UUID("12345678-1234-5678-1234-567812345678")
        fixed_str = str(fixed_id)

        cache = AsyncMock()
        cache.set = AsyncMock(return_value=True)
        cache.get = AsyncMock(return_value=fixed_str)
        cache.delete = AsyncMock()

        with patch("app.utils.inproc_lock.uuid.uuid4", return_value=fixed_id):
            async with inproc_lock(cache, "test:lock:key") as acquired:
                assert acquired is True

        cache.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_lock_not_acquired_yields_false(self, override_settings):
        """락 획득 실패 시 False yield."""
        from app.utils.inproc_lock import inproc_lock

        cache = AsyncMock()
        cache.set = AsyncMock(return_value=None)

        async with inproc_lock(cache, "test:lock:key") as acquired:
            assert acquired is False

        cache.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_lock_not_released_if_stolen(self, override_settings):
        """락 값이 다를 경우 (다른 프로세스가 재획득) 삭제하지 않는다."""
        from app.utils.inproc_lock import inproc_lock

        cache = AsyncMock()
        cache.set = AsyncMock(return_value=True)
        cache.get = AsyncMock(return_value="different-value")
        cache.delete = AsyncMock()

        async with inproc_lock(cache, "test:lock:key") as acquired:
            assert acquired is True

        cache.delete.assert_not_called()
