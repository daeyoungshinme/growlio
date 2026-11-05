"""인사이트 API 테스트 (GET /api/v1/insights/...)."""

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
    return db


_MOCK_INSIGHTS = [
    {"type": "CONCENTRATION_RISK", "severity": "WARNING", "message": "삼성전자 비중이 30% 초과"},
]


class TestInsights:
    def test_returns_401_without_auth(self, override_settings):
        from app.api.deps import get_current_user
        from app.main import app

        app.dependency_overrides.pop(get_current_user, None)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/insights")
        assert resp.status_code == 401

    def test_list_insights_returns_200(self, override_settings):
        user = make_user()
        db = _make_mock_db()
        app = setup_app(user, db)
        with (
            patch(
                "app.api.v1.insights.generate_insights",
                AsyncMock(return_value=_MOCK_INSIGHTS),
            ),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get("/api/v1/insights")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
