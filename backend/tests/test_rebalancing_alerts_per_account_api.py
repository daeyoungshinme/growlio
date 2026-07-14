"""rebalancing_alerts.py의 계좌별 독립 설정(PER_ACCOUNT) 엔드포인트 테스트."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient


def _make_user():
    return SimpleNamespace(
        id=uuid.uuid4(),
        email="test@example.com",
        display_name="테스트",
        is_active=True,
        needs_password_reset=False,
    )


def _make_mock_db():
    from sqlalchemy.ext.asyncio import AsyncSession

    db = AsyncMock(spec=AsyncSession)
    db.scalar = AsyncMock(return_value=None)
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    result.all.return_value = []
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    return db


def _setup_app(user, db):
    from app.api.deps import get_current_user
    from app.database import get_db
    from app.main import app

    async def override_auth():
        return user

    async def override_db():
        yield db

    app.dependency_overrides[get_current_user] = override_auth
    app.dependency_overrides[get_db] = override_db
    return app


def _make_portfolio(user_id, alert_scope="AGGREGATE", linked_account_ids=None):
    linked_account_ids = linked_account_ids or []
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        name="테스트 포트폴리오",
        alert_scope=alert_scope,
        linked_accounts=[SimpleNamespace(account_id=aid) for aid in linked_account_ids],
    )


def _make_account_alert_orm(user_id, portfolio_id, account_id):
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        portfolio_id=portfolio_id,
        threshold_pct=5.0,
        schedule_type="DAILY",
        schedule_day_of_week=None,
        schedule_day_of_month=None,
        trigger_condition="DRIFT_ONLY",
        mode="NOTIFY",
        strategy="BUY_ONLY",
        account_id=account_id,
        order_type="MARKET",
        market_condition_mode="DISABLED",
        auto_execution_time=None,
        notify_time="08:30",
        is_active=True,
        last_triggered_at=None,
        created_at=now,
        updated_at=now,
    )


class TestUpdateAlertScope:
    def test_returns_404_when_portfolio_not_found(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=None)
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.put(f"/api/v1/alerts/rebalancing/{uuid.uuid4()}/scope", json={"alert_scope": "PER_ACCOUNT"})
        assert resp.status_code == 404

    def test_rejects_per_account_with_fewer_than_two_linked_accounts(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        portfolio = _make_portfolio(user.id, "AGGREGATE", [uuid.uuid4()])
        db.scalar = AsyncMock(return_value=portfolio)
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.put(f"/api/v1/alerts/rebalancing/{portfolio.id}/scope", json={"alert_scope": "PER_ACCOUNT"})
        assert resp.status_code == 422

    def test_switches_to_per_account_successfully(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        acc1, acc2 = uuid.uuid4(), uuid.uuid4()
        portfolio = _make_portfolio(user.id, "AGGREGATE", [acc1, acc2])
        # 1st scalar: _get_portfolio_with_accounts, 2nd scalar: get_alert_by_portfolio(기존 aggregate 행 없음)
        db.scalar = AsyncMock(side_effect=[portfolio, None])
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.put(f"/api/v1/alerts/rebalancing/{portfolio.id}/scope", json={"alert_scope": "PER_ACCOUNT"})
        assert resp.status_code == 204
        assert portfolio.alert_scope == "PER_ACCOUNT"

    def test_switches_back_to_aggregate_and_deletes_per_account_rows(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        acc1, acc2 = uuid.uuid4(), uuid.uuid4()
        portfolio = _make_portfolio(user.id, "PER_ACCOUNT", [acc1, acc2])
        db.scalar = AsyncMock(return_value=portfolio)
        exec_result = MagicMock()
        exec_result.scalars.return_value.all.return_value = [
            _make_account_alert_orm(user.id, portfolio.id, acc1),
            _make_account_alert_orm(user.id, portfolio.id, acc2),
        ]
        db.execute = AsyncMock(return_value=exec_result)
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.put(f"/api/v1/alerts/rebalancing/{portfolio.id}/scope", json={"alert_scope": "AGGREGATE"})
        assert resp.status_code == 204
        assert portfolio.alert_scope == "AGGREGATE"
        assert db.delete.await_count == 2


class TestAggregateEndpointsRejectPerAccountScope:
    def test_get_rejects_when_per_account_scope(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        portfolio = _make_portfolio(user.id, "PER_ACCOUNT", [uuid.uuid4(), uuid.uuid4()])
        db.scalar = AsyncMock(return_value=portfolio)
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get(f"/api/v1/alerts/rebalancing/{portfolio.id}")
        assert resp.status_code == 409

    def test_upsert_rejects_when_per_account_scope(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        portfolio = _make_portfolio(user.id, "PER_ACCOUNT", [uuid.uuid4(), uuid.uuid4()])
        db.scalar = AsyncMock(return_value=portfolio)
        app = _setup_app(user, db)
        payload = {"portfolio_id": str(portfolio.id), "threshold_pct": 5.0}
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.put(f"/api/v1/alerts/rebalancing/{portfolio.id}", json=payload)
        assert resp.status_code == 409

    def test_delete_rejects_when_per_account_scope(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        portfolio = _make_portfolio(user.id, "PER_ACCOUNT", [uuid.uuid4(), uuid.uuid4()])
        db.scalar = AsyncMock(return_value=portfolio)
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.delete(f"/api/v1/alerts/rebalancing/{portfolio.id}")
        assert resp.status_code == 409


class TestListAccountRebalancingAlerts:
    def test_returns_empty_list_when_none_configured(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        portfolio = _make_portfolio(user.id, "PER_ACCOUNT", [uuid.uuid4(), uuid.uuid4()])
        db.scalar = AsyncMock(return_value=portfolio)
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get(f"/api/v1/alerts/rebalancing/{portfolio.id}/accounts")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_404_when_portfolio_not_found(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=None)
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get(f"/api/v1/alerts/rebalancing/{uuid.uuid4()}/accounts")
        assert resp.status_code == 404


class TestUpsertAccountRebalancingAlert:
    def test_rejects_when_not_per_account_scope(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        account_id = uuid.uuid4()
        portfolio = _make_portfolio(user.id, "AGGREGATE", [account_id, uuid.uuid4()])
        db.scalar = AsyncMock(return_value=portfolio)
        app = _setup_app(user, db)
        payload = {"portfolio_id": str(portfolio.id), "threshold_pct": 5.0}
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.put(f"/api/v1/alerts/rebalancing/{portfolio.id}/accounts/{account_id}", json=payload)
        assert resp.status_code == 409

    def test_rejects_account_not_linked_to_portfolio(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        linked1, linked2 = uuid.uuid4(), uuid.uuid4()
        unlinked = uuid.uuid4()
        portfolio = _make_portfolio(user.id, "PER_ACCOUNT", [linked1, linked2])
        db.scalar = AsyncMock(return_value=portfolio)
        app = _setup_app(user, db)
        payload = {"portfolio_id": str(portfolio.id), "threshold_pct": 5.0}
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.put(f"/api/v1/alerts/rebalancing/{portfolio.id}/accounts/{unlinked}", json=payload)
        assert resp.status_code == 422

    def test_creates_new_account_alert(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        acc1, acc2 = uuid.uuid4(), uuid.uuid4()
        portfolio = _make_portfolio(user.id, "PER_ACCOUNT", [acc1, acc2])
        now = datetime.now(UTC)
        # 1st scalar: _get_portfolio_with_accounts, 2nd: get_alert_by_portfolio_and_account(없음)
        db.scalar = AsyncMock(side_effect=[portfolio, None])

        def _refresh(obj):
            obj.id = uuid.uuid4()
            obj.is_active = True
            obj.last_triggered_at = None
            obj.created_at = now
            obj.updated_at = now

        db.refresh = AsyncMock(side_effect=_refresh)
        app = _setup_app(user, db)
        payload = {"portfolio_id": str(portfolio.id), "threshold_pct": 7.5, "mode": "NOTIFY"}
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.put(f"/api/v1/alerts/rebalancing/{portfolio.id}/accounts/{acc1}", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["account_id"] == str(acc1)
        assert body["threshold_pct"] == 7.5

    def test_updates_existing_account_alert(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        acc1, acc2 = uuid.uuid4(), uuid.uuid4()
        portfolio = _make_portfolio(user.id, "PER_ACCOUNT", [acc1, acc2])
        existing = _make_account_alert_orm(user.id, portfolio.id, acc1)
        db.scalar = AsyncMock(side_effect=[portfolio, existing])
        db.refresh = AsyncMock(side_effect=lambda obj: None)
        app = _setup_app(user, db)
        payload = {"portfolio_id": str(portfolio.id), "threshold_pct": 12.0, "mode": "NOTIFY"}
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.put(f"/api/v1/alerts/rebalancing/{portfolio.id}/accounts/{acc1}", json=payload)
        assert resp.status_code == 200
        assert existing.threshold_pct == 12.0
        assert existing.account_id == acc1

    def test_auto_mode_with_non_kis_account_rejected(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        acc1, acc2 = uuid.uuid4(), uuid.uuid4()
        portfolio = _make_portfolio(user.id, "PER_ACCOUNT", [acc1, acc2])
        non_kis_account = SimpleNamespace(id=acc1, user_id=user.id, asset_type="STOCK_KIWOOM")
        # 1st scalar: _get_portfolio_with_accounts, 2nd: exec_account lookup for AUTO validation
        db.scalar = AsyncMock(side_effect=[portfolio, non_kis_account])
        app = _setup_app(user, db)
        payload = {"portfolio_id": str(portfolio.id), "threshold_pct": 5.0, "mode": "AUTO"}
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.put(f"/api/v1/alerts/rebalancing/{portfolio.id}/accounts/{acc1}", json=payload)
        assert resp.status_code == 422


class TestDeleteAccountRebalancingAlert:
    def test_deletes_existing(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        account_id = uuid.uuid4()
        portfolio = _make_portfolio(user.id, "PER_ACCOUNT", [account_id, uuid.uuid4()])
        existing = _make_account_alert_orm(user.id, portfolio.id, account_id)
        db.scalar = AsyncMock(side_effect=[portfolio, existing])
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.delete(f"/api/v1/alerts/rebalancing/{portfolio.id}/accounts/{account_id}")
        assert resp.status_code == 204

    def test_returns_404_when_not_found(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        account_id = uuid.uuid4()
        portfolio = _make_portfolio(user.id, "PER_ACCOUNT", [account_id, uuid.uuid4()])
        db.scalar = AsyncMock(side_effect=[portfolio, None])
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.delete(f"/api/v1/alerts/rebalancing/{portfolio.id}/accounts/{account_id}")
        assert resp.status_code == 404


class TestTriggerAccountRebalancingAlertTest:
    def test_returns_404_when_alert_not_configured(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=None)
        app = _setup_app(user, db)
        portfolio_id = uuid.uuid4()
        account_id = uuid.uuid4()
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post(f"/api/v1/alerts/rebalancing/{portfolio_id}/accounts/{account_id}/test")
        assert resp.status_code == 404

    def test_sends_test_alert_for_account(self, override_settings):
        from unittest.mock import patch

        user = _make_user()
        db = _make_mock_db()
        portfolio_id = uuid.uuid4()
        account_id = uuid.uuid4()
        existing = _make_account_alert_orm(user.id, portfolio_id, account_id)
        db.scalar = AsyncMock(return_value=existing)
        app = _setup_app(user, db)

        with (
            TestClient(app, raise_server_exceptions=False) as client,
            patch(
                "app.services.rebalancing.alert_test.send_test_rebalancing_alert",
                new=AsyncMock(return_value={"email_sent": True, "push_sent": False}),
            ) as mock_send,
        ):
            resp = client.post(f"/api/v1/alerts/rebalancing/{portfolio_id}/accounts/{account_id}/test")

        assert resp.status_code == 200
        assert resp.json()["email_sent"] is True
        mock_send.assert_awaited_once_with(
            portfolio_id=portfolio_id,
            user_id=user.id,
            db=db,
            account_id=account_id,
        )
