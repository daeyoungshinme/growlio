"""배당금 API 테스트 (GET /api/v1/dividends/...)."""

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


_MOCK_SUMMARY = {"total_dividend_krw": 0.0, "estimated_annual_krw": 0.0}


class TestDividendSummary:
    def test_returns_401_without_auth(self, override_settings):
        from app.api.deps import get_current_user
        from app.main import app

        app.dependency_overrides.pop(get_current_user, None)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/dividends/summary")
        assert resp.status_code == 401

    def test_returns_200_with_mocked_service(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        with (
            patch(
                "app.api.v1.dividends.get_dividend_summary",
                AsyncMock(return_value=_MOCK_SUMMARY),
            ),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get("/api/v1/dividends/summary")
        assert resp.status_code == 200


class TestDividendPositions:
    def test_returns_200_with_empty_list(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        with (
            patch(
                "app.api.v1.dividends.get_position_dividend_yields",
                AsyncMock(return_value=[]),
            ),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get("/api/v1/dividends/positions")
        assert resp.status_code == 200
        assert resp.json() == []


class TestDividendByTicker:
    def test_returns_200_with_mocked_service(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        with (
            patch(
                "app.api.v1.dividends.get_ticker_dividend_summary",
                AsyncMock(return_value=[]),
            ),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get("/api/v1/dividends/by-ticker")
        assert resp.status_code == 200


class TestDividendMonthlyOptimization:
    def test_monthly_optimization_returns_200(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        with (
            patch(
                "app.api.v1.dividends.get_ticker_dividend_summary",
                AsyncMock(return_value=[]),
            ),
            patch("app.api.v1.dividends.calc_monthly_optimization", return_value={}),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get("/api/v1/dividends/monthly-optimization")
        assert resp.status_code == 200
