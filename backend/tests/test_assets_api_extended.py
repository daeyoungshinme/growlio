"""자산 API 추가 테스트 (get_account, update_account, get_snapshots)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

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


def _make_account(user_id, account_id=None):
    _id = account_id or uuid.uuid4()
    return SimpleNamespace(
        id=_id,
        user_id=user_id,
        name="테스트 계좌",
        asset_type="STOCK_OTHER",
        data_source="MANUAL",
        is_active=True,
        is_mock_mode=False,
        sort_order=0,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        manual_amount=None,
        manual_positions=None,
        manual_currency="KRW",
        ob_fintech_use_no=None,
        kis_account_no=None,
        kis_app_key=None,
        kis_app_secret=None,
        kiwoom_app_key=None,
        kiwoom_app_secret=None,
        kiwoom_account_no=None,
        deposit_krw=None,
        deposit_usd=None,
        goal_portfolio_id=None,
        real_estate_details=None,
        institution=None,
        manual_updated_at=None,
        include_in_total=True,
        notes=None,
    )


def _make_snapshot(user_id, account_id):
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        account_id=account_id,
        snapshot_date=date.today(),
        amount_krw=10_000_000.0,
        invested_amount=9_000_000.0,
        unrealized_pnl=1_000_000.0,
        positions=[],
        source="MANUAL",
        created_at=datetime.now(UTC),
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


@pytest.fixture(autouse=True)
def mock_redis_scheduler(monkeypatch):
    import app.redis_client as rc
    import app.scheduler as sched

    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)
    mock_redis.aclose = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.setex = AsyncMock()
    mock_redis.delete = AsyncMock()
    monkeypatch.setattr(rc, "redis_client", mock_redis)
    monkeypatch.setattr(sched.scheduler, "start", lambda: None)
    monkeypatch.setattr(sched.scheduler, "shutdown", lambda: None)
    yield
    rc.redis_client = None


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


class TestGetAccount:
    def test_get_account_returns_200(self, override_settings):
        user = _make_user()
        account = _make_account(user.id)
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=account)
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get(f"/api/v1/assets/{account.id}")
        assert resp.status_code == 200

    def test_get_account_returns_404(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=None)
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get(f"/api/v1/assets/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestGetSnapshots:
    def test_get_snapshots_returns_200(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/assets/snapshots/range")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_get_snapshots_with_dates(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/assets/snapshots/range?start_date=2024-01-01&end_date=2024-12-31")
        assert resp.status_code == 200

    def test_get_snapshots_invalid_date_range(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/assets/snapshots/range?start_date=2024-12-31&end_date=2024-01-01")
        assert resp.status_code == 400


class TestUpdateAccount:
    def test_update_account_name(self, override_settings):
        user = _make_user()
        account = _make_account(user.id)
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=account)

        async def mock_refresh(obj):
            pass

        db.refresh = AsyncMock(side_effect=mock_refresh)

        app = _setup_app(user, db)
        payload = {"name": "새 계좌 이름"}
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.put(f"/api/v1/assets/{account.id}", json=payload)
        assert resp.status_code == 200

    def test_update_account_returns_404_for_nonexistent(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=None)
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.put(f"/api/v1/assets/{uuid.uuid4()}", json={"name": "test"})
        assert resp.status_code == 404


class TestDeleteAccount:
    def test_delete_account_success(self, override_settings):
        user = _make_user()
        account = _make_account(user.id)
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=account)
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.delete(f"/api/v1/assets/{account.id}")
        assert resp.status_code == 204


class TestSetTargetPortfolio:
    def test_set_target_portfolio_not_found(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=None)
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.patch(
                f"/api/v1/assets/{uuid.uuid4()}/target-portfolio",
                json={"target_portfolio_id": str(uuid.uuid4())},
            )
        assert resp.status_code == 404

    def test_set_target_portfolio_success(self, override_settings):
        user = _make_user()
        account = _make_account(user.id)
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=account)
        db.refresh = AsyncMock(side_effect=lambda obj: None)
        app = _setup_app(user, db)
        portfolio_id = uuid.uuid4()
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.patch(
                f"/api/v1/assets/{account.id}/target-portfolio",
                json={"target_portfolio_id": str(portfolio_id)},
            )
        assert resp.status_code == 200
        assert account.target_portfolio_id == portfolio_id

    def test_set_target_portfolio_clear(self, override_settings):
        user = _make_user()
        account = _make_account(user.id)
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=account)
        db.refresh = AsyncMock(side_effect=lambda obj: None)
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.patch(
                f"/api/v1/assets/{account.id}/target-portfolio",
                json={"target_portfolio_id": None},
            )
        assert resp.status_code == 200
        assert account.target_portfolio_id is None


class TestBatchSetTargetPortfolio:
    def test_batch_set_empty_ids_returns_empty(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.patch(
                "/api/v1/assets/batch-target-portfolio",
                json={"portfolio_id": str(uuid.uuid4()), "account_ids": []},
            )
        assert resp.status_code == 200
        assert resp.json() == []

    def test_batch_set_forbidden_accounts(self, override_settings):
        user = _make_user()
        account = _make_account(user.id)
        db = _make_mock_db()
        result = MagicMock()
        result.scalars.return_value.all.return_value = [account]  # Only 1 of 2 requested
        db.execute = AsyncMock(return_value=result)
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.patch(
                "/api/v1/assets/batch-target-portfolio",
                json={"portfolio_id": None, "account_ids": [str(uuid.uuid4()), str(uuid.uuid4())]},
            )
        assert resp.status_code == 403

    def test_batch_set_success(self, override_settings):
        user = _make_user()
        account1 = _make_account(user.id)
        account2 = _make_account(user.id)
        db = _make_mock_db()
        result = MagicMock()
        result.scalars.return_value.all.return_value = [account1, account2]
        db.execute = AsyncMock(return_value=result)
        db.refresh = AsyncMock(side_effect=lambda obj: None)
        app = _setup_app(user, db)
        portfolio_id = uuid.uuid4()
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.patch(
                "/api/v1/assets/batch-target-portfolio",
                json={"portfolio_id": str(portfolio_id), "account_ids": [str(account1.id), str(account2.id)]},
            )
        assert resp.status_code == 200
        assert account1.target_portfolio_id == portfolio_id
        assert account2.target_portfolio_id == portfolio_id


class TestDeleteCredentials:
    def test_delete_kis_credentials_not_found(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=None)
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.delete(f"/api/v1/assets/{uuid.uuid4()}/kis-credentials")
        assert resp.status_code == 404

    def test_delete_kis_credentials_success(self, override_settings):
        user = _make_user()
        account = _make_account(user.id)
        account.kis_app_key = "encrypted_key"
        account.kis_app_secret = "encrypted_secret"
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=account)
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.delete(f"/api/v1/assets/{account.id}/kis-credentials")
        assert resp.status_code == 204
        assert account.kis_app_key is None
        assert account.kis_app_secret is None

    def test_delete_kiwoom_credentials_success(self, override_settings):
        user = _make_user()
        account = _make_account(user.id)
        account.kiwoom_app_key = "encrypted_key"
        account.kiwoom_app_secret = "encrypted_secret"
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=account)
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.delete(f"/api/v1/assets/{account.id}/kiwoom-credentials")
        assert resp.status_code == 204
        assert account.kiwoom_app_key is None
        assert account.kiwoom_app_secret is None
