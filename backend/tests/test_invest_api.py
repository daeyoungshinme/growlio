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
    from app.core.database import get_db
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


class TestGoalFeasibility:
    def test_returns_401_without_auth(self, override_settings):
        from app.api.deps import get_current_user
        from app.main import app

        app.dependency_overrides.pop(get_current_user, None)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get(
                "/api/v1/invest/goal-feasibility",
                params={"goal_amount": 500_000_000, "target_year": 2040, "initial_amount": 100_000_000},
            )
        assert resp.status_code == 401

    def test_computes_required_return_with_explicit_initial_amount(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get(
                "/api/v1/invest/goal-feasibility",
                params={
                    "goal_amount": 500_000_000,
                    "target_year": 2040,
                    "monthly_deposit_amount": 1_000_000,
                    "initial_amount": 100_000_000,
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["required_return_pct"] is not None
        assert data["pv"] == 100_000_000
        assert data["note"] is None
        assert len(data["deposit_guide"]) == 3
        monthly_deposits = [item["required_monthly_deposit"] for item in data["deposit_guide"]]
        assert monthly_deposits == sorted(monthly_deposits, reverse=True)  # 가정 수익률이 높을수록 필요 적립액↓
        for item in data["deposit_guide"]:
            assert item["required_annual_deposit"] == pytest.approx(item["required_monthly_deposit"] * 12)

    def test_falls_back_to_current_asset_total_when_initial_amount_omitted(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        with (
            patch(
                "app.api.v1.invest.build_asset_totals",
                AsyncMock(return_value=(200_000_000, 0, 0, {})),
            ),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get(
                "/api/v1/invest/goal-feasibility",
                params={"goal_amount": 500_000_000, "target_year": 2040, "monthly_deposit_amount": 1_000_000},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["pv"] == 200_000_000

    def test_fallback_excludes_real_estate_from_asset_total(self, override_settings):
        """initial_amount 미지정 시 폴백으로 쓰는 총자산에서 부동산 순자산은 제외해야 한다."""
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        with (
            patch(
                "app.api.v1.invest.build_asset_totals",
                AsyncMock(return_value=(200_000_000, 0, 0, {"REAL_ESTATE": 80_000_000})),
            ),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get(
                "/api/v1/invest/goal-feasibility",
                params={"goal_amount": 500_000_000, "target_year": 2040, "monthly_deposit_amount": 1_000_000},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["pv"] == 120_000_000

    def test_already_achieved_returns_none_with_note(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get(
                "/api/v1/invest/goal-feasibility",
                params={"goal_amount": 100_000_000, "target_year": 2040, "initial_amount": 200_000_000},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["required_return_pct"] is None
        assert data["note"] == "이미 목표 금액을 달성했습니다"
        assert data["deposit_guide"] == []

    def test_past_target_year_returns_none_with_note(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get(
                "/api/v1/invest/goal-feasibility",
                params={"goal_amount": 500_000_000, "target_year": 2020, "initial_amount": 100_000_000},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["required_return_pct"] is None
        assert "목표 연도가 이미 지났습니다" in data["note"]

    def test_infeasible_goal_returns_none_with_note(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get(
                "/api/v1/invest/goal-feasibility",
                params={
                    "goal_amount": 1_000_000_000_000,
                    "target_year": 2027,
                    "monthly_deposit_amount": 0,
                    "initial_amount": 100_000_000,
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["required_return_pct"] is None
        assert "달성이 매우 어려운 목표" in data["note"]


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
