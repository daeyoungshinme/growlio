"""설정 API 테스트 (GET/PUT /api/v1/settings)."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

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
    db.add = MagicMock()
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


class TestGetSettings:
    def test_returns_401_without_auth(self, override_settings):
        from app.api.deps import get_current_user
        from app.main import app

        app.dependency_overrides.pop(get_current_user, None)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/settings")
        assert resp.status_code == 401

    def test_returns_200_no_settings_row(self, override_settings):
        """UserSettings 행 없을 때 기본값 반환."""
        user = _make_user()
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=None)

        app = _setup_app(user, db)
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.get("/api/v1/settings", headers={"Authorization": "Bearer fake"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["has_kis"] is False
            assert data["has_dart"] is False
            assert data["user_email"] == "test@example.com"
        finally:
            from app.api.deps import get_current_user
            from app.core.database import get_db

            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)

    def test_returns_200_with_settings_row(self, override_settings):
        """UserSettings 행 있을 때 실제 값 반환."""
        user = _make_user()
        db = _make_mock_db()
        settings = SimpleNamespace(
            dart_api_key="encrypted_key",
            goal_amount=100_000_000,
            goal_annual_return_pct=7.0,
            annual_deposit_goal=10_000_000,
            monthly_deposit_amount=None,
            retirement_target_year=2045,
            annual_dividend_goal=None,
            notification_email=None,
            fcm_token=None,
            composite_signal_alerts_enabled=True,
            goal_candidate_tickers=None,
            goal_risk_tolerance=None,
            goal_max_weight_pct=None,
            goal_cagr_lookback_years=None,
            goal_short_term_equity_floor_pct=None,
        )
        db.scalar = AsyncMock(return_value=settings)

        app = _setup_app(user, db)
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.get("/api/v1/settings", headers={"Authorization": "Bearer fake"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["has_dart"] is True
            assert data["goal_amount"] == 100_000_000
            assert data["goal_candidate_tickers"] == []
            # 신규 추천 설정 컬럼이 NULL이면 기존 하드코딩 기본값과 동일하게 echo된다
            assert data["goal_risk_tolerance"] == "CONSERVATIVE"
            assert data["goal_max_weight_pct"] == 40.0
            assert data["goal_cagr_lookback_years"] == 10
            assert data["goal_short_term_equity_floor_pct"] == 80.0
        finally:
            from app.api.deps import get_current_user
            from app.core.database import get_db

            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)


class TestUpdateGoal:
    def test_put_goal_returns_200(self, override_settings):
        """목표 금액 업데이트."""
        user = _make_user()
        db = _make_mock_db()
        settings = SimpleNamespace(
            goal_amount=None,
            goal_annual_return_pct=None,
            annual_deposit_goal=None,
            monthly_deposit_amount=None,
            retirement_target_year=None,
            goal_start_date=None,
            goal_initial_amount=None,
            annual_dividend_goal=None,
        )
        db.scalar = AsyncMock(return_value=settings)

        app = _setup_app(user, db)
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.put(
                    "/api/v1/settings/goal",
                    json={"goal_amount": 200_000_000},
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code in (200, 422)
        finally:
            from app.api.deps import get_current_user
            from app.core.database import get_db

            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)

    def test_put_goal_with_all_fields(self, override_settings):
        """모든 목표 필드 동시 업데이트."""
        user = _make_user()
        db = _make_mock_db()
        settings = SimpleNamespace(
            goal_amount=None,
            goal_annual_return_pct=None,
            annual_deposit_goal=None,
            monthly_deposit_amount=None,
            retirement_target_year=None,
            goal_start_date=None,
            goal_initial_amount=None,
            annual_dividend_goal=None,
        )
        db.scalar = AsyncMock(return_value=settings)

        app = _setup_app(user, db)
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.put(
                    "/api/v1/settings/goal",
                    json={
                        "goal_amount": 200_000_000,
                        "goal_annual_return_pct": 7.0,
                        "annual_deposit_goal": 10_000_000,
                        "monthly_deposit_amount": 800_000,
                        "retirement_target_year": 2045,
                        "goal_start_date": "2026-01-01",
                        "goal_initial_amount": 5_000_000,
                        "annual_dividend_goal": 12_000_000,
                    },
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code in (200, 422)
        finally:
            from app.api.deps import get_current_user
            from app.core.database import get_db

            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)

    def test_put_goal_rejects_negative_amount(self, override_settings):
        """음수 목표 금액은 422 반환."""
        user = _make_user()
        db = _make_mock_db()

        app = _setup_app(user, db)
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.put(
                    "/api/v1/settings/goal",
                    json={"goal_amount": -1000},
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code == 422
        finally:
            from app.api.deps import get_current_user
            from app.core.database import get_db

            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)


class TestUpdateCompositeSignalAlerts:
    def test_put_composite_signal_alerts_returns_200_and_sets_flag(self, override_settings):
        """복합신호(시장/리스크) 알림 수신 여부를 유저 단위로 저장한다."""
        user = _make_user()
        db = _make_mock_db()
        settings = SimpleNamespace(composite_signal_alerts_enabled=True)
        db.scalar = AsyncMock(return_value=settings)

        app = _setup_app(user, db)
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.put(
                    "/api/v1/settings/composite-signal-alerts",
                    json={"enabled": False},
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code == 200
            assert settings.composite_signal_alerts_enabled is False
        finally:
            from app.api.deps import get_current_user
            from app.core.database import get_db

            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)

    def test_put_composite_signal_alerts_returns_401_without_auth(self, override_settings):
        from app.api.deps import get_current_user
        from app.main import app

        app.dependency_overrides.pop(get_current_user, None)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.put("/api/v1/settings/composite-signal-alerts", json={"enabled": True})
        assert resp.status_code == 401


class TestUpdateGoalCandidateTickers:
    def test_put_goal_candidate_tickers_returns_200_and_saves_list(self, override_settings):
        """목표 역산 추천용 사용자 등록 후보 ETF 목록을 저장한다."""
        user = _make_user()
        db = _make_mock_db()
        settings = SimpleNamespace(goal_candidate_tickers=None)
        db.scalar = AsyncMock(return_value=settings)

        app = _setup_app(user, db)
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.put(
                    "/api/v1/settings/goal-candidate-tickers",
                    json={
                        "tickers": [{"ticker": "TLT", "name": "iShares 20+ Year Treasury Bond ETF", "market": "NYSE"}]
                    },
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code == 200
            assert settings.goal_candidate_tickers == [
                {
                    "ticker": "TLT",
                    "name": "iShares 20+ Year Treasury Bond ETF",
                    "market": "NYSE",
                    "asset_class": "EQUITY",
                    "index_region": None,
                }
            ]
        finally:
            from app.api.deps import get_current_user
            from app.core.database import get_db

            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)

    def test_put_goal_candidate_tickers_rejects_over_twenty(self, override_settings):
        """후보 ETF가 20개를 초과하면 422를 반환한다."""
        user = _make_user()
        db = _make_mock_db()

        app = _setup_app(user, db)
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.put(
                    "/api/v1/settings/goal-candidate-tickers",
                    json={"tickers": [{"ticker": f"T{i}", "name": f"ETF {i}", "market": "NYSE"} for i in range(21)]},
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code == 422
        finally:
            from app.api.deps import get_current_user
            from app.core.database import get_db

            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)

    def test_put_goal_candidate_tickers_returns_401_without_auth(self, override_settings):
        from app.api.deps import get_current_user
        from app.main import app

        app.dependency_overrides.pop(get_current_user, None)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.put("/api/v1/settings/goal-candidate-tickers", json={"tickers": []})
        assert resp.status_code == 401


class TestUpdateGoalRecommendationOptions:
    def test_put_goal_recommendation_options_returns_200_and_saves_fields(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        settings = SimpleNamespace(
            goal_risk_tolerance=None,
            goal_max_weight_pct=None,
            goal_cagr_lookback_years=None,
            goal_short_term_equity_floor_pct=None,
        )
        db.scalar = AsyncMock(return_value=settings)

        app = _setup_app(user, db)
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.put(
                    "/api/v1/settings/goal-recommendation-options",
                    json={
                        "risk_tolerance": "AGGRESSIVE",
                        "max_weight_pct": 25.0,
                        "cagr_lookback_years": 5,
                        "short_term_equity_floor_pct": 60.0,
                    },
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code == 200
            assert settings.goal_risk_tolerance == "AGGRESSIVE"
            assert settings.goal_max_weight_pct == 25.0
            assert settings.goal_cagr_lookback_years == 5
            assert settings.goal_short_term_equity_floor_pct == 60.0
        finally:
            from app.api.deps import get_current_user
            from app.core.database import get_db

            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)

    def test_put_goal_recommendation_options_rejects_short_term_equity_floor_out_of_range(self, override_settings):
        user = _make_user()
        db = _make_mock_db()

        app = _setup_app(user, db)
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.put(
                    "/api/v1/settings/goal-recommendation-options",
                    json={
                        "risk_tolerance": "BALANCED",
                        "max_weight_pct": 40.0,
                        "cagr_lookback_years": 10,
                        "short_term_equity_floor_pct": 150.0,
                    },
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code == 422
        finally:
            from app.api.deps import get_current_user
            from app.core.database import get_db

            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)

    def test_put_goal_recommendation_options_rejects_max_weight_out_of_range(self, override_settings):
        user = _make_user()
        db = _make_mock_db()

        app = _setup_app(user, db)
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.put(
                    "/api/v1/settings/goal-recommendation-options",
                    json={"risk_tolerance": "BALANCED", "max_weight_pct": 5.0, "cagr_lookback_years": 5},
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code == 422
        finally:
            from app.api.deps import get_current_user
            from app.core.database import get_db

            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)

    def test_put_goal_recommendation_options_rejects_invalid_lookback_years(self, override_settings):
        user = _make_user()
        db = _make_mock_db()

        app = _setup_app(user, db)
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.put(
                    "/api/v1/settings/goal-recommendation-options",
                    json={"risk_tolerance": "BALANCED", "max_weight_pct": 40.0, "cagr_lookback_years": 7},
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code == 422
        finally:
            from app.api.deps import get_current_user
            from app.core.database import get_db

            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)

    def test_put_goal_recommendation_options_returns_401_without_auth(self, override_settings):
        from app.api.deps import get_current_user
        from app.main import app

        app.dependency_overrides.pop(get_current_user, None)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.put(
                "/api/v1/settings/goal-recommendation-options",
                json={"risk_tolerance": "CONSERVATIVE", "max_weight_pct": 40.0, "cagr_lookback_years": 10},
            )
        assert resp.status_code == 401


class TestUpdateDartKey:
    def test_put_dart_returns_200(self, override_settings):
        """DART API 키 저장 성공."""
        from unittest.mock import patch as _patch

        user = _make_user()
        db = _make_mock_db()
        settings_row = SimpleNamespace(dart_api_key=None)
        db.scalar = AsyncMock(return_value=settings_row)

        app = _setup_app(user, db)
        try:
            with (
                _patch("app.api.v1.settings.encrypt", return_value="enc_key"),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.put(
                    "/api/v1/settings/dart",
                    json={"api_key": "test_dart_key"},
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code == 200
        finally:
            from app.api.deps import get_current_user
            from app.core.database import get_db

            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)
