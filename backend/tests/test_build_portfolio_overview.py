"""portfolio_service.build_portfolio_overview 통합 테스트."""

from __future__ import annotations

import json
import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.portfolio_service import build_portfolio_overview


def _exec_result(items):
    result = MagicMock()
    result.scalars.return_value.all.return_value = items
    result.all.return_value = items
    return result


def _make_account(acc_id=None, asset_type="STOCK_KIS", include_in_total=True):
    return SimpleNamespace(
        id=acc_id or uuid.uuid4(),
        name="테스트계좌",
        asset_type=asset_type,
        data_source="KIS_API",
        is_active=True,
        include_in_total=include_in_total,
        institution="한국투자증권",
        is_mock_mode=False,
        manual_amount=None,
        real_estate_details=None,
        deposit_krw=None,
        deposit_usd=None,
        sort_order=0,
        created_at=None,
        tax_type="GENERAL",
        investment_horizon=None,
    )


def _make_snapshot(snap_id, acc_id):
    return SimpleNamespace(
        id=snap_id,
        account_id=acc_id,
        snapshot_date=date.today(),
        amount_krw=10_000_000,
        invested_amount=9_000_000,
        unrealized_pnl=1_000_000,
    )


def _make_position(snap_id, acc_id):
    return SimpleNamespace(
        snapshot_id=snap_id,
        account_id=acc_id,
        ticker="005930",
        name="삼성전자",
        market="KOSPI",
        qty=10,
        avg_price=70_000,
        current_price=80_000,
        value_krw=800_000,
        currency="KRW",
    )


class TestBuildPortfolioOverviewEmpty:
    @pytest.mark.asyncio
    async def test_empty_accounts_returns_zero_dict(self, override_settings):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_exec_result([]))

        result = await build_portfolio_overview(uuid.uuid4(), db)

        assert result["total_assets_krw"] == 0
        assert result["accounts"] == []
        assert result["all_positions"] == []


class TestBuildPortfolioOverviewWithAccounts:
    @pytest.mark.asyncio
    async def test_single_stock_account_with_snapshot(self, override_settings):
        """단일 주식 계좌 + 스냅샷 → 올바른 집계."""
        db = AsyncMock()
        acc_id = uuid.uuid4()
        snap_id = uuid.uuid4()

        account = _make_account(acc_id=acc_id)
        snapshot = _make_snapshot(snap_id, acc_id)
        position = _make_position(snap_id, acc_id)

        db.execute = AsyncMock(
            side_effect=[
                _exec_result([account]),  # 1. accounts
                _exec_result([snapshot]),  # 2. snapshots
                _exec_result([position]),  # 3. snap positions
                _exec_result([]),  # 4. current positions
            ]
        )

        result = await build_portfolio_overview(uuid.uuid4(), db)

        assert result["total_assets_krw"] == pytest.approx(10_000_000)
        assert result["total_invested_krw"] == pytest.approx(9_000_000)
        assert result["unrealized_pnl_krw"] == pytest.approx(1_000_000)
        assert len(result["accounts"]) == 1
        assert len(result["all_positions"]) == 1

    @pytest.mark.asyncio
    async def test_stock_return_pct_calculated(self, override_settings):
        """주식수익률 = pnl / invested * 100."""
        db = AsyncMock()
        acc_id = uuid.uuid4()
        snap_id = uuid.uuid4()

        account = _make_account(acc_id=acc_id)
        snapshot = _make_snapshot(snap_id, acc_id)

        db.execute = AsyncMock(
            side_effect=[
                _exec_result([account]),
                _exec_result([snapshot]),
                _exec_result([]),  # snap positions (empty)
                _exec_result([]),  # current positions
            ]
        )

        result = await build_portfolio_overview(uuid.uuid4(), db)
        # invested_amount=9M, pnl=1M → return = 1/9*100 ≈ 11.11%
        assert result["stock_return_pct"] == pytest.approx(1_000_000 / 9_000_000 * 100, rel=0.01)

    @pytest.mark.asyncio
    async def test_bank_account_excluded_from_stock_total(self, override_settings):
        """은행 계좌 스냅샷은 total_invested에 포함 안 됨."""
        db = AsyncMock()
        acc_id = uuid.uuid4()
        snap_id = uuid.uuid4()

        account = _make_account(acc_id=acc_id, asset_type="BANK_ACCOUNT")
        snapshot = _make_snapshot(snap_id, acc_id)

        # BANK_ACCOUNT: snap_ids=[snap_id] → call3, acc_ids=[] → no call4
        db.execute = AsyncMock(
            side_effect=[
                _exec_result([account]),
                _exec_result([snapshot]),
                _exec_result([]),  # snap positions (nothing for bank)
            ]
        )

        result = await build_portfolio_overview(uuid.uuid4(), db)

        assert result["total_assets_krw"] == pytest.approx(10_000_000)
        assert result["total_invested_krw"] == 0
        assert result["all_positions"] == []

    @pytest.mark.asyncio
    async def test_account_not_include_in_total_excluded(self, override_settings):
        """include_in_total=False 계좌는 total_assets_krw에서 제외."""
        db = AsyncMock()
        acc_id = uuid.uuid4()
        snap_id = uuid.uuid4()

        account = _make_account(acc_id=acc_id, include_in_total=False)
        snapshot = _make_snapshot(snap_id, acc_id)

        db.execute = AsyncMock(
            side_effect=[
                _exec_result([account]),
                _exec_result([snapshot]),
                _exec_result([]),  # snap positions
                _exec_result([]),  # current positions
            ]
        )

        result = await build_portfolio_overview(uuid.uuid4(), db)
        assert result["total_assets_krw"] == 0

    @pytest.mark.asyncio
    async def test_lite_mode_omits_all_positions(self, override_settings):
        """lite=True이면 all_positions 비어 있어야 함."""
        db = AsyncMock()
        acc_id = uuid.uuid4()
        snap_id = uuid.uuid4()

        account = _make_account(acc_id=acc_id)
        snapshot = _make_snapshot(snap_id, acc_id)
        position = _make_position(snap_id, acc_id)

        db.execute = AsyncMock(
            side_effect=[
                _exec_result([account]),
                _exec_result([snapshot]),
                _exec_result([position]),
                _exec_result([]),
            ]
        )

        result = await build_portfolio_overview(uuid.uuid4(), db, lite=True)

        assert result["all_positions"] == []
        assert "stock_allocation" in result

    @pytest.mark.asyncio
    async def test_real_estate_applies_mortgage(self, override_settings):
        """부동산 계좌는 mortgage 차감 후 amount 계산."""
        db = AsyncMock()
        acc_id = uuid.uuid4()

        account = SimpleNamespace(
            id=acc_id,
            name="아파트",
            asset_type="REAL_ESTATE",
            data_source="MANUAL",
            is_active=True,
            include_in_total=True,
            institution=None,
            is_mock_mode=False,
            manual_amount=500_000_000,
            real_estate_details={"mortgage_balance_krw": 200_000_000},
            deposit_krw=None,
            deposit_usd=None,
            sort_order=0,
            created_at=None,
            tax_type="GENERAL",
            investment_horizon=None,
        )

        # REAL_ESTATE: snap_ids=[], acc_ids=[] → only 2 DB calls
        db.execute = AsyncMock(
            side_effect=[
                _exec_result([account]),
                _exec_result([]),  # no snapshots
            ]
        )

        result = await build_portfolio_overview(uuid.uuid4(), db)

        acc_row = result["accounts"][0]
        assert "real_estate_details" in acc_row
        assert acc_row["amount_krw"] == pytest.approx(300_000_000)

    @pytest.mark.asyncio
    async def test_cache_cache_hit_skips_db(self, override_settings):
        """Cache 캐시 히트 시 DB를 조회하지 않는다."""
        cached = {"total_assets_krw": 5_000_000, "accounts": [], "all_positions": []}

        db = AsyncMock()
        cache = AsyncMock()
        cache.get = AsyncMock(return_value=json.dumps(cached).encode())

        result = await build_portfolio_overview(uuid.uuid4(), db, cache=cache)

        assert result["total_assets_krw"] == 5_000_000
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_cache_miss_queries_and_stores(self, override_settings):
        """Cache 미스 시 DB 쿼리 후 캐시에 저장한다."""
        db = AsyncMock()
        cache = AsyncMock()
        cache.get = AsyncMock(return_value=None)
        cache.setex = AsyncMock()

        acc_id = uuid.uuid4()
        # Need a real account so the function doesn't return early (setex only called after full build)
        account = _make_account(acc_id=acc_id, asset_type="BANK_ACCOUNT")
        db.execute = AsyncMock(
            side_effect=[
                _exec_result([account]),  # 1. accounts
                _exec_result([]),  # 2. snapshots (none)
                # BANK_ACCOUNT not in STOCK_TYPES → no current positions query
            ]
        )

        await build_portfolio_overview(uuid.uuid4(), db, cache=cache)

        cache.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_snapshot_no_manual_gives_zero(self, override_settings):
        """스냅샷도 manual_amount도 없으면 amount=0."""
        db = AsyncMock()
        acc_id = uuid.uuid4()

        account = _make_account(acc_id=acc_id)  # manual_amount=None

        db.execute = AsyncMock(
            side_effect=[
                _exec_result([account]),
                _exec_result([]),  # no snapshots
                # snap_ids=[] → no call3
                _exec_result([]),  # current positions (acc_ids=[acc_id])
            ]
        )

        result = await build_portfolio_overview(uuid.uuid4(), db)

        assert result["accounts"][0]["amount_krw"] == 0

    @pytest.mark.asyncio
    async def test_asset_type_allocation_populated(self, override_settings):
        """asset_type_allocation에 계좌 타입이 반영된다."""
        db = AsyncMock()
        acc_id = uuid.uuid4()
        snap_id = uuid.uuid4()

        account = _make_account(acc_id=acc_id, asset_type="STOCK_KIS")
        snapshot = _make_snapshot(snap_id, acc_id)

        db.execute = AsyncMock(
            side_effect=[
                _exec_result([account]),
                _exec_result([snapshot]),
                _exec_result([]),
                _exec_result([]),
            ]
        )

        result = await build_portfolio_overview(uuid.uuid4(), db)

        alloc_types = [a["type"] for a in result["asset_type_allocation"]]
        assert "STOCK_KIS" in alloc_types

    @pytest.mark.asyncio
    async def test_position_weight_in_stock_calculated(self, override_settings):
        """all_positions에 weight_in_stock 필드가 계산된다."""
        db = AsyncMock()
        acc_id = uuid.uuid4()
        snap_id = uuid.uuid4()

        account = _make_account(acc_id=acc_id)
        snapshot = _make_snapshot(snap_id, acc_id)
        position = _make_position(snap_id, acc_id)

        db.execute = AsyncMock(
            side_effect=[
                _exec_result([account]),
                _exec_result([snapshot]),
                _exec_result([position]),
                _exec_result([]),
            ]
        )

        result = await build_portfolio_overview(uuid.uuid4(), db)

        pos = result["all_positions"][0]
        assert "weight_in_stock" in pos
        assert pos["weight_in_stock"] >= 0

    @pytest.mark.asyncio
    async def test_with_account_ids_filter_applies_where(self, override_settings):
        """account_ids 전달 시 쿼리에 필터 추가 (line 170)."""
        db = AsyncMock()
        acc_id = uuid.uuid4()
        db.execute = AsyncMock(return_value=_exec_result([]))

        result = await build_portfolio_overview(uuid.uuid4(), db, account_ids=[acc_id])

        assert result["total_assets_krw"] == 0

    @pytest.mark.asyncio
    async def test_stock_account_deposit_split_into_cash_stock_bucket(self, override_settings):
        """증권 계좌(KIS)의 예수금은 CASH_STOCK 버킷으로, 포지션 평가금만 STOCK_KIS 버킷으로 분리된다."""
        db = AsyncMock()
        acc_id = uuid.uuid4()
        snap_id = uuid.uuid4()

        account = _make_account(acc_id=acc_id, asset_type="STOCK_KIS")
        snapshot = _make_snapshot(snap_id, acc_id)  # amount_krw=10,000,000
        position = _make_position(snap_id, acc_id)  # current_price=80,000 * qty=10 = 800,000 평가금

        db.execute = AsyncMock(
            side_effect=[
                _exec_result([account]),
                _exec_result([snapshot]),
                _exec_result([position]),
                _exec_result([]),
            ]
        )

        result = await build_portfolio_overview(uuid.uuid4(), db)

        by_type = {a["type"]: a["amount_krw"] for a in result["asset_type_allocation"]}
        assert by_type["STOCK_KIS"] == pytest.approx(800_000)
        assert by_type["CASH_STOCK"] == pytest.approx(10_000_000 - 800_000)

    @pytest.mark.asyncio
    async def test_kiwoom_stock_account_deposit_also_split(self, override_settings):
        """키움 증권 계좌(STOCK_KIWOOM)도 동일하게 예수금이 CASH_STOCK으로 분리된다."""
        db = AsyncMock()
        acc_id = uuid.uuid4()
        snap_id = uuid.uuid4()

        account = _make_account(acc_id=acc_id, asset_type="STOCK_KIWOOM")
        snapshot = _make_snapshot(snap_id, acc_id)  # amount_krw=10,000,000
        position = _make_position(snap_id, acc_id)  # 평가금 800,000

        db.execute = AsyncMock(
            side_effect=[
                _exec_result([account]),
                _exec_result([snapshot]),
                _exec_result([position]),
                _exec_result([]),
            ]
        )

        result = await build_portfolio_overview(uuid.uuid4(), db)

        by_type = {a["type"]: a["amount_krw"] for a in result["asset_type_allocation"]}
        assert by_type["STOCK_KIWOOM"] == pytest.approx(800_000)
        assert by_type["CASH_STOCK"] == pytest.approx(10_000_000 - 800_000)

    @pytest.mark.asyncio
    async def test_kiwoom_stock_account_positions_included_in_all_positions(self, override_settings):
        """STOCK_KIWOOM 계좌 보유종목도 all_positions에 포함되어야 한다 — 과거 STOCK_TYPES
        frozenset에서 STOCK_KIWOOM이 누락되어 종목 상세가 통째로 빠지던 회귀 방지."""
        db = AsyncMock()
        acc_id = uuid.uuid4()
        snap_id = uuid.uuid4()

        account = _make_account(acc_id=acc_id, asset_type="STOCK_KIWOOM")
        snapshot = _make_snapshot(snap_id, acc_id)
        position = _make_position(snap_id, acc_id)

        db.execute = AsyncMock(
            side_effect=[
                _exec_result([account]),
                _exec_result([snapshot]),
                _exec_result([position]),
                _exec_result([]),
            ]
        )

        result = await build_portfolio_overview(uuid.uuid4(), db)

        assert len(result["all_positions"]) == 1
        assert result["all_positions"][0]["ticker"] == "005930"

    @pytest.mark.asyncio
    async def test_current_positions_added_to_cur_pos_map(self, override_settings):
        """현재 보유 포지션(snapshot_id=None) 있을 때 cur_pos_map 채움 (line 199)."""
        db = AsyncMock()
        acc_id = uuid.uuid4()
        snap_id = uuid.uuid4()

        account = _make_account(acc_id=acc_id, asset_type="STOCK_KIS")
        snapshot = _make_snapshot(snap_id, acc_id)
        snap_pos = _make_position(snap_id, acc_id)

        cur_pos = SimpleNamespace(
            snapshot_id=None,
            account_id=acc_id,
            ticker="000660",
            name="SK하이닉스",
            market="KOSPI",
            qty=5,
            avg_price=100_000,
            current_price=120_000,
            value_krw=600_000,
            currency="KRW",
        )

        db.execute = AsyncMock(
            side_effect=[
                _exec_result([account]),
                _exec_result([snapshot]),
                _exec_result([snap_pos]),
                _exec_result([cur_pos]),
            ]
        )

        result = await build_portfolio_overview(uuid.uuid4(), db)

        assert result["total_assets_krw"] > 0
