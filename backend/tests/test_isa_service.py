"""isa_service.py 단위 테스트."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.isa_service import get_isa_status_summary


def _accounts_result(accounts: list) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = accounts
    return result


def _snapshots_result(snapshots: list) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = snapshots
    return result


def _dividend_rows_result(rows: list) -> MagicMock:
    result = MagicMock()
    result.all.return_value = rows
    return result


def _position(qty: float, avg_price: float, current_price: float | None) -> SimpleNamespace:
    return SimpleNamespace(qty=qty, avg_price=avg_price, current_price=current_price)


def _snapshot(account_id: uuid.UUID, positions: list) -> SimpleNamespace:
    return SimpleNamespace(account_id=account_id, position_items=positions)


class TestGetIsaStatusSummary:
    @pytest.mark.asyncio
    async def test_no_isa_accounts_returns_empty_list(self, mock_db, make_user_id, override_settings):
        mock_db.execute = AsyncMock(return_value=_accounts_result([]))

        result = await get_isa_status_summary(make_user_id, mock_db)

        assert result["accounts"] == []
        assert "추정치" in result["note"]

    @pytest.mark.asyncio
    async def test_missing_open_date_flags_needs_open_date(
        self, mock_db, make_account, make_user_id, override_settings
    ):
        account_id = uuid.uuid4()
        account = make_account(
            account_id=account_id,
            user_id=make_user_id,
            tax_type="ISA",
            isa_type="GENERAL",
            isa_open_date=None,
            isa_manual_cumulative_pnl_krw=None,
        )
        mock_db.execute = AsyncMock(
            side_effect=[
                _accounts_result([account]),
                _snapshots_result([]),
                _dividend_rows_result([]),
            ]
        )

        result = await get_isa_status_summary(make_user_id, mock_db)

        status = result["accounts"][0]
        assert status["needs_open_date"] is True
        assert status["maturity_date"] is None
        assert status["is_mature"] is False

    @pytest.mark.asyncio
    async def test_mature_when_three_years_elapsed(self, mock_db, make_account, make_user_id, override_settings):
        account_id = uuid.uuid4()
        open_date = date.today() - timedelta(days=365 * 3 + 5)
        account = make_account(
            account_id=account_id,
            user_id=make_user_id,
            tax_type="ISA",
            isa_type="GENERAL",
            isa_open_date=open_date,
            isa_manual_cumulative_pnl_krw=None,
        )
        mock_db.execute = AsyncMock(
            side_effect=[
                _accounts_result([account]),
                _snapshots_result([]),
                _dividend_rows_result([]),
            ]
        )

        result = await get_isa_status_summary(make_user_id, mock_db)

        status = result["accounts"][0]
        assert status["is_mature"] is True
        assert status["days_remaining"] == 0

    @pytest.mark.asyncio
    async def test_not_mature_before_three_years(self, mock_db, make_account, make_user_id, override_settings):
        account_id = uuid.uuid4()
        open_date = date.today() - timedelta(days=365)
        account = make_account(
            account_id=account_id,
            user_id=make_user_id,
            tax_type="ISA",
            isa_type="GENERAL",
            isa_open_date=open_date,
            isa_manual_cumulative_pnl_krw=None,
        )
        mock_db.execute = AsyncMock(
            side_effect=[
                _accounts_result([account]),
                _snapshots_result([]),
                _dividend_rows_result([]),
            ]
        )

        result = await get_isa_status_summary(make_user_id, mock_db)

        status = result["accounts"][0]
        assert status["is_mature"] is False
        assert status["days_remaining"] > 0

    @pytest.mark.asyncio
    async def test_auto_pnl_combines_unrealized_and_dividend(
        self, mock_db, make_account, make_user_id, override_settings
    ):
        account_id = uuid.uuid4()
        account = make_account(
            account_id=account_id,
            user_id=make_user_id,
            tax_type="ISA",
            isa_type="GENERAL",
            isa_open_date=None,
            isa_manual_cumulative_pnl_krw=None,
        )
        # 미실현손익: (12000-10000)*10 = 20,000
        snap = _snapshot(account_id, [_position(qty=10, avg_price=10_000, current_price=12_000)])
        mock_db.execute = AsyncMock(
            side_effect=[
                _accounts_result([account]),
                _snapshots_result([snap]),
                _dividend_rows_result([(account_id, 30_000.0)]),
            ]
        )

        result = await get_isa_status_summary(make_user_id, mock_db)

        status = result["accounts"][0]
        assert status["estimated_cumulative_pnl_krw"] == pytest.approx(50_000.0)
        assert status["is_manual_override"] is False

    @pytest.mark.asyncio
    async def test_manual_override_takes_precedence(self, mock_db, make_account, make_user_id, override_settings):
        account_id = uuid.uuid4()
        account = make_account(
            account_id=account_id,
            user_id=make_user_id,
            tax_type="ISA",
            isa_type="GENERAL",
            isa_open_date=None,
            isa_manual_cumulative_pnl_krw=3_000_000.0,
        )
        snap = _snapshot(account_id, [_position(qty=10, avg_price=10_000, current_price=12_000)])
        mock_db.execute = AsyncMock(
            side_effect=[
                _accounts_result([account]),
                _snapshots_result([snap]),
                _dividend_rows_result([]),
            ]
        )

        result = await get_isa_status_summary(make_user_id, mock_db)

        status = result["accounts"][0]
        assert status["estimated_cumulative_pnl_krw"] == pytest.approx(3_000_000.0)
        assert status["is_manual_override"] is True

    @pytest.mark.asyncio
    async def test_general_limit_excess_taxed_at_9_9_pct(self, mock_db, make_account, make_user_id, override_settings):
        account_id = uuid.uuid4()
        account = make_account(
            account_id=account_id,
            user_id=make_user_id,
            tax_type="ISA",
            isa_type="GENERAL",
            isa_open_date=None,
            isa_manual_cumulative_pnl_krw=3_000_000.0,  # 한도 200만원 초과 100만원
        )
        mock_db.execute = AsyncMock(
            side_effect=[
                _accounts_result([account]),
                _snapshots_result([]),
                _dividend_rows_result([]),
            ]
        )

        result = await get_isa_status_summary(make_user_id, mock_db)

        status = result["accounts"][0]
        assert status["tax_free_limit_krw"] == 2_000_000
        assert status["taxable_excess_krw"] == pytest.approx(1_000_000.0)
        assert status["estimated_tax_krw"] == pytest.approx(99_000.0)

    @pytest.mark.asyncio
    async def test_preferential_limit_is_higher(self, mock_db, make_account, make_user_id, override_settings):
        account_id = uuid.uuid4()
        account = make_account(
            account_id=account_id,
            user_id=make_user_id,
            tax_type="ISA",
            isa_type="PREFERENTIAL",
            isa_open_date=None,
            isa_manual_cumulative_pnl_krw=3_000_000.0,  # 한도 400만원 이내 → 세금 없음
        )
        mock_db.execute = AsyncMock(
            side_effect=[
                _accounts_result([account]),
                _snapshots_result([]),
                _dividend_rows_result([]),
            ]
        )

        result = await get_isa_status_summary(make_user_id, mock_db)

        status = result["accounts"][0]
        assert status["tax_free_limit_krw"] == 4_000_000
        assert status["taxable_excess_krw"] == 0.0
        assert status["estimated_tax_krw"] == 0.0
