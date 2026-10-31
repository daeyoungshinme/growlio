"""utils/currency.py 및 utils/cache_keys.py 단위 테스트."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.utils.cache_invalidation import (
    invalidate_asset_account_caches,
    invalidate_rebalancing_strategy_cache,
    invalidate_user_caches,
)
from app.utils.cache_keys import (
    alloc_history_key,
    backtest_key,
    composite_alert_sent_key,
    current_price_display_key,
    current_price_key,
    dca_analysis_key,
    dividend_info_key,
    dividend_months_key,
    dividend_summary_key,
    dividend_ticker_summary_key,
    economic_indicator_calendar_key,
    has_overseas_key,
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

    def test_dca_analysis_key(self, override_settings):
        uid = uuid.uuid4()
        key = dca_analysis_key(uid)
        assert str(uid) in key
        assert key.startswith("test:dca_analysis:")

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

    @pytest.mark.asyncio
    async def test_analysis_invalidation_also_clears_strategy(self, override_settings):
        """plans/77 B3 — 포트폴리오 수정·전술 적용(분석 캐시 무효화 경로)이 전략 비교 캐시도 지운다."""
        from app.core.cache_store import CacheStore
        from app.utils.cache_invalidation import invalidate_rebalancing_analysis_cache

        uid = uuid.uuid4()
        cache = CacheStore()
        key = rebalancing_strategy_key(uid, "portfolio-1", "all")
        other = rebalancing_strategy_key(uid, "portfolio-2", "all")
        await cache.set(key, "{}")
        await cache.set(other, "{}")

        await invalidate_rebalancing_analysis_cache(cache, uid, "portfolio-1")

        assert await cache.get(key) is None
        assert await cache.get(other) == "{}"

    @pytest.mark.asyncio
    async def test_analysis_invalidation_clears_target_factor_and_frontier(self, override_settings):
        """plans/95 A1 — 전략 재계산이 읽는 목표 팩터·프론티어 캐시가 남으면 옛 비중이 다시 조립된다."""
        from app.core.cache_store import CacheStore
        from app.utils.cache_invalidation import invalidate_rebalancing_analysis_cache
        from app.utils.cache_keys import efficient_frontier_key, factor_analysis_portfolio_key

        uid = uuid.uuid4()
        cache = CacheStore()
        factor = factor_analysis_portfolio_key("portfolio-1")
        frontier = efficient_frontier_key(uid, "portfolio-1", "acct-a")
        other_frontier = efficient_frontier_key(uid, "portfolio-2", "all")
        for k in (factor, frontier, other_frontier):
            await cache.set(k, "{}")

        await invalidate_rebalancing_analysis_cache(cache, uid, "portfolio-1")

        assert await cache.get(factor) is None
        assert await cache.get(frontier) is None
        assert await cache.get(other_frontier) == "{}"


class TestInvalidateDividendCaches:
    """positions_changed 플래그로 종목별 배당 추정(외부 API 폴백 체인 필요) 캐시 무효화를
    건너뛸 수 있는지 검증 — 계좌 동기화마다 매번 지우던 기존 동작이 "동기화 후 대시보드
    로딩이 느리다"는 체감 지연의 원인이었다."""

    @pytest.mark.asyncio
    async def test_full_invalidation_by_default(self, override_settings):
        from app.utils.cache_invalidation import invalidate_dividend_caches

        cache = AsyncMock()
        cache.scan = AsyncMock(return_value=(0, []))
        cache.unlink = AsyncMock()

        await invalidate_dividend_caches(cache, uuid.uuid4(), 2026)

        assert cache.scan.call_count == 3

    @pytest.mark.asyncio
    async def test_positions_unchanged_skips_by_ticker_cache(self, override_settings):
        from app.utils.cache_invalidation import invalidate_dividend_caches

        cache = AsyncMock()
        cache.scan = AsyncMock(return_value=(0, []))
        cache.unlink = AsyncMock()

        await invalidate_dividend_caches(cache, uuid.uuid4(), 2026, positions_changed=False)

        cache.scan.assert_called_once()
        _, kwargs = cache.scan.call_args
        assert "dividend_summary:" in kwargs["match"]


class TestInvalidateAssetAccountCachesGoalRecommendation:
    """목표 역산 추천 캐시는 보유 종목 구성이 바뀐 경우에만 지운다 — 평가액만 바뀐 정기 sync마다
    지우면 무거운 MVO 재계산이 거의 매번 콜드로 돌았다."""

    @staticmethod
    def _deleted_keys(cache: AsyncMock) -> set[str]:
        return {k for call in cache.delete.call_args_list for k in call.args}

    @pytest.mark.asyncio
    async def test_positions_changed_invalidates_goal_recommendation(self, override_settings):
        from app.core.cache_store import CacheStore
        from app.utils.cache_invalidation import invalidate_asset_account_caches
        from app.utils.cache_keys import (
            get_goal_recommendation_generation,
            goal_recommendation_key,
            goal_recommendation_stale_key,
        )

        cache = CacheStore()
        uid = uuid.uuid4()
        gen = await get_goal_recommendation_generation(cache, uid)
        await cache.set(goal_recommendation_key(uid, gen), "{}")
        await cache.set(goal_recommendation_stale_key(uid, gen), "{}")

        await invalidate_asset_account_caches(cache, uid)

        assert await cache.get(goal_recommendation_key(uid, gen)) is None
        # 보유 종목이 바뀌면 stale 결과도 틀린 답이라 함께 지운다(plans/66)
        assert await cache.get(goal_recommendation_stale_key(uid, gen)) is None
        assert await get_goal_recommendation_generation(cache, uid) != gen

    @pytest.mark.asyncio
    async def test_positions_unchanged_keeps_goal_recommendation(self, override_settings):
        from app.core.cache_store import CacheStore
        from app.utils.cache_invalidation import invalidate_asset_account_caches
        from app.utils.cache_keys import get_goal_recommendation_generation, goal_recommendation_key

        cache = CacheStore()
        uid = uuid.uuid4()
        gen = await get_goal_recommendation_generation(cache, uid)
        await cache.set(goal_recommendation_key(uid, gen), "{}")

        await invalidate_asset_account_caches(cache, uid, positions_changed=False)

        assert await cache.get(goal_recommendation_key(uid, gen)) == "{}"
        assert await get_goal_recommendation_generation(cache, uid) == gen

    @pytest.mark.asyncio
    @pytest.mark.parametrize("positions_changed", [True, False])
    async def test_holdings_factor_and_frontier_follow_positions_changed(self, positions_changed, override_settings):
        """plans/95 A2 — 보유 기반 팩터·프론티어는 구성이 바뀐 경우에만 지우고, 포트폴리오 단위 팩터는 남긴다."""
        from app.core.cache_store import CacheStore
        from app.utils.cache_keys import efficient_frontier_key, factor_analysis_key, factor_analysis_portfolio_key

        cache = CacheStore()
        uid = uuid.uuid4()
        holdings_factor = factor_analysis_key(uid, "all")
        frontier = efficient_frontier_key(uid, None, "all")
        portfolio_factor = factor_analysis_portfolio_key("portfolio-1")
        for k in (holdings_factor, frontier, portfolio_factor):
            await cache.set(k, "{}")

        await invalidate_asset_account_caches(cache, uid, positions_changed=positions_changed)

        expected = None if positions_changed else "{}"
        assert await cache.get(holdings_factor) == expected
        assert await cache.get(frontier) == expected
        assert await cache.get(portfolio_factor) == "{}"


class TestInvalidateGoalRecommendationCaches:
    @pytest.mark.asyncio
    async def test_settings_change_invalidates_stale_result_too(self, override_settings):
        """목표·후보·옵션 변경 후 stale 결과를 돌려주면 바뀌기 전 설정의 답이 보인다 — 함께 지운다."""
        from app.core.cache_store import CacheStore
        from app.utils.cache_invalidation import invalidate_goal_recommendation_caches
        from app.utils.cache_keys import (
            get_goal_recommendation_generation,
            goal_recommendation_age_key,
            goal_recommendation_age_stale_key,
            goal_recommendation_horizon_key,
            goal_recommendation_horizon_stale_key,
            goal_recommendation_key,
            goal_recommendation_stale_key,
        )

        cache = CacheStore()
        uid = uuid.uuid4()
        gen = await get_goal_recommendation_generation(cache, uid)
        keys = [
            goal_recommendation_key(uid, gen),
            goal_recommendation_stale_key(uid, gen),
            goal_recommendation_horizon_key(uid, gen),
            goal_recommendation_horizon_stale_key(uid, gen),
            goal_recommendation_age_key(uid, gen),
            goal_recommendation_age_stale_key(uid, gen),
        ]
        for key in keys:
            await cache.set(key, "{}")

        await invalidate_goal_recommendation_caches(cache, uid)

        assert [await cache.get(k) for k in keys] == [None] * len(keys)

    @pytest.mark.asyncio
    async def test_invalidation_rotates_generation(self, override_settings):
        """계산 도중 무효화되면 끝난 옛 계산은 옛 세대 키에 쓴다 — 새 세대 조회에는 보이지 않아야 한다(plans/88)."""
        from app.core.cache_store import CacheStore
        from app.utils.cache_invalidation import invalidate_goal_recommendation_caches
        from app.utils.cache_keys import get_goal_recommendation_generation, goal_recommendation_key

        cache = CacheStore()
        uid = uuid.uuid4()
        old_gen = await get_goal_recommendation_generation(cache, uid)
        assert await get_goal_recommendation_generation(cache, uid) == old_gen  # 같은 세대 안에서는 고정

        await invalidate_goal_recommendation_caches(cache, uid)
        new_gen = await get_goal_recommendation_generation(cache, uid)
        await cache.set(goal_recommendation_key(uid, old_gen), "old")  # 늦게 끝난 옛 계산

        assert new_gen != old_gen
        assert await cache.get(goal_recommendation_key(uid, new_gen)) is None

    @pytest.mark.asyncio
    async def test_generation_without_cache_is_random(self, override_settings):
        from app.utils.cache_keys import get_goal_recommendation_generation

        uid = uuid.uuid4()
        assert await get_goal_recommendation_generation(None, uid) != await get_goal_recommendation_generation(
            None, uid
        )


class TestInvalidateUserCaches:
    @pytest.mark.asyncio
    async def test_calls_cache_delete(self, override_settings):
        cache = AsyncMock()
        await invalidate_user_caches(cache, "key1", "key2")
        cache.delete.assert_called_once_with("key1", "key2")


class TestInvalidateDcaAnalysisCache:
    """DCA 분석 응답 캐시(dca_analysis_key)가 대시보드 캐시와 같은 트리거로 무효화되는지
    검증 — 별도로 무효화 트리거를 빠뜨리면 계좌 동기화/목표 설정 변경 후에도 낡은 DCA
    분석 결과가 15분간 그대로 노출된다."""

    @pytest.mark.asyncio
    async def test_invalidate_asset_account_caches_includes_dca_key(self, override_settings):
        cache = AsyncMock()
        cache.scan = AsyncMock(return_value=(0, []))
        cache.unlink = AsyncMock()
        user_id = uuid.uuid4()

        await invalidate_asset_account_caches(cache, user_id)

        deleted_keys = cache.delete.call_args.args
        assert dca_analysis_key(user_id) in deleted_keys

    @pytest.mark.asyncio
    async def test_invalidate_asset_account_caches_scans_overseas_tax_keys(self, override_settings):
        """계좌 CRUD(삭제·tax_type 변경)도 과세 대상 계좌 집합을 바꾸므로 해외 양도세 캐시를 지워야 한다
        — 예전엔 sync 경로에서만 지워 최대 1시간 stale했다."""
        cache = AsyncMock()
        cache.scan = AsyncMock(return_value=(0, []))
        cache.unlink = AsyncMock()
        user_id = uuid.uuid4()

        await invalidate_asset_account_caches(cache, user_id)

        patterns = [c.kwargs["match"] for c in cache.scan.call_args_list]
        assert f"test:tax:overseas:{user_id}:*" in patterns
        assert f"test:tax:overseas_realized:{user_id}:*" in patterns

    @pytest.mark.asyncio
    async def test_invalidate_asset_account_caches_clears_trend_and_alloc_history(self, override_settings):
        """계좌 삭제(is_active=False)·포지션 수정 후에도 월별 추이·배분 이력이 갱신돼야 한다
        — 예전엔 sync 전용 함수에서만 지워 계좌 삭제 후 배분 이력에 최대 하루 남았다."""
        cache = AsyncMock()
        cache.scan = AsyncMock(return_value=(0, []))
        cache.unlink = AsyncMock()
        user_id = uuid.uuid4()

        await invalidate_asset_account_caches(cache, user_id)

        assert monthly_trend_key(user_id) in cache.delete.call_args.args
        patterns = [c.kwargs["match"] for c in cache.scan.call_args_list]
        assert any(p.startswith("test:alloc_history_") and str(user_id) in p for p in patterns)

    @pytest.mark.asyncio
    async def test_invalidate_asset_account_caches_clears_challenge_insights_risk(self, override_settings):
        """계좌 삭제·잔액 수정·sync 후 챌린지 진행률·인사이트·리스크가 TTL(5분~1시간) 동안
        삭제 계좌를 반영한 채 남던 버그."""
        from app.utils.cache_keys import challenge_progress_key, insights_key, risk_key

        cache = AsyncMock()
        cache.scan = AsyncMock(return_value=(0, []))
        cache.unlink = AsyncMock()
        user_id = uuid.uuid4()

        await invalidate_asset_account_caches(cache, user_id)

        deleted = {k for c in cache.delete.call_args_list for k in c.args}
        assert challenge_progress_key(user_id) in deleted
        assert insights_key(user_id) in deleted
        assert risk_key(user_id) in deleted


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

    @pytest.mark.asyncio
    @pytest.mark.parametrize("rate", [1.25, -0.8, 99999.0])
    async def test_ignores_implausible_rate(self, override_settings, rate):
        """등락률 같은 다른 필드를 잘못 읽은 값이 전역 환율 캐시에 들어가면 모든 환산이 오염된다 (plans/99 A1)."""
        cache = AsyncMock()
        await cache_usd_krw_rate(cache, rate)
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

        with patch("app.services.market_data.yahoo_price._sync_usdkrw", return_value=1380.0):
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

    @pytest.mark.asyncio
    async def test_no_fallback_returns_zero_when_fetch_fails_and_cache_miss(self, override_settings):
        """allow_fallback=False면 실시간·캐시 모두 없을 때 설정 fallback 대신 0.0 (plans/97 A1)."""
        from app.utils.currency import fetch_usd_krw

        cache = AsyncMock()
        cache.get = AsyncMock(return_value=None)

        with patch("app.services.market_data.yahoo_price.fetch_usdkrw", AsyncMock(return_value=0.0)):
            rate = await fetch_usd_krw(cache, force_refresh=True, allow_fallback=False)

        assert rate == 0.0

    @pytest.mark.asyncio
    async def test_no_fallback_uses_cache_when_fetch_fails(self, override_settings):
        from app.utils.currency import fetch_usd_krw

        cache = AsyncMock()
        cache.get = AsyncMock(return_value=b"1412.5")

        with patch("app.services.market_data.yahoo_price.fetch_usdkrw", AsyncMock(return_value=0.0)):
            rate = await fetch_usd_krw(cache, force_refresh=True, allow_fallback=False)

        assert rate == pytest.approx(1412.5)


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


class TestInvalidationPatternsMatchBuilders:
    """무효화 함수의 SCAN 패턴이 키 빌더의 포맷과 어긋나지 않는지 — 빌더가 만든 키를 실제 CacheStore에 넣고
    무효화 후 사라졌는지 본다. 패턴은 f-string으로 따로 쓰여 있어, 빌더만 바꾸면 무효화가 조용히 빗나간다."""

    async def test_asset_account_invalidation_removes_every_user_scoped_key(self, override_settings):
        from app.core.cache_store import CacheStore
        from app.utils import cache_invalidation as ci
        from app.utils import cache_keys as ck

        uid, pid = uuid.uuid4(), uuid.uuid4()
        keys = [
            ck.alloc_history_key(uid, 12, "acct1"),
            ck.dividend_summary_key(uid, "acct1"),
            ck.dividend_ticker_summary_key(uid, 2026, "acct1"),
            ck.dividends_positions_key(uid, "acct1"),
            ck.portfolio_overview_key(uid, "acct1"),
            ck.portfolio_overview_lite_key(uid, "acct1"),
            ck.rebalancing_strategy_key(uid, pid, "acct1"),
            ck.rebalancing_analysis_key(uid, pid, "acct1", None),
            ck.tax_overseas_key(uid, "acct1"),
            ck.tax_overseas_realized_key(uid, 2026, "acct1"),
            ck.factor_analysis_key(uid, "acct1"),
            ck.efficient_frontier_key(uid, str(pid), "acct1"),
            ck.monthly_trend_key(uid),
            ck.dashboard_summary_key(uid),
            ck.insights_key(uid),
        ]
        store = CacheStore()
        for k in keys:
            await store.setex(k, 3600, "1")

        await ci.invalidate_asset_account_caches(store, uid, 2026)

        assert [k for k in keys if await store.get(k) is not None] == []

    async def test_portfolio_analysis_invalidation_is_scoped_to_that_portfolio(self, override_settings):
        from app.core.cache_store import CacheStore
        from app.utils import cache_invalidation as ci
        from app.utils import cache_keys as ck

        uid, pid, other = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        target = [
            ck.rebalancing_analysis_key(uid, pid, "acct1", None),
            ck.rebalancing_strategy_key(uid, pid, "acct1"),
            ck.factor_analysis_portfolio_key(pid),
            ck.efficient_frontier_key(uid, str(pid), "acct1"),
        ]
        kept = ck.rebalancing_analysis_key(uid, other, "acct1", 50000.0)
        store = CacheStore()
        for k in [*target, kept]:
            await store.setex(k, 3600, "1")

        await ci.invalidate_rebalancing_analysis_cache(store, uid, pid)

        assert [k for k in target if await store.get(k) is not None] == []
        assert await store.get(kept) == "1"
