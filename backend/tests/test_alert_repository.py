"""services/alert_repository.py 단위 테스트."""

from __future__ import annotations

import uuid

import pytest

from app.services.alert_repository import save_alert_history


class TestSaveAlertHistory:
    @pytest.mark.asyncio
    async def test_adds_alert_history_to_session(self, mock_db):
        user_id = uuid.uuid4()
        await save_alert_history(
            db=mock_db,
            user_id=user_id,
            alert_type="STOCK_PRICE",
            message="삼성전자가 목표가에 도달했습니다.",
        )
        mock_db.add.assert_called_once()
        added = mock_db.add.call_args[0][0]
        assert added.user_id == user_id
        assert added.alert_type == "STOCK_PRICE"
        assert added.message == "삼성전자가 목표가에 도달했습니다."

    @pytest.mark.asyncio
    async def test_different_alert_types(self, mock_db):
        user_id = uuid.uuid4()
        for alert_type in ("EXCHANGE_RATE", "REBALANCING", "GOAL_ACHIEVEMENT"):
            mock_db.reset_mock()
            await save_alert_history(
                db=mock_db,
                user_id=user_id,
                alert_type=alert_type,
                message="알림 메시지",
            )
            mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_does_not_call_commit(self, mock_db):
        await save_alert_history(
            db=mock_db,
            user_id=uuid.uuid4(),
            alert_type="TEST",
            message="테스트",
        )
        mock_db.commit.assert_not_called()
