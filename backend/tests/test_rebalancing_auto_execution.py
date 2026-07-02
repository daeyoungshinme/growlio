"""rebalancing_auto_execution Job 단위 테스트 — AUTO 모드 자동 실행 검증."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

# ── 공통 헬퍼 ────────────────────────────────────────────────


def _make_mock_db():
    mock_db = MagicMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=False)
    execute_result = MagicMock()
    execute_result.all.return_value = []
    mock_db.execute = AsyncMock(return_value=execute_result)
    mock_db.scalar = AsyncMock(return_value=None)
    mock_db.commit = AsyncMock()
    return mock_db


def _make_lock_cm(acquired: bool):
    lock_cm = MagicMock()
    lock_cm.__aenter__ = AsyncMock(return_value=acquired)
    lock_cm.__aexit__ = AsyncMock(return_value=False)
    return lock_cm


def _make_alert(**kwargs) -> SimpleNamespace:
    defaults = {
        "id": uuid4(),
        "user_id": uuid4(),
        "auto_execution_time": None,
        "market_condition_mode": "DISABLED",
        "threshold_pct": 5.0,
        "last_triggered_at": None,
        "mode": "AUTO",
        "is_active": True,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _make_portfolio(**kwargs) -> SimpleNamespace:
    defaults = {"id": uuid4(), "name": "Test Portfolio", "account_ids": None}
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ── run_rebalancing_auto_execution ───────────────────────────


class TestRunRebalancingAutoExecution:
    @pytest.mark.asyncio
    async def test_market_closed_skips_redis_and_execution(self):
        with (
            patch("app.jobs.rebalancing_auto_execution.is_korean_market_open", return_value=False),
            patch("app.jobs.rebalancing_auto_execution.get_redis") as mock_get_redis,
        ):
            from app.jobs.rebalancing_auto_execution import run_rebalancing_auto_execution

            await run_rebalancing_auto_execution()

        mock_get_redis.assert_not_called()

    @pytest.mark.asyncio
    async def test_lock_not_acquired_skips_auto_execution(self):
        mock_redis = MagicMock()

        with (
            patch("app.jobs.rebalancing_auto_execution.is_korean_market_open", return_value=True),
            patch("app.jobs.rebalancing_auto_execution.get_redis", new=AsyncMock(return_value=mock_redis)),
            patch("app.jobs.rebalancing_auto_execution.redis_lock", return_value=_make_lock_cm(False)),
            patch("app.jobs.rebalancing_auto_execution._run_auto_execution", new=AsyncMock()) as mock_run,
        ):
            from app.jobs.rebalancing_auto_execution import run_rebalancing_auto_execution

            await run_rebalancing_auto_execution()

        mock_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatches_when_market_open_and_lock_acquired(self):
        mock_redis = MagicMock()

        with (
            patch("app.jobs.rebalancing_auto_execution.is_korean_market_open", return_value=True),
            patch("app.jobs.rebalancing_auto_execution.get_redis", new=AsyncMock(return_value=mock_redis)),
            patch("app.jobs.rebalancing_auto_execution.redis_lock", return_value=_make_lock_cm(True)),
            patch("app.jobs.rebalancing_auto_execution._run_auto_execution", new=AsyncMock()) as mock_run,
        ):
            from app.jobs.rebalancing_auto_execution import run_rebalancing_auto_execution

            await run_rebalancing_auto_execution()

        mock_run.assert_called_once()


# ── _run_auto_execution ──────────────────────────────────────


class TestRunAutoExecution:
    @pytest.mark.asyncio
    async def test_no_active_alerts_skips_execution(self):
        mock_db = _make_mock_db()
        mock_redis = MagicMock()

        with (
            patch("app.jobs.rebalancing_auto_execution.get_redis", new=AsyncMock(return_value=mock_redis)),
            patch("app.jobs.rebalancing_auto_execution.AsyncSessionLocal", return_value=mock_db),
            patch(
                "app.services.market_signal_service.get_market_signal",
                new=AsyncMock(return_value={"composite_level": "GREEN"}),
            ),
            patch("app.jobs.rebalancing_auto_execution._execute_for_alert", new=AsyncMock()) as mock_exec,
        ):
            from app.jobs.rebalancing_auto_execution import _run_auto_execution

            await _run_auto_execution()

        mock_exec.assert_not_called()

    @pytest.mark.asyncio
    async def test_market_signal_failure_defaults_to_green_and_continues(self):
        mock_db = _make_mock_db()
        mock_redis = MagicMock()
        alert = _make_alert()
        portfolio = _make_portfolio()

        execute_result = MagicMock()
        execute_result.all.return_value = [(alert, portfolio, "u@test.com", None, None)]
        mock_db.execute = AsyncMock(return_value=execute_result)

        with (
            patch("app.jobs.rebalancing_auto_execution.get_redis", new=AsyncMock(return_value=mock_redis)),
            patch("app.jobs.rebalancing_auto_execution.AsyncSessionLocal", return_value=mock_db),
            patch(
                "app.services.market_signal_service.get_market_signal",
                new=AsyncMock(side_effect=RuntimeError("timeout")),
            ),
            patch("app.jobs.rebalancing_auto_execution.is_alert_execution_time", return_value=True),
            patch("app.jobs.rebalancing_auto_execution.already_fired_today", return_value=False),
            patch(
                "app.jobs.rebalancing_auto_execution._execute_for_alert", new=AsyncMock(return_value=True)
            ) as mock_exec,
            patch("app.jobs.rebalancing_auto_execution.save_alert_history", new=AsyncMock()),
        ):
            from app.jobs.rebalancing_auto_execution import _run_auto_execution

            await _run_auto_execution()

        mock_exec.assert_called_once()

    @pytest.mark.asyncio
    async def test_execution_time_mismatch_skips_alert(self):
        mock_db = _make_mock_db()
        mock_redis = MagicMock()
        alert = _make_alert(auto_execution_time="09:30")
        portfolio = _make_portfolio()

        execute_result = MagicMock()
        execute_result.all.return_value = [(alert, portfolio, "u@test.com", None, None)]
        mock_db.execute = AsyncMock(return_value=execute_result)

        with (
            patch("app.jobs.rebalancing_auto_execution.get_redis", new=AsyncMock(return_value=mock_redis)),
            patch("app.jobs.rebalancing_auto_execution.AsyncSessionLocal", return_value=mock_db),
            patch(
                "app.services.market_signal_service.get_market_signal",
                new=AsyncMock(return_value={"composite_level": "GREEN"}),
            ),
            patch("app.jobs.rebalancing_auto_execution.is_alert_execution_time", return_value=False),
            patch("app.jobs.rebalancing_auto_execution._execute_for_alert", new=AsyncMock()) as mock_exec,
        ):
            from app.jobs.rebalancing_auto_execution import _run_auto_execution

            await _run_auto_execution()

        mock_exec.assert_not_called()

    @pytest.mark.asyncio
    async def test_already_fired_today_skips_alert(self):
        mock_db = _make_mock_db()
        mock_redis = MagicMock()
        alert = _make_alert()
        portfolio = _make_portfolio()

        execute_result = MagicMock()
        execute_result.all.return_value = [(alert, portfolio, "u@test.com", None, None)]
        mock_db.execute = AsyncMock(return_value=execute_result)

        with (
            patch("app.jobs.rebalancing_auto_execution.get_redis", new=AsyncMock(return_value=mock_redis)),
            patch("app.jobs.rebalancing_auto_execution.AsyncSessionLocal", return_value=mock_db),
            patch(
                "app.services.market_signal_service.get_market_signal",
                new=AsyncMock(return_value={"composite_level": "GREEN"}),
            ),
            patch("app.jobs.rebalancing_auto_execution.is_alert_execution_time", return_value=True),
            patch("app.jobs.rebalancing_auto_execution.already_fired_today", return_value=True),
            patch("app.jobs.rebalancing_auto_execution._execute_for_alert", new=AsyncMock()) as mock_exec,
        ):
            from app.jobs.rebalancing_auto_execution import _run_auto_execution

            await _run_auto_execution()

        mock_exec.assert_not_called()

    @pytest.mark.asyncio
    async def test_cautious_mode_with_red_signal_blocks_execution(self):
        mock_db = _make_mock_db()
        mock_redis = MagicMock()
        alert = _make_alert(market_condition_mode="CAUTIOUS")
        portfolio = _make_portfolio()

        execute_result = MagicMock()
        execute_result.all.return_value = [(alert, portfolio, "u@test.com", None, None)]
        mock_db.execute = AsyncMock(return_value=execute_result)

        with (
            patch("app.jobs.rebalancing_auto_execution.get_redis", new=AsyncMock(return_value=mock_redis)),
            patch("app.jobs.rebalancing_auto_execution.AsyncSessionLocal", return_value=mock_db),
            patch(
                "app.services.market_signal_service.get_market_signal",
                new=AsyncMock(return_value={"composite_level": "RED"}),
            ),
            patch("app.jobs.rebalancing_auto_execution.is_alert_execution_time", return_value=True),
            patch("app.jobs.rebalancing_auto_execution.already_fired_today", return_value=False),
            patch("app.jobs.rebalancing_auto_execution._execute_for_alert", new=AsyncMock()) as mock_exec,
        ):
            from app.jobs.rebalancing_auto_execution import _run_auto_execution

            await _run_auto_execution()

        mock_exec.assert_not_called()

    @pytest.mark.asyncio
    async def test_strict_mode_with_yellow_signal_blocks_execution(self):
        mock_db = _make_mock_db()
        mock_redis = MagicMock()
        alert = _make_alert(market_condition_mode="STRICT")
        portfolio = _make_portfolio()

        execute_result = MagicMock()
        execute_result.all.return_value = [(alert, portfolio, "u@test.com", None, None)]
        mock_db.execute = AsyncMock(return_value=execute_result)

        with (
            patch("app.jobs.rebalancing_auto_execution.get_redis", new=AsyncMock(return_value=mock_redis)),
            patch("app.jobs.rebalancing_auto_execution.AsyncSessionLocal", return_value=mock_db),
            patch(
                "app.services.market_signal_service.get_market_signal",
                new=AsyncMock(return_value={"composite_level": "YELLOW"}),
            ),
            patch("app.jobs.rebalancing_auto_execution.is_alert_execution_time", return_value=True),
            patch("app.jobs.rebalancing_auto_execution.already_fired_today", return_value=False),
            patch("app.jobs.rebalancing_auto_execution._execute_for_alert", new=AsyncMock()) as mock_exec,
        ):
            from app.jobs.rebalancing_auto_execution import _run_auto_execution

            await _run_auto_execution()

        mock_exec.assert_not_called()

    @pytest.mark.asyncio
    async def test_executes_and_saves_history_when_drifting(self):
        mock_db = _make_mock_db()
        mock_redis = MagicMock()
        alert = _make_alert()
        portfolio = _make_portfolio()

        execute_result = MagicMock()
        execute_result.all.return_value = [(alert, portfolio, "u@test.com", None, None)]
        mock_db.execute = AsyncMock(return_value=execute_result)
        mock_db.scalar = AsyncMock(return_value=MagicMock())

        with (
            patch("app.jobs.rebalancing_auto_execution.get_redis", new=AsyncMock(return_value=mock_redis)),
            patch("app.jobs.rebalancing_auto_execution.AsyncSessionLocal", return_value=mock_db),
            patch(
                "app.services.market_signal_service.get_market_signal",
                new=AsyncMock(return_value={"composite_level": "GREEN"}),
            ),
            patch("app.jobs.rebalancing_auto_execution.is_alert_execution_time", return_value=True),
            patch("app.jobs.rebalancing_auto_execution.already_fired_today", return_value=False),
            patch("app.jobs.rebalancing_auto_execution._execute_for_alert", new=AsyncMock(return_value=True)),
            patch("app.jobs.rebalancing_auto_execution.save_alert_history", new=AsyncMock()) as mock_save,
        ):
            from app.jobs.rebalancing_auto_execution import _run_auto_execution

            await _run_auto_execution()

        mock_save.assert_called_once()

    @pytest.mark.asyncio
    async def test_continues_loop_after_alert_returns_false(self):
        mock_db = _make_mock_db()
        mock_redis = MagicMock()
        alert1 = _make_alert()
        alert2 = _make_alert()
        portfolio = _make_portfolio()

        execute_result = MagicMock()
        execute_result.all.return_value = [
            (alert1, portfolio, "u1@test.com", None, None),
            (alert2, portfolio, "u2@test.com", None, None),
        ]
        mock_db.execute = AsyncMock(return_value=execute_result)
        mock_db.scalar = AsyncMock(return_value=MagicMock())

        call_count = 0

        async def _exec_side_effect(alert, portfolio):
            nonlocal call_count
            result = call_count == 1  # 첫 번째 False, 두 번째 True
            call_count += 1
            return result

        with (
            patch("app.jobs.rebalancing_auto_execution.get_redis", new=AsyncMock(return_value=mock_redis)),
            patch("app.jobs.rebalancing_auto_execution.AsyncSessionLocal", return_value=mock_db),
            patch(
                "app.services.market_signal_service.get_market_signal",
                new=AsyncMock(return_value={"composite_level": "GREEN"}),
            ),
            patch("app.jobs.rebalancing_auto_execution.is_alert_execution_time", return_value=True),
            patch("app.jobs.rebalancing_auto_execution.already_fired_today", return_value=False),
            patch("app.jobs.rebalancing_auto_execution._execute_for_alert", side_effect=_exec_side_effect),
            patch("app.jobs.rebalancing_auto_execution.save_alert_history", new=AsyncMock()) as mock_save,
        ):
            from app.jobs.rebalancing_auto_execution import _run_auto_execution

            await _run_auto_execution()

        # 첫 번째 alert가 False를 반환해도 두 번째 alert까지 모두 처리
        assert call_count == 2
        mock_save.assert_called_once()


# ── _execute_for_alert ───────────────────────────────────────


class TestExecuteForAlert:
    @pytest.mark.asyncio
    async def test_returns_false_when_no_items_exceed_threshold(self):
        alert = _make_alert(threshold_pct=5.0)
        portfolio = _make_portfolio()
        analysis = SimpleNamespace(items=[SimpleNamespace(weight_diff_pct=2.0)])
        mock_db = _make_mock_db()

        with (
            patch("app.jobs.rebalancing_auto_execution.AsyncSessionLocal", return_value=mock_db),
            patch("app.services.portfolio_service.build_portfolio_overview", new=AsyncMock(return_value=MagicMock())),
            patch("app.services.rebalancing_service.analyze_rebalancing", return_value=analysis),
            patch(
                "app.services.rebalancing_alert_service.execute_auto_rebalancing_for_alert", new=AsyncMock()
            ) as mock_exec,
        ):
            from app.jobs.rebalancing_auto_execution import _execute_for_alert

            result = await _execute_for_alert(alert, portfolio)

        assert result is False
        mock_exec.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_true_when_drift_exceeds_threshold(self):
        alert = _make_alert(threshold_pct=5.0)
        portfolio = _make_portfolio()
        analysis = SimpleNamespace(items=[SimpleNamespace(weight_diff_pct=10.0)], ticker_account_map={})
        mock_db = _make_mock_db()

        with (
            patch("app.jobs.rebalancing_auto_execution.AsyncSessionLocal", return_value=mock_db),
            patch("app.services.portfolio_service.build_portfolio_overview", new=AsyncMock(return_value=MagicMock())),
            patch("app.services.rebalancing_service.analyze_rebalancing", return_value=analysis),
            patch(
                "app.services.rebalancing_alert_service.execute_auto_rebalancing_for_alert",
                new=AsyncMock(return_value=True),
            ) as mock_exec,
        ):
            from app.jobs.rebalancing_auto_execution import _execute_for_alert

            result = await _execute_for_alert(alert, portfolio)

        assert result is True
        mock_exec.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_false_when_overview_fails(self):
        alert = _make_alert()
        portfolio = _make_portfolio()
        mock_db = _make_mock_db()

        with (
            patch("app.jobs.rebalancing_auto_execution.AsyncSessionLocal", return_value=mock_db),
            patch(
                "app.services.portfolio_service.build_portfolio_overview",
                new=AsyncMock(side_effect=RuntimeError("DB error")),
            ),
        ):
            from app.jobs.rebalancing_auto_execution import _execute_for_alert

            result = await _execute_for_alert(alert, portfolio)

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_analysis_fails(self):
        alert = _make_alert()
        portfolio = _make_portfolio()
        mock_db = _make_mock_db()

        with (
            patch("app.jobs.rebalancing_auto_execution.AsyncSessionLocal", return_value=mock_db),
            patch("app.services.portfolio_service.build_portfolio_overview", new=AsyncMock(return_value=MagicMock())),
            patch("app.services.rebalancing_service.analyze_rebalancing", side_effect=ValueError("bad data")),
        ):
            from app.jobs.rebalancing_auto_execution import _execute_for_alert

            result = await _execute_for_alert(alert, portfolio)

        assert result is False

    @pytest.mark.asyncio
    async def test_negative_drift_also_triggers_execution(self):
        alert = _make_alert(threshold_pct=5.0)
        portfolio = _make_portfolio()
        analysis = SimpleNamespace(items=[SimpleNamespace(weight_diff_pct=-8.0)], ticker_account_map={})
        mock_db = _make_mock_db()

        with (
            patch("app.jobs.rebalancing_auto_execution.AsyncSessionLocal", return_value=mock_db),
            patch("app.services.portfolio_service.build_portfolio_overview", new=AsyncMock(return_value=MagicMock())),
            patch("app.services.rebalancing_service.analyze_rebalancing", return_value=analysis),
            patch(
                "app.services.rebalancing_alert_service.execute_auto_rebalancing_for_alert",
                new=AsyncMock(return_value=True),
            ) as mock_exec,
        ):
            from app.jobs.rebalancing_auto_execution import _execute_for_alert

            result = await _execute_for_alert(alert, portfolio)

        assert result is True
        mock_exec.assert_called_once()
