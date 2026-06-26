"""배당금 API 테스트 (GET /api/v1/dividends/...)."""

from __future__ import annotations

import uuid
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
    from app.database import get_db
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


class TestTickerSettings:
    def test_get_ticker_settings_returns_default_when_not_found(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        with (
            patch(
                "app.api.v1.dividends.get_ticker_settings",
                AsyncMock(return_value=None),
            ),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get("/api/v1/dividends/ticker-settings/005930?market=KOSPI")
        assert resp.status_code == 200
        data = resp.json()
        assert data["dividend_months"] == []

    def test_get_ticker_settings_returns_result_when_found(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        mock_result = {"ticker": "005930", "market": "KOSPI", "dividend_months": [3, 6, 9, 12], "is_manual": True}
        with (
            patch(
                "app.api.v1.dividends.get_ticker_settings",
                AsyncMock(return_value=mock_result),
            ),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get("/api/v1/dividends/ticker-settings/005930?market=KOSPI")
        assert resp.status_code == 200
        assert resp.json()["dividend_months"] == [3, 6, 9, 12]

    def test_put_ticker_settings_returns_200(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        mock_result = {"ticker": "005930", "market": "KOSPI", "dividend_months": [3, 9], "is_manual": True}
        with (
            patch(
                "app.api.v1.dividends.upsert_ticker_settings",
                AsyncMock(return_value=mock_result),
            ),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.put(
                "/api/v1/dividends/ticker-settings/005930",
                json={"market": "KOSPI", "dividend_months": [3, 9]},
            )
        assert resp.status_code == 200

    def test_put_ticker_settings_validates_months(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.put(
                "/api/v1/dividends/ticker-settings/005930",
                json={"market": "KOSPI", "dividend_months": []},
            )
        assert resp.status_code == 422

    def test_put_ticker_settings_validates_month_range(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.put(
                "/api/v1/dividends/ticker-settings/005930",
                json={"market": "KOSPI", "dividend_months": [0, 13]},
            )
        assert resp.status_code == 422

    def test_delete_ticker_settings_returns_404_when_not_found(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        with (
            patch(
                "app.api.v1.dividends.delete_ticker_settings",
                AsyncMock(return_value=False),
            ),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.delete("/api/v1/dividends/ticker-settings/005930?market=KOSPI")
        assert resp.status_code == 404

    def test_delete_ticker_settings_returns_200_on_success(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        with (
            patch(
                "app.api.v1.dividends.delete_ticker_settings",
                AsyncMock(return_value=True),
            ),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.delete("/api/v1/dividends/ticker-settings/005930?market=KOSPI")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True


class TestDividendDripSimulationExtended:
    def test_drip_simulation_with_custom_yield(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        mock_div_summary = {"total_dividend_krw": 0.0, "estimated_annual": 0.0}
        mock_result = {"annual_dividends": [], "compounding_years": []}
        with (
            patch("app.api.v1.dividends.get_dividend_summary", AsyncMock(return_value=mock_div_summary)),
            patch("app.api.v1.dividends.simulate_drip", MagicMock(return_value=mock_result)),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.post(
                "/api/v1/dividends/drip-simulation",
                json={"n_years": 5, "annual_dividend_yield_pct": 3.5},
            )
        assert resp.status_code == 200

    def test_drip_simulation_invalid_years(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post(
                "/api/v1/dividends/drip-simulation",
                json={"n_years": 100},
            )
        assert resp.status_code == 422


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


class TestDividendDripSimulationWithDashboardError:
    def test_drip_simulation_handles_dashboard_error(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        mock_div_summary = {"total_dividend_krw": 0.0, "estimated_annual": 0.0, "estimated_annual_krw": 0.0}
        mock_result = {"annual_dividends": [], "compounding_years": []}
        with (
            patch("app.api.v1.dividends.get_dividend_summary", AsyncMock(return_value=mock_div_summary)),
            patch(
                "app.services.asset_aggregator.get_dashboard_summary",
                AsyncMock(side_effect=Exception("dashboard error")),
            ),
            patch("app.api.v1.dividends.simulate_drip", MagicMock(return_value=mock_result)),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.post("/api/v1/dividends/drip-simulation", json={})
        assert resp.status_code == 200

    def test_drip_simulation_uses_yield_from_values(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        mock_div_summary = {"total_dividend_krw": 500000.0, "estimated_annual": 100000.0}
        mock_result = {"annual_dividends": [], "compounding_years": []}
        with (
            patch("app.api.v1.dividends.get_dividend_summary", AsyncMock(return_value=mock_div_summary)),
            patch(
                "app.services.asset_aggregator.get_dashboard_summary",
                AsyncMock(return_value={"total_assets_krw": 5000000.0}),
            ),
            patch("app.api.v1.dividends.simulate_drip", MagicMock(return_value=mock_result)),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.post("/api/v1/dividends/drip-simulation", json={})
        assert resp.status_code == 200


class TestDividendDripSimulation:
    def test_drip_simulation_returns_200(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        mock_div_summary = {"total_dividend_krw": 0.0, "estimated_annual": 0.0, "estimated_annual_krw": 0.0}
        mock_result = {"annual_dividends": [], "compounding_years": []}
        with (
            patch(
                "app.api.v1.dividends.get_dividend_summary",
                AsyncMock(return_value=mock_div_summary),
            ),
            patch(
                "app.api.v1.dividends.simulate_drip",
                MagicMock(return_value=mock_result),
            ),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.post("/api/v1/dividends/drip-simulation", json={})
        assert resp.status_code == 200
