"""적립 챌린지 알림 Job 테스트 (독려 + 월간 결산)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _user():
    return SimpleNamespace(id=uuid.uuid4(), email="u@test.com", is_active=True)


def _settings(fcm_token=None, notification_email=None):
    return SimpleNamespace(fcm_token=fcm_token, notification_email=notification_email)


def _challenge(**kw):
    base = dict(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        title="매달 50만원",
        challenge_type="DEPOSIT",
        target_amount=None,
        target_pct=None,
        target_months=6,
        account_id=None,
        start_month="2026-01",
        status="ACTIVE",
        completed_at=None,
        reminder_enabled=True,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _progress(**kw):
    base = dict(
        progress_pct=None,
        current_streak=2,
        longest_streak=2,
        this_month_net_krw=0.0,
        this_month_satisfied=False,
        this_month_target_met=False,
        current_value_krw=None,
        current_return_pct=None,
        months=[],
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _session(users, challenges):
    session = AsyncMock()
    result = MagicMock()
    result.all.return_value = users
    result.scalars.return_value.all.return_value = challenges
    session.execute = AsyncMock(return_value=result)
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.get = AsyncMock(return_value=None)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    # 챌린지 단위 savepoint — 예외는 그대로 전파(__aexit__ → None)
    nested = MagicMock()
    nested.__aenter__ = AsyncMock(return_value=nested)
    nested.__aexit__ = AsyncMock(return_value=None)
    session.begin_nested = MagicMock(return_value=nested)
    return session


class TestDepositReminderJob:
    @pytest.mark.asyncio
    async def test_no_users_does_nothing(self):
        session = _session([], [])
        with (
            patch("app.jobs.challenge_deposit_reminder.AsyncSessionLocal", return_value=session),
            patch("app.jobs._job_helpers.AsyncSessionLocal", return_value=session),
            patch("app.jobs._job_helpers.get_cache_store", new_callable=AsyncMock, return_value=AsyncMock()),
            patch(
                "app.jobs.challenge_deposit_reminder.dispatch_dual_channel_alert", new_callable=AsyncMock
            ) as dispatch,
        ):
            from app.jobs.challenge_deposit_reminder import run_challenge_deposit_reminder

            await run_challenge_deposit_reminder()
        dispatch.assert_not_called()

    @pytest.mark.asyncio
    async def test_sends_when_month_unmet(self):
        user, settings = _user(), _settings(fcm_token="tok")
        ch = _challenge(user_id=user.id)
        session = _session([(user, settings)], [ch])
        with (
            patch("app.jobs.challenge_deposit_reminder.AsyncSessionLocal", return_value=session),
            patch("app.jobs._job_helpers.AsyncSessionLocal", return_value=session),
            patch("app.jobs._job_helpers.get_cache_store", new_callable=AsyncMock, return_value=AsyncMock()),
            patch(
                "app.services.challenge_service.compute_progress",
                new_callable=AsyncMock,
                return_value=_progress(this_month_satisfied=False),
            ),
            patch(
                "app.jobs.challenge_deposit_reminder.dispatch_dual_channel_alert", new_callable=AsyncMock
            ) as dispatch,
        ):
            from app.jobs.challenge_deposit_reminder import run_challenge_deposit_reminder

            await run_challenge_deposit_reminder()
        assert dispatch.called
        assert dispatch.call_args.kwargs["alert_type"] == "CHALLENGE_REMINDER"

    @pytest.mark.asyncio
    async def test_does_not_send_when_month_satisfied(self):
        user, settings = _user(), _settings()
        ch = _challenge(user_id=user.id)
        session = _session([(user, settings)], [ch])
        with (
            patch("app.jobs.challenge_deposit_reminder.AsyncSessionLocal", return_value=session),
            patch("app.jobs._job_helpers.AsyncSessionLocal", return_value=session),
            patch("app.jobs._job_helpers.get_cache_store", new_callable=AsyncMock, return_value=AsyncMock()),
            patch(
                "app.services.challenge_service.compute_progress",
                new_callable=AsyncMock,
                return_value=_progress(this_month_satisfied=True),
            ),
            patch(
                "app.jobs.challenge_deposit_reminder.dispatch_dual_channel_alert", new_callable=AsyncMock
            ) as dispatch,
        ):
            from app.jobs.challenge_deposit_reminder import run_challenge_deposit_reminder

            await run_challenge_deposit_reminder()
        dispatch.assert_not_called()

    @pytest.mark.asyncio
    async def test_dedup_skips_when_durable_set(self):
        user, settings = _user(), _settings()
        ch = _challenge(user_id=user.id)
        session = _session([(user, settings)], [ch])
        with (
            patch("app.jobs.challenge_deposit_reminder.AsyncSessionLocal", return_value=session),
            patch("app.jobs._job_helpers.AsyncSessionLocal", return_value=session),
            patch("app.jobs._job_helpers.get_cache_store", new_callable=AsyncMock, return_value=AsyncMock()),
            patch(
                "app.services.challenge_service.compute_progress",
                new_callable=AsyncMock,
                return_value=_progress(this_month_satisfied=False),
            ),
            patch("app.jobs.challenge_deposit_reminder.get_durable", new_callable=AsyncMock, return_value="1"),
            patch(
                "app.jobs.challenge_deposit_reminder.dispatch_dual_channel_alert", new_callable=AsyncMock
            ) as dispatch,
        ):
            from app.jobs.challenge_deposit_reminder import run_challenge_deposit_reminder

            await run_challenge_deposit_reminder()
        dispatch.assert_not_called()

    @pytest.mark.asyncio
    async def test_query_filters_by_challenge_reminders_enabled(self):
        session = _session([], [])
        captured = {}

        async def cap(stmt):
            captured["stmt"] = stmt
            r = MagicMock()
            r.all.return_value = []
            return r

        session.execute = AsyncMock(side_effect=cap)
        with (
            patch("app.jobs.challenge_deposit_reminder.AsyncSessionLocal", return_value=session),
            patch("app.jobs._job_helpers.AsyncSessionLocal", return_value=session),
            patch("app.jobs._job_helpers.get_cache_store", new_callable=AsyncMock, return_value=AsyncMock()),
        ):
            from app.jobs.challenge_deposit_reminder import run_challenge_deposit_reminder

            await run_challenge_deposit_reminder()
        assert "challenge_reminders_enabled" in str(captured["stmt"])


class TestPerChallengeIsolation:
    """한 챌린지의 예외가 같은 유저의 나머지 챌린지 발송을 막지 않는다(챌린지 단위 savepoint)."""

    @pytest.mark.asyncio
    async def test_reminder_continues_after_one_challenge_fails(self):
        user, settings = _user(), _settings()
        failing, ok = _challenge(user_id=user.id, title="실패"), _challenge(user_id=user.id, title="정상")
        session = _session([(user, settings)], [failing, ok])
        with (
            patch("app.jobs.challenge_deposit_reminder.AsyncSessionLocal", return_value=session),
            patch("app.jobs._job_helpers.AsyncSessionLocal", return_value=session),
            patch("app.jobs._job_helpers.get_cache_store", new_callable=AsyncMock, return_value=AsyncMock()),
            patch(
                "app.services.challenge_service.compute_progress",
                new_callable=AsyncMock,
                side_effect=[RuntimeError("boom"), _progress()],
            ),
            patch(
                "app.jobs.challenge_deposit_reminder.dispatch_dual_channel_alert", new_callable=AsyncMock
            ) as dispatch,
            patch("app.jobs.challenge_deposit_reminder.report_job_failure") as report,
        ):
            from app.jobs.challenge_deposit_reminder import run_challenge_deposit_reminder

            await run_challenge_deposit_reminder()

        assert dispatch.await_count == 1
        assert "정상" in dispatch.call_args.kwargs["history_message"]
        # 내부 헬퍼는 커밋하지 않고(commit=False) 호출부가 savepoint 뒤에 커밋한다
        assert dispatch.call_args.kwargs["commit"] is False
        report.assert_called_once()
        assert report.call_args.kwargs["challenge_id"] == str(failing.id)
        assert session.begin_nested.call_count == 2


class TestMonthlyWrapJob:
    @pytest.mark.asyncio
    async def test_deposit_wrap_sends_and_completes_on_target_months(self):
        user, settings = _user(), _settings()
        ch = _challenge(user_id=user.id, target_months=3, start_month="2025-01")
        session = _session([(user, settings)], [ch])
        with (
            patch("app.jobs.challenge_monthly_wrap.AsyncSessionLocal", return_value=session),
            patch("app.jobs._job_helpers.AsyncSessionLocal", return_value=session),
            patch("app.jobs._job_helpers.get_cache_store", new_callable=AsyncMock, return_value=AsyncMock()),
            patch("app.jobs.challenge_monthly_wrap._prev_month_str", return_value="2026-02"),
            patch(
                "app.services.challenge_service.compute_progress",
                new_callable=AsyncMock,
                return_value=_progress(
                    current_streak=3,
                    longest_streak=3,
                    months=[SimpleNamespace(month="2026-02", net_krw=500000.0, satisfied=True, target_met=True)],
                ),
            ),
            patch("app.jobs.challenge_monthly_wrap.dispatch_dual_channel_alert", new_callable=AsyncMock) as dispatch,
            patch("app.services.challenge_service.invalidate_challenge_cache", new_callable=AsyncMock) as invalidate,
        ):
            from app.jobs.challenge_monthly_wrap import run_challenge_monthly_wrap

            await run_challenge_monthly_wrap()
        assert dispatch.called
        assert dispatch.call_args.kwargs["alert_type"] == "CHALLENGE_WRAPUP"
        assert ch.status == "COMPLETED"
        assert ch.completed_at is not None
        # COMPLETED 전환 후 챌린지 캐시가 이전 상태(ACTIVE)를 보이지 않게
        invalidate.assert_awaited_once()
        assert invalidate.await_args.args[1] == user.id

    @pytest.mark.asyncio
    async def test_failed_send_still_completes_challenge(self):
        """plans/118 A1: 알림이 실패해도(채널 없음 등) 완료는 저장한다 — 117 B2처럼 알림 성공 시에만 바꾸면
        채널이 없는 사용자는 영영 ACTIVE로 남는다. 알림 재시도는 '이번 달 완료' 조회가 맡는다."""
        user, settings = _user(), _settings()
        ch = _challenge(user_id=user.id, target_months=3, start_month="2025-01")
        session = _session([(user, settings)], [ch])
        with (
            patch("app.jobs.challenge_monthly_wrap.AsyncSessionLocal", return_value=session),
            patch("app.jobs._job_helpers.AsyncSessionLocal", return_value=session),
            patch("app.jobs._job_helpers.get_cache_store", new_callable=AsyncMock, return_value=AsyncMock()),
            patch("app.jobs.challenge_monthly_wrap._prev_month_str", return_value="2026-02"),
            patch(
                "app.services.challenge_service.compute_progress",
                new_callable=AsyncMock,
                return_value=_progress(
                    current_streak=3,
                    longest_streak=3,
                    months=[SimpleNamespace(month="2026-02", net_krw=500000.0, satisfied=True, target_met=True)],
                ),
            ),
            patch(
                "app.jobs.challenge_monthly_wrap.dispatch_dual_channel_alert",
                new_callable=AsyncMock,
                return_value=False,
            ) as dispatch,
            patch("app.services.challenge_service.invalidate_challenge_cache", new_callable=AsyncMock),
        ):
            from app.jobs.challenge_monthly_wrap import run_challenge_monthly_wrap

            await run_challenge_monthly_wrap()
        assert dispatch.called
        assert ch.status == "COMPLETED"
        assert ch.completed_at is not None

    @pytest.mark.asyncio
    async def test_retries_alert_for_completed_challenge_even_if_progress_dropped(self):
        """이번 달 완료됐지만 알림이 안 나간(dedup 키 없음) RETURN_PCT 챌린지 — 재실행 시점에 수익률이
        목표 아래로 내려가도 달성 알림을 다시 시도하고, 완료 상태·완료 시각은 그대로 둔다."""
        from datetime import UTC, datetime

        user, settings = _user(), _settings()
        done_at = datetime(2026, 3, 1, 1, 0, tzinfo=UTC)
        ch = _challenge(
            user_id=user.id,
            challenge_type="RETURN_PCT",
            target_pct=10.0,
            target_months=None,
            status="COMPLETED",
            completed_at=done_at,
        )
        session = _session([(user, settings)], [ch])
        with (
            patch("app.jobs.challenge_monthly_wrap.AsyncSessionLocal", return_value=session),
            patch("app.jobs._job_helpers.AsyncSessionLocal", return_value=session),
            patch("app.jobs._job_helpers.get_cache_store", new_callable=AsyncMock, return_value=AsyncMock()),
            patch("app.jobs.challenge_monthly_wrap._prev_month_str", return_value="2026-02"),
            patch(
                "app.services.challenge_service.compute_progress",
                new_callable=AsyncMock,
                return_value=_progress(progress_pct=80.0),
            ),
            patch(
                "app.jobs.challenge_monthly_wrap.dispatch_dual_channel_alert", new_callable=AsyncMock, return_value=True
            ) as dispatch,
            patch("app.services.challenge_service.invalidate_challenge_cache", new_callable=AsyncMock),
        ):
            from app.jobs.challenge_monthly_wrap import run_challenge_monthly_wrap

            await run_challenge_monthly_wrap()
        dispatch.assert_awaited_once()
        assert "달성" in dispatch.call_args.kwargs["history_message"]
        assert ch.status == "COMPLETED"
        assert ch.completed_at == done_at

    @pytest.mark.asyncio
    async def test_query_includes_challenges_completed_this_month(self):
        """조회는 ACTIVE + 이번 달(KST 월초 이후) 완료분 — 지난달 이전 완료분은 새 월 키로 재발송되지 않게 뺀다."""
        user, settings = _user(), _settings()
        session = _session([(user, settings)], [])
        captured = []
        orig_execute = session.execute

        async def cap(stmt):
            captured.append(stmt)
            return await orig_execute(stmt)

        session.execute = cap
        with (
            patch("app.jobs.challenge_monthly_wrap.AsyncSessionLocal", return_value=session),
            patch("app.jobs._job_helpers.AsyncSessionLocal", return_value=session),
            patch("app.jobs._job_helpers.get_cache_store", new_callable=AsyncMock, return_value=AsyncMock()),
        ):
            from app.jobs.challenge_monthly_wrap import run_challenge_monthly_wrap

            await run_challenge_monthly_wrap()
        sql = " ".join(str(st.compile(compile_kwargs={"literal_binds": True})) for st in captured)
        assert "investment_challenges.status = 'COMPLETED'" in sql
        assert "investment_challenges.completed_at >=" in sql

    @pytest.mark.asyncio
    async def test_return_pct_wrap_only_sends_when_complete(self):
        user, settings = _user(), _settings()
        ch = _challenge(user_id=user.id, challenge_type="RETURN_PCT", target_pct=10.0, target_months=None)
        session = _session([(user, settings)], [ch])
        with (
            patch("app.jobs.challenge_monthly_wrap.AsyncSessionLocal", return_value=session),
            patch("app.jobs._job_helpers.AsyncSessionLocal", return_value=session),
            patch("app.jobs._job_helpers.get_cache_store", new_callable=AsyncMock, return_value=AsyncMock()),
            patch("app.jobs.challenge_monthly_wrap._prev_month_str", return_value="2026-02"),
            patch(
                "app.services.challenge_service.compute_progress",
                new_callable=AsyncMock,
                return_value=_progress(progress_pct=50.0),
            ),
            patch("app.jobs.challenge_monthly_wrap.dispatch_dual_channel_alert", new_callable=AsyncMock) as dispatch,
        ):
            from app.jobs.challenge_monthly_wrap import run_challenge_monthly_wrap

            await run_challenge_monthly_wrap()
        dispatch.assert_not_called()
