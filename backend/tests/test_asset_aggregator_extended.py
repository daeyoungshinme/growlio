"""asset_aggregator.py 추가 커버리지 테스트 (_get_latest_snapshot_rows, _get_no_snap_accounts,
_fetch_position_maps, _get_scalar_init_data, get_dashboard_summary, _calc_returns 등)."""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── _calc_returns (순수 함수) ─────────────────────────────────

class TestCalcReturns:
    def test_no_base_returns_none(self, override_settings):
        from app.services.asset_aggregator import _calc_returns
        ann, cum = _calc_returns(1_000_000, 0.0, date(2024, 1, 1))
        assert ann is None
        assert cum is None

    def test_no_first_date_returns_none(self, override_settings):
        from app.services.asset_aggregator import _calc_returns
        ann, cum = _calc_returns(1_100_000, 1_000_000, None)
        assert ann is None
        assert cum is None

    def test_first_date_in_future_returns_none(self, override_settings):
        from app.services.asset_aggregator import _calc_returns
        future = date.today() + timedelta(days=30)
        ann, cum = _calc_returns(1_100_000, 1_000_000, future)
        assert ann is None
        assert cum is None

    def test_first_date_today_returns_none(self, override_settings):
        from app.services.asset_aggregator import _calc_returns
        ann, cum = _calc_returns(1_100_000, 1_000_000, date.today())
        assert ann is None
        assert cum is None

    def test_positive_return(self, override_settings):
        from app.services.asset_aggregator import _calc_returns
        one_year_ago = date.today().replace(year=date.today().year - 1)
        ann, cum = _calc_returns(1_100_000, 1_000_000, one_year_ago)
        assert ann is not None
        assert cum is not None
        assert cum > 0

    def test_negative_return(self, override_settings):
        from app.services.asset_aggregator import _calc_returns
        one_year_ago = date.today().replace(year=date.today().year - 1)
        ann, cum = _calc_returns(900_000, 1_000_000, one_year_ago)
        assert ann is not None
        assert cum is not None
        assert cum < 0


# ── _get_latest_snapshot_rows (DB mock) ──────────────────────

class TestGetLatestSnapshotRows:
    @pytest.mark.asyncio
    async def test_empty_returns_empty_lists(self, mock_db, override_settings):
        from app.services.asset_aggregator import _get_latest_snapshot_rows

        result = MagicMock()
        result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=result)

        rows, snapped_ids = await _get_latest_snapshot_rows(uuid.uuid4(), mock_db)

        assert rows == []
        assert snapped_ids == set()

    @pytest.mark.asyncio
    async def test_with_snapshot_rows(self, mock_db, override_settings):
        from app.services.asset_aggregator import _get_latest_snapshot_rows

        snap = SimpleNamespace(id=uuid.uuid4(), account_id=uuid.uuid4())
        acc = SimpleNamespace(id=snap.account_id, is_active=True)

        result = MagicMock()
        result.all.return_value = [(snap, acc)]
        mock_db.execute = AsyncMock(return_value=result)

        rows, snapped_ids = await _get_latest_snapshot_rows(uuid.uuid4(), mock_db)

        assert len(rows) == 1
        assert acc.id in snapped_ids


# ── _get_no_snap_accounts (DB mock) ──────────────────────────

class TestGetNoSnapAccounts:
    @pytest.mark.asyncio
    async def test_returns_accounts_not_in_snapped_ids(self, mock_db, override_settings):
        from app.services.asset_aggregator import _get_no_snap_accounts

        acc = SimpleNamespace(id=uuid.uuid4(), manual_amount=1_000_000)
        result = MagicMock()
        result.scalars.return_value.all.return_value = [acc]
        mock_db.execute = AsyncMock(return_value=result)

        accounts = await _get_no_snap_accounts(uuid.uuid4(), mock_db, set())

        assert len(accounts) == 1

    @pytest.mark.asyncio
    async def test_empty_when_all_snagged(self, mock_db, override_settings):
        from app.services.asset_aggregator import _get_no_snap_accounts

        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=result)

        accounts = await _get_no_snap_accounts(uuid.uuid4(), mock_db, {uuid.uuid4()})

        assert accounts == []


# ── _fetch_position_maps (DB mock) ───────────────────────────

class TestFetchPositionMaps:
    @pytest.mark.asyncio
    async def test_empty_ids_returns_empty_dicts(self, mock_db, override_settings):
        from app.services.asset_aggregator import _fetch_position_maps

        snap_map, cur_map = await _fetch_position_maps([], [], mock_db)

        assert snap_map == {}
        assert cur_map == {}
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_snap_positions_fetched_when_snap_ids(self, mock_db, override_settings):
        from app.services.asset_aggregator import _fetch_position_maps

        snap_id = uuid.uuid4()
        pos = SimpleNamespace(snapshot_id=snap_id, account_id=None, ticker="AAPL")

        result = MagicMock()
        result.scalars.return_value.all.return_value = [pos]
        mock_db.execute = AsyncMock(return_value=result)

        snap_map, cur_map = await _fetch_position_maps([snap_id], [], mock_db)

        assert snap_id in snap_map
        assert cur_map == {}

    @pytest.mark.asyncio
    async def test_current_positions_fetched_when_acc_ids(self, mock_db, override_settings):
        from app.services.asset_aggregator import _fetch_position_maps

        acc_id = uuid.uuid4()
        pos = SimpleNamespace(account_id=acc_id, snapshot_id=None, ticker="TSLA")

        result = MagicMock()
        result.scalars.return_value.all.return_value = [pos]
        mock_db.execute = AsyncMock(return_value=result)

        snap_map, cur_map = await _fetch_position_maps([], [acc_id], mock_db)

        assert snap_map == {}
        assert acc_id in cur_map


# ── _get_scalar_init_data (DB mock) ──────────────────────────

class TestGetScalarInitData:
    @pytest.mark.asyncio
    async def test_no_data_returns_none_and_zero(self, mock_db, override_settings):
        from app.services.asset_aggregator import _get_scalar_init_data

        result = MagicMock()
        result.first.return_value = None
        mock_db.execute = AsyncMock(return_value=result)

        first_snap, net_deposits = await _get_scalar_init_data(uuid.uuid4(), mock_db)

        assert first_snap is None
        assert net_deposits == 0.0

    @pytest.mark.asyncio
    async def test_with_data_returns_values(self, mock_db, override_settings):
        from app.services.asset_aggregator import _get_scalar_init_data

        row = SimpleNamespace(first_date=date(2023, 1, 1), net=5_000_000.0)
        result = MagicMock()
        result.first.return_value = row
        mock_db.execute = AsyncMock(return_value=result)

        first_snap, net_deposits = await _get_scalar_init_data(uuid.uuid4(), mock_db)

        assert first_snap == date(2023, 1, 1)
        assert net_deposits == 5_000_000.0


# ── _get_first_snap_date (DB mock) ───────────────────────────

class TestGetFirstSnapDate:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_snapshots(self, mock_db, override_settings):
        from app.services.asset_aggregator import _get_first_snap_date

        result = MagicMock()
        result.scalar.return_value = None
        mock_db.execute = AsyncMock(return_value=result)

        snap_date = await _get_first_snap_date(uuid.uuid4(), mock_db)

        assert snap_date is None

    @pytest.mark.asyncio
    async def test_returns_date_when_snapshots_exist(self, mock_db, override_settings):
        from app.services.asset_aggregator import _get_first_snap_date

        result = MagicMock()
        result.scalar.return_value = date(2023, 6, 1)
        mock_db.execute = AsyncMock(return_value=result)

        snap_date = await _get_first_snap_date(uuid.uuid4(), mock_db)

        assert snap_date == date(2023, 6, 1)


# ── _get_monthly_trend (DB mock) ─────────────────────────────

class TestGetMonthlyTrend:
    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_data(self, mock_db, override_settings):
        from app.services.asset_aggregator import _get_monthly_trend

        result = MagicMock()
        result.__iter__ = MagicMock(return_value=iter([]))
        mock_db.execute = AsyncMock(return_value=result)

        trend = await _get_monthly_trend(uuid.uuid4(), mock_db)

        assert trend == []

    @pytest.mark.asyncio
    async def test_redis_cache_hit(self, mock_db, override_settings):
        import json
        from app.services.asset_aggregator import _get_monthly_trend

        cached = [{"month": "2024-01-01", "total_krw": 10_000_000.0}]
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=json.dumps(cached).encode())

        trend = await _get_monthly_trend(uuid.uuid4(), mock_db, redis=redis)

        assert trend[0]["total_krw"] == 10_000_000.0
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_redis_miss_queries_db_and_caches(self, mock_db, override_settings):
        from app.services.asset_aggregator import _get_monthly_trend

        row = SimpleNamespace(month=date(2024, 1, 1), total_krw=5_000_000.0)
        result = MagicMock()
        result.__iter__ = MagicMock(return_value=iter([row]))
        mock_db.execute = AsyncMock(return_value=result)

        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock()

        trend = await _get_monthly_trend(uuid.uuid4(), mock_db, redis=redis)

        assert len(trend) == 1
        assert trend[0]["total_krw"] == 5_000_000.0
        redis.set.assert_called_once()


# ── get_dashboard_summary (all sub-functions mocked) ─────────

class TestGetDashboardSummary:
    @pytest.mark.asyncio
    async def test_returns_required_fields(self, mock_db, override_settings):
        from app.services.asset_aggregator import get_dashboard_summary

        mock_db.scalar = AsyncMock(return_value=None)  # no settings

        with (
            patch("app.services.asset_aggregator._get_scalar_init_data",
                  new=AsyncMock(return_value=(None, 0.0))),
            patch("app.services.asset_aggregator._build_asset_totals",
                  new=AsyncMock(return_value=(0.0, 0.0, 0.0, {}))),
            patch("app.services.asset_aggregator._get_monthly_trend",
                  new=AsyncMock(return_value=[])),
            patch("app.services.asset_aggregator.get_dividend_summary",
                  new=AsyncMock(return_value={
                      "annual_received": 0.0,
                      "estimated_annual": 0.0,
                      "monthly_breakdown": [],
                  })),
            patch("app.services.asset_aggregator._calc_xirr",
                  new=AsyncMock(return_value=(None, False))),
        ):
            result = await get_dashboard_summary(uuid.uuid4(), mock_db)

        required = [
            "total_assets_krw", "asset_allocation", "goal_amount",
            "goal_achievement_pct", "stock_return_pct", "annual_return_pct",
            "cumulative_return_pct", "xirr_pct", "monthly_trend",
            "annual_dividends_received", "estimated_annual_dividends",
        ]
        for key in required:
            assert key in result, f"Missing: {key}"

    @pytest.mark.asyncio
    async def test_redis_cache_hit(self, mock_db, override_settings):
        import json
        from app.services.asset_aggregator import get_dashboard_summary

        cached = {"total_assets_krw": 99_000_000}
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=json.dumps(cached).encode())

        result = await get_dashboard_summary(uuid.uuid4(), mock_db, redis=redis)

        assert result["total_assets_krw"] == 99_000_000
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_with_settings_goal_pct_calculated(self, mock_db, override_settings):
        from app.services.asset_aggregator import get_dashboard_summary

        settings = SimpleNamespace(
            goal_amount=100_000_000.0,
            annual_deposit_goal=24_000_000.0,
            goal_annual_return_pct=7.0,
            retirement_target_year=2040,
        )
        mock_db.scalar = AsyncMock(return_value=settings)

        with (
            patch("app.services.asset_aggregator._get_scalar_init_data",
                  new=AsyncMock(return_value=(None, 12_000_000.0))),
            patch("app.services.asset_aggregator._build_asset_totals",
                  new=AsyncMock(return_value=(50_000_000.0, 40_000_000.0, 50_000_000.0, {"STOCK_KIS": 50_000_000.0}))),
            patch("app.services.asset_aggregator._get_monthly_trend",
                  new=AsyncMock(return_value=[])),
            patch("app.services.asset_aggregator.get_dividend_summary",
                  new=AsyncMock(return_value={
                      "annual_received": 500_000.0,
                      "estimated_annual": 600_000.0,
                      "monthly_breakdown": [],
                  })),
            patch("app.services.asset_aggregator._calc_xirr",
                  new=AsyncMock(return_value=(8.5, False))),
        ):
            result = await get_dashboard_summary(uuid.uuid4(), mock_db)

        assert result["goal_achievement_pct"] == pytest.approx(50.0)
        assert result["deposit_achievement_pct"] == pytest.approx(50.0)
        assert result["goal_annual_return_pct"] == 7.0
        assert result["retirement_target_year"] == 2040
        assert result["xirr_pct"] == 8.5

    @pytest.mark.asyncio
    async def test_redis_miss_stores_result(self, mock_db, override_settings):
        from app.services.asset_aggregator import get_dashboard_summary

        mock_db.scalar = AsyncMock(return_value=None)

        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock()

        with (
            patch("app.services.asset_aggregator._get_scalar_init_data",
                  new=AsyncMock(return_value=(None, 0.0))),
            patch("app.services.asset_aggregator._build_asset_totals",
                  new=AsyncMock(return_value=(0.0, 0.0, 0.0, {}))),
            patch("app.services.asset_aggregator._get_monthly_trend",
                  new=AsyncMock(return_value=[])),
            patch("app.services.asset_aggregator.get_dividend_summary",
                  new=AsyncMock(return_value={
                      "annual_received": 0.0, "estimated_annual": 0.0, "monthly_breakdown": [],
                  })),
            patch("app.services.asset_aggregator._calc_xirr",
                  new=AsyncMock(return_value=(None, False))),
        ):
            await get_dashboard_summary(uuid.uuid4(), mock_db, redis=redis)

        redis.setex.assert_called_once()


# ── _build_asset_totals ─────────────────────────────────────────

class TestBuildAssetTotals:
    @pytest.mark.asyncio
    async def test_empty_rows_returns_zeros(self, mock_db, override_settings):
        from app.services.asset_aggregator import _build_asset_totals

        with (
            patch("app.services.asset_aggregator.fetch_usd_krw", new=AsyncMock(return_value=1350.0)),
            patch("app.services.asset_aggregator._get_latest_snapshot_rows", new=AsyncMock(return_value=([], set()))),
            patch("app.services.asset_aggregator._get_no_snap_accounts", new=AsyncMock(return_value=[])),
            patch("app.services.asset_aggregator._fetch_position_maps", new=AsyncMock(return_value=({}, {}))),
        ):
            total, invested, stock, by_type = await _build_asset_totals(uuid.uuid4(), mock_db)

        assert total == 0.0
        assert invested == 0.0
        assert stock == 0.0
        assert by_type == {}

    @pytest.mark.asyncio
    async def test_bank_account_row_added_to_total(self, mock_db, override_settings):
        from app.services.asset_aggregator import _build_asset_totals

        snap = SimpleNamespace(id=uuid.uuid4(), amount_krw=5_000_000.0, invested_amount=None)
        acc = SimpleNamespace(
            id=uuid.uuid4(), asset_type="BANK_ACCOUNT",
            include_in_total=True, deposit_krw=None, deposit_usd=None,
        )

        with (
            patch("app.services.asset_aggregator.fetch_usd_krw", new=AsyncMock(return_value=1350.0)),
            patch("app.services.asset_aggregator._get_latest_snapshot_rows", new=AsyncMock(return_value=([(snap, acc)], {acc.id}))),
            patch("app.services.asset_aggregator._get_no_snap_accounts", new=AsyncMock(return_value=[])),
            patch("app.services.asset_aggregator._fetch_position_maps", new=AsyncMock(return_value=({}, {}))),
        ):
            total, invested, stock, by_type = await _build_asset_totals(uuid.uuid4(), mock_db)

        assert total == pytest.approx(5_000_000.0)
        assert by_type.get("BANK_ACCOUNT") == pytest.approx(5_000_000.0)

    @pytest.mark.asyncio
    async def test_excluded_account_not_in_total(self, mock_db, override_settings):
        from app.services.asset_aggregator import _build_asset_totals

        snap = SimpleNamespace(id=uuid.uuid4(), amount_krw=5_000_000.0, invested_amount=None)
        acc = SimpleNamespace(
            id=uuid.uuid4(), asset_type="BANK_ACCOUNT",
            include_in_total=False,
            deposit_krw=None, deposit_usd=None,
        )

        with (
            patch("app.services.asset_aggregator.fetch_usd_krw", new=AsyncMock(return_value=1350.0)),
            patch("app.services.asset_aggregator._get_latest_snapshot_rows", new=AsyncMock(return_value=([(snap, acc)], {acc.id}))),
            patch("app.services.asset_aggregator._get_no_snap_accounts", new=AsyncMock(return_value=[])),
            patch("app.services.asset_aggregator._fetch_position_maps", new=AsyncMock(return_value=({}, {}))),
        ):
            total, _, _, _ = await _build_asset_totals(uuid.uuid4(), mock_db)

        assert total == 0.0

    @pytest.mark.asyncio
    async def test_no_snap_account_manual_amount_added(self, mock_db, override_settings):
        from app.services.asset_aggregator import _build_asset_totals

        acc = SimpleNamespace(
            id=uuid.uuid4(), asset_type="CASH_OTHER",
            include_in_total=True, manual_amount=3_000_000.0,
            deposit_krw=None, deposit_usd=None,
            real_estate_details=None,
        )

        with (
            patch("app.services.asset_aggregator.fetch_usd_krw", new=AsyncMock(return_value=1350.0)),
            patch("app.services.asset_aggregator._get_latest_snapshot_rows", new=AsyncMock(return_value=([], set()))),
            patch("app.services.asset_aggregator._get_no_snap_accounts", new=AsyncMock(return_value=[acc])),
            patch("app.services.asset_aggregator._fetch_position_maps", new=AsyncMock(return_value=({}, {}))),
        ):
            total, _, _, by_type = await _build_asset_totals(uuid.uuid4(), mock_db)

        assert total == pytest.approx(3_000_000.0)


# ── _calc_net_deposits_this_year ────────────────────────────────

class TestCalcNetDepositsThisYear:
    @pytest.mark.asyncio
    async def test_no_transactions_returns_zero(self, mock_db, override_settings):
        from app.services.asset_aggregator import _calc_net_deposits_this_year

        exec_result = MagicMock()
        exec_result.__iter__ = MagicMock(return_value=iter([]))
        exec_result.all = MagicMock(return_value=[])
        mock_db.execute = AsyncMock(return_value=exec_result)

        result = await _calc_net_deposits_this_year(uuid.uuid4(), mock_db)
        assert result == 0.0

    @pytest.mark.asyncio
    async def test_deposit_minus_withdrawal(self, mock_db, override_settings):
        from app.services.asset_aggregator import _calc_net_deposits_this_year

        deposit_row = SimpleNamespace(transaction_type="DEPOSIT", total=5_000_000.0)
        withdrawal_row = SimpleNamespace(transaction_type="WITHDRAWAL", total=1_000_000.0)

        exec_result = MagicMock()
        exec_result.__iter__ = MagicMock(return_value=iter([deposit_row, withdrawal_row]))
        mock_db.execute = AsyncMock(return_value=exec_result)

        result = await _calc_net_deposits_this_year(uuid.uuid4(), mock_db)
        assert result == pytest.approx(4_000_000.0)

    @pytest.mark.asyncio
    async def test_only_deposits(self, mock_db, override_settings):
        from app.services.asset_aggregator import _calc_net_deposits_this_year

        deposit_row = SimpleNamespace(transaction_type="DEPOSIT", total=3_000_000.0)

        exec_result = MagicMock()
        exec_result.__iter__ = MagicMock(return_value=iter([deposit_row]))
        mock_db.execute = AsyncMock(return_value=exec_result)

        result = await _calc_net_deposits_this_year(uuid.uuid4(), mock_db)
        assert result == pytest.approx(3_000_000.0)
