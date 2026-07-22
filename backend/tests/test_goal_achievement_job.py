"""투자 목표 달성 알림 Job 테스트."""

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


def _make_settings(
    goal_amount=None,
    annual_deposit_goal=None,
    annual_dividend_goal=None,
    notification_email=None,
    fcm_token=None,
):
    return SimpleNamespace(
        goal_amount=goal_amount,
        annual_deposit_goal=annual_deposit_goal,
        annual_dividend_goal=annual_dividend_goal,
        notification_email=notification_email,
        fcm_token=fcm_token,
    )


_MOCK_SUMMARY_ACHIEVED = {
    "total_assets_krw": 100_000_000.0,
    "goal_achievement_pct": 100.0,
    "deposit_achievement_pct": 100.0,
    "dividend_goal_achievement_pct": 100.0,
}

_MOCK_SUMMARY_NOT_ACHIEVED = {
    "total_assets_krw": 50_000_000.0,
    "goal_achievement_pct": 50.0,
    "deposit_achievement_pct": 60.0,
    "dividend_goal_achievement_pct": 40.0,
}


class TestRunGoalAchievementCheck:
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
            patch("app.jobs.goal_achievement.AsyncSessionLocal", return_value=mock_session),
            patch("app.jobs.goal_achievement.get_cache_store", new_callable=AsyncMock, return_value=AsyncMock()),
            patch("app.jobs.goal_achievement.send_goal_achievement_email", new_callable=AsyncMock) as mock_email,
        ):
            from app.jobs.goal_achievement import run_goal_achievement_check

            await run_goal_achievement_check()

        mock_email.assert_not_called()

    @pytest.mark.asyncio
    async def test_user_with_goal_not_achieved_does_not_send_email(self):
        """목표 미달성 유저에게 이메일 발송하지 않는다."""
        user = _make_user()
        settings = _make_settings(goal_amount=100_000_000)

        mock_session = AsyncMock()
        execute_result = MagicMock()
        execute_result.all.return_value = [(user, settings)]
        execute_result.scalar.return_value = None
        mock_session.execute = AsyncMock(return_value=execute_result)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("app.jobs.goal_achievement.AsyncSessionLocal", return_value=mock_session),
            patch("app.jobs.goal_achievement.get_cache_store", new_callable=AsyncMock, return_value=AsyncMock()),
            patch(
                "app.jobs.goal_achievement.get_dashboard_summary",
                new_callable=AsyncMock,
                return_value=_MOCK_SUMMARY_NOT_ACHIEVED,
            ),
            patch("app.jobs.goal_achievement.send_goal_achievement_email", new_callable=AsyncMock) as mock_email,
        ):
            from app.jobs.goal_achievement import run_goal_achievement_check

            await run_goal_achievement_check()

        mock_email.assert_not_called()

    @pytest.mark.asyncio
    async def test_sends_asset_goal_email_when_100pct_achieved(self):
        """총 자산 목표 100% 달성 시 이메일 발송."""
        user = _make_user()
        settings = _make_settings(
            goal_amount=100_000_000,
            notification_email="notify@test.com",
            fcm_token="fcm-token-asset",
        )

        mock_session = AsyncMock()
        list_result = MagicMock()
        list_result.all.return_value = [(user, settings)]
        history_result = MagicMock()
        history_result.scalar.return_value = None

        call_count = [0]

        async def mock_execute(stmt):
            call_count[0] += 1
            if call_count[0] == 1:
                return list_result
            return history_result

        mock_session.execute = AsyncMock(side_effect=mock_execute)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("app.jobs.goal_achievement.AsyncSessionLocal", return_value=mock_session),
            patch("app.jobs.goal_achievement.get_cache_store", new_callable=AsyncMock, return_value=AsyncMock()),
            patch(
                "app.jobs.goal_achievement.get_dashboard_summary",
                new_callable=AsyncMock,
                return_value=_MOCK_SUMMARY_ACHIEVED,
            ),
            patch("app.jobs.goal_achievement.send_goal_achievement_email", new_callable=AsyncMock) as mock_email,
            patch("app.jobs.goal_achievement.send_push_to_user", new_callable=AsyncMock) as mock_push,
        ):
            from app.jobs.goal_achievement import run_goal_achievement_check

            await run_goal_achievement_check()

        assert mock_email.called
        kwargs = mock_email.call_args.kwargs
        assert kwargs["to_email"] == "notify@test.com"
        assert kwargs["goal_type"] == "ASSET"

        assert mock_push.called
        push_kwargs = mock_push.call_args.kwargs
        assert push_kwargs["fcm_token"] == "fcm-token-asset"
        assert push_kwargs["data"] == {"type": "GOAL_ASSET"}

    @pytest.mark.asyncio
    async def test_sends_deposit_goal_email_when_100pct_achieved(self):
        """연간 입금 목표 100% 달성 시 이메일 발송."""
        user = _make_user()
        settings = _make_settings(annual_deposit_goal=10_000_000, fcm_token="fcm-token-deposit")

        mock_session = AsyncMock()
        list_result = MagicMock()
        list_result.all.return_value = [(user, settings)]
        history_result = MagicMock()
        history_result.scalar.return_value = None

        call_count = [0]

        async def mock_execute(stmt):
            call_count[0] += 1
            if call_count[0] == 1:
                return list_result
            return history_result

        mock_session.execute = AsyncMock(side_effect=mock_execute)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("app.jobs.goal_achievement.AsyncSessionLocal", return_value=mock_session),
            patch("app.jobs.goal_achievement.get_cache_store", new_callable=AsyncMock, return_value=AsyncMock()),
            patch(
                "app.jobs.goal_achievement.get_dashboard_summary",
                new_callable=AsyncMock,
                return_value=_MOCK_SUMMARY_ACHIEVED,
            ),
            patch("app.jobs.goal_achievement.send_goal_achievement_email", new_callable=AsyncMock) as mock_email,
            patch("app.jobs.goal_achievement.send_push_to_user", new_callable=AsyncMock) as mock_push,
        ):
            from app.jobs.goal_achievement import run_goal_achievement_check

            await run_goal_achievement_check()

        assert mock_email.called
        kwargs = mock_email.call_args.kwargs
        assert kwargs["goal_type"] == "DEPOSIT"

        assert mock_push.called
        push_kwargs = mock_push.call_args.kwargs
        assert push_kwargs["fcm_token"] == "fcm-token-deposit"
        assert push_kwargs["data"] == {"type": "GOAL_DEPOSIT"}

    @pytest.mark.asyncio
    async def test_sends_dividend_goal_email_when_100pct_achieved(self):
        """연간 배당 목표 100% 달성 시 이메일 발송."""
        user = _make_user()
        settings = _make_settings(annual_dividend_goal=5_000_000, fcm_token="fcm-token-dividend")

        mock_session = AsyncMock()
        list_result = MagicMock()
        list_result.all.return_value = [(user, settings)]
        history_result = MagicMock()
        history_result.scalar.return_value = None

        call_count = [0]

        async def mock_execute(stmt):
            call_count[0] += 1
            if call_count[0] == 1:
                return list_result
            return history_result

        mock_session.execute = AsyncMock(side_effect=mock_execute)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("app.jobs.goal_achievement.AsyncSessionLocal", return_value=mock_session),
            patch("app.jobs.goal_achievement.get_cache_store", new_callable=AsyncMock, return_value=AsyncMock()),
            patch(
                "app.jobs.goal_achievement.get_dashboard_summary",
                new_callable=AsyncMock,
                return_value=_MOCK_SUMMARY_ACHIEVED,
            ),
            patch("app.jobs.goal_achievement.send_goal_achievement_email", new_callable=AsyncMock) as mock_email,
            patch("app.jobs.goal_achievement.send_push_to_user", new_callable=AsyncMock) as mock_push,
        ):
            from app.jobs.goal_achievement import run_goal_achievement_check

            await run_goal_achievement_check()

        assert mock_email.called
        kwargs = mock_email.call_args.kwargs
        assert kwargs["goal_type"] == "DIVIDEND"

        assert mock_push.called
        push_kwargs = mock_push.call_args.kwargs
        assert push_kwargs["fcm_token"] == "fcm-token-dividend"
        assert push_kwargs["data"] == {"type": "GOAL_DIVIDEND"}

    @pytest.mark.asyncio
    async def test_query_filters_by_goal_achievement_alerts_enabled(self):
        """알림이 꺼진 유저를 애초에 쿼리 대상에서 제외하도록 WHERE절에 필터가 포함된다."""
        mock_session = AsyncMock()
        execute_result = MagicMock()
        execute_result.all.return_value = []
        captured_stmt = {}

        async def capture_execute(stmt):
            captured_stmt["stmt"] = stmt
            return execute_result

        mock_session.execute = AsyncMock(side_effect=capture_execute)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("app.jobs.goal_achievement.AsyncSessionLocal", return_value=mock_session),
            patch("app.jobs.goal_achievement.get_cache_store", new_callable=AsyncMock, return_value=AsyncMock()),
        ):
            from app.jobs.goal_achievement import run_goal_achievement_check

            await run_goal_achievement_check()

        assert "goal_achievement_alerts_enabled" in str(captured_stmt["stmt"])

    @pytest.mark.asyncio
    async def test_exception_does_not_stop_other_users(self):
        """한 유저 실패해도 다른 유저 처리 계속."""
        user1 = _make_user()
        user2 = _make_user()
        settings1 = _make_settings(goal_amount=100_000_000)
        settings2 = _make_settings(goal_amount=100_000_000)

        mock_session = AsyncMock()
        execute_result = MagicMock()
        execute_result.all.return_value = [(user1, settings1), (user2, settings2)]
        mock_session.execute = AsyncMock(return_value=execute_result)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        call_count = [0]

        async def fail_first(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("대시보드 조회 실패")
            return _MOCK_SUMMARY_NOT_ACHIEVED

        with (
            patch("app.jobs.goal_achievement.AsyncSessionLocal", return_value=mock_session),
            patch("app.jobs.goal_achievement.get_cache_store", new_callable=AsyncMock, return_value=AsyncMock()),
            patch("app.jobs.goal_achievement.get_dashboard_summary", side_effect=fail_first),
            patch("app.jobs.goal_achievement.send_goal_achievement_email", new_callable=AsyncMock),
        ):
            from app.jobs.goal_achievement import run_goal_achievement_check

            await run_goal_achievement_check()

        assert call_count[0] == 2


class TestAlreadyNotifiedThisMonth:
    @pytest.mark.asyncio
    async def test_returns_false_when_no_history(self, mock_db):
        """이달 알림 내역 없으면 False 반환."""
        from app.jobs.goal_achievement import _already_notified_this_month

        result_mock = MagicMock()
        result_mock.scalar.return_value = None
        mock_db.execute = AsyncMock(return_value=result_mock)

        result = await _already_notified_this_month(mock_db, uuid.uuid4(), "GOAL_ASSET")
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_true_when_history_exists(self, mock_db):
        """이달 알림 내역 있으면 True 반환."""
        from app.jobs.goal_achievement import _already_notified_this_month

        result_mock = MagicMock()
        result_mock.scalar.return_value = uuid.uuid4()
        mock_db.execute = AsyncMock(return_value=result_mock)

        result = await _already_notified_this_month(mock_db, uuid.uuid4(), "GOAL_ASSET")
        assert result is True
