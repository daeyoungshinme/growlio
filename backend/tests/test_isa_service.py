"""isa_service.py 단위 테스트."""

from __future__ import annotations

import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.isa_service import calc_account_auto_pnl, calc_isa_contribution_status, get_isa_status_summary
from app.utils.kst import today_kst


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


def _position(qty: float, avg_price: float, current_price: float | None, market: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(qty=qty, avg_price=avg_price, current_price=current_price, market=market)


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
        open_date = today_kst() - timedelta(days=365 * 3 + 5)
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
        open_date = today_kst() - timedelta(days=365)
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
    async def test_baseline_delta_added_to_manual_pnl(self, mock_db, make_account, make_user_id, override_settings):
        account_id = uuid.uuid4()
        account = make_account(
            account_id=account_id,
            user_id=make_user_id,
            tax_type="ISA",
            isa_type="GENERAL",
            isa_open_date=None,
            isa_manual_cumulative_pnl_krw=1_000_000.0,
            isa_baseline_auto_pnl_krw=200_000.0,
        )
        # 현재 auto_pnl = 미실현손익 20,000 + 배당 330,000 = 350,000 (baseline 200,000 대비 +150,000)
        snap = _snapshot(account_id, [_position(qty=10, avg_price=10_000, current_price=12_000)])
        mock_db.execute = AsyncMock(
            side_effect=[
                _accounts_result([account]),
                _snapshots_result([snap]),
                _dividend_rows_result([(account_id, 330_000.0)]),
            ]
        )

        result = await get_isa_status_summary(make_user_id, mock_db)

        status = result["accounts"][0]
        assert status["estimated_cumulative_pnl_krw"] == pytest.approx(1_150_000.0)
        assert status["is_manual_override"] is True

    @pytest.mark.asyncio
    async def test_legacy_manual_override_without_baseline_falls_back_to_full_replace(
        self, mock_db, make_account, make_user_id, override_settings
    ):
        account_id = uuid.uuid4()
        account = make_account(
            account_id=account_id,
            user_id=make_user_id,
            tax_type="ISA",
            isa_type="GENERAL",
            isa_open_date=None,
            isa_manual_cumulative_pnl_krw=3_000_000.0,
            isa_baseline_auto_pnl_krw=None,
        )
        # auto_pnl_now(20,000)이 존재하지만 baseline 스냅샷이 없으므로 델타는 무시하고 완전 대체 유지
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

    @pytest.mark.asyncio
    async def test_dividend_heavy_pnl_computes_saved_tax(self, mock_db, make_account, make_user_id, override_settings):
        account_id = uuid.uuid4()
        account = make_account(
            account_id=account_id,
            user_id=make_user_id,
            tax_type="ISA",
            isa_type="GENERAL",
            isa_open_date=None,
            isa_manual_cumulative_pnl_krw=None,
        )
        # 배당소득 3,000,000 → 한도 200만원 초과 100만원 → ISA세금 99,000
        mock_db.execute = AsyncMock(
            side_effect=[
                _accounts_result([account]),
                _snapshots_result([]),
                _dividend_rows_result([(account_id, 3_000_000.0)]),
            ]
        )

        result = await get_isa_status_summary(make_user_id, mock_db)

        status = result["accounts"][0]
        assert status["tax_calculation_basis"] == "AUTO_SPLIT"
        # 일반계좌였다면 배당소득세 15.4% = 462,000
        assert status["general_account_tax_krw"] == pytest.approx(462_000.0)
        assert status["tax_saved_krw"] == pytest.approx(363_000.0)

    @pytest.mark.asyncio
    async def test_overseas_gain_applies_22pct_with_deduction(
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
        # 해외주식 평가익: (20,000-10,000)*1,000 = 10,000,000
        snap = _snapshot(account_id, [_position(qty=1_000, avg_price=10_000, current_price=20_000, market="NASDAQ")])
        mock_db.execute = AsyncMock(
            side_effect=[
                _accounts_result([account]),
                _snapshots_result([snap]),
                _dividend_rows_result([]),
            ]
        )

        result = await get_isa_status_summary(make_user_id, mock_db)

        status = result["accounts"][0]
        assert status["estimated_cumulative_pnl_krw"] == pytest.approx(10_000_000.0)
        # ISA: (10,000,000-2,000,000)*9.9% = 792,000
        assert status["estimated_tax_krw"] == pytest.approx(792_000.0)
        # 일반계좌 해외양도세: (10,000,000-2,500,000)*22% = 1,650,000
        assert status["general_account_tax_krw"] == pytest.approx(1_650_000.0)
        assert status["tax_saved_krw"] == pytest.approx(858_000.0)

    @pytest.mark.asyncio
    async def test_domestic_gain_has_no_general_tax_contribution(
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
        # 국내주식 평가익: (50,000-10,000)*100 = 4,000,000 (일반계좌라도 비과세)
        snap = _snapshot(account_id, [_position(qty=100, avg_price=10_000, current_price=50_000, market="KOSPI")])
        mock_db.execute = AsyncMock(
            side_effect=[
                _accounts_result([account]),
                _snapshots_result([snap]),
                _dividend_rows_result([]),
            ]
        )

        result = await get_isa_status_summary(make_user_id, mock_db)

        status = result["accounts"][0]
        # ISA 저율과세는 부과되지만(한도 초과 200만원 * 9.9% = 198,000), 일반계좌 대비 세금은 0원이므로 절세액도 0
        assert status["estimated_tax_krw"] == pytest.approx(198_000.0)
        assert status["general_account_tax_krw"] == pytest.approx(0.0)
        assert status["tax_saved_krw"] == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_manual_override_uses_simple_approx_fallback(
        self, mock_db, make_account, make_user_id, override_settings
    ):
        account_id = uuid.uuid4()
        account = make_account(
            account_id=account_id,
            user_id=make_user_id,
            tax_type="ISA",
            isa_type="GENERAL",
            isa_open_date=None,
            isa_manual_cumulative_pnl_krw=3_000_000.0,
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
        assert status["tax_calculation_basis"] == "MANUAL_OVERRIDE_APPROX"
        # 수기입력 3,000,000 전체를 배당소득으로 가정 → 15.4% = 462,000
        assert status["general_account_tax_krw"] == pytest.approx(462_000.0)
        assert status["tax_saved_krw"] == pytest.approx(363_000.0)

    @pytest.mark.asyncio
    async def test_negative_pnl_has_zero_tax_and_saved(self, mock_db, make_account, make_user_id, override_settings):
        account_id = uuid.uuid4()
        account = make_account(
            account_id=account_id,
            user_id=make_user_id,
            tax_type="ISA",
            isa_type="GENERAL",
            isa_open_date=None,
            isa_manual_cumulative_pnl_krw=None,
        )
        # 국내주식 평가손: (5,000-10,000)*100 = -500,000
        snap = _snapshot(account_id, [_position(qty=100, avg_price=10_000, current_price=5_000, market="KOSPI")])
        mock_db.execute = AsyncMock(
            side_effect=[
                _accounts_result([account]),
                _snapshots_result([snap]),
                _dividend_rows_result([]),
            ]
        )

        result = await get_isa_status_summary(make_user_id, mock_db)

        status = result["accounts"][0]
        assert status["estimated_tax_krw"] == 0.0
        assert status["general_account_tax_krw"] == 0.0
        assert status["tax_saved_krw"] == 0.0


class TestCalcAccountAutoPnl:
    @pytest.mark.asyncio
    async def test_combines_unrealized_and_dividend_for_single_account(self, mock_db, make_user_id):
        account_id = uuid.uuid4()
        # 미실현손익: (12000-10000)*10 = 20,000
        snap = _snapshot(account_id, [_position(qty=10, avg_price=10_000, current_price=12_000)])
        mock_db.execute = AsyncMock(
            side_effect=[
                _snapshots_result([snap]),
                _dividend_rows_result([(account_id, 30_000.0)]),
            ]
        )

        result = await calc_account_auto_pnl(make_user_id, account_id, mock_db)

        assert result == pytest.approx(50_000.0)

    @pytest.mark.asyncio
    async def test_zero_when_no_snapshot_or_dividend(self, mock_db, make_user_id):
        account_id = uuid.uuid4()
        mock_db.execute = AsyncMock(
            side_effect=[
                _snapshots_result([]),
                _dividend_rows_result([]),
            ]
        )

        result = await calc_account_auto_pnl(make_user_id, account_id, mock_db)

        assert result == pytest.approx(0.0)


class TestCalcIsaContributionStatus:
    @pytest.mark.asyncio
    async def test_no_isa_accounts_returns_empty(self, mock_db):
        mock_db.execute = AsyncMock(return_value=_accounts_result([]))
        assert await calc_isa_contribution_status(uuid.uuid4(), 2026, mock_db) == []

    @pytest.mark.asyncio
    async def test_carryover_and_no_open_date(self, mock_db):
        """가입일 있으면 미납입분 이월(연 2,000만 × 경과연수, 총 1억), 없으면 올해 2,000만만 기준."""
        from datetime import date

        opened = SimpleNamespace(id=uuid.uuid4(), name="ISA 이월", isa_open_date=date(2024, 3, 1))
        capped = SimpleNamespace(id=uuid.uuid4(), name="ISA 총한도", isa_open_date=date(2019, 1, 1))
        no_date = SimpleNamespace(id=uuid.uuid4(), name="ISA 가입일없음", isa_open_date=None)
        mock_db.execute = AsyncMock(
            side_effect=[
                _accounts_result([opened, capped, no_date]),
                _dividend_rows_result(
                    [
                        (opened.id, 25_000_000, 5_000_000),  # 누적 2,500만 / 올해 500만
                        (capped.id, 95_000_000, 0),
                        (no_date.id, 30_000_000, 12_000_000),
                    ]
                ),
            ]
        )

        by_name = {s["account_name"]: s for s in await calc_isa_contribution_status(uuid.uuid4(), 2026, mock_db)}

        assert by_name["ISA 이월"]["available_limit_krw"] == 60_000_000  # 2024~2026 3년
        assert by_name["ISA 이월"]["remaining_krw"] == 35_000_000
        assert by_name["ISA 이월"]["carryover_applied"] is True
        assert by_name["ISA 총한도"]["available_limit_krw"] == 100_000_000  # 8년이지만 총 1억 상한
        assert by_name["ISA 총한도"]["remaining_krw"] == 5_000_000
        assert by_name["ISA 가입일없음"]["remaining_krw"] == 8_000_000  # 2,000만 - 올해 1,200만
        assert by_name["ISA 가입일없음"]["carryover_applied"] is False
