"""리밸런싱 API 테스트 (GET /api/v1/rebalancing)."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
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
    result.scalars.return_value.first.return_value = None
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
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


_MOCK_ANALYSIS = {
    "portfolio_id": str(uuid.uuid4()),
    "portfolio_name": "테스트 포트폴리오",
    "total_value_krw": 10_000_000,
    "items": [],
    "drift_score": 0.0,
    "needs_rebalancing": False,
}


class TestRebalancingAnalyze:
    def test_returns_401_without_auth(self, override_settings):
        from app.api.deps import get_current_user
        from app.main import app

        app.dependency_overrides.pop(get_current_user, None)
        pid = uuid.uuid4()
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get(f"/api/v1/rebalancing/portfolios/{pid}/analyze")
        assert resp.status_code == 401

    def test_returns_404_for_nonexistent_portfolio(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=None)

        app = _setup_app(user, db)
        try:
            with (
                patch(
                    "app.api.v1.rebalancing.get_redis",
                    new_callable=AsyncMock,
                    return_value=AsyncMock(get=AsyncMock(return_value=None)),
                ),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.get(
                    f"/api/v1/rebalancing/portfolios/{uuid.uuid4()}/analyze",
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code in (404, 422)
        finally:
            from app.api.deps import get_current_user
            from app.database import get_db

            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)


class TestRebalancingHistory:
    def test_returns_401_without_auth(self, override_settings):
        from app.api.deps import get_current_user
        from app.main import app

        app.dependency_overrides.pop(get_current_user, None)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/rebalancing/history")
        assert resp.status_code == 401

    def test_returns_200_empty_history(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        db.execute.return_value.scalars.return_value.all.return_value = []

        app = _setup_app(user, db)
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.get(
                    "/api/v1/rebalancing/history",
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code == 200
            assert resp.json() == []
        finally:
            from app.api.deps import get_current_user
            from app.database import get_db

            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)


class TestBrokerBalance:
    def test_returns_401_without_auth(self, override_settings):
        from app.api.deps import get_current_user
        from app.main import app

        app.dependency_overrides.pop(get_current_user, None)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get(f"/api/v1/rebalancing/broker-balance/{uuid.uuid4()}")
        assert resp.status_code == 401

    def test_returns_404_for_nonexistent_account(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=None)

        app = _setup_app(user, db)
        try:
            with (
                patch(
                    "app.api.v1.rebalancing.get_redis",
                    new_callable=AsyncMock,
                    return_value=AsyncMock(get=AsyncMock(return_value=None)),
                ),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.get(
                    f"/api/v1/rebalancing/broker-balance/{uuid.uuid4()}",
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code in (404, 422, 400)
        finally:
            from app.api.deps import get_current_user
            from app.database import get_db

            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)

    def test_returns_502_on_kis_api_error(self, override_settings):
        """KisApiError 발생 시 HTTP 502를 반환한다."""
        from types import SimpleNamespace

        from app.kis.client import KisApiError

        user = _make_user()
        db = _make_mock_db()
        account = SimpleNamespace(
            id=uuid.uuid4(),
            user_id=user.id,
            name="테스트 KIS",
            asset_type="STOCK_KIS",
            is_mock_mode=False,
            kis_account_no="12345678-01",
            kis_app_key="encrypted_key",
            kis_app_secret="encrypted_secret",
        )
        db.scalar = AsyncMock(return_value=account)

        app = _setup_app(user, db)
        try:
            with (
                patch(
                    "app.api.v1.rebalancing.get_redis",
                    new_callable=AsyncMock,
                    return_value=AsyncMock(get=AsyncMock(return_value=None)),
                ),
                patch("app.api.v1.rebalancing.get_usd_krw_rate", new_callable=AsyncMock, return_value=1350.0),
                patch(
                    "app.api.v1.rebalancing._fetch_broker_balance",
                    new_callable=AsyncMock,
                    side_effect=KisApiError("1", "호출 후처리(MCI전송) 오류 입니다."),
                ),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.get(
                    f"/api/v1/rebalancing/broker-balance/{account.id}",
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code == 502
            assert "KIS API" in resp.json()["detail"]
        finally:
            from app.api.deps import get_current_user
            from app.database import get_db

            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)
