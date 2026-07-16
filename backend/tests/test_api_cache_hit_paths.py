"""캐시 히트 경로 및 기타 단순 분기 커버리지 테스트."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

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
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    return db


def _setup_app(user, db):
    from app.api.deps import get_current_user
    from app.core.database import get_db
    from app.main import app

    async def override_auth():
        return user

    async def override_db():
        yield db

    app.dependency_overrides[get_current_user] = override_auth
    app.dependency_overrides[get_db] = override_db
    return app


class TestDividendsPositionsCacheHit:
    """dividends.py line 63: skip=0 + cached 결과 반환."""

    def test_returns_cached_list_when_skip_is_zero(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)

        cached_data = [{"ticker": "005930", "dividend_yield": 1.5}]

        with (
            patch("app.api.v1.dividends.get_cached_json", new=AsyncMock(return_value=cached_data)),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get("/api/v1/dividends/positions?skip=0&limit=10")

        assert resp.status_code == 200


class TestExchangeRateAlertsCacheHit:
    """exchange_rate_alerts.py line 78: skip=0, limit=50 + cached 결과 반환."""

    def test_returns_cached_list_for_default_params(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)

        cached_data = [
            {
                "id": str(uuid.uuid4()),
                "target_rate": 1300.0,
                "direction": "ABOVE",
                "is_active": True,
                "max_trigger_count": 1,
                "trigger_count": 0,
                "triggered_at": None,
                "created_at": "2024-01-01T00:00:00",
            }
        ]

        with (
            patch("app.api.v1.exchange_rate_alerts.get_cached_json", new=AsyncMock(return_value=cached_data)),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get("/api/v1/alerts/exchange-rate")

        assert resp.status_code == 200


class TestTaxOverseasPositionsCacheHit:
    """tax.py line 29: overseas-positions 캐시 히트 반환."""

    def test_returns_cached_overseas_positions(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)

        cached_data = [{"ticker": "AAPL", "unrealized_gain_krw": 500000}]

        with (
            patch("app.api.v1.tax.get_cached_json", new=AsyncMock(return_value=cached_data)),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get("/api/v1/tax/overseas-positions")

        assert resp.status_code == 200


class TestRebalancingAlertAutoModeAccountValidation:
    """rebalancing_alerts.py lines 169-176: AUTO 모드 + account_id 설정 시 계좌 유효성 검증."""

    def test_auto_mode_with_non_kis_account_returns_422(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)

        portfolio_id = uuid.uuid4()
        account_id = uuid.uuid4()

        mock_portfolio = SimpleNamespace(id=portfolio_id, user_id=user.id)
        mock_non_kis = SimpleNamespace(id=account_id, user_id=user.id, asset_type="BANK_ACCOUNT")
        db.scalar = AsyncMock(side_effect=[mock_portfolio, mock_non_kis])

        body = {
            "portfolio_id": str(portfolio_id),
            "threshold_pct": 5.0,
            "mode": "AUTO",
            "account_id": str(account_id),
        }

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.put(f"/api/v1/alerts/rebalancing/{portfolio_id}", json=body)

        assert resp.status_code == 422


class TestRebalancingAlertGetSuccess:
    """rebalancing_alerts.py line 153: 알림 조회 성공 시 _build_response 반환."""

    def test_returns_200_when_alert_found(self, override_settings):
        from datetime import UTC, datetime

        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)

        portfolio_id = uuid.uuid4()
        alert = SimpleNamespace(
            id=uuid.uuid4(),
            portfolio_id=portfolio_id,
            user_id=user.id,
            is_active=True,
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
            auto_execution_time=None,
            last_triggered_at=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db.scalar = AsyncMock(return_value=alert)

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get(f"/api/v1/alerts/rebalancing/{portfolio_id}")

        assert resp.status_code == 200
