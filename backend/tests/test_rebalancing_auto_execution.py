"""rebalancing_auto_execution Job 단위 테스트 — AUTO 모드 대기 플랜 생성 검증.

실제 주문 실행(매수 대기/매도 승인)은 rebalancing_plan_service.py가 전담하므로 여기서는
"플랜을 생성했는지/이메일·이력을 남겼는지"만 검증한다. 실행 자체는 test_rebalancing_plan_service.py 참고.
"""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
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
    mock_db.refresh = AsyncMock()
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
        "account_id": None,
        "auto_execution_time": None,
        "market_condition_mode": "DISABLED",
        "threshold_pct": 5.0,
        "buy_wait_minutes": 10,
        "last_triggered_at": None,
        "mode": "AUTO",
        "is_active": True,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _make_portfolio(**kwargs) -> SimpleNamespace:
    defaults = {"id": uuid4(), "name": "Test Portfolio", "account_ids": None, "linked_accounts": []}
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _make_plan(*, buy_count: int = 1, sell_count: int = 0, account_id=None) -> SimpleNamespace:
    legs = []
    if buy_count:
        legs.append(
            SimpleNamespace(
                side="BUY",
                items=[SimpleNamespace(ticker="005930")] * buy_count,
                deadline_at="2026-01-01T00:00:00+00:00",
            )
        )
    if sell_count:
        legs.append(
            SimpleNamespace(
                side="SELL",
                items=[SimpleNamespace(ticker="000660")] * sell_count,
                deadline_at="2026-01-01T06:30:00+00:00",
            )
        )
    return SimpleNamespace(id=uuid4(), account_id=account_id, legs=legs, created_at="2026-01-01T00:00:00+00:00")


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


@contextmanager
def _patch_common(mock_db, composite_level="GREEN"):
    """공통 patch 세트 — get_redis/AsyncSessionLocal/market_signal/이메일·푸시·이력 저장."""
    with ExitStack() as stack:
        stack.enter_context(
            patch("app.jobs.rebalancing_auto_execution.get_redis", new=AsyncMock(return_value=MagicMock()))
        )
        stack.enter_context(patch("app.jobs.rebalancing_auto_execution.AsyncSessionLocal", return_value=mock_db))
        stack.enter_context(
            patch(
                "app.services.market_signal_service.get_market_signal",
                new=AsyncMock(return_value={"composite_level": composite_level}),
            )
        )
        stack.enter_context(patch("app.services.push_service.send_push_to_user", new=AsyncMock(return_value=True)))
        stack.enter_context(patch("app.services.rebalancing_plan_service.save_alert_history", new=AsyncMock()))
        stack.enter_context(patch("app.services.email_service.send_rebalancing_plan_pending_email", new=AsyncMock()))
        yield


class TestRunAutoExecution:
    @pytest.mark.asyncio
    async def test_no_active_alerts_skips_generation(self):
        mock_db = _make_mock_db()

        with (
            _patch_common(mock_db),
            patch("app.jobs.rebalancing_auto_execution.build_pending_plan_for_alert", new=AsyncMock()) as mock_gen,
        ):
            from app.jobs.rebalancing_auto_execution import _run_auto_execution

            await _run_auto_execution()

        mock_gen.assert_not_called()

    @pytest.mark.asyncio
    async def test_market_signal_failure_defaults_to_green_and_continues(self):
        mock_db = _make_mock_db()
        alert = _make_alert()
        portfolio = _make_portfolio()

        execute_result = MagicMock()
        execute_result.all.return_value = [(alert, portfolio, "u@test.com", None, None)]
        mock_db.execute = AsyncMock(return_value=execute_result)

        with (
            patch("app.jobs.rebalancing_auto_execution.get_redis", new=AsyncMock(return_value=MagicMock())),
            patch("app.jobs.rebalancing_auto_execution.AsyncSessionLocal", return_value=mock_db),
            patch(
                "app.services.market_signal_service.get_market_signal",
                new=AsyncMock(side_effect=RuntimeError("timeout")),
            ),
            patch("app.jobs.rebalancing_auto_execution.is_alert_execution_time", return_value=True),
            patch("app.jobs.rebalancing_auto_execution.already_fired_today", return_value=False),
            patch("app.jobs.rebalancing_auto_execution.has_pending_plan_for_alert", new=AsyncMock(return_value=False)),
            patch(
                "app.jobs.rebalancing_auto_execution.build_pending_plan_for_alert",
                new=AsyncMock(return_value=(_make_plan(), "buy-token", None)),
            ) as mock_gen,
            patch("app.services.rebalancing_plan_service.save_alert_history", new=AsyncMock()),
            patch("app.services.email_service.send_rebalancing_plan_pending_email", new=AsyncMock()),
            patch("app.services.push_service.send_push_to_user", new=AsyncMock(return_value=True)),
        ):
            from app.jobs.rebalancing_auto_execution import _run_auto_execution

            await _run_auto_execution()

        mock_gen.assert_called_once()

    @pytest.mark.asyncio
    async def test_execution_time_mismatch_skips_alert(self):
        mock_db = _make_mock_db()
        alert = _make_alert(auto_execution_time="09:30")
        portfolio = _make_portfolio()

        execute_result = MagicMock()
        execute_result.all.return_value = [(alert, portfolio, "u@test.com", None, None)]
        mock_db.execute = AsyncMock(return_value=execute_result)

        with (
            _patch_common(mock_db),
            patch("app.jobs.rebalancing_auto_execution.is_alert_execution_time", return_value=False),
            patch("app.jobs.rebalancing_auto_execution.build_pending_plan_for_alert", new=AsyncMock()) as mock_gen,
        ):
            from app.jobs.rebalancing_auto_execution import _run_auto_execution

            await _run_auto_execution()

        mock_gen.assert_not_called()

    @pytest.mark.asyncio
    async def test_already_fired_today_skips_alert(self):
        mock_db = _make_mock_db()
        alert = _make_alert()
        portfolio = _make_portfolio()

        execute_result = MagicMock()
        execute_result.all.return_value = [(alert, portfolio, "u@test.com", None, None)]
        mock_db.execute = AsyncMock(return_value=execute_result)

        with (
            _patch_common(mock_db),
            patch("app.jobs.rebalancing_auto_execution.is_alert_execution_time", return_value=True),
            patch("app.jobs.rebalancing_auto_execution.already_fired_today", return_value=True),
            patch("app.jobs.rebalancing_auto_execution.build_pending_plan_for_alert", new=AsyncMock()) as mock_gen,
        ):
            from app.jobs.rebalancing_auto_execution import _run_auto_execution

            await _run_auto_execution()

        mock_gen.assert_not_called()

    @pytest.mark.asyncio
    async def test_pending_plan_already_exists_skips_alert(self):
        """대기 중인 leg가 있으면(취소/승인 대기) 5분 잡이 재발동해도 중복 플랜을 만들지 않는다."""
        mock_db = _make_mock_db()
        alert = _make_alert()
        portfolio = _make_portfolio()

        execute_result = MagicMock()
        execute_result.all.return_value = [(alert, portfolio, "u@test.com", None, None)]
        mock_db.execute = AsyncMock(return_value=execute_result)

        with (
            _patch_common(mock_db),
            patch("app.jobs.rebalancing_auto_execution.is_alert_execution_time", return_value=True),
            patch("app.jobs.rebalancing_auto_execution.already_fired_today", return_value=False),
            patch("app.jobs.rebalancing_auto_execution.has_pending_plan_for_alert", new=AsyncMock(return_value=True)),
            patch("app.jobs.rebalancing_auto_execution.build_pending_plan_for_alert", new=AsyncMock()) as mock_gen,
        ):
            from app.jobs.rebalancing_auto_execution import _run_auto_execution

            await _run_auto_execution()

        mock_gen.assert_not_called()

    @pytest.mark.asyncio
    async def test_cautious_mode_with_red_signal_blocks_execution(self):
        mock_db = _make_mock_db()
        alert = _make_alert(market_condition_mode="CAUTIOUS")
        portfolio = _make_portfolio()

        execute_result = MagicMock()
        execute_result.all.return_value = [(alert, portfolio, "u@test.com", None, None)]
        mock_db.execute = AsyncMock(return_value=execute_result)

        with (
            _patch_common(mock_db, composite_level="RED"),
            patch("app.jobs.rebalancing_auto_execution.is_alert_execution_time", return_value=True),
            patch("app.jobs.rebalancing_auto_execution.already_fired_today", return_value=False),
            patch("app.jobs.rebalancing_auto_execution.build_pending_plan_for_alert", new=AsyncMock()) as mock_gen,
        ):
            from app.jobs.rebalancing_auto_execution import _run_auto_execution

            await _run_auto_execution()

        mock_gen.assert_not_called()

    @pytest.mark.asyncio
    async def test_strict_mode_with_yellow_signal_blocks_execution(self):
        mock_db = _make_mock_db()
        alert = _make_alert(market_condition_mode="STRICT")
        portfolio = _make_portfolio()

        execute_result = MagicMock()
        execute_result.all.return_value = [(alert, portfolio, "u@test.com", None, None)]
        mock_db.execute = AsyncMock(return_value=execute_result)

        with (
            _patch_common(mock_db, composite_level="YELLOW"),
            patch("app.jobs.rebalancing_auto_execution.is_alert_execution_time", return_value=True),
            patch("app.jobs.rebalancing_auto_execution.already_fired_today", return_value=False),
            patch("app.jobs.rebalancing_auto_execution.build_pending_plan_for_alert", new=AsyncMock()) as mock_gen,
        ):
            from app.jobs.rebalancing_auto_execution import _run_auto_execution

            await _run_auto_execution()

        mock_gen.assert_not_called()

    @pytest.mark.asyncio
    async def test_generates_plan_and_saves_history_when_drifting(self):
        mock_db = _make_mock_db()
        alert = _make_alert()
        portfolio = _make_portfolio()

        execute_result = MagicMock()
        execute_result.all.return_value = [(alert, portfolio, "u@test.com", None, None)]
        mock_db.execute = AsyncMock(return_value=execute_result)
        mock_db.scalar = AsyncMock(return_value="계좌명")

        with (
            _patch_common(mock_db),
            patch("app.jobs.rebalancing_auto_execution.is_alert_execution_time", return_value=True),
            patch("app.jobs.rebalancing_auto_execution.already_fired_today", return_value=False),
            patch("app.jobs.rebalancing_auto_execution.has_pending_plan_for_alert", new=AsyncMock(return_value=False)),
            patch(
                "app.jobs.rebalancing_auto_execution.build_pending_plan_for_alert",
                new=AsyncMock(return_value=(_make_plan(), "buy-token", None)),
            ),
            patch("app.services.rebalancing_plan_service.save_alert_history", new=AsyncMock()) as mock_save,
            patch("app.services.email_service.send_rebalancing_plan_pending_email", new=AsyncMock()) as mock_email,
        ):
            from app.jobs.rebalancing_auto_execution import _run_auto_execution

            await _run_auto_execution()

        mock_save.assert_called_once()
        mock_email.assert_called_once()

    @pytest.mark.asyncio
    async def test_continues_loop_after_alert_returns_none(self):
        mock_db = _make_mock_db()
        alert1 = _make_alert()
        alert2 = _make_alert()
        portfolio = _make_portfolio()

        execute_result = MagicMock()
        execute_result.all.return_value = [
            (alert1, portfolio, "u1@test.com", None, None),
            (alert2, portfolio, "u2@test.com", None, None),
        ]
        mock_db.execute = AsyncMock(return_value=execute_result)
        mock_db.scalar = AsyncMock(return_value=None)

        call_count = 0

        async def _gen_side_effect(alert, portfolio, db, composite_level):
            nonlocal call_count
            result = None if call_count == 0 else (_make_plan(), "buy-token", None)
            call_count += 1
            return result

        with (
            _patch_common(mock_db),
            patch("app.jobs.rebalancing_auto_execution.is_alert_execution_time", return_value=True),
            patch("app.jobs.rebalancing_auto_execution.already_fired_today", return_value=False),
            patch("app.jobs.rebalancing_auto_execution.has_pending_plan_for_alert", new=AsyncMock(return_value=False)),
            patch("app.jobs.rebalancing_auto_execution.build_pending_plan_for_alert", side_effect=_gen_side_effect),
            patch("app.services.rebalancing_plan_service.save_alert_history", new=AsyncMock()) as mock_save,
            patch("app.services.email_service.send_rebalancing_plan_pending_email", new=AsyncMock()),
        ):
            from app.jobs.rebalancing_auto_execution import _run_auto_execution

            await _run_auto_execution()

        # 첫 번째 alert가 None을 반환해도 두 번째 alert까지 모두 처리
        assert call_count == 2
        mock_save.assert_called_once()


# ── build_pending_plan_for_alert (rebalancing_plan_service.py) ─
#
# AUTO job과 "지금 테스트 실행" quick-execute 엔드포인트가 공유하는 드리프트 분석 →
# 플랜 생성 로직. 예외를 스스로 삼키지 않는다 — 호출부(job의 _run_auto_execution 루프,
# quick-execute 엔드포인트)가 각자의 정책에 맞게 처리한다.


class TestBuildPendingPlanForAlert:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_items_exceed_threshold(self):
        alert = _make_alert(threshold_pct=5.0)
        portfolio = _make_portfolio()
        analysis = SimpleNamespace(items=[SimpleNamespace(weight_diff_pct=2.0)], ticker_account_map={})
        mock_db = _make_mock_db()

        with (
            patch("app.services.portfolio_service.build_portfolio_overview", new=AsyncMock(return_value=MagicMock())),
            patch("app.services.rebalancing_service.analyze_rebalancing", return_value=analysis),
            patch("app.services.rebalancing_plan_service.generate_pending_plan_for_alert", new=AsyncMock()) as mock_gen,
        ):
            from app.services.rebalancing_plan_service import build_pending_plan_for_alert

            result = await build_pending_plan_for_alert(alert, portfolio, mock_db, "GREEN")

        assert result is None
        mock_gen.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_plan_when_drift_exceeds_threshold(self):
        alert = _make_alert(threshold_pct=5.0)
        portfolio = _make_portfolio()
        analysis = SimpleNamespace(items=[SimpleNamespace(weight_diff_pct=10.0)], ticker_account_map={})
        mock_db = _make_mock_db()
        plan = _make_plan()

        with (
            patch("app.services.portfolio_service.build_portfolio_overview", new=AsyncMock(return_value=MagicMock())),
            patch("app.services.rebalancing_service.analyze_rebalancing", return_value=analysis),
            patch(
                "app.services.rebalancing_plan_service.generate_pending_plan_for_alert",
                new=AsyncMock(return_value=(plan, "buy-token", None)),
            ) as mock_gen,
        ):
            from app.services.rebalancing_plan_service import build_pending_plan_for_alert

            result = await build_pending_plan_for_alert(alert, portfolio, mock_db, "GREEN")

        assert result == (plan, "buy-token", None)
        assert alert.last_triggered_at == plan.created_at
        mock_gen.assert_called_once()

    @pytest.mark.asyncio
    async def test_propagates_overview_failure(self):
        from app.services.rebalancing_plan_service import build_pending_plan_for_alert

        alert = _make_alert()
        portfolio = _make_portfolio()
        mock_db = _make_mock_db()

        with (
            patch(
                "app.services.portfolio_service.build_portfolio_overview",
                new=AsyncMock(side_effect=RuntimeError("DB error")),
            ),
            pytest.raises(RuntimeError, match="DB error"),
        ):
            await build_pending_plan_for_alert(alert, portfolio, mock_db, "GREEN")

    @pytest.mark.asyncio
    async def test_propagates_analysis_failure(self):
        from app.services.rebalancing_plan_service import build_pending_plan_for_alert

        alert = _make_alert()
        portfolio = _make_portfolio()
        mock_db = _make_mock_db()

        with (
            patch("app.services.portfolio_service.build_portfolio_overview", new=AsyncMock(return_value=MagicMock())),
            patch("app.services.rebalancing_service.analyze_rebalancing", side_effect=ValueError("bad data")),
            pytest.raises(ValueError, match="bad data"),
        ):
            await build_pending_plan_for_alert(alert, portfolio, mock_db, "GREEN")

    @pytest.mark.asyncio
    async def test_negative_drift_also_generates_plan(self):
        alert = _make_alert(threshold_pct=5.0)
        portfolio = _make_portfolio()
        analysis = SimpleNamespace(items=[SimpleNamespace(weight_diff_pct=-8.0)], ticker_account_map={})
        mock_db = _make_mock_db()
        plan = _make_plan()

        with (
            patch("app.services.portfolio_service.build_portfolio_overview", new=AsyncMock(return_value=MagicMock())),
            patch("app.services.rebalancing_service.analyze_rebalancing", return_value=analysis),
            patch(
                "app.services.rebalancing_plan_service.generate_pending_plan_for_alert",
                new=AsyncMock(return_value=(plan, None, "sell-token")),
            ) as mock_gen,
        ):
            from app.services.rebalancing_plan_service import build_pending_plan_for_alert

            result = await build_pending_plan_for_alert(alert, portfolio, mock_db, "GREEN")

        assert result is not None
        mock_gen.assert_called_once()


class TestAutoExecutionPlanGenerationFailure:
    @pytest.mark.asyncio
    async def test_job_logs_and_continues_when_plan_generation_raises(self):
        """job 루프는 build_pending_plan_for_alert()의 예외를 잡고 다음 alert로 계속 진행한다."""
        mock_db = _make_mock_db()
        alert = _make_alert()
        portfolio = _make_portfolio()

        execute_result = MagicMock()
        execute_result.all.return_value = [(alert, portfolio, "u@test.com", None, None)]
        mock_db.execute = AsyncMock(return_value=execute_result)

        with (
            _patch_common(mock_db),
            patch("app.jobs.rebalancing_auto_execution.is_alert_execution_time", return_value=True),
            patch("app.jobs.rebalancing_auto_execution.already_fired_today", return_value=False),
            patch("app.jobs.rebalancing_auto_execution.has_pending_plan_for_alert", new=AsyncMock(return_value=False)),
            patch(
                "app.jobs.rebalancing_auto_execution.build_pending_plan_for_alert",
                new=AsyncMock(side_effect=RuntimeError("DB error")),
            ),
        ):
            from app.jobs.rebalancing_auto_execution import _run_auto_execution

            await _run_auto_execution()  # 예외 없이 종료되면 통과
