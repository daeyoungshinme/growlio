"""계획 110 배치 B — 세금 수치가 실제 공제·결제 규칙과 어긋나던 경로."""

from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.tax.pension_contribution_service import calc_pension_contribution_status
from app.services.tax.tax_action_service import (
    _get_rules,
    build_financial_income_action,
    build_isa_transfer_actions,
    build_loss_harvest_actions,
    build_overseas_gain_harvest_action,
    build_pension_action,
    overseas_sell_deadline,
)
from app.services.tax.tax_service import (
    _calc_health_insurance_estimate,
    _largest_domestic_holding,
    is_paper_account,
)

TODAY = date(2026, 11, 5)
RULES = _get_rules(2026)
DEDUCTION = 2_500_000


def _pension_db(rows: list[tuple[str, float]]) -> AsyncMock:
    result = MagicMock()
    result.all.return_value = rows
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)
    return db


class TestPensionLimit:
    """B1 — 연금저축 600만원 초과분은 합산 한도(900만원)를 쓰지 않는다."""

    async def test_over_contribution_keeps_irp_room(self):
        status = await calc_pension_contribution_status(
            uuid.uuid4(), 2026, _pension_db([("PENSION_SAVINGS", 8_000_000.0)])
        )
        assert status["total_remaining_krw"] == 3_000_000
        assert status["total_credited_krw"] == 6_000_000
        assert status["total_deposit_krw"] == 8_000_000  # 실제 납입액은 그대로 보여준다
        assert status["total_achievement_pct"] == pytest.approx(66.7)

    async def test_action_recommends_irp_room(self):
        status = await calc_pension_contribution_status(
            uuid.uuid4(), 2026, _pension_db([("PENSION_SAVINGS", 8_000_000.0)])
        )
        action = build_pension_action(status, True, True, 0.132, None, TODAY)
        assert action is not None
        assert action["amount_krw"] == 3_000_000
        assert action["benefit_krw"] == 396_000
        assert "IRP" in action["title"]

    async def test_within_limit_unchanged(self):
        status = await calc_pension_contribution_status(
            uuid.uuid4(), 2026, _pension_db([("PENSION_SAVINGS", 4_000_000.0), ("IRP", 2_000_000.0)])
        )
        assert status["total_remaining_krw"] == 3_000_000
        assert status["total_credited_krw"] == 6_000_000

    async def test_deleted_accounts_count(self):
        """B3 — 삭제 계좌의 올해 납입도 실제 납입이다(세금 집계 기준, plans/60·95)."""
        db = _pension_db([])
        await calc_pension_contribution_status(uuid.uuid4(), 2026, db)
        assert "is_active" not in str(db.execute.await_args.args[0])


class TestRealizedLookupFailure:
    """B2 — KIS 조회 실패를 실현손익 0으로 보고 "더 실현해도 된다"고 안내하면 안 된다."""

    positions = [{"unrealized_pnl_krw": 5_000_000}]

    def test_failure_shows_no_amount(self):
        action = build_overseas_gain_harvest_action(
            self.positions, DEDUCTION, 0.22, TODAY, realized_krw=None, realized_lookup_failed=True
        )
        assert action is not None
        assert action["amount_krw"] is None
        assert action["benefit_krw"] is None
        assert "확인하지 못했어요" in action["title"]
        assert "0원" not in action["title"]

    def test_partial_failure_also_shows_no_amount(self):
        """일부 계좌만 성공한 합계도 믿을 수 없다."""
        action = build_overseas_gain_harvest_action(
            self.positions, DEDUCTION, 0.22, TODAY, realized_krw=100_000.0, realized_lookup_failed=True
        )
        assert action is not None
        assert action["amount_krw"] is None

    def test_no_gains_no_action_even_on_failure(self):
        assert (
            build_overseas_gain_harvest_action(
                [{"unrealized_pnl_krw": -1}], DEDUCTION, 0.22, TODAY, realized_lookup_failed=True
            )
            is None
        )

    def test_success_does_not_promise_zero_tax(self):
        """B9 — 환차익이 빠진 추정이라 "양도세 0원"으로 단정하지 않는다."""
        action = build_overseas_gain_harvest_action(self.positions, DEDUCTION, 0.22, TODAY, realized_krw=0.0)
        assert action is not None
        assert action["amount_krw"] == DEDUCTION
        assert "양도세 0원" not in action["title"]
        assert "환차익" in action["detail"]


class TestIsaTransferBenefit:
    """B4 — 혜택은 옮길 수 있는 금액의 10%다. 잔액과 무관한 최대치를 보여주면 안 된다."""

    def _action(self, balances):
        account = {"account_id": "a", "account_name": "ISA", "maturity_date": "2026-11-14"}
        (action,) = build_isa_transfer_actions([account], RULES, 0.132, None, TODAY, balances)  # type: ignore[list-item]
        return action

    def test_small_balance(self):
        action = self._action({"a": 10_000_000.0})
        assert action["amount_krw"] == 10_000_000
        assert action["benefit_krw"] == 132_000  # 100만 × 13.2%

    def test_large_balance_is_capped(self):
        action = self._action({"a": 50_000_000.0})
        assert action["amount_krw"] == 30_000_000
        assert action["benefit_krw"] == 396_000  # 300만 × 13.2%

    @pytest.mark.parametrize("balances", [None, {}, {"a": 0.0}])
    def test_unknown_balance_shows_no_amount(self, balances):
        action = self._action(balances)
        assert action["amount_krw"] is None
        assert action["benefit_krw"] is None


class TestLossHarvestBenefit:
    """B5 — 손실만 팔면 올해 줄어드는 세금은 이미 실현한 과세 이익만큼뿐이다."""

    harvesting = [
        {"ticker": "A", "name": "A", "account_id": "x", "unrealized_loss_krw": -3_000_000, "tax_saved_krw": 660_000}
    ]

    def _action(self, realized):
        (action,) = build_loss_harvest_actions(
            self.harvesting, TODAY, realized_krw=realized, deduction_krw=DEDUCTION, gain_tax_rate=0.22
        )
        return action

    def test_no_realized_gain_means_no_saving_this_year(self):
        action = self._action(0.0)
        assert action["benefit_krw"] is None
        assert "줄지 않아요" in action["detail"]

    def test_saving_limited_to_realized_taxable_gain(self):
        action = self._action(3_500_000.0)  # 과세 이익 100만 → 22만
        assert action["benefit_krw"] == 220_000

    def test_saving_limited_to_loss(self):
        action = self._action(20_000_000.0)  # 손실 300만 × 22%
        assert action["benefit_krw"] == 660_000

    def test_unknown_realized(self):
        action = self._action(None)
        assert action["benefit_krw"] is None
        assert "확인하지 못해" in action["detail"]

    def test_taxable_gain_is_not_counted_twice(self):
        items = [
            {"ticker": t, "name": t, "account_id": "x", "unrealized_loss_krw": -1_000_000, "tax_saved_krw": 0}
            for t in "AB"
        ]
        actions = build_loss_harvest_actions(
            items, TODAY, realized_krw=4_000_000.0, deduction_krw=DEDUCTION, gain_tax_rate=0.22
        )
        assert [a["benefit_krw"] for a in actions] == [220_000, 110_000]

    def test_same_ticker_in_two_accounts_has_unique_ids(self):
        items = [
            {"ticker": "A", "name": "A", "account_id": acc, "unrealized_loss_krw": -1, "tax_saved_krw": 0}
            for acc in ("x", "y")
        ]
        ids = [a["id"] for a in build_loss_harvest_actions(items, TODAY)]
        assert len(set(ids)) == 2


class TestSellDeadline:
    """B6 — 양도세는 결제일 기준이라 12/31에 팔면 내년 귀속이다."""

    @pytest.mark.parametrize(
        ("year", "expected"), [(2026, date(2026, 12, 28)), (2027, date(2027, 12, 27)), (2028, date(2028, 12, 25))]
    )
    def test_last_monday_of_december(self, year, expected):
        assert overseas_sell_deadline(year) == expected
        assert overseas_sell_deadline(year).weekday() == 0

    def test_actions_use_deadline(self):
        action = build_overseas_gain_harvest_action([{"unrealized_pnl_krw": 1_000_000}], DEDUCTION, 0.22, TODAY)
        assert action is not None
        assert action["deadline"] == "2026-12-28"

    def test_actions_disappear_after_deadline(self):
        late = date(2026, 12, 29)
        assert build_overseas_gain_harvest_action([{"unrealized_pnl_krw": 1_000_000}], DEDUCTION, 0.22, late) is None
        item = {"ticker": "A", "name": "A", "unrealized_loss_krw": -1, "tax_saved_krw": 0}
        assert build_loss_harvest_actions([item], late) == []

    def test_action_available_on_deadline_day(self):
        action = build_overseas_gain_harvest_action(
            [{"unrealized_pnl_krw": 1_000_000}], DEDUCTION, 0.22, date(2026, 12, 28)
        )
        assert action is not None


def _pos(ticker, value, market="KOSPI", name=None):
    return SimpleNamespace(
        ticker=ticker, name=name or ticker, market=market, qty=1, avg_price=value, current_price=value
    )


def _row(*positions, tax_type="GENERAL"):
    return SimpleNamespace(position_items=list(positions)), SimpleNamespace(tax_type=tax_type)


class TestLargeHolder:
    """B7 — 대주주 판정은 전체 합계가 아니라 종목별이다."""

    def test_spread_holdings_are_compared_per_ticker(self):
        rows = [_row(*(_pos(f"T{i}", 240_000_000.0) for i in range(5)))]  # 합계 12억, 종목당 2.4억
        assert _largest_domestic_holding(rows)[1] == 240_000_000.0

    def test_same_ticker_is_summed_across_accounts(self):
        rows = [_row(_pos("005930", 3e9, name="삼성전자")), _row(_pos("005930", 2e9, name="삼성전자"), tax_type="ISA")]
        assert _largest_domestic_holding(rows) == ("삼성전자", 5e9)

    def test_overseas_is_ignored(self):
        assert _largest_domestic_holding([_row(_pos("AAPL", 9e9, market="NASDAQ"))]) == (None, 0.0)

    def test_empty(self):
        assert _largest_domestic_holding([]) == (None, 0.0)


class TestPaperAccount:
    """B10 — 모의투자 손익은 소득이 아니다. 단 컬럼 기본값이 True라 토스·수기 계좌를 빼면 안 된다."""

    @pytest.mark.parametrize(
        ("mock", "asset_type", "source", "expected"),
        [
            (True, "STOCK_KIS", "KIS_API", True),
            (True, "STOCK_KIWOOM", "KIWOOM_API", True),
            (False, "STOCK_KIS", "KIS_API", False),
            (True, "STOCK_TOSS", "TOSS_API", False),  # 토스에는 모의투자가 없다
            (True, "STOCK_KIS", "MANUAL", False),
            (True, "STOCK_MANUAL", "MANUAL", False),
        ],
    )
    def test_cases(self, mock, asset_type, source, expected):
        acc = SimpleNamespace(is_mock_mode=mock, asset_type=asset_type, data_source=source)
        assert is_paper_account(acc) is expected


class TestComprehensiveThreshold:
    """B11 — 2,000만원 "초과"가 기준이다."""

    def test_health_insurance_at_exact_threshold(self):
        result = _calc_health_insurance_estimate(20_000_000.0, 2026)
        assert result["dependent_risk_warning"] is False
        assert result["estimated_monthly_premium_krw"] is None

    def test_health_insurance_above_threshold(self):
        assert _calc_health_insurance_estimate(20_000_001.0, 2026)["dependent_risk_warning"] is True

    @pytest.mark.parametrize(("year", "rate", "care"), [(2025, 0.0709, 0.1295), (2026, 0.0719, 0.1314)])
    def test_premium_uses_rate_of_year(self, year, rate, care):
        result = _calc_health_insurance_estimate(30_000_000.0, year)
        expected = round((30_000_000.0 - 3_360_000.0) / 12 * rate * (1 + care), 0)
        assert result["estimated_monthly_premium_krw"] == expected

    def test_action_at_exact_threshold_is_not_over(self):
        action = build_financial_income_action(
            {"dividend_income_krw": 20_000_000, "comprehensive_tax_remaining_krw": 0}, TODAY
        )
        assert action is not None
        assert "남음" in action["title"]

    def test_action_above_threshold(self):
        action = build_financial_income_action(
            {"dividend_income_krw": 20_000_001, "comprehensive_tax_remaining_krw": 0}, TODAY
        )
        assert action is not None
        assert action["title"] == "금융소득 종합과세 대상 가능성"
