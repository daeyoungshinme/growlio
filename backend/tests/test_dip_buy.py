"""낙폭 추매 안내(plans/147·148) — 규칙 몫·구간 계산·사이클 초기화·완료 기록·ETF 대안·API·알림 잡."""

from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.exceptions import BadRequestError, ConflictError, NotFoundError
from app.jobs import dca_dip_buy_notice as job
from app.services import dip_buy_calculator as calc
from app.services import dip_buy_service as svc

TIERS = [dict(t) for t in calc.DEFAULT_TIERS]
USER = uuid.uuid4()


def _settings(**kw):
    base = dict(user_id=USER, reserve_krw=10_000_000.0, notify_mode="ON_REACH", notify_day=None, is_active=True)
    base.update(kw)
    return SimpleNamespace(**base)


def _rule(index="QQQ", allocation=100.0, **kw):
    base = dict(
        id=uuid.uuid4(),
        user_id=USER,
        index_ticker=index,
        allocation_pct=allocation,
        tiers=TIERS,
        cycle_base_krw=None,
        completed=[],
        notified_tiers=[],
        is_active=True,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _summ(settings, rules, drawdowns):
    return {s.rule.index_ticker: s for s in svc.summarize_rules(settings, rules, drawdowns)}


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
def test_single_rule_due(dd, expected_due, amount):
    s = _summ(_settings(), [_rule()], {"QQQ": dd})["QQQ"]
    assert s.due_tiers == expected_due
    assert s.due_amount_krw == amount


def test_allocation_splits_reserve_between_rules():
    # 여윳돈 1,000만원을 QQQ 60%·SPY 40% — 구간 비율은 각 몫 안에서
    out = _summ(_settings(), [_rule("QQQ", 60), _rule("SPY", 40)], {"QQQ": -12.0, "SPY": -21.0})
    assert out["QQQ"].base_krw == 6_000_000
    assert out["QQQ"].due_amount_krw == 1_200_000
    assert out["SPY"].due_amount_krw == 2_000_000  # 400만원 × (20+30)%


def test_other_rule_purchase_does_not_shrink_share():
    # QQQ가 120만원 추매해 여윳돈이 880만원 — SPY 몫은 풀(880+120) × 40% = 400만원 그대로
    qqq = _rule("QQQ", 60, cycle_base_krw=6e6, completed=[{"tier": 0, "amount_krw": 1.2e6}])
    out = _summ(_settings(reserve_krw=8_800_000.0), [qqq, _rule("SPY", 40)], {"QQQ": -12.0, "SPY": -10.5})
    assert out["SPY"].base_krw == 4_000_000
    assert out["SPY"].due_amount_krw == 800_000
    assert out["QQQ"].due_amount_krw == 0  # 이미 완료한 구간


def test_completed_tier_uses_cycle_base_and_remaining_share():
    rule = _rule(cycle_base_krw=10_000_000.0, completed=[{"tier": 0, "amount_krw": 2e6}])
    s = _summ(_settings(reserve_krw=8_000_000.0), [rule], {"QQQ": -22.0})["QQQ"]
    assert [t["state"] for t in s.statuses] == ["DONE", "DUE", "WAITING"]
    assert s.due_amount_krw == 3_000_000
    assert s.remaining_krw == 8_000_000


def test_simultaneous_rules_capped_by_reserve_in_order():
    # 여윳돈을 손으로 줄여 남은 몫보다 적으면 규칙 순서대로 여윳돈만큼만
    q = _rule("QQQ", 50, cycle_base_krw=5e6)
    sp = _rule("SPY", 50, cycle_base_krw=5e6)
    out = _summ(_settings(reserve_krw=2_000_000.0), [q, sp], {"QQQ": -35.0, "SPY": -35.0})
    assert out["QQQ"].due_amount_krw == 2_000_000
    assert out["SPY"].due_amount_krw == 0


def test_paused_settings_or_rule_has_no_due():
    assert _summ(_settings(is_active=False), [_rule()], {"QQQ": -35.0})["QQQ"].due_amount_krw == 0
    assert _summ(_settings(), [_rule(is_active=False)], {"QQQ": -35.0})["QQQ"].due_amount_krw == 0
    assert svc.summarize_rules(None, [_rule()], {"QQQ": -35.0})[0].due_amount_krw == 0


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


@pytest.mark.parametrize(
    ("allocations", "ok"),
    [([100], True), ([60, 40], True), ([60, 41], False), ([0.5], False), ([], True)],
)
def test_validate_allocations(allocations, ok):
    assert (calc.validate_allocations(allocations) is None) is ok


@pytest.mark.parametrize(
    ("day", "today", "expected"),
    [
        (25, date(2026, 11, 23), date(2026, 11, 25)),
        (25, date(2026, 11, 25), date(2026, 11, 25)),
        (20, date(2026, 11, 23), date(2026, 12, 21)),  # 12/20 일요일 → 다음 거래일
        (28, date(2026, 2, 27), date(2026, 3, 3)),  # 2/28 토 → 3/2 월(삼일절 대체공휴일) → 3/3
        (1, date(2026, 1, 1), date(2026, 1, 2)),  # 1/1 휴장 → 1/2
    ],
)
def test_next_notify_date(day, today, expected):
    from app.utils.market_hours import is_krx_trading_day

    assert calc.next_notify_date(day, today, is_krx_trading_day) == expected


def test_next_notify_date_rolled_from_last_month():
    # 지난달 30일이 주말이라 이번 달 1일로 밀렸으면 그날이 알림일
    def trading(d: date) -> bool:
        return d not in {date(2026, 5, 30), date(2026, 5, 31)}

    assert calc.next_notify_date(28, date(2026, 6, 1), lambda d: d >= date(2026, 6, 1) or trading(d)) == date(
        2026, 6, 28
    )
    assert calc.next_notify_date(30, date(2026, 6, 1), trading) == date(2026, 6, 1)


# ── ETF 대안 ───────────────────────────────────────────────

CANDIDATES = [
    {"ticker": "QQQ", "name": "Invesco QQQ Trust", "market": "NASDAQ"},
    {"ticker": "133690", "name": "TIGER 미국나스닥100", "market": "KOSPI"},
    {"ticker": "QLD", "name": "ProShares Ultra QQQ", "market": "NYSE"},
    {"ticker": "441680", "name": "TIGER 미국나스닥100커버드콜(합성)", "market": "KOSPI"},
    {"ticker": "360750", "name": "TIGER 미국S&P500", "market": "KOSPI"},
    {"ticker": "069500", "name": "KODEX 200", "market": "KOSPI"},
]


def test_candidate_etfs_match_index_and_skip_leveraged_covered_call():
    assert [c["ticker"] for c in svc.candidate_etfs_for_index(CANDIDATES, "QQQ")] == ["QQQ", "133690"]
    assert [c["ticker"] for c in svc.candidate_etfs_for_index(CANDIDATES, "SPY")] == ["360750"]
    assert svc.candidate_etfs_for_index(None, "QQQ") == []


async def test_attach_etfs_floor_shares_and_usd(mock_db):
    s = svc.summarize_rules(_settings(), [_rule()], {"QQQ": -12.0})[0]  # 200만원
    with (
        patch(
            "app.services.market_data.price_service.fetch_prices_batch_krw",
            AsyncMock(return_value={"QQQ": 750_000.0, "133690": 130_000.0}),
        ),
        patch("app.utils.currency.get_live_or_cached_usd_krw", AsyncMock(return_value=(1500.0, True))),
    ):
        await svc.attach_etfs(mock_db, None, USER, [s], CANDIDATES)
    assert [(e.ticker, e.shares, e.amount_krw, e.amount_usd) for e in s.etfs] == [
        ("QQQ", 2, 1_500_000, 1000.0),
        ("133690", 15, 1_950_000, None),
    ]


async def test_attach_etfs_price_failure_keeps_amount_only(mock_db):
    s = svc.summarize_rules(_settings(), [_rule()], {"QQQ": -12.0})[0]
    with patch(
        "app.services.market_data.price_service.fetch_prices_batch_krw", AsyncMock(side_effect=RuntimeError("x"))
    ):
        await svc.attach_etfs(mock_db, None, USER, [s], CANDIDATES)
    assert s.etfs == []
    assert s.due_amount_krw == 2_000_000


async def test_attach_etfs_skips_without_due_or_candidates(mock_db):
    s = svc.summarize_rules(_settings(), [_rule()], {"QQQ": -5.0})[0]
    with patch("app.services.market_data.price_service.fetch_prices_batch_krw", AsyncMock()) as prices:
        await svc.attach_etfs(mock_db, None, USER, [s], CANDIDATES)
    prices.assert_not_awaited()


# ── 서비스 ──────────────────────────────────────────────────


def test_reset_if_recovered_clears_cycle_and_notified():
    rule = _rule(completed=[{"tier": 0, "amount_krw": 1}], cycle_base_krw=1e7, notified_tiers=[0])
    assert svc.reset_if_recovered(rule, -1.0) is True
    assert (rule.completed, rule.cycle_base_krw, rule.notified_tiers) == ([], None, [])


def _db_with(mock_db, settings, rules):
    mock_db.scalar = AsyncMock(return_value=settings)
    result = MagicMock()
    result.scalars.return_value.all.return_value = rules
    mock_db.execute = AsyncMock(return_value=result)
    return mock_db


async def test_mark_completed_records_due_tiers_and_subtracts_reserve(mock_db):
    settings, rule = _settings(), _rule("QQQ", 60)
    _db_with(mock_db, settings, [rule, _rule("SPY", 40)])
    with patch.object(svc, "index_drawdowns", AsyncMock(return_value={"QQQ": -21.0, "SPY": -1.0})):
        await svc.mark_completed(mock_db, None, USER, rule.id, None)
    assert [c["tier"] for c in rule.completed] == [0, 1]
    assert [c["amount_krw"] for c in rule.completed] == [1_200_000, 1_800_000]
    assert rule.cycle_base_krw == 6_000_000
    assert settings.reserve_krw == 7_000_000
    mock_db.commit.assert_awaited()


async def test_mark_completed_with_actual_amount(mock_db):
    settings, rule = _settings(), _rule()
    _db_with(mock_db, settings, [rule])
    with patch.object(svc, "index_drawdowns", AsyncMock(return_value={"QQQ": -12.0})):
        await svc.mark_completed(mock_db, None, USER, rule.id, 1_800_000)
    assert rule.completed[0]["amount_krw"] == 1_800_000
    assert settings.reserve_krw == 8_200_000


async def test_mark_completed_without_due_tier_is_400(mock_db):
    rule = _rule()
    _db_with(mock_db, _settings(), [rule])
    with (
        patch.object(svc, "index_drawdowns", AsyncMock(return_value={"QQQ": -5.0})),
        pytest.raises(BadRequestError),
    ):
        await svc.mark_completed(mock_db, None, USER, rule.id, None)


async def test_mark_completed_other_users_rule_is_404(mock_db):
    _db_with(mock_db, _settings(), [_rule()])
    with pytest.raises(NotFoundError):
        await svc.mark_completed(mock_db, None, USER, uuid.uuid4(), None)


async def test_upsert_settings_mid_cycle_reserve_change_rebases(mock_db):
    settings = _settings(reserve_krw=8e6)
    rule = _rule("QQQ", 50, cycle_base_krw=5e6, completed=[{"tier": 0, "amount_krw": 2e6}])
    _db_with(mock_db, settings, [rule, _rule("SPY", 50)])
    await svc.upsert_settings(mock_db, USER, reserve_krw=13e6, notify_mode="ON_REACH", notify_day=None, is_active=True)
    assert rule.cycle_base_krw == 7.5e6  # (새 여윳돈 13 + 이미 추매 2) × 50%
    assert settings.reserve_krw == 13e6


async def test_upsert_settings_creates_and_clears_day_for_on_reach(mock_db):
    mock_db.scalar = AsyncMock(return_value=None)
    created = await svc.upsert_settings(
        mock_db, USER, reserve_krw=5e6, notify_mode="ON_REACH", notify_day=25, is_active=True
    )
    mock_db.add.assert_called_once()
    assert created.notify_day is None


async def test_upsert_settings_monthly_requires_day(mock_db):
    with pytest.raises(BadRequestError):
        await svc.upsert_settings(
            mock_db, USER, reserve_krw=5e6, notify_mode="MONTHLY_DAY", notify_day=None, is_active=True
        )


async def test_create_rule_requires_settings(mock_db):
    mock_db.scalar = AsyncMock(return_value=None)
    with pytest.raises(BadRequestError):
        await svc.create_rule(mock_db, USER, index_ticker="QQQ", allocation_pct=50, tiers=TIERS, is_active=True)


async def test_create_rule_rejects_duplicate_index_and_over_allocation(mock_db):
    _db_with(mock_db, _settings(), [_rule("QQQ", 70)])
    with pytest.raises(ConflictError):
        await svc.create_rule(mock_db, USER, index_ticker="QQQ", allocation_pct=10, tiers=TIERS, is_active=True)
    with pytest.raises(BadRequestError):
        await svc.create_rule(mock_db, USER, index_ticker="SPY", allocation_pct=40, tiers=TIERS, is_active=True)
    await svc.create_rule(mock_db, USER, index_ticker="SPY", allocation_pct=30, tiers=TIERS, is_active=True)
    mock_db.add.assert_called_once()


async def test_update_rule_index_change_clears_cycle(mock_db):
    rule = _rule(cycle_base_krw=1e7, completed=[{"tier": 0, "amount_krw": 2e6}], notified_tiers=[0])
    _db_with(mock_db, _settings(), [rule])
    await svc.update_rule(mock_db, USER, rule.id, index_ticker="SPY", allocation_pct=100, tiers=TIERS, is_active=True)
    assert (rule.completed, rule.cycle_base_krw, rule.notified_tiers) == ([], None, [])
    assert rule.index_ticker == "SPY"


async def test_update_rule_allocation_change_rebases_cycle(mock_db):
    rule = _rule("QQQ", 50, cycle_base_krw=5e6, completed=[{"tier": 0, "amount_krw": 1e6}])
    _db_with(mock_db, _settings(reserve_krw=9e6), [rule])
    await svc.update_rule(mock_db, USER, rule.id, index_ticker="QQQ", allocation_pct=80, tiers=TIERS, is_active=True)
    assert rule.cycle_base_krw == 8e6  # (9 + 1) × 80%


async def test_update_rule_missing_is_404(mock_db):
    _db_with(mock_db, _settings(), [])
    with pytest.raises(NotFoundError):
        await svc.update_rule(
            mock_db, USER, uuid.uuid4(), index_ticker="QQQ", allocation_pct=50, tiers=TIERS, is_active=True
        )


async def test_delete_rule_missing_is_404(mock_db):
    mock_db.scalar = AsyncMock(return_value=None)
    with pytest.raises(NotFoundError):
        await svc.delete_rule(mock_db, USER, uuid.uuid4())


async def test_summarize_user_resets_recovered_and_flags_tactical_hold(mock_db):
    rule = _rule("QQQ", 50, completed=[{"tier": 0, "amount_krw": 1}], cycle_base_krw=1e7)
    spy = _rule("SPY", 50)
    with (
        patch.object(svc, "get_settings", AsyncMock(return_value=_settings(notify_mode="MONTHLY_DAY", notify_day=25))),
        patch.object(svc, "list_rules", AsyncMock(return_value=[rule, spy])),
        patch.object(svc, "index_drawdowns", AsyncMock(return_value={"QQQ": -1.0, "SPY": -12.0})),
        patch.object(svc, "dca_held_portfolios", AsyncMock(return_value=["나스닥 적립"])),
    ):
        out = await svc.summarize_user(mock_db, None, USER, with_etfs=False, today=date(2026, 11, 23))
    assert rule.completed == []
    mock_db.commit.assert_awaited()
    assert out.next_notify_date == date(2026, 11, 25)
    assert out.due_amount_krw == 1_000_000  # QQQ 회복으로 초기화 → SPY 몫 1,000만 × 50% × 20%
    assert out.dca_held_portfolios == ["나스닥 적립"]


async def test_dca_held_portfolios_uses_tactical_gate(mock_db):
    held = SimpleNamespace(portfolio_id=uuid.uuid4())
    ok = SimpleNamespace(portfolio_id=uuid.uuid4())
    result = MagicMock()
    result.all.return_value = [(held, "방어"), (ok, "공격")]
    mock_db.execute = AsyncMock(return_value=result)
    regimes = {held.portfolio_id: "RISK_OFF", ok.portfolio_id: "RISK_ON"}
    with patch(
        "app.services.rebalancing.order_builder.tactical_regime_for_gate",
        AsyncMock(side_effect=lambda alert, db: regimes[alert.portfolio_id]),
    ):
        assert await svc.dca_held_portfolios(mock_db, USER) == ["방어"]


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
        {"index_ticker": "QQQ", "allocation_pct": 50, "tiers": [TIERS[1], TIERS[0]]},
        {"index_ticker": "QQQ", "allocation_pct": 50, "tiers": [{"drawdown_pct": 10, "ratio_pct": 80}, TIERS[1]]},
        {"index_ticker": "QQQ", "allocation_pct": 0, "tiers": TIERS},
        {"index_ticker": "DIA", "allocation_pct": 50, "tiers": TIERS},
    ],
)
def test_rule_validation_422(client, body):
    assert client.post("/api/v1/invest/dip-buy/rules", json=body).status_code == 422


@pytest.mark.parametrize(
    "body",
    [
        {"reserve_krw": -1},
        {"reserve_krw": 1e6, "notify_mode": "MONTHLY_DAY"},
        {"reserve_krw": 1e6, "notify_mode": "MONTHLY_DAY", "notify_day": 29},
        {"reserve_krw": 1e6, "notify_mode": "WEEKLY"},
    ],
)
def test_settings_validation_422(client, body):
    assert client.put("/api/v1/invest/dip-buy/settings", json=body).status_code == 422


def test_rule_routes_call_service(client):
    rule_id = uuid.uuid4()
    with (
        patch.object(svc, "create_rule", AsyncMock()) as create,
        patch.object(svc, "update_rule", AsyncMock()) as update,
        patch.object(svc, "delete_rule", AsyncMock()) as delete,
        patch.object(svc, "mark_completed", AsyncMock()) as complete,
        patch.object(svc, "upsert_settings", AsyncMock()) as upsert,
    ):
        body = {"index_ticker": "SPY", "allocation_pct": 40, "tiers": TIERS}
        assert client.post("/api/v1/invest/dip-buy/rules", json=body).status_code == 204
        assert client.put(f"/api/v1/invest/dip-buy/rules/{rule_id}", json=body).status_code == 204
        assert client.post(f"/api/v1/invest/dip-buy/rules/{rule_id}/complete", json={}).status_code == 204
        assert client.delete(f"/api/v1/invest/dip-buy/rules/{rule_id}").status_code == 204
        settings_body = {"reserve_krw": 1e6, "notify_mode": "MONTHLY_DAY", "notify_day": 25}
        assert client.put("/api/v1/invest/dip-buy/settings", json=settings_body).status_code == 204
    assert create.await_args.kwargs["allocation_pct"] == 40
    assert update.await_args.args[2] == rule_id
    assert complete.await_args.args[3] == rule_id
    assert delete.await_args.args[2] == rule_id
    assert upsert.await_args.kwargs["notify_day"] == 25


def test_get_status_serializes_summary(client):
    rule = _rule("QQQ", 60)
    summary = svc.UserDipBuySummary(
        settings=_settings(),
        rules=svc.summarize_rules(_settings(), [rule], {"QQQ": -12.0}),
        next_notify_date=None,
        dca_held_portfolios=["나스닥 적립"],
        has_candidates=True,
    )
    summary.rules[0].etfs = [svc.EtfOption("QQQ", "Invesco QQQ", "NASDAQ", 750_000, 1, 750_000, 500.0)]
    with patch.object(svc, "summarize_user", AsyncMock(return_value=summary)):
        resp = client.get("/api/v1/invest/dip-buy")
    assert resp.status_code == 200
    data = resp.json()
    assert data["settings"]["notify_mode"] == "ON_REACH"
    assert data["due_amount_krw"] == 1_200_000
    assert data["dca_held_portfolios"] == ["나스닥 적립"]
    row = data["rules"][0]
    assert row["allocation_pct"] == 60
    assert row["base_krw"] == 6_000_000
    assert [t["state"] for t in row["tiers"]] == ["DUE", "WAITING", "WAITING"]
    assert row["etfs"][0]["amount_usd"] == 500.0


def test_get_status_without_settings(client):
    empty = svc.UserDipBuySummary(settings=None, rules=[], next_notify_date=None)
    with patch.object(svc, "summarize_user", AsyncMock(return_value=empty)):
        data = client.get("/api/v1/invest/dip-buy").json()
    assert data["settings"] is None
    assert data["rules"] == []


# ── 알림 잡 ─────────────────────────────────────────────────


def _user_summary(*, mode="MONTHLY_DAY", run=date(2026, 11, 25), dd=-12.0, notified=()):
    settings = _settings(notify_mode=mode, notify_day=25 if mode == "MONTHLY_DAY" else None)
    rule = _rule(notified_tiers=list(notified))
    return svc.UserDipBuySummary(
        settings=settings,
        rules=svc.summarize_rules(settings, [rule], {"QQQ": dd}),
        next_notify_date=run if mode == "MONTHLY_DAY" else None,
    )


@pytest.mark.parametrize(
    ("run", "dd", "expected"),
    [
        (date(2026, 11, 24), -12.0, True),
        (date(2026, 11, 26), -12.0, True),
        (date(2026, 11, 27), -12.0, False),
        (date(2026, 11, 24), -5.0, False),
    ],
)
def test_pre_notice_window(run, dd, expected):
    assert job.pre_notice_target(_user_summary(run=run, dd=dd), date(2026, 11, 23)) is expected


async def _run_notify(slot, summary, durable=None):
    send = AsyncMock()
    with (
        patch.object(job, "today_kst", return_value=date(2026, 11, 23)),
        patch.object(job, "summarize_user", AsyncMock(return_value=summary)),
        patch.object(job, "load_goal_candidates", AsyncMock(return_value=[])),
        patch.object(job, "attach_etfs", AsyncMock()) as attach,
        patch.object(job, "get_durable", AsyncMock(side_effect=lambda db, key: (durable or {}).get(key))),
        patch.object(job, "_send", send),
    ):
        await job._notify_user(MagicMock(), None, USER, slot)
    return send, attach


async def test_monthly_pre_notice_sends_with_etfs():
    send, attach = await _run_notify("PRE", _user_summary(run=date(2026, 11, 25)))
    attach.assert_awaited_once()
    assert send.await_args.args[3] == "PRE"


async def test_monthly_day_notice_sends_confirmed_amount():
    send, _ = await _run_notify("DAY", _user_summary(run=date(2026, 11, 23)))
    assert send.await_args.args[3] == "DAY"


async def test_monthly_day_notice_cancels_when_recovered_after_pre_notice():
    s = _user_summary(run=date(2026, 11, 23), dd=-2.0)
    send, attach = await _run_notify("DAY", s, {job.dedup_key(USER, date(2026, 11, 23), "PRE"): "1"})
    assert send.await_args.args[3] == "CANCELLED"
    attach.assert_not_awaited()


async def test_monthly_day_notice_silent_when_no_amount_and_no_pre_notice():
    send, _ = await _run_notify("DAY", _user_summary(run=date(2026, 11, 23), dd=-2.0))
    send.assert_not_awaited()


async def test_monthly_notice_dedup():
    s = _user_summary(run=date(2026, 11, 25))
    send, _ = await _run_notify("PRE", s, {job.dedup_key(USER, date(2026, 11, 25), "PRE"): "1"})
    send.assert_not_awaited()


async def test_on_reach_sends_new_tiers_once_and_marks_notified():
    s = _user_summary(mode="ON_REACH", dd=-21.0, notified=[0])
    send, attach = await _run_notify("DAY", s)
    assert send.await_args.args[3] == "REACHED"
    attach.assert_awaited_once()
    await send.await_args.args[6]()  # after_sent
    assert s.rules[0].rule.notified_tiers == [0, 1]


async def test_on_reach_skips_already_notified_and_pre_slot():
    send, _ = await _run_notify("DAY", _user_summary(mode="ON_REACH", dd=-12.0, notified=[0]))
    send.assert_not_awaited()
    send, _ = await _run_notify("PRE", _user_summary(mode="ON_REACH", dd=-21.0))
    send.assert_not_awaited()


async def test_send_dispatches_dual_channel(mock_db):
    s = _user_summary(mode="ON_REACH", dd=-12.0)
    s.dca_held_portfolios = ["나스닥 적립"]
    s.rules[0].etfs = [svc.EtfOption("133690", "TIGER 미국나스닥100", "KOSPI", 130_000, 15, 1_950_000)]
    row = MagicMock()
    row.first.return_value = ("a@b.c", None, "tok")
    mock_db.execute = AsyncMock(return_value=row)
    with patch.object(job, "dispatch_dual_channel_alert", AsyncMock(return_value=True)) as dispatch:
        await job._send(mock_db, USER, s, "REACHED", s.rules, None, AsyncMock())
    kwargs = dispatch.await_args.kwargs
    assert kwargs["alert_type"] == "DCA_DIP_BUY"
    assert "추매 구간 도달 2,000,000원" in kwargs["push_title"]
    assert "TIGER 미국나스닥100 15주" in kwargs["push_body"]
    assert "전술 방어 국면" in kwargs["push_body"]


def test_email_template_phases():
    from app.services.notifications.email_templates import dip_buy_template

    rules = [("나스닥100(QQQ)", -21.4, 5e6, [("QQQ", 6, 4.5e6, 3000.0), ("TIGER 미국나스닥100", 38, 4.94e6, None)])]
    subject, html = dip_buy_template("PRE", "11월 25일(화)", rules, 5e6, ["나스닥 적립"], "L")
    assert "추매 5,000,000원" in subject
    assert "또는 TIGER 미국나스닥100" in html
    assert "$3,000.00" in html
    assert "전술 방어 국면" in html
    subject, _ = dip_buy_template("REACHED", None, rules, 5e6, [], "L")
    assert "나스닥100(QQQ) -21.4%" in subject
    subject, html = dip_buy_template("CANCELLED", "11월 25일(화)", rules, 5e6, [], "L")
    assert "취소" in subject
    assert "추매하지 않아요" in html
