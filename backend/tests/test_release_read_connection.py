"""plans/125 — 외부 I/O 전 커넥션 반납 헬퍼(`release_read_connection`)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.database import release_read_connection


def _session(*, new=(), dirty=(), deleted=(), in_tx=True) -> MagicMock:
    db = MagicMock()
    db.new, db.dirty, db.deleted = set(new), set(dirty), set(deleted)
    db.in_transaction.return_value = in_tx
    db.commit = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_commits_clean_read_transaction():
    db = _session()
    await release_read_connection(db)
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["new", "dirty", "deleted"])
async def test_leaves_pending_changes_alone(field):
    db = _session(**{field: [object()]})
    await release_read_connection(db)
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_transaction_is_noop():
    db = _session(in_tx=False)
    await release_read_connection(db)
    db.commit.assert_not_awaited()
