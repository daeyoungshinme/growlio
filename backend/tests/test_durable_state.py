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


class TestCommitFalse:
    """savepoint 안에서 쓰는 경로 — commit=False면 execute/delete만 하고 커밋은 호출부에 위임."""

    @pytest.mark.asyncio
    async def test_get_expired_row_deletes_without_commit(self, mock_db):
        row = AppState(key="k", value="v", expires_at=datetime.now(UTC) - timedelta(seconds=1))
        mock_db.get = AsyncMock(return_value=row)
        mock_db.delete = AsyncMock()
        assert await get_durable(mock_db, "k", commit=False) is None
        mock_db.delete.assert_awaited_once_with(row)
        mock_db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_set_and_delete_without_commit(self, mock_db):
        await set_durable(mock_db, "k", "v", ttl=60, commit=False)
        await delete_durable(mock_db, "k", commit=False)
        assert mock_db.execute.await_count == 2
        mock_db.commit.assert_not_called()


class TestPurgeExpiredDurable:
    @pytest.mark.asyncio
    async def test_deletes_only_expired_rows_and_commits(self, mock_db):
        from app.utils.durable_state import purge_expired_durable

        result = AsyncMock()
        result.rowcount = 3
        mock_db.execute = AsyncMock(return_value=result)

        removed = await purge_expired_durable(mock_db)

        assert removed == 3
        sql = str(mock_db.execute.call_args.args[0])
        assert "DELETE FROM app_state" in sql
        assert "expires_at <=" in sql
        mock_db.commit.assert_awaited_once()


class TestClaimDurable:
    """원자적 선점 — 배포가 겹친 두 인스턴스 중 하나만 통과해야 한다 (plans/61 C1)."""

    @staticmethod
    def _db(returning):
        from unittest.mock import MagicMock

        db = AsyncMock()
        insert_result = MagicMock()
        insert_result.scalar_one_or_none.return_value = returning
        db.execute = AsyncMock(side_effect=[MagicMock(), insert_result])
        return db

    @pytest.mark.asyncio
    async def test_first_claim_wins(self):
        from app.utils.durable_state import claim_durable

        db = self._db(returning="k")
        assert await claim_durable(db, "k", 60) is True
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_conflict_loses(self):
        from app.utils.durable_state import claim_durable

        db = self._db(returning=None)
        assert await claim_durable(db, "k", 60) is False

    @pytest.mark.asyncio
    async def test_sql_is_insert_on_conflict_do_nothing_returning(self):
        """read-then-write가 아니라 PK 충돌을 DB가 판정하는 단일 문장인지 고정한다."""
        from sqlalchemy.dialects import postgresql

        from app.utils.durable_state import claim_durable

        db = self._db(returning="k")
        await claim_durable(db, "auto:alert:2026-10-20", 60)
        purge_stmt, insert_stmt = (call.args[0] for call in db.execute.call_args_list)

        dialect = postgresql.dialect()
        insert_sql = str(insert_stmt.compile(dialect=dialect))
        assert insert_sql.startswith("INSERT INTO app_state")
        assert "ON CONFLICT (key) DO NOTHING RETURNING app_state.key" in insert_sql
        purge_sql = str(purge_stmt.compile(dialect=dialect))
        assert purge_sql.startswith("DELETE FROM app_state WHERE app_state.key =")
        assert "app_state.expires_at IS NOT NULL" in purge_sql
