"""홈 "지금 할 일" 집계 (docs/plans/50 M5)."""

from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.challenge import ChallengeSummary
from app.services import action_items_service as svc


def _drift(needs=True, name="성장형"):
    return SimpleNamespace(
        portfolio_id=uuid.uuid4(),
        portfolio_name=name,
        needs_rebalancing=needs,
        max_drift_pct=7.4,
        drifted_items_count=2,
        threshold_pct=5.0,
    )


def _shortfall(days_until=2, expected=1_000_000.0, cash=300_000.0):
    return SimpleNamespace(
        alert=SimpleNamespace(id=uuid.uuid4()),
        portfolio=SimpleNamespace(id=uuid.uuid4(), name="적립식"),
        account=SimpleNamespace(name="키움"),
        run_date=date(2026, 11, 25),
        days_until=days_until,
        cash_krw=cash,
        expected_krw=expected,
    )


def _tax_action(priority="MEDIUM", deadline="2026-12-31", category="PENSION_DEDUCTION"):
    return {
        "id": "pension",
        "category": category,
        "title": "연금 추가 납입",
        "detail": "공제 한도까지 300만원 남음",
        "amount_krw": 3_000_000.0,
        "benefit_krw": 495_000.0,
        "deadline": deadline,
        "priority": priority,
        "uses_income_bracket": True,
        "cta": {"label": "계좌 보기", "link": "/assets?tab=계좌관리"},
    }


def _tax_summary(**warnings):
    return {
        "health_insurance_estimate": {"dependent_risk_warning": warnings.get("dependent", False)},
        "comprehensive_tax_warning": warnings.get("comprehensive", False),
        "domestic_large_holder_warning": warnings.get("large_holder", False),
        "domestic_large_holder_excess_krw": warnings.get("excess", 0.0),
    }


async def _run(*, drift=None, dca=None, tax=None, challenge=None, today=date(2026, 11, 23)):
    db = MagicMock()
    db.rollback = AsyncMock()
    with (
        patch.object(svc, "get_drift_summaries", new=drift or AsyncMock(return_value=[])),
        patch.object(svc, "find_dca_cash_shortfalls", new=dca or AsyncMock(return_value=[])),
        patch.object(
            svc,
            "get_tax_action_plan_with_summary",
            new=tax or AsyncMock(return_value=({"actions": []}, _tax_summary())),
        ),
        patch.object(
            svc,
            "get_challenge_summary",
            new=challenge or AsyncMock(return_value=ChallengeSummary(needs_attention=False, count=0)),
        ),
        patch.object(svc, "today_kst", return_value=today),
    ):
        items = await svc.get_action_items(uuid.uuid4(), db, None)
    return items, db


@pytest.mark.asyncio
async def test_empty_when_no_signals():
    items, _ = await _run()
    assert items == []


@pytest.mark.asyncio
async def test_rebalance_only_for_portfolios_needing_it():
    drifts = [_drift(True, "성장형"), _drift(False, "배당형")]
    items, _ = await _run(drift=AsyncMock(return_value=drifts))
    assert [i.kind for i in items] == ["REBALANCE"]
    item = items[0]
    assert item.title == "성장형 리밸런싱 필요"
    assert "7.4%p" in item.detail
    assert item.link == f"/rebalancing?rtab=포트폴리오&portfolioId={drifts[0].portfolio_id}"


@pytest.mark.parametrize(("days_until", "priority"), [(2, "HIGH"), (3, "HIGH"), (10, "MEDIUM")])
@pytest.mark.asyncio
async def test_dca_shortfall_priority_by_days_until(days_until, priority):
    sf = _shortfall(days_until=days_until)
    items, _ = await _run(dca=AsyncMock(return_value=[sf]))
    assert items[0].kind == "DCA_SHORTFALL"
    assert items[0].priority == priority
    assert "700,000원 부족" in items[0].detail
    assert items[0].deadline == "2026-11-25"
    assert items[0].link.endswith(f"portfolioId={sf.portfolio.id}&openAlert=1")


@pytest.mark.asyncio
async def test_dca_shortfall_without_monthly_amount():
    items, _ = await _run(dca=AsyncMock(return_value=[_shortfall(expected=None, cash=5_000.0)]))
    assert "매수할 예수금이 거의 없어요" in items[0].detail


@pytest.mark.asyncio
async def test_tax_warning_and_top_action():
    tax = AsyncMock(
        return_value=({"actions": [_tax_action(), _tax_action(priority="LOW")]}, _tax_summary(comprehensive=True))
    )
    items, _ = await _run(tax=tax)
    assert [i.kind for i in items] == ["TAX_WARNING", "TAX_ACTION"]  # 1순위 액션만
    assert items[0].title == "금융소득 종합과세 대상 가능"
    assert items[1].cta_label == "계좌 보기"
    assert items[1].link == "/assets?tab=계좌관리"


@pytest.mark.asyncio
async def test_tax_warning_priority_order_matches_frontend():
    tax = AsyncMock(return_value=({"actions": []}, _tax_summary(dependent=True, comprehensive=True)))
    items, _ = await _run(tax=tax)
    assert items[0].title == "건강보험 피부양자 자격 상실 위험"

    tax = AsyncMock(return_value=({"actions": []}, _tax_summary(large_holder=True, excess=12_000_000.0)))
    items, _ = await _run(tax=tax)
    assert items[0].title == "국내주식 대주주요건 주의 (12,000,000원 초과)"


@pytest.mark.asyncio
async def test_challenge_item_with_month_end_deadline():
    challenge = AsyncMock(return_value=ChallengeSummary(needs_attention=True, count=2))
    items, _ = await _run(challenge=challenge, today=date(2026, 2, 21))
    assert items[0].kind == "CHALLENGE"
    assert "2개" in items[0].detail
    assert items[0].deadline == "2026-02-28"
    assert items[0].link == "/invest-plan?tab=챌린지"


@pytest.mark.asyncio
async def test_sorted_by_priority_then_deadline_and_capped():
    drifts = [_drift(True, f"P{i}") for i in range(4)]
    tax = AsyncMock(return_value=({"actions": [_tax_action(priority="HIGH", deadline="2026-12-01")]}, _tax_summary()))
    challenge = AsyncMock(return_value=ChallengeSummary(needs_attention=True, count=1))
    items, _ = await _run(
        drift=AsyncMock(return_value=drifts),
        dca=AsyncMock(return_value=[_shortfall(days_until=10)]),
        tax=tax,
        challenge=challenge,
    )
    assert len(items) == svc.MAX_ACTION_ITEMS
    # HIGH 중 마감 있는 세금 액션이 먼저, 그다음 마감 없는 리밸런싱(소스 순서 유지)
    assert items[0].kind == "TAX_ACTION"
    assert [i.kind for i in items[1:]] == ["REBALANCE"] * 4


@pytest.mark.asyncio
async def test_one_source_failure_keeps_others_and_rolls_back():
    challenge = AsyncMock(return_value=ChallengeSummary(needs_attention=True, count=1))
    items, db = await _run(
        drift=AsyncMock(side_effect=RuntimeError("db down")),
        challenge=challenge,
    )
    assert [i.kind for i in items] == ["CHALLENGE"]
    db.rollback.assert_awaited_once()
