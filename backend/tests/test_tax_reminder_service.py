"""tax_reminder_service.py 테스트 — 연말 절세 리마인더 콘텐츠 조합 + 유저별 발송."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.alerts.tax_reminder_service import (
    _already_sent_reminder_today,
    _get_reminder_subscribers,
    build_reminder_content,
    send_year_end_tax_reminder,
)


class TestBuildReminderContent:
    @pytest.mark.asyncio
    async def test_has_content_false_when_nothing_actionable(self, mock_db):
        with (
            patch(
                "app.services.alerts.tax_reminder_service.get_tax_summary",
                new=AsyncMock(return_value={"harvesting_recommendations": []}),
            ),
            patch(
                "app.services.alerts.tax_reminder_service.calc_pension_contribution_status",
                new=AsyncMock(return_value={"total_remaining_krw": 0.0}),
            ),
            patch(
                "app.services.alerts.tax_reminder_service.get_isa_status_summary",
                new=AsyncMock(return_value={"accounts": []}),
            ),
            patch(
                "app.services.alerts.tax_reminder_service._has_pension_accounts",
                new=AsyncMock(return_value=False),
            ),
        ):
            content = await build_reminder_content(uuid.uuid4(), mock_db)

        assert content["has_content"] is False
        assert content["harvesting_top"] == []
        assert content["pension_remaining_krw"] == 0.0

    @pytest.mark.asyncio
    async def test_pension_remaining_ignored_without_pension_accounts(self, mock_db):
        """연금 계좌가 없으면 calc_pension_contribution_status가 반환하는 잔여한도(기본 900만원)를 무시한다."""
        with (
            patch(
                "app.services.alerts.tax_reminder_service.get_tax_summary",
                new=AsyncMock(return_value={"harvesting_recommendations": []}),
            ),
            patch(
                "app.services.alerts.tax_reminder_service.calc_pension_contribution_status",
                new=AsyncMock(return_value={"total_remaining_krw": 9_000_000.0}),
            ),
            patch(
                "app.services.alerts.tax_reminder_service.get_isa_status_summary",
                new=AsyncMock(return_value={"accounts": []}),
            ),
            patch(
                "app.services.alerts.tax_reminder_service._has_pension_accounts",
                new=AsyncMock(return_value=False),
            ),
        ):
            content = await build_reminder_content(uuid.uuid4(), mock_db)

        assert content["pension_remaining_krw"] == 0.0
        assert content["has_content"] is False

    @pytest.mark.asyncio
    async def test_harvesting_top_capped_and_summed(self, mock_db):
        def _make_rec(ticker: str, loss: int, tax_saved: int) -> dict:
            return {
                "ticker": ticker,
                "name": f"{ticker} Corp",
                "market": "NASDAQ",
                "unrealized_loss_krw": loss,
                "tax_saved_krw": tax_saved,
                "qty": 1,
            }

        harvesting = [
            _make_rec("A", -1000, 220),
            _make_rec("B", -2000, 440),
            _make_rec("C", -3000, 660),
            _make_rec("D", -4000, 880),
        ]
        with (
            patch(
                "app.services.alerts.tax_reminder_service.get_tax_summary",
                new=AsyncMock(return_value={"harvesting_recommendations": harvesting}),
            ),
            patch(
                "app.services.alerts.tax_reminder_service.calc_pension_contribution_status",
                new=AsyncMock(return_value={"total_remaining_krw": 0.0}),
            ),
            patch(
                "app.services.alerts.tax_reminder_service.get_isa_status_summary",
                new=AsyncMock(return_value={"accounts": []}),
            ),
            patch(
                "app.services.alerts.tax_reminder_service._has_pension_accounts",
                new=AsyncMock(return_value=False),
            ),
        ):
            content = await build_reminder_content(uuid.uuid4(), mock_db)

        assert len(content["harvesting_top"]) == 3  # _HARVESTING_TOP_N
        assert content["harvesting_total_tax_saved_krw"] == 2200  # 전체 4건 합계
        assert content["has_content"] is True

    @pytest.mark.asyncio
    async def test_isa_near_maturity_and_over_limit_detected(self, mock_db):
        isa_accounts = [
            {
                "account_name": "ISA계좌1",
                "is_mature": False,
                "needs_open_date": False,
                "days_remaining": 10,
                "taxable_excess_krw": 0.0,
            },
            {
                "account_name": "ISA계좌2",
                "is_mature": True,
                "needs_open_date": False,
                "days_remaining": 0,
                "taxable_excess_krw": 500_000.0,
            },
        ]
        with (
            patch(
                "app.services.alerts.tax_reminder_service.get_tax_summary",
                new=AsyncMock(return_value={"harvesting_recommendations": []}),
            ),
            patch(
                "app.services.alerts.tax_reminder_service.calc_pension_contribution_status",
                new=AsyncMock(return_value={"total_remaining_krw": 0.0}),
            ),
            patch(
                "app.services.alerts.tax_reminder_service.get_isa_status_summary",
                new=AsyncMock(return_value={"accounts": isa_accounts}),
            ),
            patch(
                "app.services.alerts.tax_reminder_service._has_pension_accounts",
                new=AsyncMock(return_value=False),
            ),
        ):
            content = await build_reminder_content(uuid.uuid4(), mock_db)

        assert len(content["isa_near_maturity"]) == 1
        assert content["isa_near_maturity"][0]["account_name"] == "ISA계좌1"
        assert content["isa_over_limit_count"] == 1
        assert content["has_content"] is True


class TestGetReminderSubscribers:
    @pytest.mark.asyncio
    async def test_returns_subscribed_active_users(self, mock_db):
        user = SimpleNamespace(id=uuid.uuid4(), is_active=True)
        settings_row = SimpleNamespace(year_end_tax_reminder_enabled=True)
        result_mock = MagicMock()
        result_mock.all.return_value = [(user, settings_row)]
        mock_db.execute = AsyncMock(return_value=result_mock)

        subscribers = await _get_reminder_subscribers(mock_db)

        assert subscribers == [(user, settings_row)]


class TestAlreadySentReminderToday:
    @pytest.mark.asyncio
    async def test_returns_false_when_no_history(self, mock_db):
        result_mock = MagicMock()
        result_mock.scalar.return_value = None
        mock_db.execute = AsyncMock(return_value=result_mock)

        assert await _already_sent_reminder_today(mock_db, uuid.uuid4()) is False

    @pytest.mark.asyncio
    async def test_returns_true_when_history_exists(self, mock_db):
        result_mock = MagicMock()
        result_mock.scalar.return_value = uuid.uuid4()
        mock_db.execute = AsyncMock(return_value=result_mock)

        assert await _already_sent_reminder_today(mock_db, uuid.uuid4()) is True


class TestSendYearEndTaxReminder:
    @pytest.mark.asyncio
    async def test_no_subscribers_sends_nothing(self, mock_db):
        execute_result = MagicMock()
        execute_result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=execute_result)

        with patch("app.services.email_service.send_year_end_tax_reminder_email", new=AsyncMock()) as mock_email:
            await send_year_end_tax_reminder(mock_db)

        mock_email.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_when_no_actionable_content(self, mock_db):
        """콘텐츠가 비어있으면(has_content=False) 발송하지 않는다."""
        user = SimpleNamespace(id=uuid.uuid4(), email="user@example.com", is_active=True)
        user_settings = SimpleNamespace(notification_email=None, fcm_token=None)

        subscribers_result = MagicMock()
        subscribers_result.all.return_value = [(user, user_settings)]
        mock_db.execute = AsyncMock(return_value=subscribers_result)

        history_result = MagicMock()
        history_result.scalar.return_value = None
        per_user_session = AsyncMock()
        per_user_session.execute = AsyncMock(return_value=history_result)
        per_user_session.__aenter__ = AsyncMock(return_value=per_user_session)
        per_user_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(
                "app.services.alerts.tax_reminder_service.AsyncSessionLocal",
                return_value=per_user_session,
            ),
            patch(
                "app.services.alerts.tax_reminder_service.build_reminder_content",
                new=AsyncMock(return_value={"has_content": False}),
            ),
            patch("app.services.email_service.send_year_end_tax_reminder_email", new=AsyncMock()) as mock_email,
        ):
            await send_year_end_tax_reminder(mock_db)

        mock_email.assert_not_called()

    @pytest.mark.asyncio
    async def test_sends_email_and_push_and_saves_history(self, mock_db):
        user = SimpleNamespace(id=uuid.uuid4(), email="user@example.com", is_active=True)
        user_settings = SimpleNamespace(notification_email=None, fcm_token="token-abc")

        subscribers_result = MagicMock()
        subscribers_result.all.return_value = [(user, user_settings)]
        mock_db.execute = AsyncMock(return_value=subscribers_result)

        history_result = MagicMock()
        history_result.scalar.return_value = None
        per_user_session = AsyncMock()
        per_user_session.execute = AsyncMock(return_value=history_result)
        per_user_session.add = MagicMock()
        per_user_session.commit = AsyncMock()
        per_user_session.__aenter__ = AsyncMock(return_value=per_user_session)
        per_user_session.__aexit__ = AsyncMock(return_value=None)

        content = {
            "harvesting_top": [{"ticker": "AAPL", "unrealized_loss_krw": -100_000, "tax_saved_krw": 22_000}],
            "harvesting_total_tax_saved_krw": 22_000,
            "pension_remaining_krw": 1_000_000.0,
            "isa_near_maturity": [],
            "isa_over_limit_count": 0,
            "has_content": True,
        }

        with (
            patch(
                "app.services.alerts.tax_reminder_service.AsyncSessionLocal",
                return_value=per_user_session,
            ),
            patch(
                "app.services.alerts.tax_reminder_service.build_reminder_content",
                new=AsyncMock(return_value=content),
            ),
            patch(
                "app.services.email_service.send_year_end_tax_reminder_email",
                new=AsyncMock(return_value=True),
            ) as mock_email,
            patch(
                "app.services.push_service.send_push_to_user",
                new=AsyncMock(return_value=True),
            ) as mock_push,
        ):
            await send_year_end_tax_reminder(mock_db)

        mock_email.assert_called_once_with("user@example.com", content)
        mock_push.assert_called_once()
        push_kwargs = mock_push.call_args.kwargs
        assert push_kwargs["fcm_token"] == "token-abc"
        assert push_kwargs["data"] == {"type": "YEAR_END_TAX_REMINDER"}
        assert "손실수확 후보 1종목" in push_kwargs["body"]
        per_user_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_user_already_notified_today(self, mock_db):
        user = SimpleNamespace(id=uuid.uuid4(), email="user@example.com", is_active=True)
        user_settings = SimpleNamespace(notification_email=None, fcm_token=None)

        subscribers_result = MagicMock()
        subscribers_result.all.return_value = [(user, user_settings)]
        mock_db.execute = AsyncMock(return_value=subscribers_result)

        history_result = MagicMock()
        history_result.scalar.return_value = uuid.uuid4()  # 이미 발송됨
        per_user_session = AsyncMock()
        per_user_session.execute = AsyncMock(return_value=history_result)
        per_user_session.__aenter__ = AsyncMock(return_value=per_user_session)
        per_user_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(
                "app.services.alerts.tax_reminder_service.AsyncSessionLocal",
                return_value=per_user_session,
            ),
            patch("app.services.email_service.send_year_end_tax_reminder_email", new=AsyncMock()) as mock_email,
        ):
            await send_year_end_tax_reminder(mock_db)

        mock_email.assert_not_called()
