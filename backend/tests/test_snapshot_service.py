"""snapshot_service.py 단위 테스트."""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


class TestSyncSnapshotPositions:
    @pytest.mark.asyncio
    async def test_sync_positions_calls_db_add_for_each(self, mock_db, override_settings):
        from app.services.snapshot_service import sync_snapshot_positions

        pos1 = SimpleNamespace(
            ticker="AAPL", name="Apple", market="NASDAQ",
            qty=10, avg_price=150_000.0, avg_price_usd=100.0,
            current_price=185_000.0, value_krw=1_850_000.0,
            currency="USD", usd_rate=1350.0,
        )
        pos2 = SimpleNamespace(
            ticker="TSLA", name="Tesla", market="NASDAQ",
            qty=5, avg_price=200_000.0, avg_price_usd=None,
            current_price=250_000.0, value_krw=1_250_000.0,
            currency="USD", usd_rate=1350.0,
        )

        await sync_snapshot_positions(
            mock_db,
            snapshot_id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            positions=[pos1, pos2],
        )

        assert mock_db.add.call_count == 2

    @pytest.mark.asyncio
    async def test_empty_positions_no_adds(self, mock_db, override_settings):
        from app.services.snapshot_service import sync_snapshot_positions

        await sync_snapshot_positions(
            mock_db,
            snapshot_id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            positions=[],
        )

        mock_db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_deletes_existing_before_insert(self, mock_db, override_settings):
        from app.services.snapshot_service import sync_snapshot_positions

        await sync_snapshot_positions(
            mock_db,
            snapshot_id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            positions=[],
        )

        # execute called twice: one for SELECT FOR UPDATE, one for DELETE
        assert mock_db.execute.call_count == 2
