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
        ):
            from app.jobs.challenge_monthly_wrap import run_challenge_monthly_wrap

            await run_challenge_monthly_wrap()
        assert dispatch.called
        assert dispatch.call_args.kwargs["alert_type"] == "CHALLENGE_WRAPUP"
        assert ch.status == "COMPLETED"
        assert ch.completed_at is not None

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
