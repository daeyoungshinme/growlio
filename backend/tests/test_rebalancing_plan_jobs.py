"""rebalancing_plan_buy_execution.py / rebalancing_plan_sell_expiry.py Job 단위 테스트."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_lock_cm(acquired: bool):
    lock_cm = MagicMock()
    lock_cm.__aenter__ = AsyncMock(return_value=acquired)
    lock_cm.__aexit__ = AsyncMock(return_value=False)
    return lock_cm


def _make_mock_db():
    mock_db = MagicMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=False)
    return mock_db


class TestRunRebalancingPlanBuyExecution:
    @pytest.mark.asyncio
    async def test_market_closed_skips_execution(self):
        with (
            patch("app.jobs.rebalancing_plan_buy_execution.is_korean_market_open", return_value=False),
            patch("app.jobs.rebalancing_plan_buy_execution.get_redis") as mock_get_redis,
        ):
            from app.jobs.rebalancing_plan_buy_execution import run_rebalancing_plan_buy_execution

            await run_rebalancing_plan_buy_execution()

        mock_get_redis.assert_not_called()

    @pytest.mark.asyncio
    async def test_lock_not_acquired_skips_execution(self):
        with (
            patch("app.jobs.rebalancing_plan_buy_execution.is_korean_market_open", return_value=True),
            patch("app.jobs.rebalancing_plan_buy_execution.get_redis", new=AsyncMock(return_value=MagicMock())),
            patch("app.jobs.rebalancing_plan_buy_execution.redis_lock", return_value=_make_lock_cm(False)),
            patch("app.jobs.rebalancing_plan_buy_execution.execute_due_buy_legs", new=AsyncMock()) as mock_exec,
        ):
            from app.jobs.rebalancing_plan_buy_execution import run_rebalancing_plan_buy_execution

            await run_rebalancing_plan_buy_execution()

        mock_exec.assert_not_called()

    @pytest.mark.asyncio
    async def test_executes_due_buy_legs_when_market_open_and_lock_acquired(self):
        mock_db = _make_mock_db()
        with (
            patch("app.jobs.rebalancing_plan_buy_execution.is_korean_market_open", return_value=True),
            patch("app.jobs.rebalancing_plan_buy_execution.get_redis", new=AsyncMock(return_value=MagicMock())),
            patch("app.jobs.rebalancing_plan_buy_execution.redis_lock", return_value=_make_lock_cm(True)),
            patch("app.jobs.rebalancing_plan_buy_execution.AsyncSessionLocal", return_value=mock_db),
            patch(
                "app.jobs.rebalancing_plan_buy_execution.execute_due_buy_legs", new=AsyncMock(return_value=2)
            ) as mock_exec,
        ):
            from app.jobs.rebalancing_plan_buy_execution import run_rebalancing_plan_buy_execution

            await run_rebalancing_plan_buy_execution()

        mock_exec.assert_called_once()


class TestRunRebalancingPlanSellExpiry:
    @pytest.mark.asyncio
    async def test_calls_expire_due_sell_legs(self):
        mock_db = _make_mock_db()
        with (
            patch("app.jobs.rebalancing_plan_sell_expiry.AsyncSessionLocal", return_value=mock_db),
            patch(
                "app.jobs.rebalancing_plan_sell_expiry.expire_due_sell_legs", new=AsyncMock(return_value=3)
            ) as mock_expire,
        ):
            from app.jobs.rebalancing_plan_sell_expiry import run_rebalancing_plan_sell_expiry

            await run_rebalancing_plan_sell_expiry()

        mock_expire.assert_called_once()
