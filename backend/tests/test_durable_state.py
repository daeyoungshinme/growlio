"""durable_state.py 단위 테스트 — Postgres 기반 key-value durable state (구 Redis dedup/last-value 대체)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from app.models.app_state import AppState
from app.utils.durable_state import delete_durable, get_durable, set_durable


class TestGetDurable:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_row(self, mock_db):
        mock_db.get = AsyncMock(return_value=None)
        assert await get_durable(mock_db, "some:key") is None

    @pytest.mark.asyncio
    async def test_returns_value_when_row_exists_and_not_expired(self, mock_db):
        row = AppState(key="some:key", value="hello", expires_at=None)
        mock_db.get = AsyncMock(return_value=row)
        assert await get_durable(mock_db, "some:key") == "hello"

    @pytest.mark.asyncio
    async def test_returns_value_when_expires_at_in_future(self, mock_db):
        row = AppState(key="some:key", value="hello", expires_at=datetime.now(UTC) + timedelta(hours=1))
        mock_db.get = AsyncMock(return_value=row)
        assert await get_durable(mock_db, "some:key") == "hello"

    @pytest.mark.asyncio
    async def test_returns_none_and_deletes_when_expired(self, mock_db):
        row = AppState(key="some:key", value="stale", expires_at=datetime.now(UTC) - timedelta(seconds=1))
        mock_db.get = AsyncMock(return_value=row)
        mock_db.delete = AsyncMock()
        result = await get_durable(mock_db, "some:key")
        assert result is None
        mock_db.delete.assert_called_once_with(row)
        mock_db.commit.assert_called_once()


class TestSetDurable:
    @pytest.mark.asyncio
    async def test_calls_execute_and_commit(self, mock_db):
        await set_durable(mock_db, "some:key", "value1", ttl=60)
        mock_db.execute.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_ttl_means_no_expiry(self, mock_db):
        await set_durable(mock_db, "some:key", "value1")
        mock_db.execute.assert_called_once()
        mock_db.commit.assert_called_once()


class TestDeleteDurable:
    @pytest.mark.asyncio
    async def test_calls_execute_and_commit(self, mock_db):
        await delete_durable(mock_db, "some:key")
        mock_db.execute.assert_called_once()
        mock_db.commit.assert_called_once()
