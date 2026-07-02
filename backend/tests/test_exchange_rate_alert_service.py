"""exchange_rate_alert_service 단위 테스트."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

_FETCH_RATE = "app.services.exchange_rate_alert_service.fetch_usd_krw"
_SEND_EMAIL = "app.services.email_service.send_exchange_rate_alert"
_SEND_PUSH = "app.services.push_service.send_push_to_user"
_SAVE_HIST = "app.services.alert_service.save_alert_history"


def _make_alert(
    *,
    target_rate: float = 1300.0,
    direction: str = "BELOW",
    trigger_count: int = 0,
    max_trigger_count: int = 1,
    triggered_at=None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        target_rate=target_rate,
        direction=direction,
        trigger_count=trigger_count,
        max_trigger_count=max_trigger_count,
        triggered_at=triggered_at,
        is_active=True,
    )


def _make_db_row(alert, email="user@test.com", notification_email=None, fcm_token=None):
    return (alert, email, notification_email, fcm_token)


class TestCheckAndTriggerAlerts:
    @pytest.mark.asyncio
    async def test_no_alerts_returns_early(self, mock_db):
        """활성 알림이 없으면 아무 작업도 하지 않는다."""
        mock_db.execute.return_value.all.return_value = []

        with patch(_FETCH_RATE, new_callable=AsyncMock, return_value=1320.0):
            from app.services.exchange_rate_alert_service import check_and_trigger_alerts

            await check_and_trigger_alerts(mock_db)

        mock_db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_rate_zero_returns_early(self, mock_db):
        """환율 조회 실패(0 반환) 시 조기 종료한다."""
        with patch(_FETCH_RATE, new_callable=AsyncMock, return_value=0):
            from app.services.exchange_rate_alert_service import check_and_trigger_alerts

            await check_and_trigger_alerts(mock_db)

        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_alert_not_triggered_when_condition_not_met(self, mock_db):
        """조건 미충족(BELOW이지만 현재가 > 목표) 시 알림 미발송."""
        alert = _make_alert(target_rate=1300.0, direction="BELOW")
        mock_db.execute.return_value.all.return_value = [_make_db_row(alert)]

        with patch(_FETCH_RATE, new_callable=AsyncMock, return_value=1350.0):
            from app.services.exchange_rate_alert_service import check_and_trigger_alerts

            await check_and_trigger_alerts(mock_db)

        mock_db.commit.assert_not_called()
        assert alert.trigger_count == 0

    @pytest.mark.asyncio
    async def test_alert_triggered_below(self, mock_db):
        """BELOW 조건 충족 시 이메일+푸시 발송하고 trigger_count를 증가시킨다."""
        alert = _make_alert(target_rate=1300.0, direction="BELOW", max_trigger_count=3)
        mock_db.execute.return_value.all.return_value = [_make_db_row(alert, email="u@test.com")]

        with (
            patch(_FETCH_RATE, new_callable=AsyncMock, return_value=1280.0),
            patch(_SEND_EMAIL, new_callable=AsyncMock),
            patch(_SEND_PUSH, new_callable=AsyncMock),
            patch(_SAVE_HIST, new_callable=AsyncMock),
        ):
            from app.services.exchange_rate_alert_service import check_and_trigger_alerts

            await check_and_trigger_alerts(mock_db)

        mock_db.commit.assert_called_once()
        assert alert.trigger_count == 1
        assert alert.is_active is True  # max_trigger_count=3 이므로 유지

    @pytest.mark.asyncio
    async def test_alert_deactivated_when_max_reached(self, mock_db):
        """trigger_count가 max에 도달하면 is_active를 False로 변경한다."""
        alert = _make_alert(target_rate=1300.0, direction="BELOW", trigger_count=0, max_trigger_count=1)
        mock_db.execute.return_value.all.return_value = [_make_db_row(alert)]

        with (
            patch(_FETCH_RATE, new_callable=AsyncMock, return_value=1280.0),
            patch(_SEND_EMAIL, new_callable=AsyncMock),
            patch(_SEND_PUSH, new_callable=AsyncMock),
            patch(_SAVE_HIST, new_callable=AsyncMock),
        ):
            from app.services.exchange_rate_alert_service import check_and_trigger_alerts

            await check_and_trigger_alerts(mock_db)

        assert alert.trigger_count == 1
        assert alert.is_active is False

    @pytest.mark.asyncio
    async def test_alert_triggered_above(self, mock_db):
        """ABOVE 조건 충족 시 트리거된다."""
        alert = _make_alert(target_rate=1400.0, direction="ABOVE", max_trigger_count=2)
        mock_db.execute.return_value.all.return_value = [_make_db_row(alert)]

        with (
            patch(_FETCH_RATE, new_callable=AsyncMock, return_value=1420.0),
            patch(_SEND_EMAIL, new_callable=AsyncMock),
            patch(_SEND_PUSH, new_callable=AsyncMock),
            patch(_SAVE_HIST, new_callable=AsyncMock),
        ):
            from app.services.exchange_rate_alert_service import check_and_trigger_alerts

            await check_and_trigger_alerts(mock_db)

        assert alert.trigger_count == 1

    @pytest.mark.asyncio
    async def test_email_failure_skips_alert(self, mock_db):
        """이메일 발송 실패 시 해당 알림을 건너뛰고 commit하지 않는다."""
        alert = _make_alert(target_rate=1300.0, direction="BELOW")
        mock_db.execute.return_value.all.return_value = [_make_db_row(alert)]

        with (
            patch(_FETCH_RATE, new_callable=AsyncMock, return_value=1280.0),
            patch(_SEND_EMAIL, new_callable=AsyncMock, return_value=False),
        ):
            from app.services.exchange_rate_alert_service import check_and_trigger_alerts

            await check_and_trigger_alerts(mock_db)

        mock_db.commit.assert_not_called()
        assert alert.trigger_count == 0
