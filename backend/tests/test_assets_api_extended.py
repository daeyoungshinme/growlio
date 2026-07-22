"""자산 API 추가 테스트 (get_account, update_account, get_snapshots)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


def _make_cache_mock() -> AsyncMock:
    """SCAN+UNLINK 기반 캐시 무효화(invalidate_portfolio_overview_cache 등)를 사용하는
    코드 경로가 빈 결과를 받도록 scan을 기본 구성한 cache mock."""
    cache = AsyncMock()
    cache.scan = AsyncMock(return_value=(0, []))
    cache.unlink = AsyncMock()
    return cache


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


class TestUpdateAccountCashTransaction:
    """현금성 계좌(BANK_ACCOUNT/DEPOSIT/CASH_OTHER) 잔액 수정 시 입출금 거래 자동 생성 검증.

    수정 없이 잔액만 바꾸면 Modified Dietz 수익률 계산(net_flows_after)에서 이 변화가
    빠져 홈탭 누적 수익률이 왜곡되는 버그의 회귀 테스트."""

    def _make_cash_account(self, user_id, asset_type="BANK_ACCOUNT", deposit_krw=1_000_000.0):
        acc = _make_account(user_id)
        acc.asset_type = asset_type
        acc.deposit_krw = deposit_krw
        acc.deposit_usd = None
        acc.manual_amount = deposit_krw
        return acc

    def test_balance_increase_creates_deposit_transaction(self, override_settings):
        user = _make_user()
        account = self._make_cash_account(user.id, deposit_krw=1_000_000.0)
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=account)
        db.refresh = AsyncMock(side_effect=lambda obj: None)
        app = _setup_app(user, db)
        latest_snap = SimpleNamespace(amount_krw=1_000_000.0, invested_amount=None, unrealized_pnl=None)

        with (
            patch("app.api.v1.assets.get_cache_store", AsyncMock(return_value=_make_cache_mock())),
            patch("app.api.v1.assets.fetch_usd_krw", AsyncMock(return_value=1_300.0)),
            patch(
                "app.api.v1.assets.get_latest_snapshot_with_positions",
                AsyncMock(return_value=(latest_snap, [])),
            ),
            patch(
                "app.api.v1.assets._upsert_snapshot",
                AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4())),
            ),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.put(f"/api/v1/assets/{account.id}", json={"deposit_krw": 5_000_000.0})

        assert resp.status_code == 200
        assert db.add.call_count == 1
        tx = db.add.call_args_list[0].args[0]
        assert tx.transaction_type == "DEPOSIT"
        assert tx.amount == 4_000_000.0
        assert tx.account_id == account.id

    def test_balance_decrease_creates_withdrawal_transaction(self, override_settings):
        user = _make_user()
        account = self._make_cash_account(user.id, deposit_krw=5_000_000.0)
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=account)
        db.refresh = AsyncMock(side_effect=lambda obj: None)
        app = _setup_app(user, db)
        latest_snap = SimpleNamespace(amount_krw=5_000_000.0, invested_amount=None, unrealized_pnl=None)

        with (
            patch("app.api.v1.assets.get_cache_store", AsyncMock(return_value=_make_cache_mock())),
            patch("app.api.v1.assets.fetch_usd_krw", AsyncMock(return_value=1_300.0)),
            patch(
                "app.api.v1.assets.get_latest_snapshot_with_positions",
                AsyncMock(return_value=(latest_snap, [])),
            ),
            patch(
                "app.api.v1.assets._upsert_snapshot",
                AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4())),
            ),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.put(f"/api/v1/assets/{account.id}", json={"deposit_krw": 1_000_000.0})

        assert resp.status_code == 200
        assert db.add.call_count == 1
        tx = db.add.call_args_list[0].args[0]
        assert tx.transaction_type == "WITHDRAWAL"
        assert tx.amount == 4_000_000.0

    def test_no_change_creates_no_transaction(self, override_settings):
        user = _make_user()
        account = self._make_cash_account(user.id, deposit_krw=1_000_000.0)
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=account)
        db.refresh = AsyncMock(side_effect=lambda obj: None)
        app = _setup_app(user, db)
        latest_snap = SimpleNamespace(amount_krw=1_000_000.0, invested_amount=None, unrealized_pnl=None)

        with (
            patch("app.api.v1.assets.get_cache_store", AsyncMock(return_value=_make_cache_mock())),
            patch("app.api.v1.assets.fetch_usd_krw", AsyncMock(return_value=1_300.0)),
            patch(
                "app.api.v1.assets.get_latest_snapshot_with_positions",
                AsyncMock(return_value=(latest_snap, [])),
            ),
            patch(
                "app.api.v1.assets._upsert_snapshot",
                AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4())),
            ),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.put(f"/api/v1/assets/{account.id}", json={"deposit_krw": 1_000_000.0})

        assert resp.status_code == 200
        assert db.add.call_count == 0

    def test_first_snapshot_creates_no_transaction(self, override_settings):
        """계좌의 최초 스냅샷(latest_snap is None)은 base 값이므로 거래로 잡지 않는다."""
        user = _make_user()
        account = self._make_cash_account(user.id, deposit_krw=3_000_000.0)
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=account)
        db.refresh = AsyncMock(side_effect=lambda obj: None)
        app = _setup_app(user, db)

        with (
            patch("app.api.v1.assets.get_cache_store", AsyncMock(return_value=_make_cache_mock())),
            patch("app.api.v1.assets.fetch_usd_krw", AsyncMock(return_value=1_300.0)),
            patch(
                "app.api.v1.assets.get_latest_snapshot_with_positions",
                AsyncMock(return_value=(None, [])),
            ),
            patch(
                "app.api.v1.assets._upsert_snapshot",
                AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4())),
            ),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.put(f"/api/v1/assets/{account.id}", json={"deposit_krw": 3_000_000.0})

        assert resp.status_code == 200
        assert db.add.call_count == 0

    def test_non_cash_account_creates_no_transaction(self, override_settings):
        """STOCK_OTHER 등 비현금성 계좌는 잔액 변화가 시세 변동일 수 있으므로 거래를 만들지 않는다."""
        user = _make_user()
        account = _make_account(user.id)
        account.asset_type = "STOCK_OTHER"
        account.deposit_krw = 1_000_000.0
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=account)
        db.refresh = AsyncMock(side_effect=lambda obj: None)
        app = _setup_app(user, db)
        latest_snap = SimpleNamespace(amount_krw=1_000_000.0, invested_amount=None, unrealized_pnl=None)

        with (
            patch("app.api.v1.assets.get_cache_store", AsyncMock(return_value=_make_cache_mock())),
            patch("app.api.v1.assets.fetch_usd_krw", AsyncMock(return_value=1_300.0)),
            patch(
                "app.api.v1.assets.get_latest_snapshot_with_positions",
                AsyncMock(return_value=(latest_snap, [])),
            ),
            patch(
                "app.api.v1.assets._upsert_snapshot",
                AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4())),
            ),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.put(f"/api/v1/assets/{account.id}", json={"deposit_krw": 8_000_000.0})

        assert resp.status_code == 200
        assert db.add.call_count == 0


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


class TestUpdateIsaPnlOverride:
    def test_not_found(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=None)
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.patch(
                f"/api/v1/assets/{uuid.uuid4()}/isa-pnl-override",
                json={"cumulative_pnl_krw": 1_000_000},
            )
        assert resp.status_code == 404

    def test_rejects_non_isa_account(self, override_settings):
        user = _make_user()
        account = _make_account(user.id)
        account.tax_type = "GENERAL"
        account.isa_manual_cumulative_pnl_krw = None
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=account)
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.patch(
                f"/api/v1/assets/{account.id}/isa-pnl-override",
                json={"cumulative_pnl_krw": 1_000_000},
            )
        assert resp.status_code == 400

    def test_sets_override_on_isa_account(self, override_settings):
        user = _make_user()
        account = _make_account(user.id)
        account.tax_type = "ISA"
        account.isa_manual_cumulative_pnl_krw = None
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=account)
        db.refresh = AsyncMock(side_effect=lambda obj: None)
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.patch(
                f"/api/v1/assets/{account.id}/isa-pnl-override",
                json={"cumulative_pnl_krw": 2_500_000},
            )
        assert resp.status_code == 200
        assert account.isa_manual_cumulative_pnl_krw == 2_500_000

    def test_clears_override_with_null(self, override_settings):
        user = _make_user()
        account = _make_account(user.id)
        account.tax_type = "ISA"
        account.isa_manual_cumulative_pnl_krw = 2_500_000.0
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=account)
        db.refresh = AsyncMock(side_effect=lambda obj: None)
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.patch(
                f"/api/v1/assets/{account.id}/isa-pnl-override",
                json={"cumulative_pnl_krw": None},
            )
        assert resp.status_code == 200
        assert account.isa_manual_cumulative_pnl_krw is None
        assert account.kiwoom_app_secret is None
