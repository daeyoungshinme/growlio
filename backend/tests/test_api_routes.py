"""주요 API 엔드포인트 HTTP 상태코드 통합 테스트.

FastAPI TestClient + 의존성 오버라이드 패턴 사용 (raise_server_exceptions=False).
실제 DB/Redis 없이 인증·라우팅·응답 구조만 검증한다.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def mock_redis_and_scheduler(monkeypatch):
    """lifespan 시 Redis·Scheduler 없이도 앱이 시작되도록 모킹한다."""
    import app.redis_client as redis_mod
    import app.scheduler as scheduler_mod

    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)
    mock_redis.aclose = AsyncMock()

    # redis_client 전역 변수를 mock으로 사전 교체 → get_redis()가 바로 반환
    monkeypatch.setattr(redis_mod, "redis_client", mock_redis)
    # scheduler start/shutdown을 no-op으로 대체
    monkeypatch.setattr(scheduler_mod.scheduler, "start", lambda: None)
    monkeypatch.setattr(scheduler_mod.scheduler, "shutdown", lambda: None)
    yield
    redis_mod.redis_client = None


# ── 공통 헬퍼 ─────────────────────────────────────────────────

def _make_user(user_id: uuid.UUID | None = None):
    return SimpleNamespace(
        id=user_id or uuid.uuid4(),
        email="test@example.com",
        display_name="테스트 유저",
        is_active=True,
        needs_password_reset=False,
    )


def _make_mock_db():
    from sqlalchemy.ext.asyncio import AsyncSession

    db = AsyncMock(spec=AsyncSession)
    db.scalar = AsyncMock(return_value=None)
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = []
    execute_result.all.return_value = []
    db.execute = AsyncMock(return_value=execute_result)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    return db


def _get_app_with_auth(user=None):
    """인증 + DB 의존성이 오버라이드된 app을 반환한다."""
    from app.main import app
    from app.api.deps import get_current_user
    from app.database import get_db

    _user = user or _make_user()
    db = _make_mock_db()

    async def override_auth():
        return _user

    async def override_db():
        yield db

    app.dependency_overrides[get_current_user] = override_auth
    app.dependency_overrides[get_db] = override_db
    return app, _user, db


# ── /health ──────────────────────────────────────────────────

class TestHealth:
    """GET /health — 인증 불필요."""

    def test_health_returns_200_or_503(self, override_settings):
        """Redis 없이도 /health 엔드포인트 자체는 응답한다."""
        from app.main import app
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/health")
        # Redis 연결 불가 시 503, 가능 시 200
        assert resp.status_code in (200, 503)


# ── /api/v1/auth/me ───────────────────────────────────────────

class TestAuthRoutes:
    """GET /api/v1/auth/me — 인증 상태 확인."""

    def test_me_returns_401_without_token(self, override_settings):
        from app.main import app
        from app.api.deps import get_current_user

        app.dependency_overrides.pop(get_current_user, None)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    def test_me_returns_200_with_auth(self, override_settings):
        from app.api.deps import get_current_user

        app, user, _ = _get_app_with_auth()
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer fake"})
            assert resp.status_code == 200
            assert resp.json()["email"] == user.email
        finally:
            app.dependency_overrides.pop(get_current_user, None)


# ── /api/v1/assets ────────────────────────────────────────────

class TestAssetsRoutes:
    """GET /api/v1/assets — 계좌 목록 조회."""

    def test_returns_401_without_auth(self, override_settings):
        from app.main import app
        from app.api.deps import get_current_user

        app.dependency_overrides.pop(get_current_user, None)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/assets")
        assert resp.status_code == 401

    def test_returns_200_with_empty_accounts(self, override_settings):
        from app.api.deps import get_current_user

        app, user, db = _get_app_with_auth()
        try:
            with (
                patch("app.api.v1.assets.get_redis", new_callable=AsyncMock),
                patch("app.utils.currency.fetch_usd_krw", new_callable=AsyncMock, return_value=1350.0),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.get("/api/v1/assets", headers={"Authorization": "Bearer fake"})
            assert resp.status_code == 200
        finally:
            app.dependency_overrides.pop(get_current_user, None)


# ── /api/v1/portfolio/current ─────────────────────────────────

class TestPortfolioRoutes:
    """GET /api/v1/portfolio/current — 포트폴리오 통합 조회."""

    def test_returns_401_without_auth(self, override_settings):
        from app.main import app
        from app.api.deps import get_current_user

        app.dependency_overrides.pop(get_current_user, None)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/portfolio/overview")
        assert resp.status_code == 401

    def test_returns_200_with_mocked_service(self, override_settings):
        from app.api.deps import get_current_user

        app, user, db = _get_app_with_auth()
        mock_overview = {
            "total_value_krw": 0, "total_invested_krw": 0,
            "total_pnl_krw": 0, "total_pnl_pct": 0,
            "positions": [], "accounts": [], "allocations": [],
        }
        try:
            with (
                patch("app.api.v1.portfolio.get_redis", new_callable=AsyncMock),
                patch(
                    "app.api.v1.portfolio.build_portfolio_overview",
                    new_callable=AsyncMock, return_value=mock_overview,
                ),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.get("/api/v1/portfolio/overview", headers={"Authorization": "Bearer fake"})
            assert resp.status_code == 200
        finally:
            app.dependency_overrides.pop(get_current_user, None)


# ── /api/v1/dividends/summary ─────────────────────────────────

class TestDividendsRoutes:
    """GET /api/v1/dividends/summary — 배당금 요약."""

    def test_returns_401_without_auth(self, override_settings):
        from app.main import app
        from app.api.deps import get_current_user

        app.dependency_overrides.pop(get_current_user, None)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/dividends/summary")
        assert resp.status_code == 401

    def test_returns_200_with_mocked_service(self, override_settings):
        from app.api.deps import get_current_user

        app, user, db = _get_app_with_auth()
        mock_summary = {
            "annual_received": 0.0,
            "estimated_annual": 0.0,
            "monthly_breakdown": [],
            "by_ticker": [],
        }
        try:
            with (
                patch(
                    "app.api.v1.dividends.get_dividend_summary",
                    new_callable=AsyncMock, return_value=mock_summary,
                ),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.get("/api/v1/dividends/summary", headers={"Authorization": "Bearer fake"})
            assert resp.status_code == 200
        finally:
            app.dependency_overrides.pop(get_current_user, None)


# ── /api/v1/tax ───────────────────────────────────────────────

class TestTaxRoutes:
    """GET /api/v1/tax — 세금 추정."""

    def test_returns_401_without_auth(self, override_settings):
        from app.main import app
        from app.api.deps import get_current_user

        app.dependency_overrides.pop(get_current_user, None)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/tax/summary")
        assert resp.status_code == 401

    def test_returns_200_with_mocked_service(self, override_settings):
        from app.api.deps import get_current_user

        app, user, db = _get_app_with_auth()
        mock_tax = {
            "year": 2026, "dividend_income": 0.0, "dividend_tax": 0.0,
            "overseas_gain": 0.0, "overseas_tax": 0.0, "total_tax": 0.0,
        }
        try:
            with (
                patch(
                    "app.api.v1.tax.get_tax_summary",
                    new_callable=AsyncMock, return_value=mock_tax,
                ),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.get("/api/v1/tax/summary", headers={"Authorization": "Bearer fake"})
            assert resp.status_code == 200
        finally:
            app.dependency_overrides.pop(get_current_user, None)


# ── /api/v1/alerts/exchange-rate ─────────────────────────────

class TestAlertsRoutes:
    """GET /api/v1/alerts/exchange-rate — 환율 알림 목록."""

    def test_returns_401_without_auth(self, override_settings):
        from app.main import app
        from app.api.deps import get_current_user

        app.dependency_overrides.pop(get_current_user, None)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/alerts/exchange-rate")
        assert resp.status_code == 401

    def test_exchange_rate_alerts_returns_200_with_empty_list(self, override_settings):
        from app.api.deps import get_current_user

        app, user, db = _get_app_with_auth()
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.get(
                    "/api/v1/alerts/exchange-rate",
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code == 200
            assert isinstance(resp.json(), list)
        finally:
            app.dependency_overrides.pop(get_current_user, None)
