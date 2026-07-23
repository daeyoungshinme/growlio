"""monthly_report Job 테스트."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_user(user_id=None):
    return SimpleNamespace(
        id=user_id or uuid.uuid4(),
        email="user@test.com",
        is_active=True,
    )


def _make_settings(enabled=True, notification_email=None):
    return SimpleNamespace(
        monthly_report_enabled=enabled,
        notification_email=notification_email,
    )


_MOCK_SUMMARY = {
    "total_assets_krw": 50_000_000.0,
    "monthly_trend": [
        {"month": "2026-05-01", "total_krw": 48_000_000},
        {"month": "2026-06-01", "total_krw": 50_000_000},
    ],
    "annual_return_pct": 5.0,
    "xirr_pct": 4.8,
    "goal_amount": 100_000_000,
    "goal_achievement_pct": 50.0,
    "annual_deposit_goal": 10_000_000,
    "deposit_achievement_pct": 60.0,
    "annual_dividends_received": 500_000.0,
    "asset_allocation": [],
}


class TestRunMonthlyReport:
    @pytest.mark.asyncio
    async def test_no_users_does_nothing(self):
        """유저 없을 때 이메일 발송하지 않는다."""
        mock_session = AsyncMock()
        execute_result = MagicMock()
        execute_result.all.return_value = []
        mock_session.execute = AsyncMock(return_value=execute_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("app.jobs.monthly_report.AsyncSessionLocal", return_value=mock_session),
            patch("app.jobs._job_helpers.AsyncSessionLocal", return_value=mock_session),
            patch("app.jobs._job_helpers.get_cache_store", new_callable=AsyncMock, return_value=AsyncMock()),
            patch("app.jobs.monthly_report.send_monthly_report_email", new_callable=AsyncMock) as mock_email,
        ):
            from app.jobs.monthly_report import run_monthly_report

            await run_monthly_report()

        mock_email.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_disabled_users(self):
        """monthly_report_enabled=False인 유저는 이메일 건너뜀."""
        user = _make_user()
        settings = _make_settings(enabled=False)

        mock_session = AsyncMock()
        execute_result = MagicMock()
        execute_result.all.return_value = [(user, settings)]
        mock_session.execute = AsyncMock(return_value=execute_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("app.jobs.monthly_report.AsyncSessionLocal", return_value=mock_session),
            patch("app.jobs._job_helpers.AsyncSessionLocal", return_value=mock_session),
            patch("app.jobs._job_helpers.get_cache_store", new_callable=AsyncMock, return_value=AsyncMock()),
            patch("app.jobs.monthly_report.send_monthly_report_email", new_callable=AsyncMock) as mock_email,
        ):
            from app.jobs.monthly_report import run_monthly_report

            await run_monthly_report()

        mock_email.assert_not_called()

    @pytest.mark.asyncio
    async def test_sends_report_to_enabled_user(self):
        """enabled=True 유저에게 이메일 발송."""
        user = _make_user()
        settings = _make_settings(enabled=True, notification_email="notify@test.com")

        mock_session = AsyncMock()
        execute_result = MagicMock()
        execute_result.all.return_value = [(user, settings)]
        mock_session.execute = AsyncMock(return_value=execute_result)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("app.jobs.monthly_report.AsyncSessionLocal", return_value=mock_session),
            patch("app.jobs._job_helpers.AsyncSessionLocal", return_value=mock_session),
            patch("app.jobs._job_helpers.get_cache_store", new_callable=AsyncMock, return_value=AsyncMock()),
            patch("app.jobs.monthly_report.get_dashboard_summary", new_callable=AsyncMock, return_value=_MOCK_SUMMARY),
            patch("app.jobs.monthly_report.send_monthly_report_email", new_callable=AsyncMock) as mock_email,
        ):
            from app.jobs.monthly_report import run_monthly_report

            await run_monthly_report()

        mock_email.assert_called_once()
        call_kwargs = mock_email.call_args.kwargs
        assert call_kwargs["to_email"] == "notify@test.com"
        assert call_kwargs["total_assets_krw"] == 50_000_000.0

    @pytest.mark.asyncio
    async def test_uses_user_email_as_fallback(self):
        """notification_email 없으면 user.email 사용."""
        user = _make_user()
        settings = _make_settings(enabled=True, notification_email=None)

        mock_session = AsyncMock()
        execute_result = MagicMock()
        execute_result.all.return_value = [(user, settings)]
        mock_session.execute = AsyncMock(return_value=execute_result)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("app.jobs.monthly_report.AsyncSessionLocal", return_value=mock_session),
            patch("app.jobs._job_helpers.AsyncSessionLocal", return_value=mock_session),
            patch("app.jobs._job_helpers.get_cache_store", new_callable=AsyncMock, return_value=AsyncMock()),
            patch("app.jobs.monthly_report.get_dashboard_summary", new_callable=AsyncMock, return_value=_MOCK_SUMMARY),
            patch("app.jobs.monthly_report.send_monthly_report_email", new_callable=AsyncMock) as mock_email,
        ):
            from app.jobs.monthly_report import run_monthly_report

            await run_monthly_report()

        mock_email.assert_called_once()
        call_kwargs = mock_email.call_args.kwargs
        assert call_kwargs["to_email"] == user.email

    @pytest.mark.asyncio
    async def test_failure_does_not_stop_other_users(self):
        """한 유저 이메일 발송 실패해도 나머지 유저에게 계속 발송."""
        user1 = _make_user()
        user2 = _make_user()
        settings1 = _make_settings(enabled=True)
        settings2 = _make_settings(enabled=True)

        mock_session = AsyncMock()
        execute_result = MagicMock()
        execute_result.all.return_value = [(user1, settings1), (user2, settings2)]
        mock_session.execute = AsyncMock(return_value=execute_result)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        call_count = [0]

        async def failing_email(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("SMTP 오류")

        with (
            patch("app.jobs.monthly_report.AsyncSessionLocal", return_value=mock_session),
            patch("app.jobs._job_helpers.AsyncSessionLocal", return_value=mock_session),
            patch("app.jobs._job_helpers.get_cache_store", new_callable=AsyncMock, return_value=AsyncMock()),
            patch("app.jobs.monthly_report.get_dashboard_summary", new_callable=AsyncMock, return_value=_MOCK_SUMMARY),
            patch("app.jobs.monthly_report.send_monthly_report_email", side_effect=failing_email),
        ):
            from app.jobs.monthly_report import run_monthly_report

            await run_monthly_report()

        assert call_count[0] == 2


class TestPrevMonthLabel:
    def test_january_returns_december_of_prev_year(self):
        from datetime import date

        from app.jobs.monthly_report import _prev_month_label

        result = _prev_month_label(date(2026, 1, 15))
        assert result == "2025년 12월"

    def test_other_month_returns_prev_month(self):
        from datetime import date

        from app.jobs.monthly_report import _prev_month_label

        result = _prev_month_label(date(2026, 6, 1))
        assert result == "2026년 5월"
