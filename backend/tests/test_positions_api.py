"""포지션 API 테스트 (GET/PUT /api/v1/assets/{account_id}/positions)."""

from __future__ import annotations

import uuid
from datetime import date
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


def _make_account(user_id, account_id=None):
    _id = account_id or uuid.uuid4()
    return SimpleNamespace(
        id=_id,
        user_id=user_id,
        name="수동 계좌",
        asset_type="STOCK_OTHER",
        data_source="MANUAL",
        is_active=True,
        is_mock_mode=False,
        manual_amount=0.0,
        manual_positions=None,
        manual_currency="KRW",
        deposit_krw=None,
        deposit_usd=None,
        manual_updated_at=None,
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


class TestSavePositions:
    def test_save_positions_returns_404_for_nonexistent_account(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=None)
        app = _setup_app(user, db)
        payload = [{"ticker": "005930", "name": "삼성전자", "market": "KOSPI", "qty": 10.0, "avg_price": 70000.0}]
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.put(f"/api/v1/assets/{uuid.uuid4()}/positions", json=payload)
        assert resp.status_code == 404

    def test_save_positions_returns_200_with_empty_list(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        account = _make_account(user.id)
        db.scalar = AsyncMock(return_value=account)
        app = _setup_app(user, db)

        mock_snap = SimpleNamespace(
            id=uuid.uuid4(),
            account_id=account.id,
            user_id=user.id,
            snapshot_date=date.today(),
            amount_krw=0.0,
        )

        with patch("app.api.v1.positions.get_cache_store") as mock_get_cache:
            mock_cache = AsyncMock()
            mock_cache.set = AsyncMock(return_value=True)
            mock_cache.get = AsyncMock(return_value=None)
            mock_cache.delete = AsyncMock()
            mock_cache.scan = AsyncMock(return_value=(0, []))
            mock_cache.unlink = AsyncMock()
            mock_get_cache.return_value = mock_cache
            with patch("app.utils.inproc_lock.inproc_lock") as mock_lock:
                mock_cm = MagicMock()
                mock_cm.__aenter__ = AsyncMock(return_value=True)
                mock_cm.__aexit__ = AsyncMock(return_value=None)
                mock_lock.return_value = mock_cm
                with (
                    patch("app.api.v1.positions._upsert_snapshot", AsyncMock(return_value=mock_snap)),
                    TestClient(app, raise_server_exceptions=False) as client,
                ):
                    resp = client.put(
                        f"/api/v1/assets/{account.id}/positions",
                        json=[],
                    )
        assert resp.status_code == 200


class TestGetPositions:
    def test_returns_401_without_auth(self, override_settings):
        from app.api.deps import get_current_user
        from app.main import app

        app.dependency_overrides.pop(get_current_user, None)
        account_id = uuid.uuid4()
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get(f"/api/v1/assets/{account_id}/positions")
        assert resp.status_code == 401

    def test_returns_404_for_nonexistent_account(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=None)  # account not found
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get(f"/api/v1/assets/{uuid.uuid4()}/positions")
        assert resp.status_code == 404

    def test_returns_positions_for_valid_account(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        account = _make_account(user.id)
        db.scalar = AsyncMock(return_value=account)

        result = MagicMock()
        mock_pos = SimpleNamespace(
            ticker="005930",
            name="삼성전자",
            market="KOSPI",
            qty=10.0,
            avg_price=70000.0,
            current_price=75000.0,
            value_krw=750000.0,
            currency="KRW",
            usd_rate=None,
            avg_price_usd=None,
        )
        mock_pos.to_dict = lambda: {
            "ticker": mock_pos.ticker,
            "name": mock_pos.name,
            "market": mock_pos.market,
            "qty": mock_pos.qty,
            "avg_price": mock_pos.avg_price,
            "current_price": mock_pos.current_price,
        }
        result.scalars.return_value.all.return_value = [mock_pos]
        db.execute = AsyncMock(return_value=result)

        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get(f"/api/v1/assets/{account.id}/positions")
        assert resp.status_code == 200
        data = resp.json()
        assert "positions" in data
        assert "summary" in data


class TestSavePositionsExtended:
    """save_positions 추가 커버 — _build, USD rate, lock conflict (lines 97, 108-109, 121, 125, 139)."""

    def _make_cache_lock_ctx(self, acquired=True):
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=acquired)
        mock_cm.__aexit__ = AsyncMock(return_value=None)
        return mock_cm

    def test_save_positions_with_actual_positions(self, override_settings):
        """비어 있지 않은 포지션 리스트 저장 (lines 108-109, 121, 139)."""
        user = _make_user()
        db = _make_mock_db()
        account = _make_account(user.id)
        db.scalar = AsyncMock(return_value=account)
        app = _setup_app(user, db)

        mock_snap = SimpleNamespace(id=uuid.uuid4(), account_id=account.id, user_id=user.id)

        with patch("app.api.v1.positions.get_cache_store") as mock_gr:
            mock_cache = AsyncMock()
            mock_cache.set = AsyncMock(return_value=True)
            mock_cache.get = AsyncMock(return_value=None)
            mock_cache.delete = AsyncMock()
            mock_cache.scan = AsyncMock(return_value=(0, []))
            mock_cache.unlink = AsyncMock()
            mock_gr.return_value = mock_cache
            with (
                patch("app.utils.inproc_lock.inproc_lock", return_value=self._make_cache_lock_ctx(True)),
                patch("app.api.v1.positions._upsert_snapshot", AsyncMock(return_value=mock_snap)),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.put(
                    f"/api/v1/assets/{account.id}/positions",
                    json=[
                        {
                            "ticker": "005930",
                            "name": "삼성전자",
                            "market": "KOSPI",
                            "qty": 10.0,
                            "avg_price": 70000.0,
                        }
                    ],
                )
        assert resp.status_code == 200
        data = resp.json()
        assert "positions" in data
        assert len(data["positions"]) == 1

    def test_save_positions_with_deposit_usd_fetches_rate(self, override_settings):
        """deposit_usd 있을 때 환율 조회 경로 (line 125)."""
        user = _make_user()
        db = _make_mock_db()
        account = _make_account(user.id)
        account.deposit_usd = 1000.0
        db.scalar = AsyncMock(return_value=account)
        app = _setup_app(user, db)

        mock_snap = SimpleNamespace(id=uuid.uuid4(), account_id=account.id, user_id=user.id)

        with patch("app.api.v1.positions.get_cache_store") as mock_gr:
            mock_cache = AsyncMock()
            mock_cache.set = AsyncMock(return_value=True)
            mock_cache.get = AsyncMock(return_value=None)
            mock_cache.delete = AsyncMock()
            mock_cache.scan = AsyncMock(return_value=(0, []))
            mock_cache.unlink = AsyncMock()
            mock_gr.return_value = mock_cache
            with (
                patch("app.utils.inproc_lock.inproc_lock", return_value=self._make_cache_lock_ctx(True)),
                patch("app.api.v1.positions._upsert_snapshot", AsyncMock(return_value=mock_snap)),
                patch("app.api.v1.positions.fetch_usd_krw", AsyncMock(return_value=1350.0)),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.put(
                    f"/api/v1/assets/{account.id}/positions",
                    json=[
                        {
                            "ticker": "005930",
                            "name": "삼성전자",
                            "market": "KOSPI",
                            "qty": 5.0,
                            "avg_price": 70000.0,
                        }
                    ],
                )
        assert resp.status_code == 200

    def test_save_positions_lock_conflict_returns_409(self, override_settings):
        """Cache 락 획득 실패 시 409 (line 97)."""
        user = _make_user()
        db = _make_mock_db()
        account = _make_account(user.id)
        db.scalar = AsyncMock(return_value=account)
        app = _setup_app(user, db)

        with patch("app.api.v1.positions.get_cache_store") as mock_gr:
            mock_cache = AsyncMock()
            mock_cache.set = AsyncMock(return_value=None)  # Lock NOT acquired
            mock_cache.delete = AsyncMock()
            mock_cache.scan = AsyncMock(return_value=(0, []))
            mock_cache.unlink = AsyncMock()
            mock_gr.return_value = mock_cache
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.put(
                    f"/api/v1/assets/{account.id}/positions",
                    json=[],
                )
        assert resp.status_code == 409


class TestSyncPositionPrices:
    """sync_position_prices 엔드포인트 커버 (lines 155-215)."""

    def _make_cache_lock_ctx(self, acquired=True):
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=acquired)
        mock_cm.__aexit__ = AsyncMock(return_value=None)
        return mock_cm

    def test_sync_no_positions_returns_400(self, override_settings):
        """저장된 포지션 없을 때 400 (lines 155-173)."""
        user = _make_user()
        db = _make_mock_db()
        account = _make_account(user.id)
        db.scalar = AsyncMock(return_value=account)
        app = _setup_app(user, db)

        with patch("app.api.v1.positions.get_cache_store") as mock_gr:
            mock_cache = AsyncMock()
            mock_cache.set = AsyncMock(return_value=True)
            mock_cache.delete = AsyncMock()
            mock_cache.scan = AsyncMock(return_value=(0, []))
            mock_cache.unlink = AsyncMock()
            mock_gr.return_value = mock_cache
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post(f"/api/v1/assets/{account.id}/positions/sync-prices")
        assert resp.status_code == 400

    def test_sync_prices_lock_conflict_returns_409(self, override_settings):
        """sync-prices 락 획득 실패 시 409 (line 161)."""
        user = _make_user()
        db = _make_mock_db()
        account = _make_account(user.id)
        db.scalar = AsyncMock(return_value=account)
        app = _setup_app(user, db)

        with patch("app.api.v1.positions.get_cache_store") as mock_gr:
            mock_cache = AsyncMock()
            mock_cache.set = AsyncMock(return_value=None)  # Lock NOT acquired
            mock_cache.delete = AsyncMock()
            mock_cache.scan = AsyncMock(return_value=(0, []))
            mock_cache.unlink = AsyncMock()
            mock_gr.return_value = mock_cache
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post(f"/api/v1/assets/{account.id}/positions/sync-prices")
        assert resp.status_code == 409

    def test_sync_prices_success(self, override_settings):
        """현재가 동기화 성공 경로 (lines 175-215)."""
        user = _make_user()
        db = _make_mock_db()
        account = _make_account(user.id)
        db.scalar = AsyncMock(return_value=account)

        mock_pos = SimpleNamespace(
            ticker="005930",
            name="삼성전자",
            market="KOSPI",
            qty=10.0,
            avg_price=70000.0,
            current_price=75000.0,
            value_krw=750000.0,
        )
        mock_pos.to_dict = lambda: {
            "ticker": mock_pos.ticker,
            "name": mock_pos.name,
            "market": mock_pos.market,
            "qty": mock_pos.qty,
            "avg_price": mock_pos.avg_price,
            "current_price": mock_pos.current_price,
        }

        pos_result = MagicMock()
        pos_result.scalars.return_value.all.return_value = [mock_pos]
        db.execute = AsyncMock(return_value=pos_result)

        mock_snap = SimpleNamespace(id=uuid.uuid4(), account_id=account.id)
        app = _setup_app(user, db)

        with patch("app.api.v1.positions.get_cache_store") as mock_gr:
            mock_cache = AsyncMock()
            mock_cache.set = AsyncMock(return_value=True)
            mock_cache.delete = AsyncMock()
            mock_cache.scan = AsyncMock(return_value=(0, []))
            mock_cache.unlink = AsyncMock()
            mock_gr.return_value = mock_cache
            with (
                patch("app.api.v1.positions.fetch_prices_batch", AsyncMock(return_value={"005930": 76000.0})),
                patch("app.api.v1.positions.fetch_usd_krw", AsyncMock(return_value=None)),
                patch("app.api.v1.positions._upsert_snapshot", AsyncMock(return_value=mock_snap)),
                patch("app.api.v1.positions.sync_snapshot_positions", AsyncMock()),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.post(f"/api/v1/assets/{account.id}/positions/sync-prices")
        assert resp.status_code == 200
        data = resp.json()
        assert "positions" in data

    def test_sync_prices_overseas_applies_usd_rate(self, override_settings):
        """해외 종목 환율 적용 경로 (lines 181, 187)."""
        user = _make_user()
        db = _make_mock_db()
        account = _make_account(user.id)
        db.scalar = AsyncMock(return_value=account)

        mock_pos = SimpleNamespace(
            ticker="AAPL",
            name="애플",
            market="NASDAQ",
            qty=5.0,
            avg_price=200000.0,
            current_price=200000.0,
            value_krw=1000000.0,
        )
        mock_pos.to_dict = lambda: {
            "ticker": mock_pos.ticker,
            "name": mock_pos.name,
            "market": mock_pos.market,
            "qty": mock_pos.qty,
            "avg_price": mock_pos.avg_price,
            "current_price": mock_pos.current_price,
        }

        pos_result = MagicMock()
        pos_result.scalars.return_value.all.return_value = [mock_pos]
        db.execute = AsyncMock(return_value=pos_result)

        mock_snap = SimpleNamespace(id=uuid.uuid4(), account_id=account.id)
        app = _setup_app(user, db)

        with patch("app.api.v1.positions.get_cache_store") as mock_gr:
            mock_cache = AsyncMock()
            mock_cache.set = AsyncMock(return_value=True)
            mock_cache.delete = AsyncMock()
            mock_cache.scan = AsyncMock(return_value=(0, []))
            mock_cache.unlink = AsyncMock()
            mock_gr.return_value = mock_cache
            with (
                patch("app.api.v1.positions.fetch_prices_batch", AsyncMock(return_value={"AAPL": 210.0})),
                patch("app.api.v1.positions.fetch_usd_krw", AsyncMock(return_value=1350.0)),
                patch("app.api.v1.positions._upsert_snapshot", AsyncMock(return_value=mock_snap)),
                patch("app.api.v1.positions.sync_snapshot_positions", AsyncMock()),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.post(f"/api/v1/assets/{account.id}/positions/sync-prices")
        assert resp.status_code == 200
        assert mock_pos.current_price == pytest.approx(210.0 * 1350.0)

    def test_sync_prices_no_price_in_map_uses_fallback(self, override_settings):
        """가격 미조회 시 기존 current_price 사용 (line 191)."""
        user = _make_user()
        db = _make_mock_db()
        account = _make_account(user.id)
        db.scalar = AsyncMock(return_value=account)

        mock_pos = SimpleNamespace(
            ticker="005930",
            name="삼성전자",
            market="KOSPI",
            qty=10.0,
            avg_price=70000.0,
            current_price=71000.0,
            value_krw=710000.0,
        )
        mock_pos.to_dict = lambda: {
            "ticker": mock_pos.ticker,
            "name": mock_pos.name,
            "market": mock_pos.market,
            "qty": mock_pos.qty,
            "avg_price": mock_pos.avg_price,
            "current_price": mock_pos.current_price,
        }

        pos_result = MagicMock()
        pos_result.scalars.return_value.all.return_value = [mock_pos]
        db.execute = AsyncMock(return_value=pos_result)

        mock_snap = SimpleNamespace(id=uuid.uuid4(), account_id=account.id)
        app = _setup_app(user, db)

        with patch("app.api.v1.positions.get_cache_store") as mock_gr:
            mock_cache = AsyncMock()
            mock_cache.set = AsyncMock(return_value=True)
            mock_cache.delete = AsyncMock()
            mock_cache.scan = AsyncMock(return_value=(0, []))
            mock_cache.unlink = AsyncMock()
            mock_gr.return_value = mock_cache
            with (
                patch(
                    "app.api.v1.positions.fetch_prices_batch", AsyncMock(return_value={})
                ),  # Empty → ticker not found
                patch("app.api.v1.positions.fetch_usd_krw", AsyncMock(return_value=None)),
                patch("app.api.v1.positions._upsert_snapshot", AsyncMock(return_value=mock_snap)),
                patch("app.api.v1.positions.sync_snapshot_positions", AsyncMock()),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.post(f"/api/v1/assets/{account.id}/positions/sync-prices")
        assert resp.status_code == 200
        assert mock_pos.current_price == pytest.approx(71000.0)  # Unchanged
