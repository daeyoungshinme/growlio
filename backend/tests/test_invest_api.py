"""DCA 투자 API 테스트 (GET /api/v1/invest/dca-analysis)."""

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


_MOCK_DCA = {
    "settings": {
        "monthly_deposit_amount": None,
        "goal_annual_return_pct": None,
        "goal_amount": None,
        "goal_start_date": None,
        "goal_initial_amount": None,
    },
    "projection_months": [],
    "yearly_achievements": [],
    "goal_timeline": {
        "months_to_goal": None,
        "expected_goal_date": None,
        "actual_expected_goal_date": None,
        "current_progress_pct": None,
        "on_track": None,
        "lead_lag_months": None,
    },
    "is_configured": False,
}


class TestDcaAnalysis:
    def test_returns_401_without_auth(self, override_settings):
        from app.api.deps import get_current_user
        from app.main import app

        app.dependency_overrides.pop(get_current_user, None)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/invest/dca-analysis")
        assert resp.status_code == 401

    def test_returns_200_with_mocked_service(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        with (
            patch(
                "app.api.v1.invest.dca_service.get_dca_analysis",
                AsyncMock(return_value=_MOCK_DCA),
            ),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get("/api/v1/invest/dca-analysis")
        assert resp.status_code == 200

    def test_returns_dca_data_structure(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        with (
            patch(
                "app.api.v1.invest.dca_service.get_dca_analysis",
                AsyncMock(return_value=_MOCK_DCA),
            ),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get("/api/v1/invest/dca-analysis")
        data = resp.json()
        assert "projection_months" in data


_MOCK_DIVIDEND_PLAN = {
    "annual_dividend_goal": None,
    "estimated_annual_krw": 1_200_000,
    "estimated_monthly_krw": 100_000,
    "actual_annual_received_krw": 500_000,
    "goal_achievement_pct": None,
    "monthly_projected": [{"month": m, "amount_krw": 0} for m in range(1, 13)],
    "monthly_received": [],
    "yearly_received": [],
}


class TestDividendPlan:
    def test_returns_200_with_mocked_service(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        with (
            patch(
                "app.api.v1.invest.dividend_plan_service.get_dividend_plan",
                AsyncMock(return_value=_MOCK_DIVIDEND_PLAN),
            ),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get("/api/v1/invest/dividend-plan")
        assert resp.status_code == 200
        data = resp.json()
        assert "estimated_annual_krw" in data
        assert "monthly_projected" in data
        assert len(data["monthly_projected"]) == 12
