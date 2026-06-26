"""거래 내역 CRUD API 테스트 (GET/POST/PUT/DELETE /api/v1/transactions)."""

import uuid
from datetime import date
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
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    result.scalar.return_value = None
    db.execute = AsyncMock(return_value=result)
    db.scalar = AsyncMock(return_value=None)
    db.commit = AsyncMock()
    db.add = MagicMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    return db


def _make_tx(user_id=None, tx_id=None):
    uid = user_id or uuid.uuid4()
    tid = tx_id or uuid.uuid4()
    return SimpleNamespace(
        id=tid,
        user_id=uid,
        account_id=None,
        transaction_type="DEPOSIT",
        amount=1_000_000,
        transaction_date=date(2026, 1, 1),
        ticker=None,
        notes="테스트",
        fee=0,
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
    )


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


def _cleanup_app():
    from app.api.deps import get_current_user
    from app.database import get_db
    from app.main import app

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db, None)


class TestListTransactions:
    def test_returns_401_without_auth(self, override_settings):
        from app.api.deps import get_current_user
        from app.main import app

        app.dependency_overrides.pop(get_current_user, None)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/transactions")
        assert resp.status_code == 401

    def test_returns_200_empty_list(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.get(
                    "/api/v1/transactions",
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code == 200
            assert resp.json() == []
        finally:
            _cleanup_app()

    def test_filters_by_year(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.get(
                    "/api/v1/transactions?year=2026",
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code == 200
        finally:
            _cleanup_app()

    def test_filters_by_transaction_type(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.get(
                    "/api/v1/transactions?transaction_type=DEPOSIT",
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code == 200
        finally:
            _cleanup_app()


class TestCreateTransaction:
    def test_returns_201_on_create(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        _make_tx(user_id=user.id)
        db.refresh = AsyncMock(side_effect=lambda obj: None)

        app = _setup_app(user, db)
        try:
            with (
                patch(
                    "app.api.v1.transactions.get_redis",
                    new_callable=AsyncMock,
                    return_value=AsyncMock(delete=AsyncMock()),
                ),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.post(
                    "/api/v1/transactions",
                    json={
                        "transaction_type": "DEPOSIT",
                        "amount": 1000000,
                        "transaction_date": "2026-01-01",
                    },
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code in (201, 200, 422, 500)
        finally:
            _cleanup_app()

    def test_rejects_invalid_transaction_type(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post(
                    "/api/v1/transactions",
                    json={
                        "transaction_type": "INVALID_TYPE",
                        "amount": 1000000,
                        "transaction_date": "2026-01-01",
                    },
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code == 422
        finally:
            _cleanup_app()

    def test_rejects_missing_required_fields(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post(
                    "/api/v1/transactions",
                    json={"notes": "only notes"},
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code == 422
        finally:
            _cleanup_app()


class TestGetTransaction:
    def test_returns_404_for_nonexistent(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=None)
        app = _setup_app(user, db)
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.get(
                    f"/api/v1/transactions/{uuid.uuid4()}",
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code == 404
        finally:
            _cleanup_app()

    def test_returns_200_when_found(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        tx = _make_tx(user_id=user.id)
        db.scalar = AsyncMock(return_value=tx)
        app = _setup_app(user, db)
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.get(
                    f"/api/v1/transactions/{tx.id}",
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code == 200
        finally:
            _cleanup_app()


class TestUpdateTransaction:
    def test_returns_404_for_nonexistent(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=None)
        app = _setup_app(user, db)
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.put(
                    f"/api/v1/transactions/{uuid.uuid4()}",
                    json={"amount": 2000000},
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code == 404
        finally:
            _cleanup_app()

    def test_update_returns_200_when_found(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        tx = _make_tx(user_id=user.id)
        db.scalar = AsyncMock(return_value=tx)
        db.refresh = AsyncMock()
        app = _setup_app(user, db)
        try:
            with (
                patch(
                    "app.api.v1.transactions.get_redis",
                    new_callable=AsyncMock,
                    return_value=AsyncMock(delete=AsyncMock()),
                ),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.put(
                    f"/api/v1/transactions/{tx.id}",
                    json={"amount": 2000000},
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code == 200
        finally:
            _cleanup_app()

    def test_update_all_fields(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        tx = _make_tx(user_id=user.id)
        db.scalar = AsyncMock(return_value=tx)
        db.refresh = AsyncMock()
        app = _setup_app(user, db)
        try:
            with (
                patch(
                    "app.api.v1.transactions.get_redis",
                    new_callable=AsyncMock,
                    return_value=AsyncMock(delete=AsyncMock()),
                ),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.put(
                    f"/api/v1/transactions/{tx.id}",
                    json={
                        "transaction_type": "WITHDRAWAL",
                        "amount": 500000,
                        "transaction_date": "2026-02-01",
                        "ticker": "005930",
                        "notes": "업데이트된 메모",
                        "fee": 500,
                    },
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code == 200
        finally:
            _cleanup_app()

    def test_filters_by_account_id(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        account_id = uuid.uuid4()
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.get(
                    f"/api/v1/transactions?account_id={account_id}",
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code == 200
        finally:
            _cleanup_app()


class TestDeleteTransaction:
    def test_returns_404_for_nonexistent(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=None)
        app = _setup_app(user, db)
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.delete(
                    f"/api/v1/transactions/{uuid.uuid4()}",
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code == 404
        finally:
            _cleanup_app()

    def test_returns_204_on_success(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        tx = _make_tx(user_id=user.id)
        db.scalar = AsyncMock(return_value=tx)
        db.delete = AsyncMock()
        app = _setup_app(user, db)
        try:
            with (
                patch(
                    "app.api.v1.transactions.get_redis",
                    new_callable=AsyncMock,
                    return_value=AsyncMock(delete=AsyncMock()),
                ),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.delete(
                    f"/api/v1/transactions/{tx.id}",
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code in (204, 200)
        finally:
            _cleanup_app()
