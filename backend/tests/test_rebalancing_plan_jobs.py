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
    """시장(KR/US) 개장 여부는 이 job이 아니라 `execute_due_buy_legs()` 내부에서 leg별로
    판단한다(NYSE 시간대 AUTO 지원 이후) — 이 job은 lock 획득 여부만 게이팅한다."""

    @pytest.mark.asyncio
    async def test_lock_not_acquired_skips_execution(self):
        with (
            patch("app.jobs.rebalancing_plan_buy_execution.get_cache_store", new=AsyncMock(return_value=MagicMock())),
            patch("app.jobs.rebalancing_plan_buy_execution.inproc_lock", return_value=_make_lock_cm(False)),
            patch("app.jobs.rebalancing_plan_buy_execution.execute_due_buy_legs", new=AsyncMock()) as mock_exec,
        ):
            from app.jobs.rebalancing_plan_buy_execution import run_rebalancing_plan_buy_execution

            await run_rebalancing_plan_buy_execution()

        mock_exec.assert_not_called()

    @pytest.mark.asyncio
    async def test_executes_due_buy_legs_when_lock_acquired(self):
        mock_db = _make_mock_db()
        with (
            patch("app.jobs.rebalancing_plan_buy_execution.get_cache_store", new=AsyncMock(return_value=MagicMock())),
            patch("app.jobs.rebalancing_plan_buy_execution.inproc_lock", return_value=_make_lock_cm(True)),
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
