"""alerts API 테스트 (GET/POST/DELETE /api/v1/alerts/...)."""

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


def _make_alert_orm(user_id):
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        target_rate=1300.0,
        direction="BELOW",
        is_active=True,
        max_trigger_count=1,
        trigger_count=0,
        triggered_at=None,
        created_at=datetime.now(UTC),
    )


class TestExchangeRateAlerts:
    def test_list_returns_401_without_auth(self, override_settings):
        from app.api.deps import get_current_user
        from app.main import app

        app.dependency_overrides.pop(get_current_user, None)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/alerts/exchange-rate")
        assert resp.status_code == 401

    def test_list_returns_200(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/alerts/exchange-rate")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_create_exchange_rate_alert(self, override_settings):
        user = _make_user()
        db = _make_mock_db()

        alert_orm = _make_alert_orm(user.id)
        db.refresh = AsyncMock(side_effect=lambda obj: None)

        app = _setup_app(user, db)
        payload = {"target_rate": 1300.0, "direction": "BELOW", "max_trigger_count": 1}

        from unittest.mock import patch

        with (
            TestClient(app, raise_server_exceptions=False) as client,
            patch("app.api.v1.exchange_rate_alerts.ExchangeRateAlert") as MockAlert,
        ):
            instance = MagicMock()
            instance.id = alert_orm.id
            instance.user_id = user.id
            instance.target_rate = 1300.0
            instance.direction = "BELOW"
            instance.is_active = True
            instance.max_trigger_count = 1
            instance.trigger_count = 0
            instance.triggered_at = None
            instance.created_at = datetime.now(UTC)
            MockAlert.return_value = instance
            resp = client.post("/api/v1/alerts/exchange-rate", json=payload)
        assert resp.status_code in (200, 201)

    def test_create_validates_target_rate(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        payload = {"target_rate": -100.0, "direction": "BELOW"}
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post("/api/v1/alerts/exchange-rate", json=payload)
        assert resp.status_code == 422

    def test_delete_not_found(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=None)
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.delete(f"/api/v1/alerts/exchange-rate/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestStockPriceAlerts:
    def test_list_stock_price_alerts(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/alerts/stock-price")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_delete_stock_price_alert_not_found(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=None)
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.delete(f"/api/v1/alerts/stock-price/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestAlertHistory:
    def test_list_alert_history_returns_200(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/alerts/history")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestRebalancingAlerts:
    def test_list_rebalancing_alerts(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/alerts/rebalancing")
        assert resp.status_code == 200

    def test_get_rebalancing_alert_not_found(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=None)
        app = _setup_app(user, db)
        portfolio_id = uuid.uuid4()
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get(f"/api/v1/alerts/rebalancing/{portfolio_id}")
        assert resp.status_code == 404


class TestExchangeRateAlertExtended:
    def test_reactivate_exchange_rate_alert_not_found(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=None)
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.patch(f"/api/v1/alerts/exchange-rate/{uuid.uuid4()}/reactivate")
        assert resp.status_code == 404

    def test_reactivate_exchange_rate_alert_success(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        alert_orm = SimpleNamespace(
            id=uuid.uuid4(),
            user_id=user.id,
            target_rate=1300.0,
            direction="BELOW",
            is_active=False,
            max_trigger_count=1,
            trigger_count=3,
            triggered_at=None,
            created_at=datetime.now(UTC),
        )
        db.scalar = AsyncMock(return_value=alert_orm)
        db.refresh = AsyncMock(side_effect=lambda obj: None)
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.patch(f"/api/v1/alerts/exchange-rate/{alert_orm.id}/reactivate")
        assert resp.status_code == 200
        assert alert_orm.is_active is True
        assert alert_orm.trigger_count == 0

    def test_delete_exchange_rate_alert_success(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        alert_orm = SimpleNamespace(
            id=uuid.uuid4(),
            user_id=user.id,
            target_rate=1300.0,
            direction="BELOW",
            is_active=True,
            max_trigger_count=1,
            trigger_count=0,
            triggered_at=None,
            created_at=datetime.now(UTC),
        )
        db.scalar = AsyncMock(return_value=alert_orm)
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.delete(f"/api/v1/alerts/exchange-rate/{alert_orm.id}")
        assert resp.status_code == 204


class TestRebalancingAlertExtended:
    def _make_rebalancing_alert_orm(self, user_id, portfolio_id):
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
            account_id=None,
            order_type="MARKET",
            market_condition_mode="DISABLED",
            is_active=True,
            last_triggered_at=None,
            deposit_trigger_enabled=False,
            deposit_accounts=[],
            deposit_trigger_min_amount_krw=None,
            last_deposit_checked_at=None,
            created_at=now,
            updated_at=now,
        )

    def test_upsert_rebalancing_alert_portfolio_not_found(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=None)
        app = _setup_app(user, db)
        portfolio_id = uuid.uuid4()
        payload = {"portfolio_id": str(portfolio_id), "threshold_pct": 5.0}
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.put(f"/api/v1/alerts/rebalancing/{portfolio_id}", json=payload)
        assert resp.status_code == 404

    def test_upsert_rebalancing_alert_create_new(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        portfolio_id = uuid.uuid4()
        portfolio_orm = SimpleNamespace(id=portfolio_id, user_id=user.id, name="테스트")
        now = datetime.now(UTC)
        # First scalar returns portfolio, second returns None (no existing alert)
        db.scalar = AsyncMock(side_effect=[portfolio_orm, None])

        def _refresh(obj):
            # Populate DB-generated fields on the new alert
            obj.id = uuid.uuid4()
            obj.is_active = True
            obj.last_triggered_at = None
            obj.deposit_accounts = []
            obj.created_at = now
            obj.updated_at = now

        db.refresh = AsyncMock(side_effect=_refresh)
        app = _setup_app(user, db)
        payload = {"portfolio_id": str(portfolio_id), "threshold_pct": 5.0}
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.put(f"/api/v1/alerts/rebalancing/{portfolio_id}", json=payload)
        assert resp.status_code in (200, 201)

    def test_upsert_rebalancing_alert_auto_mode_sets_aggregate_scope(self, override_settings):
        """회귀 테스트: AGGREGATE 포트폴리오에서 AUTO 모드로 저장해도 alert_scope는 AGGREGATE로

        저장되어야 한다. account_id(실행계좌)는 AUTO 모드면 NOT NULL이 되므로, 과거에는 이
        NOT NULL 여부로 스코프를 판별해 저장 직후 재조회(GET)가 항상 404를 내는 버그가 있었다.
        """
        user = _make_user()
        db = _make_mock_db()
        portfolio_id = uuid.uuid4()
        exec_account_id = uuid.uuid4()
        portfolio_orm = SimpleNamespace(id=portfolio_id, user_id=user.id, name="테스트")
        exec_account = SimpleNamespace(id=exec_account_id, user_id=user.id, asset_type="STOCK_KIS")
        now = datetime.now(UTC)
        # 1st scalar: portfolio, 2nd: AUTO 실행계좌 검증, 3rd: get_alert_by_portfolio(기존 알림 없음)
        db.scalar = AsyncMock(side_effect=[portfolio_orm, exec_account, None])

        created_alert = {}

        def _capture_add(obj):
            created_alert["obj"] = obj

        db.add = MagicMock(side_effect=_capture_add)

        def _refresh(obj):
            obj.id = uuid.uuid4()
            obj.is_active = True
            obj.last_triggered_at = None
            obj.deposit_accounts = []
            obj.created_at = now
            obj.updated_at = now

        db.refresh = AsyncMock(side_effect=_refresh)
        app = _setup_app(user, db)
        payload = {
            "portfolio_id": str(portfolio_id),
            "threshold_pct": 5.0,
            "mode": "AUTO",
            "account_id": str(exec_account_id),
        }
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.put(f"/api/v1/alerts/rebalancing/{portfolio_id}", json=payload)
        assert resp.status_code in (200, 201)
        assert created_alert["obj"].account_id == exec_account_id
        assert created_alert["obj"].alert_scope == "AGGREGATE"

    def test_upsert_rebalancing_alert_auto_to_notify_disables_auto_and_stays_gettable(self, override_settings):
        """회귀 테스트: AGGREGATE+AUTO 알림을 NOTIFY로 전환(자동 리밸런싱 해제)해도

        alert_scope는 AGGREGATE로 유지되고 account_id는 비워지며, 저장 직후 GET이 여전히
        200으로 정상 조회되어야 한다 (스코프 드리프트로 알림이 사라진 것처럼 보이는 회귀 방지 —
        as1의 잘못된 백필로 발견된 좀비 알림 버그와 같은 계열).
        """
        user = _make_user()
        db = _make_mock_db()
        portfolio_id = uuid.uuid4()
        portfolio_orm = SimpleNamespace(id=portfolio_id, user_id=user.id, name="테스트")
        alert_orm = self._make_rebalancing_alert_orm(user.id, portfolio_id)
        alert_orm.alert_scope = "AGGREGATE"
        alert_orm.mode = "AUTO"
        alert_orm.account_id = uuid.uuid4()

        # PUT: 1st scalar portfolio, 2nd get_alert_by_portfolio(기존 알림)
        # GET: 3rd scalar portfolio, 4th get_alert_by_portfolio(방금 수정된 알림)
        db.scalar = AsyncMock(side_effect=[portfolio_orm, alert_orm, portfolio_orm, alert_orm])
        db.refresh = AsyncMock(side_effect=lambda obj: None)
        app = _setup_app(user, db)
        payload = {"portfolio_id": str(portfolio_id), "threshold_pct": 5.0, "mode": "NOTIFY"}
        with TestClient(app, raise_server_exceptions=False) as client:
            put_resp = client.put(f"/api/v1/alerts/rebalancing/{portfolio_id}", json=payload)
            get_resp = client.get(f"/api/v1/alerts/rebalancing/{portfolio_id}")

        assert put_resp.status_code in (200, 201)
        assert alert_orm.mode == "NOTIFY"
        assert alert_orm.account_id is None
        assert alert_orm.alert_scope == "AGGREGATE"
        assert get_resp.status_code == 200
        assert get_resp.json()["mode"] == "NOTIFY"

    def test_upsert_rebalancing_alert_update_existing(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        portfolio_id = uuid.uuid4()
        portfolio_orm = SimpleNamespace(id=portfolio_id, user_id=user.id, name="테스트")
        alert_orm = self._make_rebalancing_alert_orm(user.id, portfolio_id)
        # First scalar returns portfolio, second returns existing alert
        db.scalar = AsyncMock(side_effect=[portfolio_orm, alert_orm])
        db.refresh = AsyncMock(side_effect=lambda obj: None)
        app = _setup_app(user, db)
        payload = {"portfolio_id": str(portfolio_id), "threshold_pct": 10.0}
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.put(f"/api/v1/alerts/rebalancing/{portfolio_id}", json=payload)
        assert resp.status_code in (200, 201)
        assert alert_orm.threshold_pct == 10.0

    def test_delete_rebalancing_alert_success(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        portfolio_id = uuid.uuid4()
        alert_orm = self._make_rebalancing_alert_orm(user.id, portfolio_id)
        db.scalar = AsyncMock(return_value=alert_orm)
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.delete(f"/api/v1/alerts/rebalancing/{portfolio_id}")
        assert resp.status_code == 204

    def test_delete_rebalancing_alert_not_found(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=None)
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.delete(f"/api/v1/alerts/rebalancing/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_rebalancing_alert_validator_invalid_threshold(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        portfolio_id = uuid.uuid4()
        portfolio_orm = SimpleNamespace(id=portfolio_id, user_id=user.id, name="테스트")
        db.scalar = AsyncMock(return_value=portfolio_orm)
        app = _setup_app(user, db)
        payload = {"portfolio_id": str(portfolio_id), "threshold_pct": 99.0}
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.put(f"/api/v1/alerts/rebalancing/{portfolio_id}", json=payload)
        assert resp.status_code == 422

    def test_rebalancing_alert_validator_invalid_dow(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        portfolio_id = uuid.uuid4()
        portfolio_orm = SimpleNamespace(id=portfolio_id, user_id=user.id, name="테스트")
        db.scalar = AsyncMock(return_value=portfolio_orm)
        app = _setup_app(user, db)
        payload = {
            "portfolio_id": str(portfolio_id),
            "threshold_pct": 5.0,
            "schedule_type": "WEEKLY",
            "schedule_day_of_week": 9,
        }
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.put(f"/api/v1/alerts/rebalancing/{portfolio_id}", json=payload)
        assert resp.status_code == 422

    def test_test_rebalancing_alert_not_found(self, override_settings):
        """알림 미설정 시 404 반환."""
        user = _make_user()
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=None)
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post(f"/api/v1/alerts/rebalancing/{uuid.uuid4()}/test")
        assert resp.status_code == 404

    def test_test_rebalancing_alert_email_and_push_success(self, override_settings):
        """이메일+FCM 모두 성공 시 200 반환."""
        from unittest.mock import AsyncMock as AM
        from unittest.mock import patch

        user = _make_user()
        db = _make_mock_db()
        portfolio_id = uuid.uuid4()
        alert_orm = self._make_rebalancing_alert_orm(user.id, portfolio_id)
        db.scalar = AsyncMock(return_value=alert_orm)
        app = _setup_app(user, db)

        with (
            patch(
                "app.services.rebalancing_alert_service.send_test_rebalancing_alert",
                new=AM(return_value={"email_sent": True, "push_sent": True}),
            ),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.post(f"/api/v1/alerts/rebalancing/{portfolio_id}/test")

        assert resp.status_code == 200
        data = resp.json()
        assert data["email_sent"] is True
        assert data["push_sent"] is True
        assert "✓" in data["message"]

    def test_test_rebalancing_alert_email_only(self, override_settings):
        """이메일만 성공(FCM 미설정) 시 적절한 message 반환."""
        from unittest.mock import AsyncMock as AM
        from unittest.mock import patch

        user = _make_user()
        db = _make_mock_db()
        portfolio_id = uuid.uuid4()
        alert_orm = self._make_rebalancing_alert_orm(user.id, portfolio_id)
        db.scalar = AsyncMock(return_value=alert_orm)
        app = _setup_app(user, db)

        with (
            patch(
                "app.services.rebalancing_alert_service.send_test_rebalancing_alert",
                new=AM(return_value={"email_sent": True, "push_sent": False}),
            ),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.post(f"/api/v1/alerts/rebalancing/{portfolio_id}/test")

        assert resp.status_code == 200
        data = resp.json()
        assert data["email_sent"] is True
        assert data["push_sent"] is False
        assert "FCM" in data["message"]

    def test_test_rebalancing_alert_no_channel(self, override_settings):
        """이메일+FCM 모두 실패해도 200 반환 (결과를 유저에게 알림)."""
        from unittest.mock import AsyncMock as AM
        from unittest.mock import patch

        user = _make_user()
        db = _make_mock_db()
        portfolio_id = uuid.uuid4()
        alert_orm = self._make_rebalancing_alert_orm(user.id, portfolio_id)
        db.scalar = AsyncMock(return_value=alert_orm)
        app = _setup_app(user, db)

        with (
            patch(
                "app.services.rebalancing_alert_service.send_test_rebalancing_alert",
                new=AM(return_value={"email_sent": False, "push_sent": False}),
            ),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.post(f"/api/v1/alerts/rebalancing/{portfolio_id}/test")

        assert resp.status_code == 200
        data = resp.json()
        assert data["email_sent"] is False
        assert data["push_sent"] is False
        assert "없음" in data["message"] or "확인" in data["message"]


class TestStockPriceAlertExtended:
    def _make_stock_alert_orm(self, user_id):
        return SimpleNamespace(
            id=uuid.uuid4(),
            user_id=user_id,
            ticker="005930",
            market="KOSPI",
            name="삼성전자",
            target_price=75000.0,
            direction="ABOVE",
            is_active=True,
            max_trigger_count=1,
            trigger_count=0,
            triggered_at=None,
            created_at=datetime.now(UTC),
        )

    def test_create_stock_price_alert_success(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        alert_orm = self._make_stock_alert_orm(user.id)
        db.refresh = AsyncMock(side_effect=lambda obj: None)
        app = _setup_app(user, db)
        payload = {
            "ticker": "005930",
            "market": "KOSPI",
            "name": "삼성전자",
            "target_price": 75000.0,
            "direction": "ABOVE",
        }
        from unittest.mock import patch

        with (
            TestClient(app, raise_server_exceptions=False) as client,
            patch("app.api.v1.stock_price_alerts.StockPriceAlert") as MockAlert,
        ):
            MockAlert.return_value = alert_orm
            resp = client.post("/api/v1/alerts/stock-price", json=payload)
        assert resp.status_code in (200, 201)

    def test_create_stock_price_alert_invalid_price(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        payload = {
            "ticker": "005930",
            "market": "KOSPI",
            "name": "삼성전자",
            "target_price": -1.0,
            "direction": "ABOVE",
        }
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post("/api/v1/alerts/stock-price", json=payload)
        assert resp.status_code == 422

    def test_create_stock_price_alert_invalid_count(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        payload = {
            "ticker": "005930",
            "market": "KOSPI",
            "name": "삼성전자",
            "target_price": 75000.0,
            "direction": "ABOVE",
            "max_trigger_count": 0,
        }
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post("/api/v1/alerts/stock-price", json=payload)
        assert resp.status_code == 422

    def test_reactivate_stock_price_alert_not_found(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=None)
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.patch(f"/api/v1/alerts/stock-price/{uuid.uuid4()}/reactivate")
        assert resp.status_code == 404

    def test_reactivate_stock_price_alert_success(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        alert_orm = self._make_stock_alert_orm(user.id)
        alert_orm.is_active = False
        alert_orm.trigger_count = 3
        db.scalar = AsyncMock(return_value=alert_orm)
        db.refresh = AsyncMock(side_effect=lambda obj: None)
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.patch(f"/api/v1/alerts/stock-price/{alert_orm.id}/reactivate")
        assert resp.status_code == 200
        assert alert_orm.is_active is True
        assert alert_orm.trigger_count == 0

    def test_delete_stock_price_alert_success(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        alert_orm = self._make_stock_alert_orm(user.id)
        db.scalar = AsyncMock(return_value=alert_orm)
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.delete(f"/api/v1/alerts/stock-price/{alert_orm.id}")
        assert resp.status_code == 204
