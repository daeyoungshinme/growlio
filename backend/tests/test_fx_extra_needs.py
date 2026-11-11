"""추가 환전 항목(여행 등) — 구간 계산·CRUD·항목 범위 알림 맞추기·발송 문구(plans/123)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.cache_store import CacheStore
from app.exceptions import BadRequestError, ConflictError, NotFoundError
from app.services import fx_extra_need_service as svc
from app.services import fx_plan_service

TODAY = date(2026, 11, 11)


def _closes(n=250, start=1300.0, step=0.4):
    return [start + i * step + (5 if i % 2 else -5) for i in range(n)]


def _position(rate=1400.0):
    pos = fx_plan_service.compute_fx_position(_closes(), rate)
    assert pos is not None
    return pos


def _need(*, amount=1000.0, exchanged=0.0, days=30, name="도쿄 여행"):
    return SimpleNamespace(
        id=uuid.uuid4(),
        name=name,
        amount_usd=amount,
        exchanged_usd=exchanged,
        due_date=TODAY + timedelta(days=days),
        reserved_account_id=None,
    )


# ── 구간 계산 ───────────────────────────────────────────────


def test_urgent_need_puts_everything_now():
    tranches = svc.compute_extra_need_tranches(_position(), 800.0, 14, 1400.0)
    assert [(t.label, t.target_rate, t.usd) for t in tranches] == [("지금", None, 800.0)]
    assert tranches[0].krw_estimate == 1_120_000


def test_far_need_splits_like_dca_plan():
    pos = _position()
    tranches = svc.compute_extra_need_tranches(pos, 900.0, 40, 1400.0)
    assert tranches == fx_plan_service.compute_fx_plan(pos, 900.0, 1400.0)
    assert tranches[0].label == "지금"
    assert all(t.target_rate is not None and t.target_rate < 1400 for t in tranches[1:])


def test_unknown_position_has_no_dca_day_label():
    tranches = svc.compute_extra_need_tranches(None, 500.0, 40, 1400.0)
    assert [t.label for t in tranches] == ["필요일 전에 환전"]


@pytest.mark.parametrize(("remaining", "days"), [(0.0, 30), (0.004, 30), (500.0, -1)])
def test_no_tranches_when_done_or_past_due(remaining, days):
    assert svc.compute_extra_need_tranches(_position(), remaining, days, 1400.0) == []


@pytest.mark.parametrize(
    ("kwargs", "has_rate", "status"),
    [
        ({"exchanged": 1000.0}, True, "DONE"),
        ({"days": -1}, True, "PAST_DUE"),
        ({}, False, "NO_RATE"),
        ({"exchanged": 300.0}, True, "OK"),
    ],
)
def test_need_row_status(kwargs, has_rate, status):
    row = svc.build_need_row(_need(**kwargs), _position(), 1400.0, has_rate, TODAY)
    assert row["status"] == status
    assert bool(row["tranches"]) == (status == "OK")


def test_need_row_remaining_and_days_left():
    row = svc.build_need_row(_need(amount=1000.0, exchanged=250.0, days=20), _position(), 1400.0, True, TODAY)
    assert (row["remaining_usd"], row["days_left"]) == (750.0, 20)
    assert sum(t["usd"] for t in row["tranches"]) == pytest.approx(750.0, abs=0.02)


def test_need_row_caps_exchanged_at_amount():
    row = svc.build_need_row(_need(amount=100.0, exchanged=150.0), None, 1400.0, True, TODAY)
    assert (row["exchanged_usd"], row["remaining_usd"], row["status"]) == (100.0, 0.0, "DONE")


# ── 목록 ────────────────────────────────────────────────────


def _list_db(needs, names=None):
    db = MagicMock()
    result = MagicMock()
    result.all.return_value = list(zip(needs, names or [None] * len(needs), strict=True))
    db.execute = AsyncMock(return_value=result)
    return db


async def test_list_without_needs_skips_rate_lookup():
    with patch.object(svc, "load_fx_rate_context", new=AsyncMock()) as ctx:
        data = await svc.list_fx_extra_needs(_list_db([]), CacheStore(), uuid.uuid4())
    assert data == {"rate": None, "rate_is_live": True, "needs": []}
    ctx.assert_not_awaited()


async def test_list_hides_fallback_rate():
    ctx = fx_plan_service.FxRateContext(1300.0, False, None, has_rate=False)
    with (
        patch.object(svc, "load_fx_rate_context", new=AsyncMock(return_value=ctx)),
        patch.object(svc, "today_kst", return_value=TODAY),
    ):
        data = await svc.list_fx_extra_needs(_list_db([_need()]), CacheStore(), uuid.uuid4())
    assert data["rate"] is None
    assert data["needs"][0]["status"] == "NO_RATE"


# ── 생성·수정·삭제 ──────────────────────────────────────────


def _crud_db(*, count=0, need=None):
    db = MagicMock()
    db.scalar = AsyncMock(side_effect=[count] if need is None else [need])
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    return db


async def test_create_rejects_past_due_date():
    with patch.object(svc, "today_kst", return_value=TODAY), pytest.raises(BadRequestError):
        await svc.create_fx_extra_need(_crud_db(), uuid.uuid4(), "여행", 100.0, 0.0, TODAY - timedelta(days=1))


async def test_create_rejects_exchanged_over_amount():
    with patch.object(svc, "today_kst", return_value=TODAY), pytest.raises(BadRequestError):
        await svc.create_fx_extra_need(_crud_db(), uuid.uuid4(), "여행", 100.0, 150.0, TODAY)


async def test_create_enforces_user_cap():
    db = _crud_db(count=10)
    with patch.object(svc, "today_kst", return_value=TODAY), pytest.raises(ConflictError):
        await svc.create_fx_extra_need(db, uuid.uuid4(), "여행", 100.0, 0.0, TODAY)
    db.add.assert_not_called()


async def test_create_saves_need():
    db = _crud_db(count=2)
    user_id = uuid.uuid4()
    with patch.object(svc, "today_kst", return_value=TODAY):
        need = await svc.create_fx_extra_need(db, user_id, "여행", 100.0, 20.0, TODAY)
    assert (need.user_id, need.name, need.amount_usd, need.exchanged_usd, need.due_date) == (
        user_id,
        "여행",
        100.0,
        20.0,
        TODAY,
    )
    db.add.assert_called_once_with(need)
    db.commit.assert_awaited_once()


async def test_update_missing_need_is_404():
    db = MagicMock()
    db.scalar = AsyncMock(return_value=None)
    with pytest.raises(NotFoundError):
        await svc.update_fx_extra_need(db, uuid.uuid4(), uuid.uuid4(), {"name": "x"})


async def test_update_rejects_moving_due_date_to_past():
    need = _need(days=5)
    with patch.object(svc, "today_kst", return_value=TODAY), pytest.raises(BadRequestError):
        await svc.update_fx_extra_need(
            _crud_db(need=need), uuid.uuid4(), need.id, {"due_date": TODAY - timedelta(days=1)}
        )


async def test_update_past_due_need_keeps_other_edits():
    need = _need(days=-3)
    with patch.object(svc, "today_kst", return_value=TODAY):
        await svc.update_fx_extra_need(_crud_db(need=need), uuid.uuid4(), need.id, {"exchanged_usd": 1000.0})
    assert need.exchanged_usd == 1000.0


async def test_update_checks_amount_against_existing_exchanged():
    need = _need(amount=1000.0, exchanged=600.0)
    with patch.object(svc, "today_kst", return_value=TODAY), pytest.raises(BadRequestError):
        await svc.update_fx_extra_need(_crud_db(need=need), uuid.uuid4(), need.id, {"amount_usd": 500.0})


async def test_delete_removes_need():
    need = _need()
    db = _crud_db(need=need)
    await svc.delete_fx_extra_need(db, uuid.uuid4(), need.id)
    db.delete.assert_awaited_once_with(need)
    db.commit.assert_awaited_once()


# ── 항목 범위 알림 맞추기 ───────────────────────────────────


def _alert(rate, *, portfolio_id=None, fx_need_id=None, source="FX_PLAN", usd=100.0):
    return SimpleNamespace(
        target_rate=rate,
        source=source,
        portfolio_id=portfolio_id,
        fx_need_id=fx_need_id,
        triggered_at=None,
        planned_usd=usd,
        is_active=True,
    )


def _sync_db(alerts, *, due=TODAY + timedelta(days=30)):
    db = MagicMock()
    db.scalar = AsyncMock(side_effect=[due, len(alerts)])
    result = MagicMock()
    result.scalars.return_value.all.return_value = alerts
    db.execute = AsyncMock(return_value=result)
    db.delete = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


async def _sync_need(db, need_id, targets):
    with patch.object(fx_plan_service, "today_kst", return_value=TODAY):
        return await fx_plan_service.sync_fx_plan_alerts(
            db, CacheStore(), uuid.uuid4(), None, targets, fx_need_id=need_id
        )


async def test_need_sync_creates_alert_scoped_to_need():
    need_id = uuid.uuid4()
    db = _sync_db([])
    result = await _sync_need(db, need_id, [(1350.0, 300.0)])
    assert result.created == 1
    created = db.add.call_args.args[0]
    assert (created.fx_need_id, created.portfolio_id, created.source, created.planned_usd) == (
        need_id,
        None,
        "FX_PLAN",
        300.0,
    )


async def test_need_sync_leaves_portfolio_and_other_need_alerts():
    need_id = uuid.uuid4()
    portfolio_alert = _alert(1320.0, portfolio_id=uuid.uuid4())
    other_need_alert = _alert(1310.0, fx_need_id=uuid.uuid4())
    mine = _alert(1300.0, fx_need_id=need_id)
    db = _sync_db([portfolio_alert, other_need_alert, mine])

    result = await _sync_need(db, need_id, [])

    assert result.removed == 1
    db.delete.assert_awaited_once_with(mine)


async def test_portfolio_sync_leaves_need_alerts():
    pid = uuid.uuid4()
    need_alert = _alert(1300.0, fx_need_id=uuid.uuid4())
    plan_alert = _alert(1320.0, portfolio_id=pid)
    db = MagicMock()
    db.scalar = AsyncMock(side_effect=[pid, 2])
    result = MagicMock()
    result.scalars.return_value.all.return_value = [need_alert, plan_alert]
    db.execute = AsyncMock(return_value=result)
    db.delete = AsyncMock()
    db.commit = AsyncMock()

    out = await fx_plan_service.sync_fx_plan_alerts(db, CacheStore(), uuid.uuid4(), pid, [])

    assert out.removed == 1
    db.delete.assert_awaited_once_with(plan_alert)


async def test_need_sync_missing_need_is_404():
    db = _sync_db([], due=None)
    with pytest.raises(NotFoundError):
        await _sync_need(db, uuid.uuid4(), [(1350.0, 300.0)])


async def test_need_sync_refuses_new_alerts_for_past_due_need_but_allows_release():
    with pytest.raises(BadRequestError):
        await _sync_need(_sync_db([], due=TODAY - timedelta(days=1)), uuid.uuid4(), [(1350.0, 300.0)])
    need_id = uuid.uuid4()
    db = _sync_db([_alert(1300.0, fx_need_id=need_id)], due=TODAY - timedelta(days=1))
    result = await _sync_need(db, need_id, [])
    assert result.removed == 1


async def test_sync_requires_exactly_one_scope():
    with pytest.raises(ValueError, match="하나만"):
        await fx_plan_service.sync_fx_plan_alerts(
            MagicMock(), CacheStore(), uuid.uuid4(), uuid.uuid4(), [], fx_need_id=uuid.uuid4()
        )


# ── 발송 문구 ───────────────────────────────────────────────


async def test_need_alert_message_names_the_need(mock_db):
    alert = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        target_rate=1300.0,
        direction="BELOW",
        trigger_count=0,
        max_trigger_count=1,
        triggered_at=None,
        is_active=True,
        source="FX_PLAN",
        planned_usd=500.0,
    )
    mock_db.execute.return_value.all.return_value = [(alert, "u@test.com", None, None, "도쿄 여행")]
    with (
        patch("app.services.alerts.exchange_rate_service.fetch_usd_krw", new=AsyncMock(return_value=1290.0)),
        patch(
            "app.services.notifications.email_service.send_exchange_rate_alert", new=AsyncMock(return_value=True)
        ) as mock_email,
        patch("app.services.notifications.push_service.send_push_to_user", new=AsyncMock(return_value=True)) as push,
        patch("app.services.alerts.alert_service.save_alert_history", new=AsyncMock()),
    ):
        from app.services.alerts.exchange_rate_service import check_and_trigger_alerts

        await check_and_trigger_alerts(mock_db)

    assert mock_email.await_args.kwargs["plan_label"] == "도쿄 여행"
    assert "도쿄 여행 구간 $500" in push.await_args.kwargs["body"]


async def test_alert_query_skips_past_due_needs(mock_db):
    mock_db.execute.return_value.all.return_value = []
    with (
        patch("app.services.alerts.exchange_rate_service.fetch_usd_krw", new=AsyncMock(return_value=1290.0)),
        patch("app.services.alerts.exchange_rate_service.today_kst", return_value=TODAY),
    ):
        from app.services.alerts.exchange_rate_service import check_and_trigger_alerts

        await check_and_trigger_alerts(mock_db)

    stmt = mock_db.execute.await_args.args[0]
    sql = str(stmt)
    assert "fx_extra_needs.due_date >=" in sql
    assert TODAY in stmt.compile().params.values()


def test_email_template_for_need():
    from app.services.notifications.email_templates.alerts import exchange_rate_alert_template

    subject, html = exchange_rate_alert_template(1300.0, "BELOW", 1290.0, 500.0, "https://x", "도쿄 여행")
    assert subject.startswith("[Growlio] 도쿄 여행 환전 구간 도달")
    assert "이미 환전한 금액" in html


# ── 지금 할 일 ──────────────────────────────────────────────


async def test_action_item_title_names_need():
    from app.services import action_items_service as ai

    rows = [
        (SimpleNamespace(target_rate=1320.0, planned_usd=300.0), "도쿄 여행"),
        (SimpleNamespace(target_rate=1300.0, planned_usd=200.0), "도쿄 여행"),
    ]
    with patch.object(ai, "_recent_fx_plan_alerts", new=AsyncMock(return_value=rows)):
        items = await ai._fx_plan_items(uuid.uuid4(), MagicMock(), CacheStore())
    assert items[0].title == "목표 환율 도달 — $500 환전 (도쿄 여행)"
    assert "이미 환전한 금액" in items[0].detail


async def test_action_item_mixed_with_dca_plan_counts_others():
    from app.services import action_items_service as ai

    rows = [
        (SimpleNamespace(target_rate=1320.0, planned_usd=300.0), None),
        (SimpleNamespace(target_rate=1300.0, planned_usd=200.0), "도쿄 여행"),
    ]
    with patch.object(ai, "_recent_fx_plan_alerts", new=AsyncMock(return_value=rows)):
        items = await ai._fx_plan_items(uuid.uuid4(), MagicMock(), CacheStore())
    assert items[0].title.endswith("(도쿄 여행 외 1건)")
    assert "계좌를 동기화" in items[0].detail


# ── API ─────────────────────────────────────────────────────


@pytest.fixture
def api():
    from app.api.deps import get_current_user
    from app.core.database import get_db
    from app.main import app

    user = SimpleNamespace(id=uuid.uuid4(), email="t@e.com", is_active=True, needs_password_reset=False)

    async def override_auth():
        return user

    async def override_db():
        yield MagicMock()

    app.dependency_overrides[get_current_user] = override_auth
    app.dependency_overrides[get_db] = override_db
    yield TestClient(app), user
    app.dependency_overrides.clear()


def _row_need():
    return SimpleNamespace(
        id=uuid.uuid4(),
        name="여행",
        amount_usd=500.0,
        exchanged_usd=0.0,
        due_date=date.today() + timedelta(days=60),
        created_at=datetime.now(UTC),
        reserved_account_id=None,
    )


def test_api_create_returns_row(api):
    client, user = api
    need = _row_need()
    ctx = fx_plan_service.FxRateContext(1400.0, True, None, has_rate=True)
    with (
        patch.object(svc, "create_fx_extra_need", new=AsyncMock(return_value=need)) as create,
        patch.object(fx_plan_service, "load_fx_rate_context", new=AsyncMock(return_value=ctx)),
    ):
        res = client.post(
            "/api/v1/invest/fx-extra-needs",
            json={"name": "  여행 ", "amount_usd": 500, "due_date": need.due_date.isoformat()},
        )
    assert res.status_code == 201, res.text
    body = res.json()
    assert (body["status"], body["remaining_usd"]) == ("OK", 500.0)
    assert create.await_args.args[1:] == (user.id, "여행", 500.0, 0.0, need.due_date)


@pytest.mark.parametrize(
    "payload",
    [
        {"name": " ", "amount_usd": 100, "due_date": "2099-01-01"},
        {"name": "x", "amount_usd": 0, "due_date": "2099-01-01"},
        {"name": "x", "amount_usd": 100, "exchanged_usd": -1, "due_date": "2099-01-01"},
        {"name": "x" * 41, "amount_usd": 100, "due_date": "2099-01-01"},
    ],
)
def test_api_create_validation_422(api, payload):
    client, _ = api
    assert client.post("/api/v1/invest/fx-extra-needs", json=payload).status_code == 422


def test_api_patch_sends_only_given_fields(api):
    client, _ = api
    need = _row_need()
    ctx = fx_plan_service.FxRateContext(1400.0, True, None, has_rate=True)
    with (
        patch.object(svc, "update_fx_extra_need", new=AsyncMock(return_value=need)) as update,
        patch.object(fx_plan_service, "load_fx_rate_context", new=AsyncMock(return_value=ctx)),
    ):
        res = client.patch(f"/api/v1/invest/fx-extra-needs/{need.id}", json={"exchanged_usd": 500})
    assert res.status_code == 200, res.text
    assert update.await_args.args[3] == {"exchanged_usd": 500.0}


def test_api_delete_invalidates_alert_cache(api):
    client, _ = api
    with (
        patch.object(svc, "delete_fx_extra_need", new=AsyncMock()) as delete,
        patch("app.api.v1.invest.invalidate_exchange_rate_alert_caches", new=AsyncMock()) as inv,
    ):
        res = client.delete(f"/api/v1/invest/fx-extra-needs/{uuid.uuid4()}")
    assert res.status_code == 204
    delete.assert_awaited_once()
    inv.assert_awaited_once()


def test_api_alert_sync_uses_need_scope(api):
    client, user = api
    need_id = uuid.uuid4()
    result = fx_plan_service.FxPlanAlertSyncResult(1, 0, 0, 0)
    with patch.object(fx_plan_service, "sync_fx_plan_alerts", new=AsyncMock(return_value=result)) as sync:
        res = client.put(
            f"/api/v1/invest/fx-extra-needs/{need_id}/alerts",
            json={"targets": [{"target_rate": 1350, "usd": 300}]},
        )
    assert res.status_code == 200, res.text
    assert sync.await_args.args[3] is None
    assert sync.await_args.kwargs == {"fx_need_id": need_id}
    assert sync.await_args.args[4] == [(1350.0, 300.0)]


def test_api_alert_sync_rejects_duplicate_targets(api):
    client, _ = api
    res = client.put(
        f"/api/v1/invest/fx-extra-needs/{uuid.uuid4()}/alerts",
        json={"targets": [{"target_rate": 1350, "usd": 1}, {"target_rate": 1350, "usd": 2}]},
    )
    assert res.status_code == 422


def test_api_list(api):
    client, _ = api
    with patch.object(
        svc, "list_fx_extra_needs", new=AsyncMock(return_value={"rate": None, "rate_is_live": True, "needs": []})
    ):
        res = client.get("/api/v1/invest/fx-extra-needs")
    assert res.status_code == 200
    assert res.json()["needs"] == []


# ── 보관 증권 계좌(plans/123 후속) ───────────────────────────


def test_need_row_includes_reserved_account():
    n = _need()
    n.reserved_account_id = uuid.uuid4()
    row = svc.build_need_row(n, None, 1400.0, True, TODAY, "메리츠")
    assert (row["reserved_account_id"], row["reserved_account_name"]) == (n.reserved_account_id, "메리츠")
    n.reserved_account_id = None
    assert svc.build_need_row(n, None, 1400.0, True, TODAY, "메리츠")["reserved_account_name"] is None


async def test_list_returns_reserved_account_name():
    n = _need()
    n.reserved_account_id = uuid.uuid4()
    ctx = fx_plan_service.FxRateContext(1400.0, True, None, has_rate=True)
    with (
        patch.object(svc, "load_fx_rate_context", new=AsyncMock(return_value=ctx)),
        patch.object(svc, "today_kst", return_value=TODAY),
    ):
        data = await svc.list_fx_extra_needs(_list_db([n], ["메리츠"]), CacheStore(), uuid.uuid4())
    assert data["needs"][0]["reserved_account_name"] == "메리츠"


async def test_create_rejects_unowned_or_non_stock_account():
    db = MagicMock()
    db.scalar = AsyncMock(return_value=None)  # 소유한 활성 증권 계좌가 아님
    with patch.object(svc, "today_kst", return_value=TODAY), pytest.raises(NotFoundError):
        await svc.create_fx_extra_need(db, uuid.uuid4(), "여행", 100.0, 0.0, TODAY, reserved_account_id=uuid.uuid4())
    stmt = db.scalar.await_args.args[0]
    sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "STOCK_OTHER" in sql
    assert "is_active" in sql


async def test_create_saves_reserved_account():
    account = SimpleNamespace(id=uuid.uuid4())
    db = MagicMock()
    db.scalar = AsyncMock(side_effect=[account, 0])
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    with patch.object(svc, "today_kst", return_value=TODAY):
        need = await svc.create_fx_extra_need(
            db, uuid.uuid4(), "여행", 100.0, 0.0, TODAY, reserved_account_id=account.id
        )
    assert need.reserved_account_id == account.id


async def test_update_clears_reserved_account_with_null():
    need = _need()
    need.reserved_account_id = uuid.uuid4()
    db = _crud_db(need=need)
    with patch.object(svc, "today_kst", return_value=TODAY):
        await svc.update_fx_extra_need(db, uuid.uuid4(), need.id, {"reserved_account_id": None})
    assert need.reserved_account_id is None


async def test_update_validates_new_reserved_account():
    need = _need()
    db = MagicMock()
    db.scalar = AsyncMock(side_effect=[need, None])
    with patch.object(svc, "today_kst", return_value=TODAY), pytest.raises(NotFoundError):
        await svc.update_fx_extra_need(db, uuid.uuid4(), need.id, {"reserved_account_id": uuid.uuid4()})


def test_api_patch_passes_null_reserved_account(api):
    client, _ = api
    need = _row_need()
    ctx = fx_plan_service.FxRateContext(1400.0, True, None, has_rate=True)
    with (
        patch.object(svc, "update_fx_extra_need", new=AsyncMock(return_value=need)) as update,
        patch.object(fx_plan_service, "load_fx_rate_context", new=AsyncMock(return_value=ctx)),
    ):
        res = client.patch(f"/api/v1/invest/fx-extra-needs/{need.id}", json={"reserved_account_id": None, "name": None})
    assert res.status_code == 200, res.text
    # name의 null은 무시, 보관 계좌의 null은 해제 값으로 전달
    assert update.await_args.args[3] == {"reserved_account_id": None}
