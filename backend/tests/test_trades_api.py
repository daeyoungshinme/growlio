"""수기 매매 기록 CRUD + 기간별 매수 현황 API 테스트 (/api/v1/trades)."""

import uuid
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

AUTH = {"Authorization": "Bearer fake"}


def _make_user():
    return SimpleNamespace(id=uuid.uuid4(), email="t@example.com", is_active=True, needs_password_reset=False)


def _make_mock_db():
    from sqlalchemy.ext.asyncio import AsyncSession

    db = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=result)
    db.scalar = AsyncMock(return_value=None)
    db.commit = AsyncMock()
    db.add = MagicMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    return db


def _trade(user_id):
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        account_id=uuid.uuid4(),
        side="BUY",
        ticker="005930",
        market="KOSPI",
        name="삼성전자",
        qty=10,
        price_krw=70_000,
        fee=None,
        trade_date=date(2026, 10, 2),
        notes=None,
        created_at=datetime(2026, 10, 2),
    )


@pytest.fixture
def client_ctx(override_settings):
    from app.api.deps import get_current_user
    from app.core.database import get_db
    from app.main import app

    user = _make_user()
    db = _make_mock_db()

    async def override_auth():
        return user

    async def override_db():
        yield db

    app.dependency_overrides[get_current_user] = override_auth
    app.dependency_overrides[get_db] = override_db
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, user, db
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db, None)


_EMPTY_SUMMARY = {
    "start": date(2026, 10, 1),
    "end": date(2026, 10, 8),
    "items": [],
    "summary": {
        "bought_amount_krw": 0,
        "held_cost_krw": 0,
        "value_krw": 0,
        "realized_pnl_krw": 0,
        "total_pnl_krw": 0,
        "return_pct": None,
    },
    "tracking_started": [],
}


class TestPeriodSummary:
    def test_defaults_to_current_month(self, client_ctx):
        client, user, _ = client_ctx
        with (
            patch("app.api.v1.trades.today_kst", return_value=date(2026, 10, 8)),
            patch("app.api.v1.trades.get_period_purchases", AsyncMock(return_value=_EMPTY_SUMMARY)) as svc,
        ):
            resp = client.get("/api/v1/trades/period-summary", headers=AUTH)
        assert resp.status_code == 200
        args = svc.await_args.args
        assert args[2:5] == (date(2026, 10, 1), date(2026, 10, 31), date(2026, 10, 8))

    def test_year_period(self, client_ctx):
        client, _, _ = client_ctx
        with (
            patch("app.api.v1.trades.today_kst", return_value=date(2026, 10, 8)),
            patch("app.api.v1.trades.get_period_purchases", AsyncMock(return_value=_EMPTY_SUMMARY)) as svc,
        ):
            resp = client.get("/api/v1/trades/period-summary?period=year&year=2025", headers=AUTH)
        assert resp.status_code == 200
        assert svc.await_args.args[2:4] == (date(2025, 1, 1), date(2025, 12, 31))

    def test_future_period_rejected(self, client_ctx):
        client, _, _ = client_ctx
        with patch("app.api.v1.trades.today_kst", return_value=date(2026, 10, 8)):
            resp = client.get("/api/v1/trades/period-summary?period=month&year=2026&month=11", headers=AUTH)
        assert resp.status_code == 400

    def test_foreign_account_404(self, client_ctx):
        client, _, db = client_ctx
        db.scalar = AsyncMock(return_value=None)
        resp = client.get(f"/api/v1/trades/period-summary?account_id={uuid.uuid4()}", headers=AUTH)
        assert resp.status_code == 404


class TestTradeCrud:
    def test_list(self, client_ctx):
        client, _, _ = client_ctx
        resp = client.get("/api/v1/trades", headers=AUTH)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_requires_owned_account(self, client_ctx):
        client, _, db = client_ctx
        db.scalar = AsyncMock(return_value=None)
        body = {
            "account_id": str(uuid.uuid4()),
            "side": "BUY",
            "ticker": "005930",
            "market": "KOSPI",
            "qty": 10,
            "price_krw": 70000,
            "trade_date": "2026-10-02",
        }
        resp = client.post("/api/v1/trades", json=body, headers=AUTH)
        assert resp.status_code == 404
        db.add.assert_not_called()

    def test_create(self, client_ctx):
        client, user, db = client_ctx
        db.scalar = AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4()))

        async def fake_refresh(obj):
            obj.id = uuid.uuid4()
            obj.created_at = datetime(2026, 10, 2)

        db.refresh = AsyncMock(side_effect=fake_refresh)
        body = {
            "account_id": str(uuid.uuid4()),
            "side": "BUY",
            "ticker": " aapl ",
            "market": "NASDAQ",
            "qty": 2,
            "price_krw": 300000,
            "trade_date": "2026-10-02",
        }
        resp = client.post("/api/v1/trades", json=body, headers=AUTH)
        assert resp.status_code == 201
        assert resp.json()["ticker"] == "AAPL"
        db.commit.assert_awaited()

    def test_create_rejects_non_positive_price(self, client_ctx):
        client, _, _ = client_ctx
        body = {
            "account_id": str(uuid.uuid4()),
            "side": "BUY",
            "ticker": "005930",
            "market": "KOSPI",
            "qty": 1,
            "price_krw": 0,
            "trade_date": "2026-10-02",
        }
        assert client.post("/api/v1/trades", json=body, headers=AUTH).status_code == 422

    def test_update(self, client_ctx):
        client, user, db = client_ctx
        trade = _trade(user.id)
        db.scalar = AsyncMock(return_value=trade)
        resp = client.put(f"/api/v1/trades/{trade.id}", json={"qty": 5}, headers=AUTH)
        assert resp.status_code == 200
        assert trade.qty == 5

    def test_create_rejects_future_date(self, client_ctx):
        client, _, _ = client_ctx
        body = {
            "account_id": str(uuid.uuid4()),
            "side": "BUY",
            "ticker": "005930",
            "market": "KOSPI",
            "qty": 1,
            "price_krw": 70000,
            "trade_date": "2026-10-09",
        }
        with patch("app.schemas.trade.today_kst", return_value=date(2026, 10, 8)):
            assert client.post("/api/v1/trades", json=body, headers=AUTH).status_code == 422

    def test_update_null_clears_fee_and_notes_but_keeps_required(self, client_ctx):
        client, user, db = client_ctx
        trade = _trade(user.id)
        trade.fee, trade.notes = 500, "메모"
        db.scalar = AsyncMock(return_value=trade)
        resp = client.put(f"/api/v1/trades/{trade.id}", json={"fee": None, "notes": None, "qty": None}, headers=AUTH)
        assert resp.status_code == 200
        assert trade.fee is None
        assert trade.notes is None
        assert trade.qty == 10  # 필수 필드의 null은 "변경 없음"

    def test_delete_404(self, client_ctx):
        client, _, db = client_ctx
        db.scalar = AsyncMock(return_value=None)
        resp = client.delete(f"/api/v1/trades/{uuid.uuid4()}", headers=AUTH)
        assert resp.status_code == 404

    def test_delete(self, client_ctx):
        client, user, db = client_ctx
        trade = _trade(user.id)
        db.scalar = AsyncMock(return_value=trade)
        resp = client.delete(f"/api/v1/trades/{trade.id}", headers=AUTH)
        assert resp.status_code == 204
        db.delete.assert_awaited_with(trade)
