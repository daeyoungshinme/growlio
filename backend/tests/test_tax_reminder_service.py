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


def _action(action_id: str, benefit: float | None) -> dict:
    return {
        "id": action_id,
        "category": "PENSION_DEDUCTION",
        "title": f"{action_id} 제목",
        "detail": "상세",
        "amount_krw": 1_000_000.0,
        "benefit_krw": benefit,
        "deadline": "2026-12-31",
        "priority": "HIGH",
        "uses_income_bracket": False,
        "cta": {"label": "보기", "link": "/assets"},
    }


class TestBuildReminderContent:
    @pytest.mark.asyncio
    async def test_has_content_false_when_no_actions(self, mock_db):
        with patch(
            "app.services.alerts.tax_reminder_service.get_tax_action_plan",
            new=AsyncMock(return_value={"actions": []}),
        ):
            content = await build_reminder_content(uuid.uuid4(), mock_db)

        assert content["has_content"] is False
        assert content["actions"] == []
        assert content["total_benefit_krw"] == 0

    @pytest.mark.asyncio
    async def test_reuses_action_plan_top_n_and_sums_benefit(self, mock_db):
        """앱 세금 탭의 절세 액션 플랜을 그대로 재사용 — 상위 5건만, benefit None은 0으로 합산."""
        actions = [_action(f"a{i}", 10_000.0 if i != 1 else None) for i in range(7)]
        with patch(
            "app.services.alerts.tax_reminder_service.get_tax_action_plan",
            new=AsyncMock(return_value={"actions": actions}),
        ):
            content = await build_reminder_content(uuid.uuid4(), mock_db)

        assert [a["id"] for a in content["actions"]] == ["a0", "a1", "a2", "a3", "a4"]
        assert content["total_benefit_krw"] == 40_000.0
        assert content["has_content"] is True


class TestReminderTemplate:
    def test_renders_actions_escaped_with_benefit_and_deadline(self):
        from app.services.email_templates import year_end_tax_reminder_template

        action = _action("x", 99_000.0)
        action["title"] = "<b>ISA</b> 이전"
        subject, html = year_end_tax_reminder_template({"actions": [action], "total_benefit_krw": 99_000.0})

        assert "연말 절세 리마인더" in subject
        assert "&lt;b&gt;ISA&lt;/b&gt; 이전" in html
        assert "예상 절세 약 99,000원" in html
        assert "마감 2026-12-31" in html


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
            "actions": [_action("pension", 150_000.0), _action("isa", None)],
            "total_benefit_krw": 150_000.0,
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
        assert push_kwargs["body"] == "pension 제목 외 1건"
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
