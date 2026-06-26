"""대시보드 API 테스트 (GET /api/v1/dashboard)."""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


def _make_user():
    import uuid
    from types import SimpleNamespace

    return SimpleNamespace(
        id=uuid.uuid4(),
        email="test@example.com",
        display_name="테스트 유저",
        is_active=True,
        needs_password_reset=False,
    )


def _make_mock_db():
    from unittest.mock import AsyncMock, MagicMock

    from sqlalchemy.ext.asyncio import AsyncSession

    db = AsyncMock(spec=AsyncSession)
    db.scalar = AsyncMock(return_value=None)
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    result.all.return_value = []
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    db.add = MagicMock()
    return db


_MOCK_DASHBOARD = {
    "total_assets_krw": 50_000_000.0,
    "asset_allocation": [],
    "goal_amount": None,
    "goal_achievement_pct": None,
    "stock_return_pct": 5.0,
    "annual_return_pct": 3.0,
    "cumulative_return_pct": 10.0,
    "xirr_pct": None,
    "xirr_is_estimated": False,
    "goal_annual_return_pct": None,
    "retirement_target_year": None,
    "monthly_trend": [],
    "annual_deposit_goal": None,
    "deposit_achievement_pct": None,
    "annual_dividends_received": 0.0,
    "estimated_annual_dividends": 0.0,
    "dividend_monthly_breakdown": [],
}


class TestDashboardApi:
    def test_returns_401_without_auth(self, override_settings):
        from app.api.deps import get_current_user
        from app.main import app

        app.dependency_overrides.pop(get_current_user, None)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/dashboard")
        assert resp.status_code == 401

    def test_returns_200_with_mocked_service(self, override_settings):
        from app.api.deps import get_current_user
        from app.database import get_db
        from app.main import app

        user = _make_user()
        db = _make_mock_db()

        async def override_auth():
            return user

        async def override_db():
            yield db

        app.dependency_overrides[get_current_user] = override_auth
        app.dependency_overrides[get_db] = override_db
        try:
            with (
                patch(
                    "app.api.v1.dashboard.get_dashboard_summary",
                    new_callable=AsyncMock,
                    return_value=_MOCK_DASHBOARD,
                ),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.get("/api/v1/dashboard", headers={"Authorization": "Bearer fake"})
            assert resp.status_code == 200
            data = resp.json()
            assert "total_assets_krw" in data
            assert data["total_assets_krw"] == 50_000_000.0
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)

    def test_returns_200_when_cache_hit(self, override_settings):
        """Redis 캐시 히트 시에도 200 응답."""
        import json

        from app.api.deps import get_current_user
        from app.database import get_db
        from app.main import app

        user = _make_user()
        db = _make_mock_db()

        async def override_auth():
            return user

        async def override_db():
            yield db

        app.dependency_overrides[get_current_user] = override_auth
        app.dependency_overrides[get_db] = override_db
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(_MOCK_DASHBOARD))
        try:
            with (
                patch("app.api.v1.dashboard.get_redis", new_callable=AsyncMock, return_value=mock_redis),
                patch(
                    "app.api.v1.dashboard.get_dashboard_summary",
                    new_callable=AsyncMock,
                    return_value=_MOCK_DASHBOARD,
                ),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.get("/api/v1/dashboard", headers={"Authorization": "Bearer fake"})
            assert resp.status_code == 200
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)
