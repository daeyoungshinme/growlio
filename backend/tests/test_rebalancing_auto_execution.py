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
    # get_confirmed_composite_level()의 durable_state 조회(db.get) 기본값 — 저장된 confirmed level
    # 없음(최초 실행)으로 취급, raw level을 그대로 confirmed로 부트스트랩한다.
    mock_db.get = AsyncMock(return_value=None)
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


def _make_plan(*, buy_count: int = 1, sell_count: int = 0, account_id=None, market="KR") -> SimpleNamespace:
    legs = []
    if buy_count:
        legs.append(
            SimpleNamespace(
                side="BUY",
                market=market,
                items=[SimpleNamespace(ticker="005930")] * buy_count,
                deadline_at="2026-01-01T00:00:00+00:00",
            )
        )
    if sell_count:
        legs.append(
            SimpleNamespace(
                side="SELL",
                market=market,
                items=[SimpleNamespace(ticker="000660")] * sell_count,
                deadline_at="2026-01-01T06:30:00+00:00",
            )
        )
    return SimpleNamespace(id=uuid4(), account_id=account_id, legs=legs, created_at="2026-01-01T00:00:00+00:00")


# ── run_rebalancing_auto_execution ───────────────────────────


class TestRunRebalancingAutoExecution:
    @pytest.mark.asyncio
    async def test_market_closed_skips_cache_and_execution(self):
        with (
            patch("app.jobs.rebalancing_auto_execution.is_korean_market_open", return_value=False),
            patch("app.jobs.rebalancing_auto_execution.is_us_market_open", return_value=False),
            patch("app.jobs.rebalancing_auto_execution.get_cache_store") as mock_get_cache,
        ):
            from app.jobs.rebalancing_auto_execution import run_rebalancing_auto_execution

            await run_rebalancing_auto_execution()

        mock_get_cache.assert_not_called()

    @pytest.mark.asyncio
    async def test_lock_not_acquired_skips_auto_execution(self):
        mock_cache = MagicMock()

        with (
            patch("app.jobs.rebalancing_auto_execution.is_korean_market_open", return_value=True),
            patch("app.jobs.rebalancing_auto_execution.get_cache_store", new=AsyncMock(return_value=mock_cache)),
            patch("app.jobs.rebalancing_auto_execution.inproc_lock", return_value=_make_lock_cm(False)),
            patch("app.jobs.rebalancing_auto_execution._run_auto_execution", new=AsyncMock()) as mock_run,
        ):
            from app.jobs.rebalancing_auto_execution import run_rebalancing_auto_execution

            await run_rebalancing_auto_execution()

        mock_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatches_when_market_open_and_lock_acquired(self):
        mock_cache = MagicMock()

        with (
            patch("app.jobs.rebalancing_auto_execution.is_korean_market_open", return_value=True),
            patch("app.jobs.rebalancing_auto_execution.get_cache_store", new=AsyncMock(return_value=mock_cache)),
            patch("app.jobs.rebalancing_auto_execution.inproc_lock", return_value=_make_lock_cm(True)),
            patch("app.jobs.rebalancing_auto_execution._run_auto_execution", new=AsyncMock()) as mock_run,
        ):
            from app.jobs.rebalancing_auto_execution import run_rebalancing_auto_execution

            await run_rebalancing_auto_execution()

        mock_run.assert_called_once()


# ── _run_auto_execution ──────────────────────────────────────


@contextmanager
def _patch_common(mock_db, composite_level="GREEN"):
    """공통 patch 세트 — get_cache_store/AsyncSessionLocal/market_signal/이메일·푸시·이력 저장."""
    with ExitStack() as stack:
        stack.enter_context(
            patch("app.jobs.rebalancing_auto_execution.get_cache_store", new=AsyncMock(return_value=MagicMock()))
        )
        stack.enter_context(patch("app.jobs.rebalancing_auto_execution.AsyncSessionLocal", return_value=mock_db))
        stack.enter_context(
            patch(
                "app.services.market_signal_service.get_market_signal",
                new=AsyncMock(return_value={"composite_level": composite_level}),
            )
        )
        stack.enter_context(patch("app.services.push_service.send_push_to_user", new=AsyncMock(return_value=True)))
        stack.enter_context(patch("app.services.rebalancing.plan_service.save_alert_history", new=AsyncMock()))
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
            patch("app.jobs.rebalancing_auto_execution.get_cache_store", new=AsyncMock(return_value=MagicMock())),
            patch("app.jobs.rebalancing_auto_execution.AsyncSessionLocal", return_value=mock_db),
            patch(
                "app.services.market_signal_service.get_market_signal",
                new=AsyncMock(side_effect=RuntimeError("timeout")),
            ),
            patch("app.jobs.rebalancing_auto_execution.is_alert_execution_time", return_value=True),
            patch("app.jobs.rebalancing_auto_execution.already_fired_today", return_value=False),
            patch(
                "app.jobs.rebalancing_auto_execution.get_alert_ids_with_pending_plan",
                new=AsyncMock(return_value=set()),
            ),
            patch(
                "app.jobs.rebalancing_auto_execution.build_pending_plan_for_alert",
                new=AsyncMock(return_value=(_make_plan(), [("KR", "buy-token")], [])),
            ) as mock_gen,
            patch("app.services.rebalancing.plan_service.save_alert_history", new=AsyncMock()),
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
            patch(
                "app.jobs.rebalancing_auto_execution.get_alert_ids_with_pending_plan",
                new=AsyncMock(side_effect=lambda alert_ids, db: set(alert_ids)),
            ),
            patch("app.jobs.rebalancing_auto_execution.build_pending_plan_for_alert", new=AsyncMock()) as mock_gen,
        ):
            from app.jobs.rebalancing_auto_execution import _run_auto_execution

            await _run_auto_execution()

        mock_gen.assert_not_called()

    @pytest.mark.asyncio
    async def test_pending_plan_check_is_batched_and_skips_only_pending_alert(self):
        """N개 알림 중 일부만 pending이면 그 알림만 스킵하고, pending 조회는 alert마다가
        아니라 루프 전체에 대해 단 한 번만 이뤄진다(N+1 회귀 방지)."""
        mock_db = _make_mock_db()
        pending_alert = _make_alert()
        clear_alert = _make_alert()
        portfolio = _make_portfolio()

        execute_result = MagicMock()
        execute_result.all.return_value = [
            (pending_alert, portfolio, "u@test.com", None, None),
            (clear_alert, portfolio, "u@test.com", None, None),
        ]
        mock_db.execute = AsyncMock(return_value=execute_result)

        pending_check = AsyncMock(return_value={pending_alert.id})

        with (
            _patch_common(mock_db),
            patch("app.jobs.rebalancing_auto_execution.is_alert_execution_time", return_value=True),
            patch("app.jobs.rebalancing_auto_execution.already_fired_today", return_value=False),
            patch("app.jobs.rebalancing_auto_execution.get_alert_ids_with_pending_plan", new=pending_check),
            patch(
                "app.jobs.rebalancing_auto_execution.build_pending_plan_for_alert",
                new=AsyncMock(return_value=(_make_plan(), [("KR", "buy-token")], [])),
            ) as mock_gen,
            patch("app.services.rebalancing.plan_service.save_alert_history", new=AsyncMock()),
            patch("app.services.email_service.send_rebalancing_plan_pending_email", new=AsyncMock()),
        ):
            from app.jobs.rebalancing_auto_execution import _run_auto_execution

            await _run_auto_execution()

        pending_check.assert_awaited_once()
        awaited_alert_ids = pending_check.await_args.args[0]
        assert set(awaited_alert_ids) == {pending_alert.id, clear_alert.id}
        mock_gen.assert_awaited_once()
        assert mock_gen.await_args.args[0] is clear_alert

    @pytest.mark.asyncio
    async def test_tax_gate_blocked_notifies_instead_of_crashing(self):
        """build_pending_plan_for_alert()가 TaxGateBlocked를 반환하면 3-tuple로 언패킹하지 않고
        notify_tax_gate_blocked()를 호출한 뒤 다음 alert로 넘어가야 한다."""
        from app.services.rebalancing.plan_service import TaxGateBlocked

        mock_db = _make_mock_db()
        alert = _make_alert(tax_impact_gate_mode="ENABLED", max_tax_impact_krw=100_000.0)
        portfolio = _make_portfolio()

        execute_result = MagicMock()
        execute_result.all.return_value = [(alert, portfolio, "u@test.com", None, None)]
        mock_db.execute = AsyncMock(return_value=execute_result)

        blocked = TaxGateBlocked(estimated_tax_krw=200_000.0, max_tax_impact_krw=100_000.0)

        with (
            _patch_common(mock_db),
            patch("app.jobs.rebalancing_auto_execution.is_alert_execution_time", return_value=True),
            patch("app.jobs.rebalancing_auto_execution.already_fired_today", return_value=False),
            patch(
                "app.jobs.rebalancing_auto_execution.get_alert_ids_with_pending_plan",
                new=AsyncMock(return_value=set()),
            ),
            patch(
                "app.jobs.rebalancing_auto_execution.build_pending_plan_for_alert",
                new=AsyncMock(return_value=blocked),
            ) as mock_gen,
            patch("app.jobs.rebalancing_auto_execution.notify_tax_gate_blocked", new=AsyncMock()) as mock_notify,
        ):
            from app.jobs.rebalancing_auto_execution import _run_auto_execution

            await _run_auto_execution()  # TaxGateBlocked를 (plan, buy, sell)로 언패킹하면 여기서 예외 발생

        mock_gen.assert_called_once()
        mock_notify.assert_called_once()
        assert mock_notify.call_args.args[0] is alert
        assert mock_notify.call_args.args[1] is portfolio
        assert mock_notify.call_args.args[2] is blocked

    @pytest.mark.asyncio
    async def test_daily_value_cap_blocked_notifies_instead_of_crashing(self):
        """build_pending_plan_for_alert()가 DailyValueCapBlocked를 반환하면 3-tuple로 언패킹하지 않고
        notify_daily_value_cap_blocked()를 호출한 뒤 다음 alert로 넘어가야 한다."""
        from app.services.rebalancing.plan_service import DailyValueCapBlocked

        mock_db = _make_mock_db()
        alert = _make_alert()
        portfolio = _make_portfolio()

        execute_result = MagicMock()
        execute_result.all.return_value = [(alert, portfolio, "u@test.com", None, None)]
        mock_db.execute = AsyncMock(return_value=execute_result)

        blocked = DailyValueCapBlocked(
            today_total_krw=5_000_000.0, attempted_value_krw=6_000_000.0, cap_krw=10_000_000.0
        )

        with (
            _patch_common(mock_db),
            patch("app.jobs.rebalancing_auto_execution.is_alert_execution_time", return_value=True),
            patch("app.jobs.rebalancing_auto_execution.already_fired_today", return_value=False),
            patch(
                "app.jobs.rebalancing_auto_execution.get_alert_ids_with_pending_plan",
                new=AsyncMock(return_value=set()),
            ),
            patch(
                "app.jobs.rebalancing_auto_execution.build_pending_plan_for_alert",
                new=AsyncMock(return_value=blocked),
            ) as mock_gen,
            patch("app.jobs.rebalancing_auto_execution.notify_daily_value_cap_blocked", new=AsyncMock()) as mock_notify,
        ):
            from app.jobs.rebalancing_auto_execution import _run_auto_execution

            await _run_auto_execution()  # DailyValueCapBlocked를 (plan, buy, sell)로 언패킹하면 여기서 예외 발생

        mock_gen.assert_called_once()
        mock_notify.assert_called_once()
        assert mock_notify.call_args.args[0] is alert
        assert mock_notify.call_args.args[1] is portfolio
        assert mock_notify.call_args.args[2] is blocked

    @pytest.mark.asyncio
    async def test_market_signal_blocked_notifies_with_gate_context(self):
        """시장신호 게이트로 차단되면 build_pending_plan_for_alert()를 아예 호출하지 않고
        notify_market_signal_gate_blocked()에 등급·게이트 모드·데이터 신선도를 실어 전달해야 한다."""
        from app.services.rebalancing.plan_service import MarketSignalGateBlocked

        mock_db = _make_mock_db()
        alert = _make_alert(market_condition_mode="STRICT")
        portfolio = _make_portfolio()

        execute_result = MagicMock()
        execute_result.all.return_value = [(alert, portfolio, "u@test.com", None, None)]
        mock_db.execute = AsyncMock(return_value=execute_result)

        with (
            _patch_common(mock_db, composite_level="RED"),
            patch("app.jobs.rebalancing_auto_execution.is_alert_execution_time", return_value=True),
            patch("app.jobs.rebalancing_auto_execution.already_fired_today", return_value=False),
            patch("app.jobs.rebalancing_auto_execution.build_pending_plan_for_alert", new=AsyncMock()) as mock_gen,
            patch(
                "app.jobs.rebalancing_auto_execution.notify_market_signal_gate_blocked", new=AsyncMock()
            ) as mock_notify,
        ):
            from app.jobs.rebalancing_auto_execution import _run_auto_execution

            await _run_auto_execution()

        mock_gen.assert_not_called()
        mock_notify.assert_called_once()
        assert mock_notify.call_args.args[0] is alert
        assert mock_notify.call_args.args[1] is portfolio
        blocked = mock_notify.call_args.args[2]
        assert isinstance(blocked, MarketSignalGateBlocked)
        assert blocked.composite_level == "RED"
        assert blocked.market_condition_mode == "STRICT"

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
            patch(
                "app.jobs.rebalancing_auto_execution.notify_market_signal_gate_blocked", new=AsyncMock()
            ) as mock_notify,
        ):
            from app.jobs.rebalancing_auto_execution import _run_auto_execution

            await _run_auto_execution()

        mock_gen.assert_not_called()
        mock_notify.assert_called_once()

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
            patch(
                "app.jobs.rebalancing_auto_execution.notify_market_signal_gate_blocked", new=AsyncMock()
            ) as mock_notify,
        ):
            from app.jobs.rebalancing_auto_execution import _run_auto_execution

            await _run_auto_execution()

        mock_gen.assert_not_called()
        mock_notify.assert_called_once()

    @pytest.mark.asyncio
    async def test_stale_data_freshness_blocks_cautious_execution(self):
        """시장 신호를 신뢰할 수 없는 상태(STALE)면 composite_level이 GREEN이어도 CAUTIOUS는 차단한다.

        회귀 테스트 — FRED_API_KEY 미설정 등으로 대부분 신호가 조회 실패해도 과거에는
        GREEN으로 오판되어 CAUTIOUS 게이트를 통과했다."""
        mock_db = _make_mock_db()
        alert = _make_alert(market_condition_mode="CAUTIOUS")
        portfolio = _make_portfolio()

        execute_result = MagicMock()
        execute_result.all.return_value = [(alert, portfolio, "u@test.com", None, None)]
        mock_db.execute = AsyncMock(return_value=execute_result)

        with (
            patch("app.jobs.rebalancing_auto_execution.get_cache_store", new=AsyncMock(return_value=MagicMock())),
            patch("app.jobs.rebalancing_auto_execution.AsyncSessionLocal", return_value=mock_db),
            patch(
                "app.services.market_signal_service.get_market_signal",
                new=AsyncMock(return_value={"composite_level": "GREEN", "data_freshness": "STALE"}),
            ),
            patch("app.jobs.rebalancing_auto_execution.is_alert_execution_time", return_value=True),
            patch("app.jobs.rebalancing_auto_execution.already_fired_today", return_value=False),
            patch("app.services.push_service.send_push_to_user", new=AsyncMock(return_value=True)),
            patch("app.services.rebalancing.plan_service.save_alert_history", new=AsyncMock()),
            patch("app.services.email_service.send_rebalancing_plan_pending_email", new=AsyncMock()),
            patch("app.jobs.rebalancing_auto_execution.build_pending_plan_for_alert", new=AsyncMock()) as mock_gen,
            patch(
                "app.jobs.rebalancing_auto_execution.notify_market_signal_gate_blocked", new=AsyncMock()
            ) as mock_notify,
        ):
            from app.jobs.rebalancing_auto_execution import _run_auto_execution

            await _run_auto_execution()

        mock_gen.assert_not_called()
        mock_notify.assert_called_once()

    @pytest.mark.asyncio
    async def test_market_signal_exception_blocks_cautious_execution(self):
        """market_signal 조회 자체가 예외를 던지면 STALE로 폴백해 CAUTIOUS/STRICT를 보수적으로 차단한다."""
        mock_db = _make_mock_db()
        alert = _make_alert(market_condition_mode="CAUTIOUS")
        portfolio = _make_portfolio()

        execute_result = MagicMock()
        execute_result.all.return_value = [(alert, portfolio, "u@test.com", None, None)]
        mock_db.execute = AsyncMock(return_value=execute_result)

        with (
            patch("app.jobs.rebalancing_auto_execution.get_cache_store", new=AsyncMock(return_value=MagicMock())),
            patch("app.jobs.rebalancing_auto_execution.AsyncSessionLocal", return_value=mock_db),
            patch(
                "app.services.market_signal_service.get_market_signal",
                new=AsyncMock(side_effect=RuntimeError("timeout")),
            ),
            patch("app.jobs.rebalancing_auto_execution.is_alert_execution_time", return_value=True),
            patch("app.jobs.rebalancing_auto_execution.already_fired_today", return_value=False),
            patch("app.services.push_service.send_push_to_user", new=AsyncMock(return_value=True)),
            patch("app.services.rebalancing.plan_service.save_alert_history", new=AsyncMock()),
            patch("app.services.email_service.send_rebalancing_plan_pending_email", new=AsyncMock()),
            patch("app.jobs.rebalancing_auto_execution.build_pending_plan_for_alert", new=AsyncMock()) as mock_gen,
            patch(
                "app.jobs.rebalancing_auto_execution.notify_market_signal_gate_blocked", new=AsyncMock()
            ) as mock_notify,
        ):
            from app.jobs.rebalancing_auto_execution import _run_auto_execution

            await _run_auto_execution()

        mock_gen.assert_not_called()
        mock_notify.assert_called_once()

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
            patch(
                "app.jobs.rebalancing_auto_execution.get_alert_ids_with_pending_plan",
                new=AsyncMock(return_value=set()),
            ),
            patch(
                "app.jobs.rebalancing_auto_execution.build_pending_plan_for_alert",
                new=AsyncMock(return_value=(_make_plan(), [("KR", "buy-token")], [])),
            ),
            patch("app.services.rebalancing.plan_service.save_alert_history", new=AsyncMock()) as mock_save,
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

        async def _gen_side_effect(alert, portfolio, db, composite_level, cache=None):
            nonlocal call_count
            result = None if call_count == 0 else (_make_plan(), [("KR", "buy-token")], [])
            call_count += 1
            return result

        with (
            _patch_common(mock_db),
            patch("app.jobs.rebalancing_auto_execution.is_alert_execution_time", return_value=True),
            patch("app.jobs.rebalancing_auto_execution.already_fired_today", return_value=False),
            patch(
                "app.jobs.rebalancing_auto_execution.get_alert_ids_with_pending_plan",
                new=AsyncMock(return_value=set()),
            ),
            patch("app.jobs.rebalancing_auto_execution.build_pending_plan_for_alert", side_effect=_gen_side_effect),
            patch("app.services.rebalancing.plan_service.save_alert_history", new=AsyncMock()) as mock_save,
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
            patch("app.services.rebalancing.service.analyze_rebalancing", return_value=analysis),
            patch("app.services.rebalancing.plan_service.generate_pending_plan_for_alert", new=AsyncMock()) as mock_gen,
        ):
            from app.services.rebalancing.plan_service import build_pending_plan_for_alert

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
            patch("app.services.rebalancing.service.analyze_rebalancing", return_value=analysis),
            patch(
                "app.services.rebalancing.plan_service.generate_pending_plan_for_alert",
                new=AsyncMock(return_value=(plan, "buy-token", None)),
            ) as mock_gen,
        ):
            from app.services.rebalancing.plan_service import build_pending_plan_for_alert

            result = await build_pending_plan_for_alert(alert, portfolio, mock_db, "GREEN")

        assert result == (plan, "buy-token", None)
        assert alert.last_triggered_at == plan.created_at
        mock_gen.assert_called_once()

    @pytest.mark.asyncio
    async def test_propagates_overview_failure(self):
        from app.services.rebalancing.plan_service import build_pending_plan_for_alert

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
        from app.services.rebalancing.plan_service import build_pending_plan_for_alert

        alert = _make_alert()
        portfolio = _make_portfolio()
        mock_db = _make_mock_db()

        with (
            patch("app.services.portfolio_service.build_portfolio_overview", new=AsyncMock(return_value=MagicMock())),
            patch("app.services.rebalancing.service.analyze_rebalancing", side_effect=ValueError("bad data")),
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
            patch("app.services.rebalancing.service.analyze_rebalancing", return_value=analysis),
            patch(
                "app.services.rebalancing.plan_service.generate_pending_plan_for_alert",
                new=AsyncMock(return_value=(plan, None, "sell-token")),
            ) as mock_gen,
        ):
            from app.services.rebalancing.plan_service import build_pending_plan_for_alert

            result = await build_pending_plan_for_alert(alert, portfolio, mock_db, "GREEN")

        assert result is not None
        mock_gen.assert_called_once()

    @pytest.mark.asyncio
    async def test_tax_gate_blocks_when_estimated_tax_exceeds_max(self):
        from app.services.rebalancing.plan_service import TaxGateBlocked, build_pending_plan_for_alert

        alert = _make_alert(threshold_pct=5.0, tax_impact_gate_mode="ENABLED", max_tax_impact_krw=100_000.0)
        portfolio = _make_portfolio()
        analysis = SimpleNamespace(items=[SimpleNamespace(weight_diff_pct=10.0)], ticker_account_map={})
        mock_db = _make_mock_db()

        with (
            patch("app.services.portfolio_service.build_portfolio_overview", new=AsyncMock(return_value=MagicMock())),
            patch("app.services.rebalancing.service.analyze_rebalancing", return_value=analysis),
            patch(
                "app.services.rebalancing.diagnosis_service._build_tax_preview",
                return_value=(500_000.0, 200_000.0, 0.0, [], []),
            ),
            patch("app.services.rebalancing.plan_service.generate_pending_plan_for_alert", new=AsyncMock()) as mock_gen,
        ):
            result = await build_pending_plan_for_alert(alert, portfolio, mock_db, "GREEN")

        assert isinstance(result, TaxGateBlocked)
        assert result.estimated_tax_krw == 200_000.0
        assert result.max_tax_impact_krw == 100_000.0
        mock_gen.assert_not_called()

    @pytest.mark.asyncio
    async def test_tax_gate_enabled_but_under_threshold_still_generates_plan(self):
        alert = _make_alert(threshold_pct=5.0, tax_impact_gate_mode="ENABLED", max_tax_impact_krw=1_000_000.0)
        portfolio = _make_portfolio()
        analysis = SimpleNamespace(items=[SimpleNamespace(weight_diff_pct=10.0)], ticker_account_map={})
        mock_db = _make_mock_db()
        plan = _make_plan()

        with (
            patch("app.services.portfolio_service.build_portfolio_overview", new=AsyncMock(return_value=MagicMock())),
            patch("app.services.rebalancing.service.analyze_rebalancing", return_value=analysis),
            patch(
                "app.services.rebalancing.diagnosis_service._build_tax_preview",
                return_value=(500_000.0, 200_000.0, 0.0, [], []),
            ),
            patch(
                "app.services.rebalancing.plan_service.generate_pending_plan_for_alert",
                new=AsyncMock(return_value=(plan, "buy-token", None)),
            ) as mock_gen,
        ):
            from app.services.rebalancing.plan_service import build_pending_plan_for_alert

            result = await build_pending_plan_for_alert(alert, portfolio, mock_db, "GREEN")

        assert result == (plan, "buy-token", None)
        mock_gen.assert_called_once()

    @pytest.mark.asyncio
    async def test_tax_gate_disabled_skips_tax_preview_entirely(self):
        """DISABLED(기본값)면 _build_tax_preview 자체를 호출하지 않는다 — 불필요한 계산 스킵."""
        alert = _make_alert(threshold_pct=5.0)  # tax_impact_gate_mode 기본 DISABLED
        portfolio = _make_portfolio()
        analysis = SimpleNamespace(items=[SimpleNamespace(weight_diff_pct=10.0)], ticker_account_map={})
        mock_db = _make_mock_db()
        plan = _make_plan()

        with (
            patch("app.services.portfolio_service.build_portfolio_overview", new=AsyncMock(return_value=MagicMock())),
            patch("app.services.rebalancing.service.analyze_rebalancing", return_value=analysis),
            patch("app.services.rebalancing.diagnosis_service._build_tax_preview") as mock_tax_preview,
            patch(
                "app.services.rebalancing.plan_service.generate_pending_plan_for_alert",
                new=AsyncMock(return_value=(plan, "buy-token", None)),
            ),
        ):
            from app.services.rebalancing.plan_service import build_pending_plan_for_alert

            await build_pending_plan_for_alert(alert, portfolio, mock_db, "GREEN")

        mock_tax_preview.assert_not_called()

    @pytest.mark.asyncio
    async def test_daily_value_cap_blocks_when_total_exceeds_cap(self):
        """오늘 이미 실행된 금액 + 이번 계획 예상 금액이 유저 단위 하루 상한을 초과하면 차단한다."""
        from app.services.rebalancing.plan_service import DailyValueCapBlocked, build_pending_plan_for_alert

        alert = _make_alert(threshold_pct=5.0)
        portfolio = _make_portfolio()
        analysis = SimpleNamespace(
            items=[SimpleNamespace(weight_diff_pct=10.0, diff_krw=-6_000_000.0)], ticker_account_map={}
        )
        mock_db = _make_mock_db()
        # 순서: (1) UserSettings.auto_rebalancing_daily_value_cap_krw 조회, (2) 오늘 합산 조회
        mock_db.scalar = AsyncMock(side_effect=[10_000_000.0, 5_000_000.0])

        with (
            patch("app.services.portfolio_service.build_portfolio_overview", new=AsyncMock(return_value=MagicMock())),
            patch("app.services.rebalancing.service.analyze_rebalancing", return_value=analysis),
            patch("app.services.rebalancing.plan_service.generate_pending_plan_for_alert", new=AsyncMock()) as mock_gen,
        ):
            result = await build_pending_plan_for_alert(alert, portfolio, mock_db, "GREEN")

        assert isinstance(result, DailyValueCapBlocked)
        assert result.cap_krw == 10_000_000.0
        assert result.today_total_krw == 5_000_000.0
        assert result.attempted_value_krw == 6_000_000.0
        mock_gen.assert_not_called()

    @pytest.mark.asyncio
    async def test_daily_value_cap_under_threshold_still_generates_plan(self):
        alert = _make_alert(threshold_pct=5.0)
        portfolio = _make_portfolio()
        analysis = SimpleNamespace(
            items=[SimpleNamespace(weight_diff_pct=10.0, diff_krw=-1_000_000.0)], ticker_account_map={}
        )
        mock_db = _make_mock_db()
        mock_db.scalar = AsyncMock(side_effect=[10_000_000.0, 5_000_000.0])
        plan = _make_plan()

        with (
            patch("app.services.portfolio_service.build_portfolio_overview", new=AsyncMock(return_value=MagicMock())),
            patch("app.services.rebalancing.service.analyze_rebalancing", return_value=analysis),
            patch(
                "app.services.rebalancing.plan_service.generate_pending_plan_for_alert",
                new=AsyncMock(return_value=(plan, "buy-token", None)),
            ) as mock_gen,
        ):
            from app.services.rebalancing.plan_service import build_pending_plan_for_alert

            result = await build_pending_plan_for_alert(alert, portfolio, mock_db, "GREEN")

        assert result == (plan, "buy-token", None)
        mock_gen.assert_called_once()

    @pytest.mark.asyncio
    async def test_daily_value_cap_unset_skips_check_entirely(self):
        """상한 미설정(None, 기본값)이면 오늘 합산 조회 자체를 하지 않는다 — 불필요한 쿼리 스킵."""
        alert = _make_alert(threshold_pct=5.0)
        portfolio = _make_portfolio()
        analysis = SimpleNamespace(
            items=[SimpleNamespace(weight_diff_pct=10.0, diff_krw=-1_000_000.0)], ticker_account_map={}
        )
        mock_db = _make_mock_db()  # db.scalar 기본값 None(상한 미설정)
        plan = _make_plan()

        with (
            patch("app.services.portfolio_service.build_portfolio_overview", new=AsyncMock(return_value=MagicMock())),
            patch("app.services.rebalancing.service.analyze_rebalancing", return_value=analysis),
            patch("app.services.rebalancing.plan_service.sum_today_auto_plan_value_krw", new=AsyncMock()) as mock_sum,
            patch(
                "app.services.rebalancing.plan_service.generate_pending_plan_for_alert",
                new=AsyncMock(return_value=(plan, "buy-token", None)),
            ),
        ):
            from app.services.rebalancing.plan_service import build_pending_plan_for_alert

            await build_pending_plan_for_alert(alert, portfolio, mock_db, "GREEN")

        mock_sum.assert_not_called()


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
            patch(
                "app.jobs.rebalancing_auto_execution.get_alert_ids_with_pending_plan",
                new=AsyncMock(return_value=set()),
            ),
            patch(
                "app.jobs.rebalancing_auto_execution.build_pending_plan_for_alert",
                new=AsyncMock(side_effect=RuntimeError("DB error")),
            ),
        ):
            from app.jobs.rebalancing_auto_execution import _run_auto_execution

            await _run_auto_execution()  # 예외 없이 종료되면 통과
