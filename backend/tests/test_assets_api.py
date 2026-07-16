"""자산(계좌) API 테스트 (GET/POST/PATCH/DELETE /api/v1/assets/...)."""

from __future__ import annotations

import contextlib
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


def _make_account_orm(user_id, account_id=None):
    return SimpleNamespace(
        id=account_id or uuid.uuid4(),
        user_id=user_id,
        name="테스트 계좌",
        asset_type="STOCK_KIS",
        data_source="KIS_API",
        is_active=True,
        is_mock_mode=True,
        sort_order=0,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        manual_amount=None,
        manual_positions=None,
        manual_currency="KRW",
        kis_account_no="12345678-01",
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
    from app.core.database import get_db
    from app.main import app

    async def override_auth():
        return user

    async def override_db():
        yield db

    app.dependency_overrides[get_current_user] = override_auth
    app.dependency_overrides[get_db] = override_db
    return app


class TestListAccounts:
    def test_returns_401_without_auth(self, override_settings):
        from app.api.deps import get_current_user
        from app.main import app

        app.dependency_overrides.pop(get_current_user, None)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/assets")
        assert resp.status_code == 401

    def test_returns_empty_list(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/assets")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_accounts(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        account = _make_account_orm(user.id)
        result = MagicMock()
        result.scalars.return_value.all.return_value = [account]
        db.execute = AsyncMock(return_value=result)
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/assets")
        assert resp.status_code == 200
        assert len(resp.json()) == 1


class TestCreateAccount:
    def test_create_manual_account(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        account = _make_account_orm(user.id)

        async def mock_refresh(obj):
            for k, v in vars(account).items():
                if not k.startswith("_"):
                    with contextlib.suppress(Exception):
                        setattr(obj, k, v)

        db.refresh = AsyncMock(side_effect=mock_refresh)
        app = _setup_app(user, db)
        payload = {
            "name": "테스트 수동 계좌",
            "asset_type": "STOCK_OTHER",
            "data_source": "MANUAL",
            "manual_amount": 1000000,
        }
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post("/api/v1/assets", json=payload)
        assert resp.status_code in (200, 201)

    def test_create_manual_account_ignores_stray_kis_account_no(self, override_settings):
        """브라우저 자동완성 등으로 kis_account_no에 형식이 안 맞는 값이 남아있어도
        data_source가 MANUAL이면 무시되고 정상 생성되어야 한다."""
        user = _make_user()
        db = _make_mock_db()
        account = _make_account_orm(user.id)

        async def mock_refresh(obj):
            for k, v in vars(account).items():
                if not k.startswith("_"):
                    with contextlib.suppress(Exception):
                        setattr(obj, k, v)

        db.refresh = AsyncMock(side_effect=mock_refresh)
        app = _setup_app(user, db)
        payload = {
            "name": "테스트 수동 계좌",
            "asset_type": "STOCK_OTHER",
            "data_source": "MANUAL",
            "manual_amount": 1000000,
            "kis_account_no": "12345 서울시 강남구",
        }
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post("/api/v1/assets", json=payload)
        assert resp.status_code in (200, 201)


class TestDeleteAccount:
    def test_delete_returns_404_for_nonexistent(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=None)
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.delete(f"/api/v1/assets/{uuid.uuid4()}")
        assert resp.status_code == 404
