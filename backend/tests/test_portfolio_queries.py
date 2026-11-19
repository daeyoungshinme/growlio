"""services/portfolio/_portfolio_queries.py 단위 테스트."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.portfolio._portfolio_queries import (
    alert_drift_thresholds,
    get_active_alerts_by_portfolio,
    get_last_rebalanced_at,
)


def _alert(portfolio_id, threshold, relative=None):
    return SimpleNamespace(
        portfolio_id=portfolio_id, threshold_pct=Decimal(str(threshold)), relative_threshold_pct=relative
    )


class TestAlertDriftThresholds:
    def test_defaults_when_no_alerts(self):
        assert alert_drift_thresholds([]) == (5.0, None)

    def test_per_account_alerts_use_min_of_each(self):
        """PER_ACCOUNT 스코프에 기준이 다른 알림이 여럿이면 각각 최솟값(가장 먼저 트리거되는 값)."""
        pid = uuid.uuid4()
        alerts = [_alert(pid, 8.0, Decimal("30")), _alert(pid, 3.0), _alert(pid, 5.0, Decimal("25"))]
        assert alert_drift_thresholds(alerts) == (3.0, 25.0)

    def test_relative_off_when_no_alert_sets_it(self):
        pid = uuid.uuid4()
        assert alert_drift_thresholds([_alert(pid, 4.0)]) == (4.0, None)


class TestGetActiveAlertsByPortfolio:
    @pytest.mark.asyncio
    async def test_groups_by_portfolio(self, mock_db):
        a, b = uuid.uuid4(), uuid.uuid4()
        rows = [_alert(a, 3.0), _alert(b, 8.0), _alert(a, 5.0)]
        mock_db.execute.return_value.scalars.return_value.all.return_value = rows

        result = await get_active_alerts_by_portfolio(mock_db, uuid.uuid4())

        assert [x.threshold_pct for x in result[str(a)]] == [Decimal("3.0"), Decimal("5.0")]
        assert len(result[str(b)]) == 1

    @pytest.mark.asyncio
    async def test_empty(self, mock_db):
        mock_db.execute.return_value.scalars.return_value.all.return_value = []
        assert await get_active_alerts_by_portfolio(mock_db, uuid.uuid4()) == {}


class TestGetLastRebalancedAt:
    @pytest.mark.asyncio
    async def test_maps_portfolio_to_latest(self, mock_db):
        pid = uuid.uuid4()
        at = datetime(2026, 11, 1, tzinfo=UTC)
        mock_db.execute.return_value.all.return_value = [(pid, at)]

        assert await get_last_rebalanced_at(mock_db, uuid.uuid4()) == {str(pid): at}

    @pytest.mark.asyncio
    async def test_query_excludes_failed_and_deleted_portfolios(self, mock_db):
        mock_db.execute.return_value.all.return_value = []
        await get_last_rebalanced_at(mock_db, uuid.uuid4())

        sql = str(mock_db.execute.call_args.args[0])
        assert "total_success >" in sql
        assert "portfolio_id IS NOT NULL" in sql
