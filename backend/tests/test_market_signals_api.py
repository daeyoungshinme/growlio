"""시장 신호 API 테스트 (GET /api/v1/market-signals/...)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _restore_db_override():
    """이 파일이 덮어쓴 get_db 목이 뒤 테스트로 새지 않게 원복한다."""
    yield
    from app.api.deps import get_db
    from app.main import app

    app.dependency_overrides.pop(get_db, None)


def _make_user():
    return SimpleNamespace(
        id=uuid.uuid4(),
        email="test@example.com",
        display_name="테스트",
        is_active=True,
        needs_password_reset=False,
    )


def _setup_app(user):
    from app.api.deps import get_current_user, get_db
    from app.main import app

    async def override_auth():
        return user

    async def override_db():
        yield AsyncMock()

    app.dependency_overrides[get_current_user] = override_auth
    app.dependency_overrides[get_db] = override_db
    return app


_MOCK_SIGNAL = {
    "composite_level": "GREEN",
    "signals": {},
    "data_freshness": "LIVE",
}


class TestGetMarketSignalEndpoint:
    def test_returns_200_with_mocked_service(self, override_settings):
        user = _make_user()
        app = _setup_app(user)
        with (
            patch("app.api.v1.market_signals.get_market_signal", new=AsyncMock(return_value=_MOCK_SIGNAL)),
            patch("app.api.v1.market_signals.get_last_composite_level", new=AsyncMock(return_value=None)),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get("/api/v1/market-signals")
        assert resp.status_code == 200

    def test_includes_confirmed_level_without_mutating_cached_signal(self, override_settings):
        """AUTO 게이트 기준 등급을 함께 내려 준다 — 공유 캐시 dict는 건드리지 않는다(plans/63 P1-5)."""
        user = _make_user()
        app = _setup_app(user)
        cached = {**_MOCK_SIGNAL, "composite_level": "RED"}
        with (
            patch("app.api.v1.market_signals.get_market_signal", new=AsyncMock(return_value=cached)),
            patch("app.api.v1.market_signals.get_last_composite_level", new=AsyncMock(return_value="YELLOW")),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.get("/api/v1/market-signals")
        assert resp.status_code == 200
        body = resp.json()
        assert body["composite_level"] == "RED"
        assert body["confirmed_level"] == "YELLOW"
        assert "confirmed_level" not in cached

    def test_returns_401_without_auth(self, override_settings):
        from app.api.deps import get_current_user
        from app.main import app

        app.dependency_overrides.pop(get_current_user, None)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/market-signals")
        assert resp.status_code == 401
