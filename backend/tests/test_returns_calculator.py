"""returns_calculator.py 단위 테스트 — xirr, calc_returns, calc_xirr."""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.returns_calculator import calc_returns, calc_xirr, xirr


class TestXirr:
    def test_basic_positive_return(self):
        flows = [
            (date(2022, 1, 1), -10000.0),
            (date(2023, 1, 1), 11000.0),
        ]
        result = xirr(flows)
        assert result is not None
        assert result == pytest.approx(10.0, abs=0.5)

    def test_negative_return(self):
        flows = [
            (date(2022, 1, 1), -10000.0),
            (date(2023, 1, 1), 8000.0),
        ]
        result = xirr(flows)
        assert result is not None
        assert result < 0

    def test_single_cashflow_returns_none(self):
        flows = [(date(2022, 1, 1), -10000.0)]
        assert xirr(flows) is None

    def test_all_positive_flows_returns_none(self):
        flows = [
            (date(2022, 1, 1), 5000.0),
            (date(2023, 1, 1), 6000.0),
        ]
        assert xirr(flows) is None

    def test_all_negative_flows_returns_none(self):
        flows = [
            (date(2022, 1, 1), -5000.0),
            (date(2023, 1, 1), -6000.0),
        ]
        assert xirr(flows) is None

    def test_multiple_cashflows(self):
        flows = [
            (date(2020, 1, 1), -10000.0),
            (date(2021, 1, 1), -2000.0),
            (date(2022, 1, 1), -2000.0),
            (date(2023, 1, 1), 18000.0),
        ]
        result = xirr(flows)
        assert result is not None

    def test_unreasonable_return_clamped_to_none(self):
        # 극단적 수익률은 None 반환
        flows = [
            (date(2022, 1, 1), -1.0),
            (date(2022, 1, 2), 100000.0),
        ]
        result = xirr(flows)
        # None이거나 1000% 이하이어야 함
        assert result is None or result <= 1000.0


class TestCalcReturns:
    def test_positive_annualized_return(self):
        today = date.today()
        first_date = date(today.year - 2, today.month, 1)
        annualized, cumulative = calc_returns(12000.0, 10000.0, first_date)
        assert annualized is not None
        assert annualized > 0
        assert cumulative is not None
        assert cumulative == pytest.approx(20.0, abs=0.1)

    def test_zero_base_returns_none(self):
        annualized, cumulative = calc_returns(10000.0, 0.0, date(2020, 1, 1))
        assert annualized is None
        assert cumulative is None

    def test_none_first_date_returns_none(self):
        annualized, cumulative = calc_returns(10000.0, 5000.0, None)
        assert annualized is None
        assert cumulative is None

    def test_future_first_date_returns_none(self):
        from datetime import timedelta

        future = date.today() + timedelta(days=30)
        annualized, cumulative = calc_returns(10000.0, 5000.0, future)
        assert annualized is None
        assert cumulative is None

    def test_same_day_first_date_returns_none(self):
        annualized, cumulative = calc_returns(10000.0, 5000.0, date.today())
        assert annualized is None
        assert cumulative is None


class TestCalcXirr:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_transactions_no_snapshots(self):
        db = AsyncMock()
        execute_result = MagicMock()
        execute_result.all.return_value = []
        execute_result.first.return_value = None
        db.execute = AsyncMock(return_value=execute_result)

        result, used_snapshot = await calc_xirr(uuid.uuid4(), 10000.0, db)
        assert result is None
        assert used_snapshot is False

    @pytest.mark.asyncio
    async def test_uses_snapshot_fallback_when_no_transactions(self):
        db = AsyncMock()
        no_tx_result = MagicMock()
        no_tx_result.all.return_value = []

        snap_row = MagicMock()
        snap_row.total = 5000.0
        snap_row.snapshot_date = date(2022, 1, 1)
        snap_result = MagicMock()
        snap_result.first.return_value = snap_row

        db.execute = AsyncMock(side_effect=[no_tx_result, snap_result])

        result, used_snapshot = await calc_xirr(uuid.uuid4(), 6000.0, db)
        assert used_snapshot is True
        assert result is not None

    @pytest.mark.asyncio
    async def test_uses_transaction_cashflows(self):
        db = AsyncMock()
        tx_row = MagicMock()
        tx_row.transaction_date = date(2022, 1, 1)
        tx_row.transaction_type = "DEPOSIT"
        tx_row.amount = 10000.0

        tx_result = MagicMock()
        tx_result.all.return_value = [tx_row]
        db.execute = AsyncMock(return_value=tx_result)

        result, used_snapshot = await calc_xirr(uuid.uuid4(), 11000.0, db)
        assert used_snapshot is False
        assert result is not None

    @pytest.mark.asyncio
    async def test_withdrawal_transaction_adds_positive_cashflow(self):
        db = AsyncMock()
        tx_row = MagicMock()
        tx_row.transaction_date = date(2022, 6, 1)
        tx_row.transaction_type = "WITHDRAWAL"
        tx_row.amount = 2000.0

        tx_result = MagicMock()
        tx_result.all.return_value = [tx_row]
        db.execute = AsyncMock(return_value=tx_result)

        result, used_snapshot = await calc_xirr(uuid.uuid4(), 9000.0, db)
        assert used_snapshot is False
