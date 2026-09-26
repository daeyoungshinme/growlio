"""세금 추정 API 테스트 (GET /api/v1/tax/...)."""

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
    result.all.return_value = []
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
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


_MOCK_TAX_SUMMARY = {
    "year": 2024,
    "overseas_realized_gain_krw": 0.0,
    "dividend_total_krw": 0.0,
    "dividend_tax_krw": 0.0,
    "overseas_tax_krw": 0.0,
    "total_tax_krw": 0.0,
    "comprehensive_income_warning": False,
}

_MOCK_OVERSEAS_POSITIONS: list = []


class TestTaxSummary:
    def test_returns_401_without_auth(self, override_settings):
        from app.api.deps import get_current_user
        from app.main import app

        app.dependency_overrides.pop(get_current_user, None)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/tax/summary")
        assert resp.status_code == 401

    def test_returns_200_with_mocked_service(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        with (
            patch(
                "app.api.v1.tax.get_tax_summary",
                AsyncMock(return_value=_MOCK_TAX_SUMMARY),
            ),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get("/api/v1/tax/summary")
        assert resp.status_code == 200

    def test_returns_200_with_year_param(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        with (
            patch(
                "app.api.v1.tax.get_tax_summary",
                AsyncMock(return_value=_MOCK_TAX_SUMMARY),
            ),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get("/api/v1/tax/summary?year=2023")
        assert resp.status_code == 200

    def test_returns_400_for_invalid_year(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/tax/summary?year=1999")
        assert resp.status_code == 400


class TestOverseasPositionsTax:
    def test_returns_401_without_auth(self, override_settings):
        from app.api.deps import get_current_user
        from app.main import app

        app.dependency_overrides.pop(get_current_user, None)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/tax/overseas-positions")
        assert resp.status_code == 401

    def test_returns_200_with_mocked_service(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        with (
            patch(
                "app.api.v1.tax.get_overseas_positions_detail",
                AsyncMock(return_value=_MOCK_OVERSEAS_POSITIONS),
            ),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get("/api/v1/tax/overseas-positions")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


_MOCK_ISA_STATUS: dict = {"accounts": [], "note": "추정치입니다."}
_MOCK_PENSION_CONTRIBUTION = {
    "year": 2026,
    "pension_savings_deposit_krw": 0.0,
    "irp_deposit_krw": 0.0,
    "total_deposit_krw": 0.0,
    "pension_savings_limit_krw": 6_000_000,
    "total_limit_krw": 9_000_000,
    "pension_savings_achievement_pct": 0.0,
    "total_achievement_pct": 0.0,
    "pension_savings_remaining_krw": 6_000_000.0,
    "total_remaining_krw": 9_000_000.0,
    "note": "수기 입력 기준입니다.",
}


class TestIsaStatus:
    def test_returns_401_without_auth(self, override_settings):
        from app.api.deps import get_current_user
        from app.main import app

        app.dependency_overrides.pop(get_current_user, None)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/tax/isa-status")
        assert resp.status_code == 401

    def test_returns_200_with_mocked_service(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        with (
            patch(
                "app.api.v1.tax.get_isa_status_summary",
                AsyncMock(return_value=_MOCK_ISA_STATUS),
            ),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get("/api/v1/tax/isa-status")
        assert resp.status_code == 200
        assert resp.json()["accounts"] == []


class TestPensionContribution:
    def test_returns_401_without_auth(self, override_settings):
        from app.api.deps import get_current_user
        from app.main import app

        app.dependency_overrides.pop(get_current_user, None)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/tax/pension-contribution")
        assert resp.status_code == 401

    def test_returns_200_with_mocked_service(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        with (
            patch(
                "app.api.v1.tax.calc_pension_contribution_status",
                AsyncMock(return_value=_MOCK_PENSION_CONTRIBUTION),
            ),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get("/api/v1/tax/pension-contribution")
        assert resp.status_code == 200

    def test_returns_400_for_invalid_year(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/tax/pension-contribution?year=1999")
        assert resp.status_code == 400


class TestTaxActionPlan:
    def test_returns_200_with_mocked_service(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        mock_plan = {"year": 2026, "income_bracket": None, "actions": [], "note": "참고용"}
        with (
            patch("app.api.v1.tax.get_tax_action_plan", AsyncMock(return_value=mock_plan)) as mock_service,
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get("/api/v1/tax/action-plan")
        assert resp.status_code == 200
        assert resp.json()["actions"] == []
        mock_service.assert_awaited_once()

    def test_returns_400_for_other_year(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/tax/action-plan?year=2020")
        assert resp.status_code == 400

    def test_returns_401_without_auth(self, override_settings):
        from app.api.deps import get_current_user
        from app.main import app

        app.dependency_overrides.pop(get_current_user, None)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/tax/action-plan")
        assert resp.status_code == 401


_MOCK_REALIZED = {
    "year": 2026,
    "realized_gain_krw": 1_000_000.0,
    "source": "BROKER",
    "covered_accounts": [],
    "uncovered_accounts": [],
    "as_of": "2026-09-26",
}


class TestOverseasRealized:
    def test_returns_200_with_mocked_service(self, override_settings):
        user = _make_user()
        app = _setup_app(user, _make_mock_db())
        with (
            patch("app.api.v1.tax.get_overseas_realized_summary", new=AsyncMock(return_value=_MOCK_REALIZED)),
            TestClient(app) as client,
        ):
            resp = client.get("/api/v1/tax/overseas-realized")
        assert resp.status_code == 200
        assert resp.json()["realized_gain_krw"] == 1_000_000.0

    def test_returns_400_for_future_year(self, override_settings):
        user = _make_user()
        app = _setup_app(user, _make_mock_db())
        with TestClient(app) as client:
            resp = client.get("/api/v1/tax/overseas-realized?year=2999")
        assert resp.status_code == 400

    def test_summary_passes_realized_gain(self, override_settings):
        user = _make_user()
        app = _setup_app(user, _make_mock_db())
        summary_mock = AsyncMock(return_value=_MOCK_TAX_SUMMARY)
        with (
            patch("app.api.v1.tax.get_overseas_realized_summary", new=AsyncMock(return_value=_MOCK_REALIZED)),
            patch("app.api.v1.tax.get_tax_summary", new=summary_mock),
            TestClient(app) as client,
        ):
            resp = client.get("/api/v1/tax/summary")
        assert resp.status_code == 200
        assert summary_mock.call_args.kwargs["overseas_realized_krw"] == 1_000_000.0
