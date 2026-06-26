"""시장 신호 API 테스트 (GET /api/v1/market-signals/...)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


def _make_user():
    return SimpleNamespace(
        id=uuid.uuid4(),
        email="test@example.com",
        display_name="테스트",
        is_active=True,
        needs_password_reset=False,
    )


def _setup_app(user):
    from app.api.deps import get_current_user
    from app.main import app

    async def override_auth():
        return user

    app.dependency_overrides[get_current_user] = override_auth
    return app


_MOCK_SIGNAL = {
    "composite_level": "GREEN",
    "signals": {},
    "data_freshness": "LIVE",
}

_MOCK_MACRO = {
    "cpi": {"direction": "flat"},
    "implication": {"label": "중립"},
    "data_freshness": "LIVE",
}


class TestGetMarketSignalEndpoint:
    def test_returns_200_with_mocked_service(self, override_settings):
        user = _make_user()
        app = _setup_app(user)
        with (
            patch("app.api.v1.market_signals.get_market_signal", new=AsyncMock(return_value=_MOCK_SIGNAL)),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get("/api/v1/market-signals")
        assert resp.status_code == 200

    def test_returns_401_without_auth(self, override_settings):
        from app.api.deps import get_current_user
        from app.main import app

        app.dependency_overrides.pop(get_current_user, None)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/market-signals")
        assert resp.status_code == 401


class TestGetMacroDiagnosisEndpoint:
    def test_returns_200_with_mocked_service(self, override_settings):
        user = _make_user()
        app = _setup_app(user)
        with (
            patch("app.api.v1.market_signals.get_macro_diagnosis", new=AsyncMock(return_value=_MOCK_MACRO)),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get("/api/v1/market-signals/macro-diagnosis")
        assert resp.status_code == 200
