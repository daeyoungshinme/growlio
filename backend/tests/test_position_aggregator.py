"""services/position_aggregator.py 단위 테스트."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.position_aggregator import query_latest_position_map


def _snapshot(snapshot_id):
    return SimpleNamespace(id=snapshot_id)


def _account(account_id):
    return SimpleNamespace(id=account_id)


def _position(ticker, market, value_krw, name=None):
    return SimpleNamespace(ticker=ticker, market=market, value_krw=value_krw, name=name)


def _queue_execute_results(mock_db, *results):
    """mock_db.execute()가 호출될 때마다 순서대로 다른 결과를 반환하도록 설정."""
    mock_db.execute = AsyncMock(side_effect=list(results))


class TestQueryLatestPositionMap:
    @pytest.mark.asyncio
    async def test_aggregates_by_ticker_and_market(self, mock_db, make_user_id):
        snap_id = uuid.uuid4()
        account_id = uuid.uuid4()

        snap_account_result = MagicMock()
        snap_account_result.all.return_value = [(_snapshot(snap_id), _account(account_id))]

        position_result = MagicMock()
        position_result.scalars.return_value.all.return_value = [
            _position("005930", "KOSPI", 500_000.0),
            _position("005930", "KOSPI", 250_000.0),
            _position("AAPL", "NASDAQ", 1_000_000.0),
        ]

        _queue_execute_results(mock_db, snap_account_result, position_result)

        result = await query_latest_position_map(make_user_id, mock_db)

        assert result["005930-KOSPI"]["value_krw"] == 750_000.0
        assert result["AAPL-NASDAQ"]["value_krw"] == 1_000_000.0
        assert "name" not in result["005930-KOSPI"]

    @pytest.mark.asyncio
    async def test_include_name_uses_first_seen_position_name(self, mock_db, make_user_id):
        snap_id = uuid.uuid4()
        account_id = uuid.uuid4()

        snap_account_result = MagicMock()
        snap_account_result.all.return_value = [(_snapshot(snap_id), _account(account_id))]

        position_result = MagicMock()
        position_result.scalars.return_value.all.return_value = [
            _position("005930", "KOSPI", 500_000.0, name="삼성전자"),
        ]

        _queue_execute_results(mock_db, snap_account_result, position_result)

        result = await query_latest_position_map(make_user_id, mock_db, include_name=True)

        assert result["005930-KOSPI"]["name"] == "삼성전자"

    @pytest.mark.asyncio
    async def test_no_snapshots_skips_position_query(self, mock_db, make_user_id):
        snap_account_result = MagicMock()
        snap_account_result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=snap_account_result)

        result = await query_latest_position_map(make_user_id, mock_db)

        assert result == {}
        mock_db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_account_ids_filter_is_applied_to_query(self, mock_db, make_user_id):
        account_ids = [uuid.uuid4()]
        snap_account_result = MagicMock()
        snap_account_result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=snap_account_result)

        await query_latest_position_map(make_user_id, mock_db, account_ids=account_ids)

        called_stmt = mock_db.execute.call_args[0][0]
        assert "id IN" in str(called_stmt).replace("\n", " ")
