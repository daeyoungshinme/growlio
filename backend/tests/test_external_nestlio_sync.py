"""nestlio 연동 강화용 외부 API — POST /external/transactions 멱등(external_ref), GET /external/net-deposits,
GET /external/net-worth-history, GET /external/account-performance, 그리고 계좌 범위 XIRR 현금흐름."""

from __future__ import annotations

import uuid
from contextlib import ExitStack
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.services.external_queries import build_account_cashflows
from app.services.returns_calculator import xirr


def _make_user():
    return SimpleNamespace(id=uuid.uuid4(), email="test@example.com", display_name="테스트", is_active=True)


def _make_mock_db():
    from sqlalchemy.ext.asyncio import AsyncSession

    db = AsyncMock(spec=AsyncSession)
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()
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


def _auto_account(user_id):
    # 자동 연동(KIS 등) 계좌 — 예수금·스냅샷 갱신 분기를 타지 않아 멱등 동작만 본다.
    return SimpleNamespace(id=uuid.uuid4(), user_id=user_id, data_source="KIS", deposit_krw=None, deposit_usd=None)


def _tx_body(account_id, external_ref="nestlio:42:d1"):
    return {
        "account_id": str(account_id),
        "transaction_type": "DEPOSIT",
        "amount": 300_000,
        "transaction_date": "2026-10-08",
        "external_ref": external_ref,
    }


def _common_tx_patches(stack: ExitStack, account):
    stack.enter_context(patch("app.api.v1.external._get_owned_account", AsyncMock(return_value=account)))
    stack.enter_context(patch("app.api.v1.external.get_cache_store", AsyncMock(return_value=None)))
    stack.enter_context(patch("app.api.v1.external.invalidate_asset_account_caches", AsyncMock()))
    stack.enter_context(patch("app.api.v1.external.invalidate_user_caches", AsyncMock()))


class TestExternalTransactionIdempotency:
    def test_same_external_ref_returns_existing_without_recording(self, override_settings):
        user = _make_user()
        account = _auto_account(user.id)
        db = _make_mock_db()
        app = _setup_app(user, db)
        existing = SimpleNamespace(id=uuid.uuid4())

        with ExitStack() as stack:
            _common_tx_patches(stack, account)
            find = stack.enter_context(
                patch("app.api.v1.external.find_by_external_ref", AsyncMock(return_value=existing))
            )
            client = stack.enter_context(TestClient(app, raise_server_exceptions=False))
            resp = client.post("/api/v1/external/transactions", json=_tx_body(account.id))

        assert resp.status_code == 201
        assert resp.json() == {
            "transaction_id": str(existing.id),
            "deposit_krw_adjusted": False,
            "deposit_krw": None,
            "duplicate": True,
        }
        find.assert_awaited_once_with(db, user.id, "nestlio:42:d1")
        db.add.assert_not_called()
        db.commit.assert_not_awaited()

    def test_new_external_ref_is_stored_on_transaction(self, override_settings):
        user = _make_user()
        account = _auto_account(user.id)
        db = _make_mock_db()
        app = _setup_app(user, db)

        with ExitStack() as stack:
            _common_tx_patches(stack, account)
            stack.enter_context(patch("app.api.v1.external.find_by_external_ref", AsyncMock(return_value=None)))
            client = stack.enter_context(TestClient(app, raise_server_exceptions=False))
            resp = client.post("/api/v1/external/transactions", json=_tx_body(account.id))

        assert resp.status_code == 201
        assert resp.json()["duplicate"] is False
        added = db.add.call_args.args[0]
        assert added.external_ref == "nestlio:42:d1"

    def test_concurrent_duplicate_rolls_back_and_returns_first_row(self, override_settings):
        user = _make_user()
        account = _auto_account(user.id)
        db = _make_mock_db()
        db.commit = AsyncMock(side_effect=IntegrityError("insert", {}, Exception("unique")))
        app = _setup_app(user, db)
        first = SimpleNamespace(id=uuid.uuid4())

        with ExitStack() as stack:
            _common_tx_patches(stack, account)
            stack.enter_context(patch("app.api.v1.external.find_by_external_ref", AsyncMock(side_effect=[None, first])))
            client = stack.enter_context(TestClient(app, raise_server_exceptions=False))
            resp = client.post("/api/v1/external/transactions", json=_tx_body(account.id))

        assert resp.status_code == 201
        assert resp.json()["transaction_id"] == str(first.id)
        assert resp.json()["duplicate"] is True
        db.rollback.assert_awaited_once()

    def test_rejects_overlong_external_ref(self, override_settings):
        user = _make_user()
        app = _setup_app(user, _make_mock_db())
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post("/api/v1/external/transactions", json=_tx_body(uuid.uuid4(), external_ref="x" * 101))
        assert resp.status_code == 422


class TestNetDeposits:
    def test_excludes_nestlio_pushed_rows_by_default(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        account_id = uuid.uuid4()
        rows = [{"account_id": str(account_id), "month": "2026-09", "net_deposit_krw": 500_000.0}]

        with (
            patch("app.api.v1.external.monthly_net_deposits_by_account", AsyncMock(return_value=rows)) as query,
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get(
                "/api/v1/external/net-deposits", params={"account_ids": [str(account_id)], "start_month": "2026-01"}
            )

        assert resp.status_code == 200
        assert resp.json() == rows
        query.assert_awaited_once_with(db, user.id, [account_id], "2026-01", "nestlio:")

    def test_empty_prefix_disables_filter(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        account_id = uuid.uuid4()

        with (
            patch("app.api.v1.external.monthly_net_deposits_by_account", AsyncMock(return_value=[])) as query,
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            client.get(
                "/api/v1/external/net-deposits",
                params={"account_ids": [str(account_id)], "start_month": "2026-01", "exclude_ref_prefix": ""},
            )

        assert query.await_args.args[-1] is None

    def test_validates_start_month(self, override_settings):
        app = _setup_app(_make_user(), _make_mock_db())
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get(
                "/api/v1/external/net-deposits", params={"account_ids": [str(uuid.uuid4())], "start_month": "2026-13"}
            )
        assert resp.status_code == 422


class TestNetWorthHistory:
    def test_returns_monthly_totals_as_year_month(self, override_settings):
        app = _setup_app(_make_user(), _make_mock_db())
        trend = [{"month": "2026-09-01", "total_krw": 1_000_000.0}, {"month": "2026-10-01", "total_krw": 1_200_000.0}]

        with (
            patch("app.api.v1.external.get_cache_store", AsyncMock(return_value=None)),
            patch("app.api.v1.external.get_monthly_trend", AsyncMock(return_value=trend)),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get("/api/v1/external/net-worth-history")

        assert resp.status_code == 200
        assert resp.json() == [
            {"month": "2026-09", "total_krw": 1_000_000.0},
            {"month": "2026-10", "total_krw": 1_200_000.0},
        ]


class TestAccountPerformance:
    def test_returns_scoped_performance(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        account_id = uuid.uuid4()
        result = {
            "xirr_pct": 7.5,
            "current_value_krw": 11_000_000.0,
            "net_invested_krw": 10_000_000.0,
            "account_count": 1,
        }

        with (
            patch("app.api.v1.external.account_scoped_performance", AsyncMock(return_value=result)) as perf,
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get("/api/v1/external/account-performance", params={"account_ids": [str(account_id)]})

        assert resp.status_code == 200
        assert resp.json() == result
        perf.assert_awaited_once_with(db, user.id, [account_id])

    def test_requires_account_ids(self, override_settings):
        app = _setup_app(_make_user(), _make_mock_db())
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/external/account-performance")
        assert resp.status_code == 422


class TestAccountCashflows:
    def test_deposits_are_outflows_withdrawals_inflows_and_value_last(self):
        flows = [(date(2025, 10, 1), "DEPOSIT", 1_000_000.0), (date(2026, 4, 1), "WITHDRAWAL", 100_000.0)]
        cashflows = build_account_cashflows(flows, 1_000_000.0, date(2026, 10, 1))
        assert cashflows == [
            (date(2025, 10, 1), -1_000_000.0),
            (date(2026, 4, 1), 100_000.0),
            (date(2026, 10, 1), 1_000_000.0),
        ]

    def test_one_year_ten_percent_gain_is_about_ten_percent_xirr(self):
        cashflows = build_account_cashflows(
            [(date(2025, 10, 1), "DEPOSIT", 1_000_000.0)], 1_100_000.0, date(2026, 10, 1)
        )
        assert xirr(cashflows) == 10.0


async def test_monthly_net_deposits_query_scopes_user_active_and_prefix():
    """라우터 테스트는 이 함수를 통째로 mock하므로, 실제 SQL 조건(소유자·활성 계좌·접두사 제외)을 여기서 고정한다."""
    from sqlalchemy.dialects import postgresql

    from app.services.external_queries import monthly_net_deposits_by_account

    db = AsyncMock()
    result = MagicMock()
    result.all.return_value = [
        SimpleNamespace(account_id=uuid.uuid4(), month="2026-09", net=100_000),
        SimpleNamespace(account_id=uuid.uuid4(), month="2026-10", net=0),  # 순입금 0은 제외
    ]
    db.execute = AsyncMock(return_value=result)

    out = await monthly_net_deposits_by_account(db, uuid.uuid4(), [uuid.uuid4()], "2026-01", "nestlio:")

    assert [r["month"] for r in out] == ["2026-09"]
    sql = str(db.execute.call_args.args[0].compile(dialect=postgresql.dialect()))
    assert "JOIN asset_accounts ON asset_accounts.id = transactions.account_id" in sql
    assert "asset_accounts.is_active IS true" in sql
    assert "transactions.user_id =" in sql
    assert "transactions.external_ref IS NULL" in sql


async def test_monthly_net_deposits_empty_ids_skips_query():
    from app.services.external_queries import monthly_net_deposits_by_account

    db = AsyncMock()
    assert await monthly_net_deposits_by_account(db, uuid.uuid4(), [], "2026-01", None) == []
    db.execute.assert_not_called()
