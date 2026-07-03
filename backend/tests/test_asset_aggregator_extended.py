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
        from app.services.returns_calculator import calc_returns as _calc_returns

        ann, cum = _calc_returns(1_000_000, 0.0, date(2024, 1, 1))
        assert ann is None
        assert cum is None

    def test_no_first_date_returns_none(self, override_settings):
        from app.services.returns_calculator import calc_returns as _calc_returns

        ann, cum = _calc_returns(1_100_000, 1_000_000, None)
        assert ann is None
        assert cum is None

    def test_first_date_in_future_returns_none(self, override_settings):
        from app.services.returns_calculator import calc_returns as _calc_returns

        future = date.today() + timedelta(days=30)
        ann, cum = _calc_returns(1_100_000, 1_000_000, future)
        assert ann is None
        assert cum is None

    def test_first_date_today_returns_none(self, override_settings):
        from app.services.returns_calculator import calc_returns as _calc_returns

        ann, cum = _calc_returns(1_100_000, 1_000_000, date.today())
        assert ann is None
        assert cum is None

    def test_positive_return(self, override_settings):
        from app.services.returns_calculator import calc_returns as _calc_returns

        one_year_ago = date.today().replace(year=date.today().year - 1)
        ann, cum = _calc_returns(1_100_000, 1_000_000, one_year_ago)
        assert ann is not None
        assert cum is not None
        assert cum > 0

    def test_negative_return(self, override_settings):
        from app.services.returns_calculator import calc_returns as _calc_returns

        one_year_ago = date.today().replace(year=date.today().year - 1)
        ann, cum = _calc_returns(900_000, 1_000_000, one_year_ago)
        assert ann is not None
        assert cum is not None
        assert cum < 0

    def test_inactive_account_txn_in_net_flows_distorts_return(self, override_settings):
        """비활성 계좌 거래가 net_flows에 포함되면 수익률이 왜곡됨을 보여주는 회귀 시나리오.

        base=1000만원(활성 A), 현재=1200만원, 실제 추가 입금 없음 → 올바른 수익률 20%.
        버그: 비활성 B의 입금 300만원이 net_flows에 포함되면 gain이 줄어 수익률이 음수로 왜곡됨.
        """
        from app.services.returns_calculator import calc_returns as _calc_returns

        one_year_ago = date.today().replace(year=date.today().year - 1)

        _, cum_correct = _calc_returns(12_000_000, 10_000_000, one_year_ago, net_flows=0)
        assert cum_correct == pytest.approx(20.0, abs=0.01)

        _, cum_wrong = _calc_returns(12_000_000, 10_000_000, one_year_ago, net_flows=3_000_000)
        assert cum_wrong < 0

    def test_later_added_account_initial_deposit_double_counting(self, override_settings):
        """나중 추가된 계좌의 초기 입금이 first_snap_total과 net_flows 양쪽에 반영되면 수익률 왜곡.

        시나리오: A(1000만) + B(600만 초기포함) = base 1600만, 현재 1800만.
        A 이후 추가 입금 200만원만 net_flows여야 수익률 0%(실비용만 회수).
        버그: B 초기 입금 500만원도 net_flows에 포함되면 gain이 이중으로 빠져 수익률이 음수로 왜곡됨.
        """
        from app.services.returns_calculator import calc_returns as _calc_returns

        one_year_ago = date.today().replace(year=date.today().year - 1)

        _, cum_correct = _calc_returns(18_000_000, 16_000_000, one_year_ago, net_flows=2_000_000)
        assert cum_correct == pytest.approx(0.0, abs=0.01)

        _, cum_wrong = _calc_returns(18_000_000, 16_000_000, one_year_ago, net_flows=7_000_000)
        assert cum_wrong < -10


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

        (
            first_snap,
            net_deposits,
            non_stock_first_total,
            non_stock_net_flows_after,
        ) = await _get_scalar_init_data(uuid.uuid4(), mock_db)

        assert first_snap is None
        assert net_deposits == 0.0
        assert non_stock_first_total == 0.0
        assert non_stock_net_flows_after == 0.0

    @pytest.mark.asyncio
    async def test_with_data_returns_values(self, mock_db, override_settings):
        from app.services.asset_aggregator import _get_scalar_init_data

        row = SimpleNamespace(
            first_date=date(2023, 1, 1),
            net=5_000_000.0,
            non_stock_first_total=8_000_000.0,
            non_stock_net_flows_after=2_000_000.0,
        )
        result = MagicMock()
        result.first.return_value = row
        mock_db.execute = AsyncMock(return_value=result)

        (
            first_snap,
            net_deposits,
            non_stock_first_total,
            non_stock_net_flows_after,
        ) = await _get_scalar_init_data(uuid.uuid4(), mock_db)

        assert first_snap == date(2023, 1, 1)
        assert net_deposits == 5_000_000.0
        assert non_stock_first_total == 8_000_000.0
        assert non_stock_net_flows_after == 2_000_000.0


# ── 수익률 이중계산 불변조건 (b3101a9 → 1bb29f1 → 84dee24 3회 재작업 영역) ──


class TestNonStockNetFlowsInvariant:
    @pytest.mark.asyncio
    async def test_scalar_init_data_sql_excludes_stock_accounts_from_net_flows(self, mock_db, override_settings):
        """non_stock_net_flows_after SQL이 STOCK_KIS/KIWOOM/OTHER 계좌를 제외하고,
        net_after_ns CTE가 (전체 계좌 기준) paf가 아닌 (비주식 필터링된) paf_ns와 JOIN하는지 고정.

        누군가 이 필터를 제거/변경하면 즉시 실패해 4번째 이중계산 재발을 예방한다.
        """
        from app.services.asset_aggregator import _get_scalar_init_data

        result = MagicMock()
        result.first.return_value = None
        mock_db.execute = AsyncMock(return_value=result)

        await _get_scalar_init_data(uuid.uuid4(), mock_db)

        sql_text = str(mock_db.execute.call_args[0][0])
        assert "STOCK_KIS" in sql_text
        assert "STOCK_KIWOOM" in sql_text
        assert "STOCK_OTHER" in sql_text

        net_after_ns_start = sql_text.index("net_after_ns AS")
        net_after_ns_body = sql_text[net_after_ns_start:]
        assert "JOIN paf_ns" in net_after_ns_body

    @pytest.mark.asyncio
    async def test_dashboard_uses_filtered_non_stock_net_flows_not_raw_totals(self, mock_db, override_settings):
        """get_dashboard_summary가 net_flows 인자로 미필터 net_investment/net_deposits_ytd가 아니라
        반드시 필터링된 non_stock_net_flows_after를 사용하는지 고정.

        net_investment/net_deposits_ytd에는 STOCK_KIS 계좌 거래도 포함되므로, 이 값들이 실수로
        net_flows 인자에 섞여 들어가면 STOCK_KIS 계좌에 Transaction이 있고 없음에 따라
        cumulative_return_pct가 달라진다 — 이 테스트는 그런 오염 없이 값이 불변임을 확인한다.
        """
        from datetime import date as _date

        from app.services.asset_aggregator import get_dashboard_summary

        first_snap = _date(2023, 6, 1)
        mock_db.scalar = AsyncMock(return_value=None)

        # net_deposits_ytd=77M(미필터, STOCK_KIS 거래 포함 가정) 은 일부러
        # non_stock_net_flows_after(필터링됨)=0 과 크게 다른 값으로 설정 — 실제 사용되면 즉시 티가 남.
        with (
            patch(
                "app.services.asset_aggregator._get_scalar_init_data",
                new=AsyncMock(return_value=(first_snap, 77_000_000.0, 50_000_000.0, 0.0)),
            ),
            patch(
                "app.services.asset_aggregator._build_asset_totals",
                new=AsyncMock(return_value=(60_000_000.0, 0.0, 0.0, {})),
            ),
            patch("app.services.asset_aggregator._get_monthly_trend", new=AsyncMock(return_value=[])),
            patch(
                "app.services.asset_aggregator.get_dividend_summary",
                new=AsyncMock(return_value={"annual_received": 0.0, "estimated_annual": 0.0, "monthly_breakdown": []}),
            ),
            patch("app.services.asset_aggregator._calc_xirr", new=AsyncMock(return_value=(None, False))),
        ):
            result = await get_dashboard_summary(uuid.uuid4(), mock_db)

        # net_flows=0(필터링된 값) 사용 시: gain=(60M-50M-0)=10M, base=50M → cumulative=20%
        # net_deposits_ytd(77M)가 잘못 사용됐다면 이 값과 크게 달라진다.
        assert result["cumulative_return_pct"] == pytest.approx(20.0, abs=0.1)


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
        redis.setex = AsyncMock()

        trend = await _get_monthly_trend(uuid.uuid4(), mock_db, redis=redis)

        assert len(trend) == 1
        assert trend[0]["total_krw"] == 5_000_000.0
        redis.setex.assert_called_once()


# ── get_dashboard_summary (all sub-functions mocked) ─────────


class TestGetDashboardSummary:
    @pytest.mark.asyncio
    async def test_returns_required_fields(self, mock_db, override_settings):
        from app.services.asset_aggregator import get_dashboard_summary

        mock_db.scalar = AsyncMock(return_value=None)  # no settings

        with (
            patch(
                "app.services.asset_aggregator._get_scalar_init_data",
                new=AsyncMock(return_value=(None, 0.0, 0.0, 0.0)),
            ),
            patch("app.services.asset_aggregator._build_asset_totals", new=AsyncMock(return_value=(0.0, 0.0, 0.0, {}))),
            patch("app.services.asset_aggregator._get_monthly_trend", new=AsyncMock(return_value=[])),
            patch(
                "app.services.asset_aggregator.get_dividend_summary",
                new=AsyncMock(
                    return_value={
                        "annual_received": 0.0,
                        "estimated_annual": 0.0,
                        "monthly_breakdown": [],
                    }
                ),
            ),
            patch("app.services.asset_aggregator._calc_xirr", new=AsyncMock(return_value=(None, False))),
        ):
            result = await get_dashboard_summary(uuid.uuid4(), mock_db)

        required = [
            "total_assets_krw",
            "asset_allocation",
            "goal_amount",
            "goal_achievement_pct",
            "stock_return_pct",
            "annual_return_pct",
            "cumulative_return_pct",
            "xirr_pct",
            "monthly_trend",
            "annual_dividends_received",
            "estimated_annual_dividends",
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
            annual_dividend_goal=None,
        )
        mock_db.scalar = AsyncMock(return_value=settings)

        with (
            patch(
                "app.services.asset_aggregator._get_scalar_init_data",
                new=AsyncMock(return_value=(None, 12_000_000.0, 0.0, 0.0)),
            ),
            patch(
                "app.services.asset_aggregator._build_asset_totals",
                new=AsyncMock(return_value=(50_000_000.0, 40_000_000.0, 50_000_000.0, {"STOCK_KIS": 50_000_000.0})),
            ),
            patch("app.services.asset_aggregator._get_monthly_trend", new=AsyncMock(return_value=[])),
            patch(
                "app.services.asset_aggregator.get_dividend_summary",
                new=AsyncMock(
                    return_value={
                        "annual_received": 500_000.0,
                        "estimated_annual": 600_000.0,
                        "monthly_breakdown": [],
                    }
                ),
            ),
            patch("app.services.asset_aggregator._calc_xirr", new=AsyncMock(return_value=(8.5, False))),
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
            patch(
                "app.services.asset_aggregator._get_scalar_init_data",
                new=AsyncMock(return_value=(None, 0.0, 0.0, 0.0)),
            ),
            patch("app.services.asset_aggregator._build_asset_totals", new=AsyncMock(return_value=(0.0, 0.0, 0.0, {}))),
            patch("app.services.asset_aggregator._get_monthly_trend", new=AsyncMock(return_value=[])),
            patch(
                "app.services.asset_aggregator.get_dividend_summary",
                new=AsyncMock(
                    return_value={
                        "annual_received": 0.0,
                        "estimated_annual": 0.0,
                        "monthly_breakdown": [],
                    }
                ),
            ),
            patch("app.services.asset_aggregator._calc_xirr", new=AsyncMock(return_value=(None, False))),
        ):
            await get_dashboard_summary(uuid.uuid4(), mock_db, redis=redis)

        redis.setex.assert_called_once()


# ── _build_asset_totals ─────────────────────────────────────────


class TestBuildAssetTotals:
    @pytest.mark.asyncio
    async def test_empty_rows_returns_zeros(self, mock_db, override_settings):
        from app.services.composition_calculator import build_asset_totals

        with (
            patch("app.services.composition_calculator.fetch_usd_krw", new=AsyncMock(return_value=1350.0)),
            patch(
                "app.services.composition_calculator.get_latest_snapshot_rows",
                new=AsyncMock(return_value=([], set())),
            ),
            patch("app.services.composition_calculator.get_no_snap_accounts", new=AsyncMock(return_value=[])),
            patch("app.services.composition_calculator._fetch_snapshot_positions", new=AsyncMock(return_value={})),
            patch("app.services.composition_calculator._fetch_current_positions", new=AsyncMock(return_value={})),
        ):
            total, invested, stock, by_type = await build_asset_totals(uuid.uuid4(), mock_db)

        assert total == 0.0
        assert invested == 0.0
        assert stock == 0.0
        assert by_type == {}

    @pytest.mark.asyncio
    async def test_bank_account_row_added_to_total(self, mock_db, override_settings):
        from app.services.composition_calculator import build_asset_totals

        snap = SimpleNamespace(id=uuid.uuid4(), amount_krw=5_000_000.0, invested_amount=None)
        acc = SimpleNamespace(
            id=uuid.uuid4(),
            asset_type="BANK_ACCOUNT",
            include_in_total=True,
            deposit_krw=None,
            deposit_usd=None,
        )

        with (
            patch("app.services.composition_calculator.fetch_usd_krw", new=AsyncMock(return_value=1350.0)),
            patch(
                "app.services.composition_calculator.get_latest_snapshot_rows",
                new=AsyncMock(return_value=([(snap, acc)], {acc.id})),
            ),
            patch("app.services.composition_calculator.get_no_snap_accounts", new=AsyncMock(return_value=[])),
            patch("app.services.composition_calculator._fetch_snapshot_positions", new=AsyncMock(return_value={})),
            patch("app.services.composition_calculator._fetch_current_positions", new=AsyncMock(return_value={})),
        ):
            total, invested, stock, by_type = await build_asset_totals(uuid.uuid4(), mock_db)

        assert total == pytest.approx(5_000_000.0)
        assert by_type.get("BANK_ACCOUNT") == pytest.approx(5_000_000.0)

    @pytest.mark.asyncio
    async def test_excluded_account_not_in_total(self, mock_db, override_settings):
        from app.services.composition_calculator import build_asset_totals

        snap = SimpleNamespace(id=uuid.uuid4(), amount_krw=5_000_000.0, invested_amount=None)
        acc = SimpleNamespace(
            id=uuid.uuid4(),
            asset_type="BANK_ACCOUNT",
            include_in_total=False,
            deposit_krw=None,
            deposit_usd=None,
        )

        with (
            patch("app.services.composition_calculator.fetch_usd_krw", new=AsyncMock(return_value=1350.0)),
            patch(
                "app.services.composition_calculator.get_latest_snapshot_rows",
                new=AsyncMock(return_value=([(snap, acc)], {acc.id})),
            ),
            patch("app.services.composition_calculator.get_no_snap_accounts", new=AsyncMock(return_value=[])),
            patch("app.services.composition_calculator._fetch_snapshot_positions", new=AsyncMock(return_value={})),
            patch("app.services.composition_calculator._fetch_current_positions", new=AsyncMock(return_value={})),
        ):
            total, _, _, _ = await build_asset_totals(uuid.uuid4(), mock_db)

        assert total == 0.0

    @pytest.mark.asyncio
    async def test_no_snap_account_manual_amount_added(self, mock_db, override_settings):
        from app.services.composition_calculator import build_asset_totals

        acc = SimpleNamespace(
            id=uuid.uuid4(),
            asset_type="CASH_OTHER",
            include_in_total=True,
            manual_amount=3_000_000.0,
            deposit_krw=None,
            deposit_usd=None,
            real_estate_details=None,
        )

        with (
            patch("app.services.composition_calculator.fetch_usd_krw", new=AsyncMock(return_value=1350.0)),
            patch(
                "app.services.composition_calculator.get_latest_snapshot_rows",
                new=AsyncMock(return_value=([], set())),
            ),
            patch("app.services.composition_calculator.get_no_snap_accounts", new=AsyncMock(return_value=[acc])),
            patch("app.services.composition_calculator._fetch_snapshot_positions", new=AsyncMock(return_value={})),
            patch("app.services.composition_calculator._fetch_current_positions", new=AsyncMock(return_value={})),
        ):
            total, _, _, by_type = await build_asset_totals(uuid.uuid4(), mock_db)

        assert total == pytest.approx(3_000_000.0)

    @pytest.mark.asyncio
    async def test_stock_account_no_positions_not_counted_as_equity(self, mock_db, override_settings):
        """포지션 없는 주식 계좌의 예수금이 stock_value가 아닌 bank_total에 포함되어야 함.
        (Bug 1 regression guard: stock_equity = amount 잘못 처리하던 버그 방지)
        """
        from app.services.composition_calculator import build_asset_totals

        acc_id = uuid.uuid4()
        snap_id = uuid.uuid4()
        # 주식 계좌, 포지션 없음, 예수금 1,000만원
        snap = SimpleNamespace(id=snap_id, amount_krw=10_000_000.0, invested_amount=None)
        acc = SimpleNamespace(
            id=acc_id,
            asset_type="STOCK_KIS",
            include_in_total=True,
            deposit_krw=None,
            deposit_usd=None,
        )

        with (
            patch("app.services.composition_calculator.fetch_usd_krw", new=AsyncMock(return_value=1350.0)),
            patch(
                "app.services.composition_calculator.get_latest_snapshot_rows",
                new=AsyncMock(return_value=([(snap, acc)], {acc_id})),
            ),
            patch("app.services.composition_calculator.get_no_snap_accounts", new=AsyncMock(return_value=[])),
            # 포지션 없음
            patch("app.services.composition_calculator._fetch_snapshot_positions", new=AsyncMock(return_value={})),
            patch("app.services.composition_calculator._fetch_current_positions", new=AsyncMock(return_value={})),
        ):
            total, invested, stock, by_type = await build_asset_totals(uuid.uuid4(), mock_db)

        assert total == pytest.approx(10_000_000.0)  # 총자산에는 포함
        assert stock == pytest.approx(0.0)  # 주식 평가액 0 (종목 없음)
        assert invested == pytest.approx(0.0)  # 투자원가 0
        # CASH_STOCK 버킷에 예수금이 포함되어야 함
        assert by_type.get("CASH_STOCK", 0.0) == pytest.approx(10_000_000.0)

    @pytest.mark.asyncio
    async def test_dashboard_cash_only_matches_legacy_modified_dietz(self, mock_db, override_settings):
        """주식이 없는(total_invested=0) 유저는 non_stock_first_total만으로 기존 Modified Dietz와 동일하게 계산.
        net_flows_after=0 → Modified Dietz = 단순 수익률 공식과 동일.
        """
        from datetime import date as _date

        from app.services.asset_aggregator import get_dashboard_summary

        first_snap = _date(2023, 6, 1)
        mock_db.scalar = AsyncMock(return_value=None)

        with (
            # 비주식 계좌 최초 스냅샷 총액 5,000만원, 이후 입금 없음
            patch(
                "app.services.asset_aggregator._get_scalar_init_data",
                new=AsyncMock(return_value=(first_snap, 0.0, 50_000_000.0, 0.0)),
            ),
            # 현재 총자산 6,000만원, 주식 없음
            patch(
                "app.services.asset_aggregator._build_asset_totals",
                new=AsyncMock(return_value=(60_000_000.0, 0.0, 0.0, {})),
            ),
            patch("app.services.asset_aggregator._get_monthly_trend", new=AsyncMock(return_value=[])),
            patch(
                "app.services.asset_aggregator.get_dividend_summary",
                new=AsyncMock(return_value={"annual_received": 0.0, "estimated_annual": 0.0, "monthly_breakdown": []}),
            ),
            patch("app.services.asset_aggregator._calc_xirr", new=AsyncMock(return_value=(None, False))),
        ):
            result = await get_dashboard_summary(uuid.uuid4(), mock_db)

        # net_flows=0 → gain=(60M-50M-0)=10M, weighted_base=50M → cumulative=20%
        assert result["cumulative_return_pct"] == pytest.approx(20.0, abs=0.1)

    @pytest.mark.asyncio
    async def test_dashboard_stock_only_uses_cost_basis(self, mock_db, override_settings):
        """비주식 계좌가 없을 때(non_stock_first_total=0) 주식 매입원가(total_invested) 기준으로 계산."""
        from datetime import date as _date

        from app.services.asset_aggregator import get_dashboard_summary

        first_snap = _date(2023, 6, 1)
        mock_db.scalar = AsyncMock(return_value=None)

        with (
            # 비주식 계좌 없음(non_stock_first_total=0)
            patch(
                "app.services.asset_aggregator._get_scalar_init_data",
                new=AsyncMock(return_value=(first_snap, 0.0, 0.0, 0.0)),
            ),
            # 전액 주식: 총자산 4,000만원 = 주식 평가액, 매입원가 3,000만원
            patch(
                "app.services.asset_aggregator._build_asset_totals",
                new=AsyncMock(return_value=(40_000_000.0, 30_000_000.0, 40_000_000.0, {})),
            ),
            patch("app.services.asset_aggregator._get_monthly_trend", new=AsyncMock(return_value=[])),
            patch(
                "app.services.asset_aggregator.get_dividend_summary",
                new=AsyncMock(return_value={"annual_received": 0.0, "estimated_annual": 0.0, "monthly_breakdown": []}),
            ),
            patch("app.services.asset_aggregator._calc_xirr", new=AsyncMock(return_value=(None, False))),
        ):
            result = await get_dashboard_summary(uuid.uuid4(), mock_db)

        # 매입원가 기준: cumulative = (4,000 / 3,000 - 1) × 100 = 33.33%
        assert result["cumulative_return_pct"] == pytest.approx(33.33, abs=0.1)

    @pytest.mark.asyncio
    async def test_dashboard_mixed_stock_and_cash_blends_cost_basis_with_modified_dietz(
        self, mock_db, override_settings
    ):
        """주식+현금 혼재 시, 주식은 매입원가 기준 실제 손익을 그대로 반영해
        stock_return_pct(97.1%)와 무관하게 낮게 나오던(32.22%) 실사용자 버그 재현 시나리오.

        주식: 매입원가 1,000만원 → 평가액 1,971만원 (stock_return_pct = 97.1%)
        현금: 추적 시작 이후 변동 없음 (non_stock_first_total=1,000만원, flows=0 → gain 0)
        total_assets_krw = 1,971만 + 1,000만 = 2,971만원
        base = 1,000만(매입원가) + 1,000만(비주식 최초 스냅샷) = 2,000만원
        gain = 2,971만 - 2,000만 - 0 = 971만원 → cumulative = 971/2000 × 100 = 48.55%
        (현금 미반영 시절의 왜곡된 32%대보다 실제 주식 수익률에 훨씬 가까워짐)
        """
        from datetime import date as _date

        from app.services.asset_aggregator import get_dashboard_summary

        first_snap = _date(2023, 6, 1)
        mock_db.scalar = AsyncMock(return_value=None)

        with (
            patch(
                "app.services.asset_aggregator._get_scalar_init_data",
                new=AsyncMock(return_value=(first_snap, 0.0, 10_000_000.0, 0.0)),
            ),
            patch(
                "app.services.asset_aggregator._build_asset_totals",
                new=AsyncMock(return_value=(29_710_000.0, 10_000_000.0, 19_710_000.0, {})),
            ),
            patch("app.services.asset_aggregator._get_monthly_trend", new=AsyncMock(return_value=[])),
            patch(
                "app.services.asset_aggregator.get_dividend_summary",
                new=AsyncMock(return_value={"annual_received": 0.0, "estimated_annual": 0.0, "monthly_breakdown": []}),
            ),
            patch("app.services.asset_aggregator._calc_xirr", new=AsyncMock(return_value=(None, False))),
        ):
            result = await get_dashboard_summary(uuid.uuid4(), mock_db)

        assert result["stock_return_pct"] == pytest.approx(97.1, abs=0.1)
        assert result["cumulative_return_pct"] == pytest.approx(48.55, abs=0.1)
        # 현금이 섞여 있으므로 주식 단독 수익률보다는 낮지만, 기존처럼 그 절반 아래로 왜곡되지는 않아야 함
        assert result["cumulative_return_pct"] < result["stock_return_pct"]

    @pytest.mark.asyncio
    async def test_dashboard_modified_dietz_excludes_deposits(self, mock_db, override_settings):
        """최초 스냅샷 이후 입금분은 수익률에서 제외됨 (Modified Dietz).

        기준: 5,000만원, 이후 1,000만원 입금, 현재 6,200만원
        순투자 수익: 6,200 - 5,000 - 1,000 = 200만원
        Modified Dietz weighted_base: 5,000 + 0.5×1,000 = 5,500만원
        cumulative ≈ 200/5500 × 100 ≈ 3.636%
        """
        from datetime import date as _date

        from app.services.asset_aggregator import get_dashboard_summary

        first_snap = _date(2023, 6, 1)
        mock_db.scalar = AsyncMock(return_value=None)

        with (
            patch(
                "app.services.asset_aggregator._get_scalar_init_data",
                new=AsyncMock(return_value=(first_snap, 0.0, 50_000_000.0, 10_000_000.0)),
            ),
            patch(
                "app.services.asset_aggregator._build_asset_totals",
                new=AsyncMock(return_value=(62_000_000.0, 0.0, 0.0, {})),
            ),
            patch("app.services.asset_aggregator._get_monthly_trend", new=AsyncMock(return_value=[])),
            patch(
                "app.services.asset_aggregator.get_dividend_summary",
                new=AsyncMock(return_value={"annual_received": 0.0, "estimated_annual": 0.0, "monthly_breakdown": []}),
            ),
            patch("app.services.asset_aggregator._calc_xirr", new=AsyncMock(return_value=(None, False))),
        ):
            result = await get_dashboard_summary(uuid.uuid4(), mock_db)

        # gain=2M, weighted_base=55M → 2/55×100 ≈ 3.636%
        assert result["cumulative_return_pct"] == pytest.approx(2_000_000 / 55_000_000 * 100, abs=0.01)

    @pytest.mark.asyncio
    async def test_dashboard_modified_dietz_with_withdrawal(self, mock_db, override_settings):
        """출금이 있을 때 Modified Dietz가 올바른 수익률을 반환.

        기준: 5,000만원, 이후 500만원 출금(net_flows_after=-500만), 현재 4,300만원
        순투자 수익: 4,300 - 5,000 - (-500) = -200만원 (손실)
        Modified Dietz weighted_base: 5,000 + 0.5×(-500) = 4,750만원
        cumulative ≈ -200/4750 × 100 ≈ -4.211%
        """
        from datetime import date as _date

        from app.services.asset_aggregator import get_dashboard_summary

        first_snap = _date(2023, 6, 1)
        mock_db.scalar = AsyncMock(return_value=None)

        with (
            patch(
                "app.services.asset_aggregator._get_scalar_init_data",
                new=AsyncMock(return_value=(first_snap, 0.0, 50_000_000.0, -5_000_000.0)),
            ),
            patch(
                "app.services.asset_aggregator._build_asset_totals",
                new=AsyncMock(return_value=(43_000_000.0, 0.0, 0.0, {})),
            ),
            patch("app.services.asset_aggregator._get_monthly_trend", new=AsyncMock(return_value=[])),
            patch(
                "app.services.asset_aggregator.get_dividend_summary",
                new=AsyncMock(return_value={"annual_received": 0.0, "estimated_annual": 0.0, "monthly_breakdown": []}),
            ),
            patch("app.services.asset_aggregator._calc_xirr", new=AsyncMock(return_value=(None, False))),
        ):
            result = await get_dashboard_summary(uuid.uuid4(), mock_db)

        # gain=-2M, weighted_base=47.5M → -2/47.5×100 ≈ -4.211%
        assert result["cumulative_return_pct"] == pytest.approx(-2_000_000 / 47_500_000 * 100, abs=0.01)
