"""_position_queries 단위 테스트 — fetch_manual_positions DB 쿼리 헬퍼 검증."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_fetch_manual_positions_returns_matching_rows(mock_db):
    from app.services._position_queries import fetch_manual_positions

    pos = SimpleNamespace(snapshot_id=None, account_id=uuid4())
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = [pos]
    mock_db.execute.return_value = execute_result

    result = await fetch_manual_positions(uuid4(), mock_db)

    assert result == [pos]
    mock_db.execute.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_manual_positions_returns_empty_list_when_no_rows(mock_db):
    from app.services._position_queries import fetch_manual_positions

    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = execute_result

    result = await fetch_manual_positions(uuid4(), mock_db)

    assert result == []


@pytest.mark.asyncio
async def test_fetch_manual_positions_returns_multiple_rows(mock_db):
    from app.services._position_queries import fetch_manual_positions

    positions = [SimpleNamespace(snapshot_id=None) for _ in range(3)]
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = positions
    mock_db.execute.return_value = execute_result

    result = await fetch_manual_positions(uuid4(), mock_db)

    assert len(result) == 3
