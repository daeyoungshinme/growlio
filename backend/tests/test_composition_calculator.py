"""composition_calculator.py 단위 테스트."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.composition_calculator import (
    build_asset_totals,
    fetch_position_maps,
    get_latest_snapshot_rows,
    get_no_snap_accounts,
)


def _make_account(
    asset_type="BANK_ACCOUNT",
    is_active=True,
    include_in_total=True,
    manual_amount=None,
    deposit_krw=0,
    deposit_usd=0,
    real_estate_details=None,
):
    acc = MagicMock()
    acc.id = uuid.uuid4()
    acc.asset_type = asset_type
    acc.is_active = is_active
    acc.include_in_total = include_in_total
    acc.manual_amount = manual_amount
    acc.deposit_krw = deposit_krw
    acc.deposit_usd = deposit_usd
    acc.real_estate_details = real_estate_details
    return acc


def _make_snapshot(amount_krw=1000000.0, invested_amount=None):
    snap = MagicMock()
    snap.id = uuid.uuid4()
    snap.amount_krw = amount_krw
    snap.invested_amount = invested_amount
    return snap


class TestGetLatestSnapshotRows:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_rows(self, mock_db):
        execute_result = MagicMock()
        execute_result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=execute_result)

        rows, snapped_ids = await get_latest_snapshot_rows(uuid.uuid4(), mock_db)

        assert rows == []
        assert snapped_ids == set()

    @pytest.mark.asyncio
    async def test_returns_rows_and_snapped_ids(self, mock_db):
        acc = _make_account()
        snap = _make_snapshot()

        execute_result = MagicMock()
        execute_result.all.return_value = [(snap, acc)]
        mock_db.execute = AsyncMock(return_value=execute_result)

        rows, snapped_ids = await get_latest_snapshot_rows(uuid.uuid4(), mock_db)

        assert len(rows) == 1
        assert acc.id in snapped_ids


class TestGetNoSnapAccounts:
    @pytest.mark.asyncio
    async def test_excludes_already_snapped_accounts(self, mock_db):
        execute_result = MagicMock()
        execute_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=execute_result)

        result = await get_no_snap_accounts(uuid.uuid4(), mock_db, {uuid.uuid4()})
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_accounts_with_manual_amount(self, mock_db):
        acc = _make_account(manual_amount=500000.0)
        execute_result = MagicMock()
        execute_result.scalars.return_value.all.return_value = [acc]
        mock_db.execute = AsyncMock(return_value=execute_result)

        result = await get_no_snap_accounts(uuid.uuid4(), mock_db, set())
        assert len(result) == 1


class TestFetchPositionMaps:
    @pytest.mark.asyncio
    async def test_empty_inputs_return_empty_maps(self, mock_db):
        snap_pos, cur_pos = await fetch_position_maps([], [], mock_db)
        assert snap_pos == {}
        assert cur_pos == {}

    @pytest.mark.asyncio
    async def test_groups_positions_by_snapshot_id(self, mock_db):
        snap_id = uuid.uuid4()
        pos = MagicMock()
        pos.snapshot_id = snap_id
        pos.account_id = uuid.uuid4()

        execute_result = MagicMock()
        execute_result.scalars.return_value.all.return_value = [pos]
        mock_db.execute = AsyncMock(return_value=execute_result)

        snap_pos, _ = await fetch_position_maps([snap_id], [], mock_db)
        assert snap_id in snap_pos
        assert len(snap_pos[snap_id]) == 1


class TestBuildAssetTotals:
    @pytest.mark.asyncio
    async def test_returns_zeros_for_empty_accounts(self, mock_db):
        with (
            patch("app.services.composition_calculator.fetch_usd_krw", AsyncMock(return_value=1300.0)),
            patch("app.services.composition_calculator.get_latest_snapshot_rows", AsyncMock(return_value=([], set()))),
            patch("app.services.composition_calculator.get_no_snap_accounts", AsyncMock(return_value=[])),
            patch("app.services.composition_calculator._fetch_snapshot_positions", AsyncMock(return_value={})),
            patch("app.services.composition_calculator._fetch_current_positions", AsyncMock(return_value={})),
        ):
            total, invested, stock, by_type = await build_asset_totals(uuid.uuid4(), mock_db)

        assert total == pytest.approx(0.0)
        assert invested == pytest.approx(0.0)
        assert stock == pytest.approx(0.0)
        assert by_type == {}

    @pytest.mark.asyncio
    async def test_aggregates_bank_account(self, mock_db):
        acc = _make_account(asset_type="BANK_ACCOUNT")
        snap = _make_snapshot(amount_krw=2000000.0)

        with (
            patch("app.services.composition_calculator.fetch_usd_krw", AsyncMock(return_value=1300.0)),
            patch(
                "app.services.composition_calculator.get_latest_snapshot_rows",
                AsyncMock(return_value=([(snap, acc)], {acc.id})),
            ),
            patch("app.services.composition_calculator.get_no_snap_accounts", AsyncMock(return_value=[])),
            patch("app.services.composition_calculator._fetch_snapshot_positions", AsyncMock(return_value={})),
            patch("app.services.composition_calculator._fetch_current_positions", AsyncMock(return_value={})),
        ):
            total, invested, stock, by_type = await build_asset_totals(uuid.uuid4(), mock_db)

        assert total == pytest.approx(2000000.0)
        assert by_type.get("BANK_ACCOUNT", 0) == pytest.approx(2000000.0)

    @pytest.mark.asyncio
    async def test_exclude_from_total_skipped(self, mock_db):
        acc = _make_account(asset_type="BANK_ACCOUNT", include_in_total=False)
        snap = _make_snapshot(amount_krw=1000000.0)

        with (
            patch("app.services.composition_calculator.fetch_usd_krw", AsyncMock(return_value=1300.0)),
            patch(
                "app.services.composition_calculator.get_latest_snapshot_rows",
                AsyncMock(return_value=([(snap, acc)], {acc.id})),
            ),
            patch("app.services.composition_calculator.get_no_snap_accounts", AsyncMock(return_value=[])),
            patch("app.services.composition_calculator._fetch_snapshot_positions", AsyncMock(return_value={})),
            patch("app.services.composition_calculator._fetch_current_positions", AsyncMock(return_value={})),
        ):
            total, _, _, _ = await build_asset_totals(uuid.uuid4(), mock_db)

        assert total == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_stock_account_snapshot_path(self, mock_db):
        acc = _make_account(asset_type="STOCK_KIS", include_in_total=True)
        snap = _make_snapshot(amount_krw=3000000.0, invested_amount=2500000.0)
        snap_id = snap.id

        # Position inside the snapshot — non-zero eval_value
        pos = MagicMock()
        pos.current_price = 50000.0
        pos.qty = 10.0
        pos.avg_price = 45000.0

        with (
            patch("app.services.composition_calculator.fetch_usd_krw", AsyncMock(return_value=1300.0)),
            patch(
                "app.services.composition_calculator.get_latest_snapshot_rows",
                AsyncMock(return_value=([(snap, acc)], {acc.id})),
            ),
            patch("app.services.composition_calculator.get_no_snap_accounts", AsyncMock(return_value=[])),
            patch(
                "app.services.composition_calculator._fetch_snapshot_positions",
                AsyncMock(return_value={snap_id: [pos]}),
            ),
            patch("app.services.composition_calculator._fetch_current_positions", AsyncMock(return_value={})),
        ):
            total, invested, stock, by_type = await build_asset_totals(uuid.uuid4(), mock_db)

        assert total == pytest.approx(3000000.0)
        assert invested == pytest.approx(2500000.0)
        assert "STOCK_KIS" in by_type

    @pytest.mark.asyncio
    async def test_no_snap_stock_account(self, mock_db):
        acc = _make_account(
            asset_type="STOCK_KIS",
            include_in_total=True,
            deposit_krw=500000,
            deposit_usd=0,
        )
        acc_id = acc.id

        pos = MagicMock()
        pos.current_price = 60000.0
        pos.qty = 5.0
        pos.avg_price = 50000.0

        with (
            patch("app.services.composition_calculator.fetch_usd_krw", AsyncMock(return_value=1300.0)),
            patch("app.services.composition_calculator.get_latest_snapshot_rows", AsyncMock(return_value=([], set()))),
            patch("app.services.composition_calculator.get_no_snap_accounts", AsyncMock(return_value=[acc])),
            patch("app.services.composition_calculator._fetch_snapshot_positions", AsyncMock(return_value={})),
            patch(
                "app.services.composition_calculator._fetch_current_positions",
                AsyncMock(return_value={acc_id: [pos]}),
            ),
        ):
            total, invested, stock, by_type = await build_asset_totals(uuid.uuid4(), mock_db)

        assert total > 0.0
        assert "STOCK_KIS" in by_type

    @pytest.mark.asyncio
    async def test_no_snap_real_estate_account(self, mock_db):
        acc = _make_account(
            asset_type="REAL_ESTATE",
            include_in_total=True,
            manual_amount=500000000.0,
            real_estate_details={"mortgage_balance_krw": 200000000},
        )

        with (
            patch("app.services.composition_calculator.fetch_usd_krw", AsyncMock(return_value=1300.0)),
            patch("app.services.composition_calculator.get_latest_snapshot_rows", AsyncMock(return_value=([], set()))),
            patch("app.services.composition_calculator.get_no_snap_accounts", AsyncMock(return_value=[acc])),
            patch("app.services.composition_calculator._fetch_snapshot_positions", AsyncMock(return_value={})),
            patch("app.services.composition_calculator._fetch_current_positions", AsyncMock(return_value={})),
        ):
            total, _, _, by_type = await build_asset_totals(uuid.uuid4(), mock_db)

        assert total == pytest.approx(300000000.0)
        assert by_type.get("REAL_ESTATE", 0) == pytest.approx(300000000.0)

    @pytest.mark.asyncio
    async def test_no_snap_other_account_uses_manual_amount(self, mock_db):
        acc = _make_account(
            asset_type="OTHER",
            include_in_total=True,
            manual_amount=1000000.0,
        )

        with (
            patch("app.services.composition_calculator.fetch_usd_krw", AsyncMock(return_value=1300.0)),
            patch("app.services.composition_calculator.get_latest_snapshot_rows", AsyncMock(return_value=([], set()))),
            patch("app.services.composition_calculator.get_no_snap_accounts", AsyncMock(return_value=[acc])),
            patch("app.services.composition_calculator._fetch_snapshot_positions", AsyncMock(return_value={})),
            patch("app.services.composition_calculator._fetch_current_positions", AsyncMock(return_value={})),
        ):
            total, _, _, by_type = await build_asset_totals(uuid.uuid4(), mock_db)

        assert total == pytest.approx(1000000.0)
        assert by_type.get("OTHER", 0) == pytest.approx(1000000.0)
