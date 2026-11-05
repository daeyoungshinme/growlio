"""배당금 API 테스트 (GET /api/v1/dividends/...)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from tests.api_helpers import make_user, setup_app


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
        user = make_user()
        db = _make_mock_db()
        app = setup_app(user, db)
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
        user = make_user()
        db = _make_mock_db()
        app = setup_app(user, db)
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
        user = make_user()
        db = _make_mock_db()
        app = setup_app(user, db)
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
        user = make_user()
        db = _make_mock_db()
        app = setup_app(user, db)
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
