"""services/_portfolio_queries.py 단위 테스트."""

from __future__ import annotations

import uuid

import pytest

from app.services._portfolio_queries import get_active_alert_thresholds


class TestGetActiveAlertThresholds:
    @pytest.mark.asyncio
    async def test_returns_min_threshold_for_per_account_scope(self, mock_db):
        """PER_ACCOUNT 스코프 포트폴리오에 threshold가 다른 활성 알림이 여럿이면 최솟값을 반환한다."""
        portfolio_id = uuid.uuid4()
        user_id = uuid.uuid4()
        mock_db.execute.return_value.all.return_value = [(portfolio_id, 3.0)]

        result = await get_active_alert_thresholds(mock_db, user_id)

        assert result == {str(portfolio_id): 3.0}

    @pytest.mark.asyncio
    async def test_returns_empty_dict_when_no_active_alerts(self, mock_db):
        mock_db.execute.return_value.all.return_value = []

        result = await get_active_alert_thresholds(mock_db, uuid.uuid4())

        assert result == {}

    @pytest.mark.asyncio
    async def test_multiple_portfolios_each_keep_their_own_min(self, mock_db):
        portfolio_a = uuid.uuid4()
        portfolio_b = uuid.uuid4()
        user_id = uuid.uuid4()
        mock_db.execute.return_value.all.return_value = [
            (portfolio_a, 3.0),
            (portfolio_b, 8.0),
        ]

        result = await get_active_alert_thresholds(mock_db, user_id)

        assert result == {str(portfolio_a): 3.0, str(portfolio_b): 8.0}
