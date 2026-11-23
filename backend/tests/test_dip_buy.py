"""낙폭 추매 안내(plans/147) — 구간 계산·사이클 초기화·완료 기록·종목 분할·API 검증·알림 잡."""

from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.exceptions import BadRequestError, NotFoundError
from app.jobs import dca_dip_buy_notice as job
from app.services import dip_buy_calculator as calc
from app.services import dip_buy_service as svc

TIERS = [dict(t) for t in calc.DEFAULT_TIERS]


def _plan(**kw):
    base = dict(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        portfolio_id=uuid.uuid4(),
        is_active=True,
        index_ticker="QQQ",
        reserve_krw=10_000_000.0,
        tiers=TIERS,
        cycle_base_krw=None,
        completed=[],
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _statuses(plan, dd):
    return calc.tier_statuses(plan.tiers, plan.completed, dd, plan.reserve_krw, plan.cycle_base_krw)


# ── 순수 계산 ───────────────────────────────────────────────


@pytest.mark.parametrize(
    ("dd", "expected_due", "amount"),
    [
        (-9.9, [], 0),
        (-10.0, [0], 2_000_000),
        (-21.0, [0, 1], 5_000_000),  # 한 번에 두 구간을 건너뛰면 합산
        (-35.0, [0, 1, 2], 10_000_000),
        (None, [], 0),  # 낙폭 확인 불가면 안내하지 않는다
    ],
)
def test_due_tiers_and_amount(dd, expected_due, amount):
    plan = _plan()
    st = _statuses(plan, dd)
    assert calc.due_tiers(st) == expected_due
    assert calc.due_amount(st, plan.reserve_krw) == amount


def test_completed_tier_is_not_due_again_and_uses_cycle_base():
    # 첫 구간 200만원 추매 후 잔액 800만원 — 다음 구간은 사이클 기준액(1,000만원)의 30%
    plan = _plan(reserve_krw=8_000_000.0, cycle_base_krw=10_000_000.0, completed=[{"tier": 0, "amount_krw": 2e6}])
    st = _statuses(plan, -22.0)
    assert [s["state"] for s in st] == ["DONE", "DUE", "WAITING"]
    assert calc.due_amount(st, plan.reserve_krw) == 3_000_000


def test_due_amount_capped_by_reserve():
    plan = _plan(reserve_krw=1_000_000.0, cycle_base_krw=10_000_000.0, completed=[{"tier": 0, "amount_krw": 2e6}])
    assert calc.due_amount(_statuses(plan, -25.0), plan.reserve_krw) == 1_000_000


@pytest.mark.parametrize(
    ("dd", "completed", "base", "expected"),
    [
        (-2.9, [{"tier": 0}], None, True),
        (-3.1, [{"tier": 0}], None, False),
        (-1.0, [], None, False),  # 지울 기록이 없으면 저장하지 않는다
        (-1.0, [], 5e6, True),
        (None, [{"tier": 0}], None, False),
    ],
)
def test_should_reset(dd, completed, base, expected):
    assert calc.should_reset(dd, completed, base) is expected


@pytest.mark.parametrize(
    "tiers",
    [
        [],
        [{"drawdown_pct": 10, "ratio_pct": 20}] * 4,
        [{"drawdown_pct": 20, "ratio_pct": 20}, {"drawdown_pct": 10, "ratio_pct": 20}],
        [{"drawdown_pct": 10, "ratio_pct": 60}, {"drawdown_pct": 20, "ratio_pct": 50}],
        [{"drawdown_pct": 70, "ratio_pct": 20}],
    ],
)
def test_validate_tiers_rejects(tiers):
    assert calc.validate_tiers(tiers) is not None


def test_validate_tiers_accepts_default():
    assert calc.validate_tiers(TIERS) is None


# ── 서비스 ──────────────────────────────────────────────────


def test_reset_if_recovered_clears_cycle():
    plan = _plan(completed=[{"tier": 0, "amount_krw": 1}], cycle_base_krw=1e7)
    assert svc.reset_if_recovered(plan, -1.0) is True
    assert plan.completed == []
    assert plan.cycle_base_krw is None


async def test_mark_completed_records_due_tiers_and_subtracts_reserve(mock_db):
    plan = _plan()
    mock_db.scalar = AsyncMock(return_value=plan)
    with patch.object(svc, "index_drawdowns", AsyncMock(return_value={"QQQ": -21.0})):
        await svc.mark_completed(mock_db, None, plan.user_id, plan.portfolio_id, None)
    assert [c["tier"] for c in plan.completed] == [0, 1]
    assert [c["amount_krw"] for c in plan.completed] == [2_000_000, 3_000_000]
    assert plan.cycle_base_krw == 10_000_000
    assert plan.reserve_krw == 5_000_000
    mock_db.commit.assert_awaited()


async def test_mark_completed_with_actual_amount(mock_db):
    plan = _plan()
    mock_db.scalar = AsyncMock(return_value=plan)
    with patch.object(svc, "index_drawdowns", AsyncMock(return_value={"QQQ": -12.0})):
        await svc.mark_completed(mock_db, None, plan.user_id, plan.portfolio_id, 1_800_000)
    assert plan.completed[0]["amount_krw"] == 1_800_000
    assert plan.reserve_krw == 8_200_000


async def test_mark_completed_without_due_tier_is_400(mock_db):
    mock_db.scalar = AsyncMock(return_value=_plan())
    with (
        patch.object(svc, "index_drawdowns", AsyncMock(return_value={"QQQ": -5.0})),
        pytest.raises(BadRequestError),
    ):
        await svc.mark_completed(mock_db, None, uuid.uuid4(), uuid.uuid4(), None)


async def test_mark_completed_missing_plan_is_404(mock_db):
    with pytest.raises(NotFoundError):
        await svc.mark_completed(mock_db, None, uuid.uuid4(), uuid.uuid4(), None)


async def test_upsert_requires_owned_portfolio(mock_db):
    with pytest.raises(NotFoundError):
        await svc.upsert_plan(
            mock_db, uuid.uuid4(), uuid.uuid4(), index_ticker="QQQ", reserve_krw=1e6, tiers=TIERS, is_active=True
        )


async def test_upsert_mid_cycle_reserve_change_rebases(mock_db):
    plan = _plan(reserve_krw=8e6, cycle_base_krw=1e7, completed=[{"tier": 0, "amount_krw": 2e6}])
    mock_db.scalar = AsyncMock(side_effect=[SimpleNamespace(id=plan.portfolio_id), plan])
    await svc.upsert_plan(
        mock_db, plan.user_id, plan.portfolio_id, index_ticker="QQQ", reserve_krw=13e6, tiers=TIERS, is_active=True
    )
    assert plan.cycle_base_krw == 15e6  # 새 잔액 + 이미 추매한 금액
    assert plan.reserve_krw == 13e6


async def test_upsert_index_change_clears_cycle(mock_db):
    plan = _plan(cycle_base_krw=1e7, completed=[{"tier": 0, "amount_krw": 2e6}])
    mock_db.scalar = AsyncMock(side_effect=[SimpleNamespace(id=plan.portfolio_id), plan])
    await svc.upsert_plan(
        mock_db, plan.user_id, plan.portfolio_id, index_ticker="SPY", reserve_krw=8e6, tiers=TIERS, is_active=True
    )
    assert plan.completed == []
    assert plan.cycle_base_krw is None
    assert plan.index_ticker == "SPY"


async def test_summarize_plan_run_dates_and_amount(mock_db):
    plan = _plan()
    alert = SimpleNamespace(id=uuid.uuid4(), account_id=uuid.uuid4())
    with (
        patch.object(svc, "dca_alert_for_portfolio", AsyncMock(return_value=alert)),
        patch.object(svc, "is_auto_schedule_day", return_value=False),
        patch.object(svc, "next_auto_schedule_date", return_value=date(2026, 11, 25)),
    ):
        s = await svc.summarize_plan(mock_db, plan, SimpleNamespace(name="P"), -21.0, today=date(2026, 11, 23))
    assert s.due_amount_krw == 5_000_000
    assert s.due_tiers == [0, 1]
    assert s.next_run_date == date(2026, 11, 25)
    assert s.is_run_day is False


async def test_summarize_inactive_plan_has_no_due(mock_db):
    with patch.object(svc, "dca_alert_for_portfolio", AsyncMock(return_value=None)):
        s = await svc.summarize_plan(mock_db, _plan(is_active=False), SimpleNamespace(name="P"), -35.0)
    assert s.due_amount_krw == 0
    assert s.next_run_date is None


async def test_allocate_items_uses_dca_split_and_usd(mock_db):
    plan = _plan()
    alert = SimpleNamespace(id=uuid.uuid4(), account_id=uuid.uuid4())
    summary = svc.DipBuySummary(
        plan=plan,
        portfolio=SimpleNamespace(name="P"),
        alert=alert,
        drawdown_pct=-12.0,
        statuses=[],
        due_amount_krw=2_000_000,
        due_tiers=[0],
        next_run_date=None,
        is_run_day=False,
    )
    rows = [
        SimpleNamespace(ticker="QQQM", name="QQQM", market="NASDAQ", shares_to_trade=3.0, current_price_krw=300_000),
        SimpleNamespace(ticker="379810", name="KODEX 나스닥100", market="KOSPI", shares_to_trade=50.0,
                        current_price_krw=20_000),
    ]  # fmt: skip
    with (
        patch(
            "app.services.rebalancing.plan_generation.dca_items_for_amount",
            AsyncMock(return_value=(None, None, rows)),
        ) as split,
        patch("app.utils.currency.get_live_or_cached_usd_krw", AsyncMock(return_value=(1500.0, True))),
    ):
        await svc.allocate_items(mock_db, None, summary)
    assert split.await_args.args[-1] == 2_000_000
    assert [(i.ticker, i.amount_krw, i.amount_usd) for i in summary.items] == [
        ("QQQM", 900_000, 600.0),
        ("379810", 1_000_000, None),
    ]
    assert summary.leftover_krw == 100_000


async def test_allocate_items_failure_keeps_amount_only(mock_db):
    summary = svc.DipBuySummary(
        plan=_plan(),
        portfolio=SimpleNamespace(name="P"),
        alert=SimpleNamespace(id=uuid.uuid4(), account_id=uuid.uuid4()),
        drawdown_pct=-12.0,
        statuses=[],
        due_amount_krw=2_000_000,
        due_tiers=[0],
        next_run_date=None,
        is_run_day=False,
    )
    with patch(
        "app.services.rebalancing.plan_generation.dca_items_for_amount", AsyncMock(side_effect=RuntimeError("x"))
    ):
        await svc.allocate_items(mock_db, None, summary)
    assert summary.items == []
    assert summary.leftover_krw == 2_000_000


async def test_index_drawdowns_handles_failure():
    with patch(
        "app.services.market_signal.technical_signal_service.get_technical_signals",
        AsyncMock(side_effect=RuntimeError("down")),
    ):
        assert await svc.index_drawdowns(None) == {"QQQ": None, "SPY": None}


async def test_index_drawdowns_reads_snapshot():
    with patch(
        "app.services.market_signal.technical_signal_service.get_technical_signals",
        AsyncMock(return_value={"QQQ": {"drawdown_pct": -12.5}, "SPY": {"drawdown_pct": None}}),
    ):
        assert await svc.index_drawdowns(None) == {"QQQ": -12.5, "SPY": None}


# ── API ─────────────────────────────────────────────────────


@pytest.fixture
def client():
    from tests.api_helpers import make_mock_db, make_user, setup_app

    app = setup_app(make_user(), make_mock_db())
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "body",
    [
        {"reserve_krw": 1e6, "tiers": [{"drawdown_pct": 20, "ratio_pct": 50}, {"drawdown_pct": 10, "ratio_pct": 20}]},
        {"reserve_krw": 1e6, "tiers": [{"drawdown_pct": 10, "ratio_pct": 70}, {"drawdown_pct": 20, "ratio_pct": 50}]},
        {"reserve_krw": -1, "tiers": TIERS},
        {"reserve_krw": 1e6, "tiers": TIERS, "index_ticker": "DIA"},
    ],
)
def test_upsert_validation_422(client, body):
    resp = client.put(f"/api/v1/invest/dip-buy/{uuid.uuid4()}", json=body)
    assert resp.status_code == 422


def test_upsert_unowned_portfolio_404(client):
    resp = client.put(f"/api/v1/invest/dip-buy/{uuid.uuid4()}", json={"reserve_krw": 1e6, "tiers": TIERS})
    assert resp.status_code == 404


def test_get_status_serializes_summary(client):
    plan = _plan()
    summary = svc.DipBuySummary(
        plan=plan,
        portfolio=SimpleNamespace(name="나스닥 적립"),
        alert=SimpleNamespace(id=uuid.uuid4()),
        drawdown_pct=-12.0,
        statuses=_statuses(plan, -12.0),
        due_amount_krw=2_000_000,
        due_tiers=[0],
        next_run_date=date(2026, 11, 25),
        is_run_day=False,
        items=[svc.DipBuyItemRow("QQQM", "QQQM", "NASDAQ", 3, 900_000, 300_000, 600.0)],
        leftover_krw=100_000,
    )
    with patch.object(svc, "summarize_user_plans", AsyncMock(return_value=[summary])):
        resp = client.get("/api/v1/invest/dip-buy")
    assert resp.status_code == 200
    data = resp.json()
    assert data["reset_drawdown_pct"] == calc.RESET_DRAWDOWN_PCT
    row = data["plans"][0]
    assert row["portfolio_name"] == "나스닥 적립"
    assert row["has_dca_schedule"] is True
    assert [t["state"] for t in row["tiers"]] == ["DUE", "WAITING", "WAITING"]
    assert row["items"][0]["amount_usd"] == 600.0


# ── 알림 잡 ─────────────────────────────────────────────────


def _summary(*, due=2_000_000.0, run=date(2026, 11, 25), is_run_day=False):
    return svc.DipBuySummary(
        plan=_plan(),
        portfolio=SimpleNamespace(name="P"),
        alert=SimpleNamespace(id=uuid.uuid4()),
        drawdown_pct=-12.0,
        statuses=[],
        due_amount_krw=due,
        due_tiers=[0] if due else [],
        next_run_date=run,
        is_run_day=is_run_day,
    )


@pytest.mark.parametrize(
    ("run", "due", "expected"),
    [
        (date(2026, 11, 24), 1.0, True),
        (date(2026, 11, 26), 1.0, True),
        (date(2026, 11, 27), 1.0, False),
        (date(2026, 11, 24), 0.0, False),
    ],
)
def test_pre_notice_window(run, due, expected):
    assert job.pre_notice_target(_summary(due=due, run=run), date(2026, 11, 23)) is expected


async def _run_notify(slot, summary, durable=None):
    send = AsyncMock()
    with (
        patch.object(job, "today_kst", return_value=date(2026, 11, 23)),
        patch.object(job, "summarize_user_plans", AsyncMock(return_value=[summary])),
        patch.object(job, "allocate_items", AsyncMock()) as alloc,
        patch.object(job, "get_durable", AsyncMock(side_effect=lambda db, key: (durable or {}).get(key))),
        patch.object(job, "_send", send),
    ):
        await job._notify_user(MagicMock(), None, summary.plan.user_id, slot)
    return send, alloc


async def test_pre_notice_sends_with_items():
    s = _summary(run=date(2026, 11, 25))
    send, alloc = await _run_notify("PRE", s)
    alloc.assert_awaited_once()
    assert send.await_args.args[2] == "PRE"


async def test_day_notice_sends_confirmed_amount():
    s = _summary(run=date(2026, 11, 23), is_run_day=True)
    send, _ = await _run_notify("DAY", s)
    assert send.await_args.args[2] == "DAY"


async def test_day_notice_cancels_when_recovered_after_pre_notice():
    s = _summary(due=0.0, run=date(2026, 11, 23), is_run_day=True)
    send, alloc = await _run_notify("DAY", s, {job.dedup_key(s.plan.id, s.next_run_date, "PRE"): "1"})
    assert send.await_args.args[2] == "CANCELLED"
    alloc.assert_not_awaited()


async def test_day_notice_silent_when_no_amount_and_no_pre_notice():
    s = _summary(due=0.0, run=date(2026, 11, 23), is_run_day=True)
    send, _ = await _run_notify("DAY", s)
    send.assert_not_awaited()


async def test_notice_dedup():
    s = _summary(run=date(2026, 11, 25))
    send, _ = await _run_notify("PRE", s, {job.dedup_key(s.plan.id, s.next_run_date, "PRE"): "1"})
    send.assert_not_awaited()


async def test_send_dispatches_dual_channel(mock_db):
    s = _summary(run=date(2026, 11, 25))
    s.items = [svc.DipBuyItemRow("QQQM", "QQQM", "NASDAQ", 3, 900_000, 300_000, 600.0)]
    row = MagicMock()
    row.first.return_value = ("a@b.c", None, "tok")
    mock_db.execute = AsyncMock(return_value=row)
    with patch.object(job, "dispatch_dual_channel_alert", AsyncMock(return_value=True)) as dispatch:
        await job._send(mock_db, s, "PRE", "k")
    kwargs = dispatch.await_args.kwargs
    assert kwargs["alert_type"] == "DCA_DIP_BUY"
    assert "추매 예정 2,000,000원" in kwargs["push_title"]
    assert "QQQM 3주" in kwargs["push_body"]


def test_email_template_phases():
    from app.services.notifications.email_templates import dip_buy_template

    subject, html = dip_buy_template(
        "P", "PRE", "11월 25일(화)", "QQQ", -21.4, 5e6, [("QQQM", 3, 9e5, 600.0)], 5e6, "L"
    )
    assert "추매 5,000,000원" in subject
    assert "QQQM" in html
    assert "$600.00" in html
    subject, html = dip_buy_template("P", "CANCELLED", "11월 25일(화)", "QQQ", -2.0, 0, [], 5e6, "L")
    assert "취소" in subject
    assert "추매하지 않아요" in html
