"""대시보드가 홈용 주식 평가손익·목표 달성 예상월을 함께 싣는다(plans/151 B1)."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.exc import OperationalError

_AGG = "app.services.portfolio.asset_aggregator"

_OVERVIEW = {"total_stock_krw": 12_000_000.0, "unrealized_pnl_krw": 1_500_000.0, "stock_return_pct": 14.29}


async def _extras(goal_settings=None, overview=None, month="2031-04", **patches):
    from app.services.portfolio.asset_aggregator import _home_extras

    with (
        patch(
            f"{_AGG}.build_portfolio_overview",
            new=patches.get("overview_mock") or AsyncMock(return_value=overview or _OVERVIEW),
        ) as ov,
        patch(f"{_AGG}.compute_goal_expected_month", new=AsyncMock(return_value=month)) as goal,
    ):
        result, _ok = await _home_extras(uuid.uuid4(), AsyncMock(), None, goal_settings, 50_000_000.0)
    return result, ov, goal


@pytest.mark.asyncio
async def test_stock_pnl_uses_lite_overview_excluding_out_of_total(override_settings):
    result, ov, _ = await _extras()
    assert result["stock_pnl"] == {
        "total_stock_krw": 12_000_000.0,
        "unrealized_pnl_krw": 1_500_000.0,
        "return_pct": 14.29,
    }
    kwargs = ov.await_args.kwargs
    assert kwargs["lite"] is True
    assert kwargs["exclude_out_of_total"] is True  # 자산 탭과 같은 기준


@pytest.mark.asyncio
async def test_no_stock_means_no_stock_pnl(override_settings):
    result, _, _ = await _extras(overview={**_OVERVIEW, "total_stock_krw": 0.0})
    assert result["stock_pnl"] is None


@pytest.mark.asyncio
async def test_goal_month_only_with_goal_settings(override_settings):
    without, _, goal = await _extras(goal_settings=None)
    assert without["goal_expected_month"] is None
    goal.assert_not_awaited()

    with_goal, _, _ = await _extras(goal_settings=SimpleNamespace(goal_amount=1))
    assert with_goal["goal_expected_month"] == "2031-04"


@pytest.mark.asyncio
async def test_non_db_failure_is_isolated(override_settings):
    result, _, _ = await _extras(overview_mock=AsyncMock(side_effect=KeyError("total_stock_krw")))
    assert result == {"stock_pnl": None, "goal_expected_month": None}


@pytest.mark.asyncio
async def test_db_failure_propagates(override_settings):
    """rollback으로 삼키면 같은 세션을 이어 쓰는 호출부의 ORM 객체가 만료된다 — 다른 집계 쿼리처럼 올린다."""
    with pytest.raises(OperationalError):
        await _extras(overview_mock=AsyncMock(side_effect=OperationalError("select", {}, Exception("down"))))


# ── get_home_dashboard — 공용 요약 + 홈 전용 필드(따로 캐시, plans/152 B3) ──

_SUMMARY = {"total_assets_krw": 1.0, "investable_assets_krw": 50_000_000.0, "goal_amount": 100_000_000.0}


async def _home(cache, extras_result):
    from app.services.portfolio.asset_aggregator import get_home_dashboard

    user_id = uuid.UUID(int=1)
    with (
        patch(f"{_AGG}.get_dashboard_summary", new=AsyncMock(return_value=dict(_SUMMARY))),
        patch(f"{_AGG}.get_settings_row", new=AsyncMock(return_value=SimpleNamespace(goal_amount=1))),
        patch(f"{_AGG}._home_extras", new=AsyncMock(return_value=extras_result)) as extras,
    ):
        result = await get_home_dashboard(user_id, AsyncMock(), cache)
    return result, extras


@pytest.mark.asyncio
async def test_home_dashboard_merges_and_caches_extras(override_settings):
    from app.core.cache_store import CacheStore
    from app.utils.cache_keys import TTL_DASHBOARD_HOME_EXTRAS, dashboard_home_extras_key

    cache = CacheStore()
    ok = ({"stock_pnl": None, "goal_expected_month": "2031-04"}, True)
    with patch.object(cache, "setex", wraps=cache.setex) as setex:
        first, extras = await _home(cache, ok)
    assert first["goal_expected_month"] == "2031-04"
    assert first["total_assets_krw"] == 1.0
    assert setex.call_args.args[:2] == (dashboard_home_extras_key(uuid.UUID(int=1)), TTL_DASHBOARD_HOME_EXTRAS)

    second, extras2 = await _home(cache, ok)
    assert second == first
    extras2.assert_not_awaited()  # 캐시 재사용


@pytest.mark.asyncio
async def test_home_dashboard_failed_extras_cached_briefly(override_settings):
    from app.core.cache_store import CacheStore
    from app.utils.cache_keys import TTL_DASHBOARD_HOME_EXTRAS_FAILED

    cache = CacheStore()
    failed = ({"stock_pnl": None, "goal_expected_month": None}, False)
    with patch.object(cache, "setex", wraps=cache.setex) as setex:
        result, _ = await _home(cache, failed)
    assert result["stock_pnl"] is None
    assert setex.call_args.args[1] == TTL_DASHBOARD_HOME_EXTRAS_FAILED
