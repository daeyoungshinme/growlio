"""외부(자매 앱) 읽기 전용 API 테스트 (GET /api/v1/external/accounts)."""

from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


def _make_user():
    return SimpleNamespace(id=uuid.uuid4(), email="test@example.com", display_name="테스트", is_active=True)


def _make_account(user_id, **overrides):
    defaults = dict(
        id=uuid.uuid4(),
        user_id=user_id,
        name="테스트 계좌",
        asset_type="BANK_ACCOUNT",
        manual_amount=1000.0,
        data_source="MANUAL",
        deposit_krw=None,
        deposit_usd=None,
        manual_updated_at=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_mock_db():
    from sqlalchemy.ext.asyncio import AsyncSession

    db = AsyncMock(spec=AsyncSession)
    db.add = MagicMock()
    db.commit = AsyncMock()
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


class TestListAccountBalances:
    def test_returns_401_without_auth(self, override_settings):
        from app.api.deps import get_current_user
        from app.main import app

        app.dependency_overrides.pop(get_current_user, None)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/external/accounts")
        assert resp.status_code == 401

    def test_uses_latest_snapshot_when_available(self, override_settings):
        user = _make_user()
        account = _make_account(user.id)
        db = AsyncMock()
        app = _setup_app(user, db)
        snapshot = SimpleNamespace(amount_krw=1_234_000.0, snapshot_date=date(2026, 8, 1))

        with (
            patch("app.api.v1.external._list_accounts", AsyncMock(return_value=[account])),
            patch("app.api.v1.external.get_latest_snapshot_with_positions", AsyncMock(return_value=(snapshot, []))),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get("/api/v1/external/accounts")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["id"] == str(account.id)
        assert body[0]["current_value_krw"] == 1_234_000.0
        assert body[0]["as_of"] == "2026-08-01"

    def test_falls_back_to_manual_amount_without_snapshot(self, override_settings):
        user = _make_user()
        account = _make_account(user.id, manual_amount=500_000.0)
        db = AsyncMock()
        app = _setup_app(user, db)

        with (
            patch("app.api.v1.external._list_accounts", AsyncMock(return_value=[account])),
            patch("app.api.v1.external.get_latest_snapshot_with_positions", AsyncMock(return_value=(None, []))),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get("/api/v1/external/accounts")

        assert resp.status_code == 200
        body = resp.json()
        assert body[0]["current_value_krw"] == 500_000.0
        assert body[0]["as_of"] is None


class TestListRealEstateItems:
    """부동산 시세/담보대출 분리 조회 (GET /api/v1/external/real-estate)."""

    def test_returns_401_without_auth(self, override_settings):
        from app.api.deps import get_current_user
        from app.main import app

        app.dependency_overrides.pop(get_current_user, None)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/external/real-estate")
        assert resp.status_code == 401

    def test_filters_to_real_estate_accounts_only(self, override_settings):
        user = _make_user()
        bank = _make_account(user.id, asset_type="BANK_ACCOUNT", manual_amount=1_000_000.0)
        real_estate = _make_account(
            user.id,
            asset_type="REAL_ESTATE",
            manual_amount=500_000_000.0,
            real_estate_details={
                "address": "서울시 강남구",
                "property_type": "아파트",
                "purchase_price_krw": 400_000_000.0,
                "purchase_date": "2020-01-01",
                "mortgage_balance_krw": 150_000_000.0,
            },
        )
        db = AsyncMock()
        app = _setup_app(user, db)

        with (
            patch("app.api.v1.external._list_accounts", AsyncMock(return_value=[bank, real_estate])),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get("/api/v1/external/real-estate")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        item = body[0]
        assert item["id"] == str(real_estate.id)
        assert item["address"] == "서울시 강남구"
        assert item["property_type"] == "아파트"
        assert item["market_value_krw"] == 500_000_000.0
        assert item["mortgage_balance_krw"] == 150_000_000.0
        assert item["net_equity_krw"] == 350_000_000.0
        assert item["purchase_price_krw"] == 400_000_000.0
        assert item["purchase_date"] == "2020-01-01"

    def test_defaults_mortgage_to_zero_when_details_missing(self, override_settings):
        user = _make_user()
        real_estate = _make_account(
            user.id,
            asset_type="REAL_ESTATE",
            manual_amount=300_000_000.0,
            real_estate_details=None,
        )
        db = AsyncMock()
        app = _setup_app(user, db)

        with (
            patch("app.api.v1.external._list_accounts", AsyncMock(return_value=[real_estate])),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get("/api/v1/external/real-estate")

        assert resp.status_code == 200
        body = resp.json()
        assert body[0]["mortgage_balance_krw"] == 0
        assert body[0]["net_equity_krw"] == 300_000_000.0
        assert body[0]["address"] is None

    def test_returns_empty_list_when_no_real_estate_accounts(self, override_settings):
        user = _make_user()
        bank = _make_account(user.id, asset_type="BANK_ACCOUNT")
        db = AsyncMock()
        app = _setup_app(user, db)

        with (
            patch("app.api.v1.external._list_accounts", AsyncMock(return_value=[bank])),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get("/api/v1/external/real-estate")

        assert resp.status_code == 200
        assert resp.json() == []


class TestCreateExternalTransaction:
    """nestlio 저축/투자 내역 반영 (POST /api/v1/external/transactions)."""

    def _patches(self, account, snapshot=None, positions=None):
        return (
            patch("app.api.v1.external._get_owned_account", AsyncMock(return_value=account)),
            patch("app.api.v1.external.get_cache_store", AsyncMock(return_value=None)),
            patch("app.api.v1.external.fetch_usd_krw", AsyncMock(return_value=1300.0)),
            patch(
                "app.api.v1.external.get_latest_snapshot_with_positions",
                AsyncMock(return_value=(snapshot, positions or [])),
            ),
            patch("app.api.v1.external._upsert_snapshot", AsyncMock()),
            patch("app.api.v1.external.invalidate_asset_account_caches", AsyncMock()),
            patch("app.api.v1.external.invalidate_user_caches", AsyncMock()),
        )

    def test_returns_401_without_auth(self, override_settings):
        from app.api.deps import get_current_user
        from app.main import app

        app.dependency_overrides.pop(get_current_user, None)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post(
                "/api/v1/external/transactions",
                json={
                    "account_id": str(uuid.uuid4()),
                    "transaction_type": "DEPOSIT",
                    "amount": 100000,
                    "transaction_date": "2026-08-01",
                },
            )
        assert resp.status_code == 401

    def test_manual_account_deposit_adjusts_deposit_krw_and_snapshots(self, override_settings):
        user = _make_user()
        account = _make_account(user.id, data_source="MANUAL", deposit_krw=100_000.0, deposit_usd=None)
        db = _make_mock_db()
        app = _setup_app(user, db)

        patches = self._patches(account)
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4] as upsert_mock,
            patches[5],
            patches[6],
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.post(
                "/api/v1/external/transactions",
                json={
                    "account_id": str(account.id),
                    "transaction_type": "DEPOSIT",
                    "amount": 50_000,
                    "transaction_date": "2026-08-01",
                    "notes": "적금 이체",
                },
            )

        assert resp.status_code == 201
        body = resp.json()
        assert body["deposit_krw_adjusted"] is True
        assert body["deposit_krw"] == 150_000.0
        assert account.deposit_krw == 150_000.0
        upsert_mock.assert_awaited_once()
        assert db.add.call_count == 1  # Transaction row만 add (계좌는 기존 ORM 객체 수정)

    def test_manual_account_withdrawal_subtracts_deposit_krw(self, override_settings):
        user = _make_user()
        account = _make_account(user.id, data_source="MANUAL", deposit_krw=100_000.0, deposit_usd=None)
        db = _make_mock_db()
        app = _setup_app(user, db)

        patches = self._patches(account)
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
            patches[5],
            patches[6],
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.post(
                "/api/v1/external/transactions",
                json={
                    "account_id": str(account.id),
                    "transaction_type": "WITHDRAWAL",
                    "amount": 30_000,
                    "transaction_date": "2026-08-01",
                },
            )

        assert resp.status_code == 201
        assert resp.json()["deposit_krw"] == 70_000.0

    def test_auto_synced_account_records_history_without_touching_deposit_krw(self, override_settings):
        user = _make_user()
        account = _make_account(
            user.id, data_source="KIS_API", asset_type="STOCK_KIS", deposit_krw=500_000.0, deposit_usd=None
        )
        db = _make_mock_db()
        app = _setup_app(user, db)

        patches = self._patches(account)
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4] as upsert_mock,
            patches[5],
            patches[6],
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.post(
                "/api/v1/external/transactions",
                json={
                    "account_id": str(account.id),
                    "transaction_type": "DEPOSIT",
                    "amount": 50_000,
                    "transaction_date": "2026-08-01",
                },
            )

        assert resp.status_code == 201
        body = resp.json()
        assert body["deposit_krw_adjusted"] is False
        assert body["deposit_krw"] is None
        assert account.deposit_krw == 500_000.0  # 자동연동 계좌는 손대지 않음
        upsert_mock.assert_not_awaited()

    def test_rejects_dividend_transaction_type(self, override_settings):
        user = _make_user()
        account = _make_account(user.id, data_source="MANUAL", deposit_krw=0.0)
        db = _make_mock_db()
        app = _setup_app(user, db)

        patches = self._patches(account)
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
            patches[5],
            patches[6],
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.post(
                "/api/v1/external/transactions",
                json={
                    "account_id": str(account.id),
                    "transaction_type": "DIVIDEND",
                    "amount": 1_000,
                    "transaction_date": "2026-08-01",
                },
            )

        assert resp.status_code == 400

    def test_returns_404_for_account_not_owned(self, override_settings):
        from fastapi import HTTPException, status

        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)

        with (
            patch(
                "app.api.v1.external._get_owned_account",
                AsyncMock(side_effect=HTTPException(status.HTTP_404_NOT_FOUND, "계좌를 찾을 수 없습니다")),
            ),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.post(
                "/api/v1/external/transactions",
                json={
                    "account_id": str(uuid.uuid4()),
                    "transaction_type": "DEPOSIT",
                    "amount": 10_000,
                    "transaction_date": "2026-08-01",
                },
            )

        assert resp.status_code == 404
