"""홈 "지금 할 일" 집계 (docs/plans/50 M5)."""

from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.tactical import TacticalStrategy
from app.schemas.challenge import ChallengeSummary
from app.services import action_items_service as svc


def _drift(needs=True, name="성장형", max_drift=7.4):
    return SimpleNamespace(
        portfolio_id=uuid.uuid4(),
        portfolio_name=name,
        needs_rebalancing=needs,
        max_drift_pct=max_drift,
        drifted_items_count=2,
        threshold_pct=5.0,
    )


def _tactical(
    *, last="RISK_ON", applied=None, partial=None, pending=None, weights=None, name="미국 전술", portfolio_id=None
):
    strategy = TacticalStrategy(user_id=uuid.uuid4(), portfolio_id=portfolio_id or uuid.uuid4())
    strategy.last_regime = last
    strategy.applied_regime = applied
    strategy.partial_regime = partial
    strategy.pending_regime = pending
    # 기본 비중표 공격 국면(QQQ 50·SPY 40·현금 10)과 같으면 적용 완료
    items = [
        SimpleNamespace(ticker=t, weight=w) for t, w in (weights or {"QQQ": 50.0, "SPY": 40.0, "CASH": 10.0}).items()
    ]
    return strategy, SimpleNamespace(id=strategy.portfolio_id, name=name, items=items)


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


async def _run(
    *, drift=None, dca=None, tax=None, challenge=None, tactical=None, linked=frozenset(), today=date(2026, 11, 23)
):
    db = MagicMock()
    db.rollback = AsyncMock()
    with (
        patch.object(svc, "_tactical_strategies", new=tactical or AsyncMock(return_value=[])),
        patch.object(svc, "_dca_tactical_linked_portfolio_ids", new=AsyncMock(return_value=set(linked))),
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
    # 예수금 부족 푸시와 같은 목적지(적립 계획 탭) — plans/63 P3-4
    assert items[0].link == "/invest-plan?tab=적립 계획"


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
async def test_rebalance_grouped_into_one_row_when_two_or_more():
    drifts = [_drift(True, "성장형", 6.0), _drift(True, "배당형", 9.3), _drift(False, "안정형")]
    items, _ = await _run(drift=AsyncMock(return_value=drifts))
    assert len(items) == 1
    item = items[0]
    assert item.id == svc.REBALANCE_GROUP_ID
    assert item.kind == "REBALANCE"
    assert item.priority == "HIGH"
    assert item.title == "리밸런싱 필요 · 포트폴리오 2개"
    assert item.detail == "배당형 최대 9.3%p 이탈 외 1개"
    assert item.cta_label == "자세히 보기"
    assert item.link == "/rebalancing"


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
    # 리밸런싱 4개는 1행으로 묶여 적립·챌린지가 상한에 잘리지 않는다 (docs/plans/73)
    # HIGH 중 마감 있는 세금 액션이 먼저, 그다음 마감 없는 리밸런싱(소스 순서 유지)
    assert [i.kind for i in items] == ["TAX_ACTION", "REBALANCE", "DCA_SHORTFALL", "CHALLENGE"]
    assert items[1].id == svc.REBALANCE_GROUP_ID


@pytest.mark.asyncio
async def test_one_source_failure_keeps_others_and_rolls_back():
    challenge = AsyncMock(return_value=ChallengeSummary(needs_attention=True, count=1))
    items, db = await _run(
        drift=AsyncMock(side_effect=RuntimeError("db down")),
        challenge=challenge,
    )
    assert [i.kind for i in items] == ["CHALLENGE"]
    db.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# 전술 배분 (docs/plans/75)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tactical_regime_not_applied_is_high():
    row = _tactical(last="RISK_ON", applied="NEUTRAL", weights={"QQQ": 30.0, "SPY": 40.0, "CASH": 30.0})
    items, _ = await _run(tactical=AsyncMock(return_value=[row]))
    assert [i.kind for i in items] == ["TACTICAL"]
    item = items[0]
    assert item.priority == "HIGH"
    assert item.title == "미국 전술 전술: 공격 국면 비중 적용 전"
    assert item.detail == "제안 나스닥100 50% · S&P500 40% · 현금 10%"
    assert item.cta_label == "적용하기"
    assert item.link == f"/rebalancing?rtab=목표 조정&gmode=전술&portfolioId={row[1].id}"


@pytest.mark.asyncio
async def test_tactical_partial_applied_is_medium():
    row = _tactical(last="RISK_ON", applied="NEUTRAL", partial="RISK_ON")
    items, _ = await _run(tactical=AsyncMock(return_value=[row]))
    assert items[0].priority == "MEDIUM"
    assert items[0].cta_label == "나머지 적용"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"applied": "RISK_ON"},  # 적용 완료 — 현재 비중 = 제안 비중
        {"applied": "RISK_ON", "pending": "NEUTRAL"},  # 전환 확인 중은 할 일 아님
        {"last": None},  # 국면 미확정
    ],
)
@pytest.mark.asyncio
async def test_tactical_no_item(kwargs):
    items, _ = await _run(tactical=AsyncMock(return_value=[_tactical(**kwargs)]))
    assert items == []


@pytest.mark.asyncio
async def test_tactical_weights_changed_after_apply_is_high():
    # 국면은 적용했지만 웅덩이 투입·틸트 등으로 제안 비중이 바뀌었거나 목표를 손으로 고친 경우
    row = _tactical(applied="RISK_ON", weights={"QQQ": 45.0, "SPY": 45.0, "CASH": 10.0})
    items, _ = await _run(tactical=AsyncMock(return_value=[row]))
    assert items[0].priority == "HIGH"


@pytest.mark.asyncio
async def test_tactical_skipped_when_dca_linked():
    row = _tactical(applied="NEUTRAL")
    items, _ = await _run(tactical=AsyncMock(return_value=[row]), linked={row[1].id})
    assert items == []


@pytest.mark.asyncio
async def test_tactical_portfolio_removed_from_rebalance():
    pid = uuid.uuid4()
    tactical_drift, other = _drift(True, "미국 전술", 12.0), _drift(True, "성장형", 6.0)
    tactical_drift.portfolio_id = pid
    row = _tactical(applied="NEUTRAL", portfolio_id=pid)
    items, _ = await _run(tactical=AsyncMock(return_value=[row]), drift=AsyncMock(return_value=[tactical_drift, other]))
    # 전술 포트폴리오는 리밸런싱에서 빠져 남은 1개는 묶음이 아닌 단일 행 — 같은 HIGH면 전술이 먼저
    assert [i.id for i in items] == [f"tactical:{pid}", f"rebalance:{other.portfolio_id}"]


@pytest.mark.asyncio
async def test_tactical_failure_keeps_rebalance_rows():
    drift = _drift(True, "미국 전술")
    items, db = await _run(
        tactical=AsyncMock(side_effect=RuntimeError("db down")), drift=AsyncMock(return_value=[drift])
    )
    assert [i.kind for i in items] == ["REBALANCE"]
    db.rollback.assert_awaited_once()
