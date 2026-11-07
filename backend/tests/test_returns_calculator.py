"""returns_calculator.py 단위 테스트 — xirr, calc_returns, calc_xirr."""

from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.portfolio.returns_calculator import (
    anchored_cashflows,
    calc_returns,
    calc_xirr,
    xirr,
    xirr_from_cashflows,
)
from app.utils.kst import today_kst


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
        # 결과는 % 단위 — 그 연이율로 할인한 NPV가 0이어야 한다(구현 방식과 무관한 독립 검증, 소수 2자리 반올림 허용)
        t0 = flows[0][0]
        npv = sum(cf / (1 + result / 100) ** ((d - t0).days / 365.0) for d, cf in flows)
        assert abs(npv) < 5.0
        assert 5 < result < 15

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
        today = today_kst()
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

        future = today_kst() + timedelta(days=30)
        annualized, cumulative = calc_returns(10000.0, 5000.0, future)
        assert annualized is None
        assert cumulative is None

    def test_same_day_first_date_returns_none(self):
        annualized, cumulative = calc_returns(10000.0, 5000.0, today_kst())
        assert annualized is None
        assert cumulative is None

    def test_extreme_annualized_near_90_day_floor_clamped_to_none(self):
        from datetime import timedelta

        # 90일 남짓한 기간에 누적 100% 수익률만으로도 (365/91≈4 지수) 연환산이
        # 1000%를 훌쩍 넘김 — xirr()과 동일한 -99~1000 클램프로 None 반환해야 함.
        first_date = today_kst() - timedelta(days=91)
        annualized, cumulative = calc_returns(20000.0, 10000.0, first_date)
        assert annualized is None
        assert cumulative == pytest.approx(100.0, abs=0.1)


def _db(account_ids, tx_rows, opening_rows):
    """calc_xirr 조회 순서: scalars(계좌 id) → execute(입출금) → execute(계좌별 첫 스냅샷)."""
    db = AsyncMock()
    ids = MagicMock()
    ids.all.return_value = account_ids
    db.scalars = AsyncMock(return_value=ids)
    tx = MagicMock()
    tx.all.return_value = tx_rows
    op = MagicMock()
    op.all.return_value = opening_rows
    db.execute = AsyncMock(side_effect=[tx, op])
    return db


def _tx(account_id, d, tx_type, amount):
    return SimpleNamespace(account_id=account_id, transaction_date=d, transaction_type=tx_type, amount=amount)


def _opening(account_id, d, amount):
    return SimpleNamespace(account_id=account_id, snapshot_date=d, amount_krw=amount)


class TestAnchoredCashflows:
    A = uuid.uuid4()
    B = uuid.uuid4()
    TODAY = date(2026, 10, 1)

    def test_opening_balance_is_first_outflow_and_same_day_tx_dropped(self):
        flows = [
            (self.A, date(2025, 10, 1), "DEPOSIT", 999.0),  # 첫 스냅샷 당일 — 스냅샷에 이미 반영
            (self.A, date(2026, 4, 1), "DEPOSIT", 1_000_000.0),
        ]
        openings = {self.A: (date(2025, 10, 1), 50_000_000.0)}
        assert anchored_cashflows(flows, openings, 56_000_000.0, self.TODAY) == [
            (date(2025, 10, 1), -50_000_000.0),
            (date(2026, 4, 1), -1_000_000.0),
            (self.TODAY, 56_000_000.0),
        ]

    def test_history_before_first_snapshot_skips_opening(self):
        """거래 이력이 첫 스냅샷보다 앞서면 이력이 기초 잔액을 설명 — 기초 잔액을 넣으면 이중 계산."""
        flows = [(self.A, date(2024, 1, 1), "DEPOSIT", 10_000.0), (self.A, date(2025, 6, 1), "WITHDRAWAL", 1_000.0)]
        openings = {self.A: (date(2025, 1, 1), 12_000.0)}
        assert anchored_cashflows(flows, openings, 11_000.0, self.TODAY) == [
            (date(2024, 1, 1), -10_000.0),
            (date(2025, 6, 1), 1_000.0),
            (self.TODAY, 11_000.0),
        ]

    def test_unassigned_and_snapshotless_flows_kept(self):
        flows = [(None, date(2025, 3, 1), "DEPOSIT", 100.0), (self.B, date(2025, 2, 1), "DEPOSIT", 200.0)]
        openings = {self.A: (date(2025, 5, 1), 0.0)}  # 0원 기초 잔액은 넣지 않는다
        assert anchored_cashflows(flows, openings, 400.0, self.TODAY) == [
            (date(2025, 2, 1), -200.0),
            (date(2025, 3, 1), -100.0),
            (self.TODAY, 400.0),
        ]

    def test_synced_account_with_small_deposit_gives_sane_xirr(self):
        """plans/116 A1 회귀: 50M 동기화 계좌 + 1달 전 1M 입금. 기초 잔액이 빠지면 XIRR이 범위 밖(None)이 됐다."""
        flows = [(self.B, date(2026, 9, 1), "DEPOSIT", 1_000_000.0)]
        openings = {self.A: (date(2025, 10, 1), 50_000_000.0), self.B: (date(2025, 10, 1), 0.0)}
        result = xirr_from_cashflows(anchored_cashflows(flows, openings, 56_000_000.0, self.TODAY))
        assert result is not None
        assert 8 < result < 12

    def test_all_same_day_returns_none(self):
        assert xirr_from_cashflows([(self.TODAY, -100.0), (self.TODAY, 110.0)]) is None


class TestCalcXirr:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_transactions_no_snapshots(self):
        db = _db([], [], [])
        assert await calc_xirr(uuid.uuid4(), 10000.0, db) == (None, False)

    @pytest.mark.asyncio
    async def test_snapshot_only_is_estimated(self):
        acc = uuid.uuid4()
        db = _db([acc], [], [_opening(acc, date(2022, 1, 1), 5000.0)])
        result, estimated = await calc_xirr(uuid.uuid4(), 6000.0, db)
        assert estimated is True
        assert result is not None
        assert result > 0

    @pytest.mark.asyncio
    async def test_snapshot_from_today_returns_none(self):
        acc = uuid.uuid4()
        db = _db([acc], [], [_opening(acc, today_kst(), 5000.0)])
        assert await calc_xirr(uuid.uuid4(), 6000.0, db) == (None, True)

    @pytest.mark.asyncio
    async def test_transactions_combined_with_opening_balance(self):
        acc = uuid.uuid4()
        start = date(today_kst().year - 1, today_kst().month, 1)
        db = _db(
            [acc],
            [_tx(acc, today_kst().replace(day=1), "DEPOSIT", 1_000_000.0)],
            [_opening(acc, start, 50_000_000.0)],
        )
        result, estimated = await calc_xirr(uuid.uuid4(), 56_000_000.0, db)
        assert estimated is False
        assert result is not None
        assert 0 < result < 20

    @pytest.mark.asyncio
    async def test_withdrawal_only_transactions_without_snapshot(self):
        db = _db(
            [], [_tx(None, date(2022, 1, 1), "DEPOSIT", 10000.0), _tx(None, date(2022, 6, 1), "WITHDRAWAL", 2000.0)], []
        )
        result, estimated = await calc_xirr(uuid.uuid4(), 9000.0, db)
        assert estimated is False
        assert result is not None
