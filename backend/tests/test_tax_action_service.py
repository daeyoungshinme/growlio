"""tax_action_service.py 테스트 — 절세 액션 플랜(A1~A6) 조합·우선순위."""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.tax_action_service import (
    _DEDUCTION_RULES,
    _priority,
    _sort_actions,
    build_financial_income_action,
    build_isa_contribution_actions,
    build_isa_transfer_actions,
    build_loss_harvest_actions,
    build_overseas_gain_harvest_action,
    build_pension_action,
    get_tax_action_plan,
    pension_credit_rate,
)

RULES = _DEDUCTION_RULES[2026]
TODAY = date(2026, 10, 15)


def _pension(total_remaining: float, ps_remaining: float) -> dict:
    return {
        "year": 2026,
        "pension_savings_deposit_krw": 6_000_000 - ps_remaining,
        "irp_deposit_krw": 0.0,
        "total_deposit_krw": 9_000_000 - total_remaining,
        "pension_savings_limit_krw": 6_000_000,
        "total_limit_krw": 9_000_000,
        "pension_savings_achievement_pct": 0.0,
        "total_achievement_pct": 0.0,
        "pension_savings_remaining_krw": ps_remaining,
        "total_remaining_krw": total_remaining,
        "note": "",
    }


def _isa_account(maturity: str | None, account_id: str = "isa-1") -> dict:
    return {"account_id": account_id, "account_name": "ISA계좌", "maturity_date": maturity}


class TestPensionCreditRate:
    def test_under_55m_uses_high_rate(self):
        assert pension_credit_rate("UNDER_55M", RULES) == 0.165

    @pytest.mark.parametrize("bracket", ["OVER_55M", None])
    def test_over_or_missing_uses_conservative_rate(self, bracket):
        assert pension_credit_rate(bracket, RULES) == 0.132


class TestBuildPensionAction:
    def test_none_when_remaining_zero(self):
        assert build_pension_action(_pension(0, 0), True, True, 0.132, None, TODAY) is None

    def test_none_without_pension_accounts(self):
        assert build_pension_action(_pension(9_000_000, 6_000_000), False, False, 0.132, None, TODAY) is None

    def test_irp_fills_total_remaining_with_monthly_split(self):
        action = build_pension_action(_pension(3_000_000, 1_000_000), True, True, 0.165, "UNDER_55M", TODAY)
        assert action is not None
        assert action["amount_krw"] == 3_000_000
        assert action["benefit_krw"] == 495_000  # 300만 × 16.5%
        assert action["deadline"] == "2026-12-31"
        assert "매월 약 1,000,000원" in action["detail"]  # 10~12월 3개월 분할
        assert "소득 구간을 입력하면" not in action["detail"]

    def test_pension_savings_only_capped_at_600(self):
        action = build_pension_action(_pension(5_000_000, 2_000_000), True, False, 0.132, None, TODAY)
        assert action is not None
        assert action["amount_krw"] == 2_000_000
        assert action["benefit_krw"] == 264_000
        assert "소득 구간을 입력하면" in action["detail"]
        assert action["uses_income_bracket"] is True

    def test_december_has_no_split_note(self):
        action = build_pension_action(_pension(1_000_000, 0), False, True, 0.132, None, date(2026, 12, 20))
        assert action is not None
        assert "매월" not in action["detail"]
        assert action["priority"] == "HIGH"  # 마감 D-11


class TestBuildIsaTransferActions:
    @pytest.mark.parametrize(
        ("maturity", "expected"),
        [
            ("2027-01-23", 0),  # D-100 — 아직 안내 전
            ("2026-11-14", 1),  # D-30
            ("2026-09-01", 1),  # 만기 후 44일
            ("2026-08-01", 0),  # 만기 후 75일 — 60일 경과
            (None, 0),  # 가입일 미입력
        ],
    )
    def test_window(self, maturity, expected):
        actions = build_isa_transfer_actions([_isa_account(maturity)], RULES, 0.132, None, TODAY)
        assert len(actions) == expected

    def test_benefit_and_deadline(self):
        (action,) = build_isa_transfer_actions([_isa_account("2026-11-14")], RULES, 0.165, "UNDER_55M", TODAY)
        assert action["benefit_krw"] == 495_000  # 300만 × 16.5%
        assert action["amount_krw"] == 30_000_000
        assert action["deadline"] == "2027-01-13"  # 만기 + 60일
        assert action["category"] == "ISA_PENSION_TRANSFER"


class TestBuildIsaContributionActions:
    def test_skips_full_and_mentions_carryover(self):
        contrib = [
            {"account_id": "a", "account_name": "ISA A", "remaining_krw": 0.0, "carryover_applied": False},
            {"account_id": "b", "account_name": "ISA B", "remaining_krw": 25_000_000.0, "carryover_applied": True},
        ]
        actions = build_isa_contribution_actions(contrib, TODAY)
        assert len(actions) == 1
        assert actions[0]["amount_krw"] == 25_000_000
        assert actions[0]["benefit_krw"] is None
        assert "이월 포함" in actions[0]["detail"]


class TestBuildOverseasGainHarvestAction:
    def test_capped_at_deduction(self):
        positions = [{"unrealized_pnl_krw": 4_000_000}, {"unrealized_pnl_krw": -1_000_000}]
        action = build_overseas_gain_harvest_action(positions, 2_500_000, 0.22, TODAY)
        assert action is not None
        assert action["amount_krw"] == 2_500_000
        assert action["benefit_krw"] == 550_000

    def test_uses_positive_gains_only(self):
        positions = [{"unrealized_pnl_krw": 1_000_000}, {"unrealized_pnl_krw": -3_000_000}]
        action = build_overseas_gain_harvest_action(positions, 2_500_000, 0.22, TODAY)
        assert action is not None
        assert action["amount_krw"] == 1_000_000

    def test_none_without_gains(self):
        assert build_overseas_gain_harvest_action([{"unrealized_pnl_krw": -5}], 2_500_000, 0.22, TODAY) is None


class TestBuildLossHarvestActions:
    def test_top3(self):
        harvesting = [
            {"ticker": t, "name": t, "unrealized_loss_krw": -1_000_000, "tax_saved_krw": 220_000} for t in "ABCD"
        ]
        actions = build_loss_harvest_actions(harvesting, TODAY)
        assert [a["id"] for a in actions] == ["loss-harvest-A", "loss-harvest-B", "loss-harvest-C"]
        assert actions[0]["amount_krw"] == 1_000_000
        assert actions[0]["benefit_krw"] == 220_000


class TestBuildFinancialIncomeAction:
    def test_none_below_watch_line(self):
        assert (
            build_financial_income_action(
                {"dividend_income_krw": 14_999_999, "comprehensive_tax_remaining_krw": 5_000_001}, TODAY
            )
            is None
        )

    def test_near_threshold(self):
        action = build_financial_income_action(
            {"dividend_income_krw": 16_000_000, "comprehensive_tax_remaining_krw": 4_000_000}, TODAY
        )
        assert action is not None
        assert action["amount_krw"] == 4_000_000
        assert "4,000,000원 남음" in action["title"]

    def test_over_threshold(self):
        action = build_financial_income_action(
            {"dividend_income_krw": 21_000_000, "comprehensive_tax_remaining_krw": 0}, TODAY
        )
        assert action is not None
        assert action["amount_krw"] is None
        assert "대상 가능성" in action["title"]


class TestPriorityAndSort:
    def test_priority_by_deadline_or_benefit(self):
        assert _priority(date(2026, 11, 1), 0, TODAY) == "HIGH"
        assert _priority(date(2026, 12, 31), 0, TODAY) == "MEDIUM"
        assert _priority(None, 600_000, TODAY) == "HIGH"
        assert _priority(None, 150_000, TODAY) == "MEDIUM"
        assert _priority(None, None, TODAY) == "LOW"

    def test_sort_priority_then_deadline_then_benefit(self):
        def a(aid, priority, deadline, benefit):
            return {"id": aid, "priority": priority, "deadline": deadline, "benefit_krw": benefit}

        actions = [
            a("low", "LOW", None, None),
            a("med-big", "MEDIUM", "2026-12-31", 300_000),
            a("high-later", "HIGH", "2026-12-31", 900_000),
            a("high-sooner", "HIGH", "2026-11-01", 10),
            a("med-small", "MEDIUM", "2026-12-31", 100_000),
        ]
        ordered = [x["id"] for x in _sort_actions(actions)]
        assert ordered == ["high-sooner", "high-later", "med-big", "med-small", "low"]


def _result(scalar=None, rows=None) -> MagicMock:
    r = MagicMock()
    r.scalar.return_value = scalar
    r.all.return_value = rows or []
    return r


_TAX_SUMMARY = {
    "dividend_income_krw": 0,
    "comprehensive_tax_remaining_krw": 20_000_000,
    "overseas_gain_deduction_krw": 2_500_000,
    "rates": {"overseas_tax_rate_pct": 22.0},
    "harvesting_recommendations": [],
}


class TestGetTaxActionPlan:
    @pytest.mark.asyncio
    async def test_combines_services_and_skips_absent_account_types(self, mock_db):
        """ISA 계좌가 없으면 ISA 서비스를 호출하지 않고, 연금 액션은 저장된 소득 구간 공제율을 쓴다."""
        mock_db.execute = AsyncMock(side_effect=[_result(scalar="UNDER_55M"), _result(rows=[("IRP",), ("GENERAL",)])])
        isa_mock = AsyncMock()
        with (
            patch(
                "app.services.tax_action_service.today_kst",
                return_value=TODAY,
            ),
            patch(
                "app.services.tax_action_service.calc_pension_contribution_status",
                new=AsyncMock(return_value=_pension(2_000_000, 6_000_000)),
            ),
            patch("app.services.tax_action_service.get_isa_status_summary", new=isa_mock),
            patch(
                "app.services.tax_action_service.get_tax_summary",
                new=AsyncMock(return_value=_TAX_SUMMARY),
            ),
            patch(
                "app.services.tax_action_service.get_overseas_positions_detail",
                new=AsyncMock(return_value=[{"unrealized_pnl_krw": 1_000_000}]),
            ),
        ):
            plan = await get_tax_action_plan(uuid.uuid4(), 2026, mock_db)

        isa_mock.assert_not_called()
        assert plan["income_bracket"] == "UNDER_55M"
        assert [a["category"] for a in plan["actions"]] == ["PENSION_DEDUCTION", "OVERSEAS_GAIN_HARVEST"]
        assert plan["actions"][0]["benefit_krw"] == 330_000  # 200만 × 16.5%

    @pytest.mark.asyncio
    async def test_empty_when_nothing_actionable(self, mock_db):
        mock_db.execute = AsyncMock(side_effect=[_result(scalar=None), _result(rows=[])])
        with (
            patch(
                "app.services.tax_action_service.get_tax_summary",
                new=AsyncMock(return_value=_TAX_SUMMARY),
            ),
            patch(
                "app.services.tax_action_service.get_overseas_positions_detail",
                new=AsyncMock(return_value=[]),
            ),
        ):
            plan = await get_tax_action_plan(uuid.uuid4(), 2026, mock_db)

        assert plan["actions"] == []
        assert plan["income_bracket"] is None
