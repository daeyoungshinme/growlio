"""자산(계좌) API 테스트 (GET/POST/PATCH/DELETE /api/v1/assets/...)."""

from __future__ import annotations

import contextlib
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from tests.api_helpers import make_mock_db, make_user, setup_app


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
        manual_currency="KRW",
        kis_account_no="12345678-01",
        kis_app_key=None,
        kis_app_secret=None,
        kiwoom_app_key=None,
        kiwoom_app_secret=None,
        kiwoom_account_no=None,
        toss_account_no=None,
        toss_client_id=None,
        toss_client_secret=None,
        deposit_krw=None,
        deposit_usd=None,
        goal_portfolio_id=None,
        real_estate_details=None,
        institution=None,
        manual_updated_at=None,
        include_in_total=True,
        notes=None,
    )


class TestListAccounts:
    def test_returns_401_without_auth(self, override_settings):
        from app.api.deps import get_current_user
        from app.main import app

        app.dependency_overrides.pop(get_current_user, None)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/assets")
        assert resp.status_code == 401

    def test_returns_empty_list(self, override_settings):
        user = make_user()
        db = make_mock_db()
        app = setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/assets")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_rejects_invalid_pagination(self, override_settings):
        """plans/118 B4: 음수 skip(Postgres OFFSET 오류 → 500)·상한 초과 limit은 422."""
        user = make_user()
        app = setup_app(user, make_mock_db())
        with TestClient(app, raise_server_exceptions=False) as client:
            codes = [
                client.get(url).status_code
                for url in (
                    "/api/v1/assets?skip=-1",
                    "/api/v1/assets?limit=0",
                    "/api/v1/assets?limit=10000",
                    "/api/v1/alerts/stock-price?skip=-1",
                    "/api/v1/alerts/stock-price?limit=501",
                )
            ]
        assert codes == [422] * 5

    def test_returns_accounts(self, override_settings):
        user = make_user()
        db = make_mock_db()
        account = _make_account_orm(user.id)
        result = MagicMock()
        result.scalars.return_value.all.return_value = [account]
        db.execute = AsyncMock(return_value=result)
        app = setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/assets")
        assert resp.status_code == 200
        assert len(resp.json()) == 1


class TestCreateAccount:
    def test_create_manual_account(self, override_settings):
        user = make_user()
        db = make_mock_db()
        account = _make_account_orm(user.id)

        async def mock_refresh(obj):
            for k, v in vars(account).items():
                if not k.startswith("_"):
                    with contextlib.suppress(Exception):
                        setattr(obj, k, v)

        db.refresh = AsyncMock(side_effect=mock_refresh)
        app = setup_app(user, db)
        payload = {
            "name": "테스트 수동 계좌",
            "asset_type": "STOCK_OTHER",
            "data_source": "MANUAL",
            "manual_amount": 1000000,
        }
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post("/api/v1/assets", json=payload)
        assert resp.status_code in (200, 201)

    def test_create_account_invalidates_asset_caches(self, override_settings, monkeypatch):
        """계좌 생성 후 대시보드·추이 캐시가 남으면 새 계좌가 TTL 동안 안 보인다."""
        user = make_user()
        db = make_mock_db()
        account = _make_account_orm(user.id)

        async def mock_refresh(obj):
            for k, v in vars(account).items():
                if not k.startswith("_"):
                    with contextlib.suppress(Exception):
                        setattr(obj, k, v)

        db.refresh = AsyncMock(side_effect=mock_refresh)
        invalidate = AsyncMock()
        monkeypatch.setattr("app.api.v1.assets.invalidate_asset_account_caches", invalidate)
        app = setup_app(user, db)
        payload = {
            "name": "테스트 수동 계좌",
            "asset_type": "STOCK_OTHER",
            "data_source": "MANUAL",
            "manual_amount": 1000000,
        }
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post("/api/v1/assets", json=payload)
        assert resp.status_code == 201
        invalidate.assert_awaited_once()
        assert invalidate.await_args.args[1] == user.id

    def test_create_manual_account_ignores_stray_kis_account_no(self, override_settings):
        """브라우저 자동완성 등으로 kis_account_no에 형식이 안 맞는 값이 남아있어도
        data_source가 MANUAL이면 무시되고 정상 생성되어야 한다."""
        user = make_user()
        db = make_mock_db()
        account = _make_account_orm(user.id)

        async def mock_refresh(obj):
            for k, v in vars(account).items():
                if not k.startswith("_"):
                    with contextlib.suppress(Exception):
                        setattr(obj, k, v)

        db.refresh = AsyncMock(side_effect=mock_refresh)
        app = setup_app(user, db)
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

    def test_create_kis_account_promotes_verified_token(self, override_settings):
        """자격증명 확인(verify-kis-credentials) 단계에서 발급된 유저 레벨 토큰이 있으면
        계좌 생성 시 그 계좌로 승격되어야 한다 — 등록 직후 프론트가 자동 호출하는 첫
        동기화가 KIS 토큰을 또 발급받으려다 발급 속도 제한에 걸리는 것을 방지하기 위함."""
        user = make_user()
        db = make_mock_db()
        account = _make_account_orm(user.id)

        async def mock_refresh(obj):
            for k, v in vars(account).items():
                if not k.startswith("_"):
                    with contextlib.suppress(Exception):
                        setattr(obj, k, v)

        db.refresh = AsyncMock(side_effect=mock_refresh)
        verified_token = SimpleNamespace(
            access_token="verified-token",
            expires_at=datetime.now(UTC) + timedelta(hours=12),
        )
        db.scalar = AsyncMock(return_value=verified_token)

        app = setup_app(user, db)
        payload = {
            "name": "KIS 계좌",
            "asset_type": "STOCK_KIS",
            "data_source": "KIS_API",
            "kis_account_no": "12345678-01",
            "kis_app_key": "app-key",
            "kis_app_secret": "app-secret",
            "is_mock_mode": True,
        }
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post("/api/v1/assets", json=payload)

        assert resp.status_code in (200, 201)
        # promote_user_token_to_account가 KisToken upsert를 수행했는지 확인
        assert db.execute.await_count >= 1

    def test_create_kis_account_without_verified_token_skips_promotion(self, override_settings):
        """유저 레벨 토큰이 없으면(자격증명 확인을 건너뛴 경우 등) 조용히 넘어가고
        계좌 생성은 정상 완료되어야 한다."""
        user = make_user()
        db = make_mock_db()
        account = _make_account_orm(user.id)

        async def mock_refresh(obj):
            for k, v in vars(account).items():
                if not k.startswith("_"):
                    with contextlib.suppress(Exception):
                        setattr(obj, k, v)

        db.refresh = AsyncMock(side_effect=mock_refresh)
        db.scalar = AsyncMock(return_value=None)

        app = setup_app(user, db)
        payload = {
            "name": "KIS 계좌",
            "asset_type": "STOCK_KIS",
            "data_source": "KIS_API",
            "kis_account_no": "12345678-01",
            "kis_app_key": "app-key",
            "kis_app_secret": "app-secret",
            "is_mock_mode": True,
        }
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post("/api/v1/assets", json=payload)
        assert resp.status_code in (200, 201)

    def test_create_kiwoom_account_requires_account_no(self, override_settings):
        """키움은 스키마 validator가 없어 라우터가 스펙 테이블로 필수값을 검증한다."""
        user = make_user()
        db = make_mock_db()
        app = setup_app(user, db)
        payload = {
            "name": "키움 계좌",
            "asset_type": "STOCK_OTHER",
            "data_source": "KIWOOM_API",
            "kiwoom_app_key": "app-key",
            "kiwoom_app_secret": "app-secret",
        }
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post("/api/v1/assets", json=payload)
        assert resp.status_code == 400
        assert "키움 계좌번호" in resp.json()["detail"]
        db.add.assert_not_called()

    def test_create_kiwoom_account_encrypts_and_forces_asset_type(self, override_settings):
        user = make_user()
        db = make_mock_db()
        db.add = MagicMock()
        app = setup_app(user, db)
        payload = {
            "name": "키움 계좌",
            "asset_type": "STOCK_OTHER",
            "data_source": "KIWOOM_API",
            "kiwoom_account_no": "12345678-01",
            "kiwoom_app_key": "app-key",
            "kiwoom_app_secret": "app-secret",
        }
        with TestClient(app, raise_server_exceptions=False) as client:
            client.post("/api/v1/assets", json=payload)

        from app.services.accounts.credential_service import decrypt

        added = db.add.call_args.args[0]
        assert added.asset_type == "STOCK_KIWOOM"
        assert added.kiwoom_app_key != "app-key"
        assert decrypt(added.kiwoom_app_key) == "app-key"
        assert decrypt(added.kiwoom_app_secret) == "app-secret"
        assert added.kis_app_key is None


class TestDeleteAccount:
    def test_delete_returns_404_for_nonexistent(self, override_settings):
        user = make_user()
        db = make_mock_db()
        db.scalar = AsyncMock(return_value=None)
        app = setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.delete(f"/api/v1/assets/{uuid.uuid4()}")
        assert resp.status_code == 404
