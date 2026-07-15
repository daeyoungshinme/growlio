"""리밸런싱 API 테스트 (GET /api/v1/rebalancing)."""

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
    result.scalars.return_value.first.return_value = None
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
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


_MOCK_ANALYSIS = {
    "portfolio_id": str(uuid.uuid4()),
    "portfolio_name": "테스트 포트폴리오",
    "total_value_krw": 10_000_000,
    "items": [],
    "drift_score": 0.0,
    "needs_rebalancing": False,
}


class TestRebalancingAnalyze:
    def test_returns_401_without_auth(self, override_settings):
        from app.api.deps import get_current_user
        from app.main import app

        app.dependency_overrides.pop(get_current_user, None)
        pid = uuid.uuid4()
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get(f"/api/v1/rebalancing/portfolios/{pid}/analyze")
        assert resp.status_code == 401

    def test_returns_404_for_nonexistent_portfolio(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=None)

        app = _setup_app(user, db)
        try:
            with (
                patch(
                    "app.api.v1.rebalancing.get_redis",
                    new_callable=AsyncMock,
                    return_value=AsyncMock(get=AsyncMock(return_value=None)),
                ),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.get(
                    f"/api/v1/rebalancing/portfolios/{uuid.uuid4()}/analyze",
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code in (404, 422)
        finally:
            from app.api.deps import get_current_user
            from app.database import get_db

            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)


class TestRebalancingHistory:
    def test_returns_401_without_auth(self, override_settings):
        from app.api.deps import get_current_user
        from app.main import app

        app.dependency_overrides.pop(get_current_user, None)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/rebalancing/history")
        assert resp.status_code == 401

    def test_returns_200_empty_history(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        db.execute.return_value.scalars.return_value.all.return_value = []

        app = _setup_app(user, db)
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.get(
                    "/api/v1/rebalancing/history",
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code == 200
            assert resp.json() == []
        finally:
            from app.api.deps import get_current_user
            from app.database import get_db

            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)


class TestDriftSummary:
    def test_composite_signal_alerts_disabled_forces_has_composite_signal_false(self, override_settings):
        """유저가 composite_signal_alerts_enabled=False로 꺼두면, 실제 신호 상태와 무관하게
        모든 포트폴리오 summary의 has_composite_signal이 False로 강제된다."""
        user = _make_user()
        db = _make_mock_db()
        portfolio = SimpleNamespace(
            id=uuid.uuid4(), name="테스트 포트폴리오", account_ids=None, base_type="STOCK", items=[]
        )
        settings_row = SimpleNamespace(composite_signal_alerts_enabled=False)
        db.scalar = AsyncMock(return_value=settings_row)

        app = _setup_app(user, db)
        try:
            with (
                patch(
                    "app.api.v1.rebalancing.get_linked_portfolios",
                    new_callable=AsyncMock,
                    return_value=[portfolio],
                ),
                patch(
                    "app.api.v1.rebalancing.get_active_alert_thresholds",
                    new_callable=AsyncMock,
                    return_value={},
                ),
                patch(
                    "app.api.v1.rebalancing.build_portfolio_overview",
                    new_callable=AsyncMock,
                    return_value={"all_positions": [], "total_assets_krw": 0, "total_stock_krw": 0},
                ),
                patch(
                    "app.api.v1.rebalancing.fetch_market_and_risk_signal",
                    new_callable=AsyncMock,
                ) as mock_fetch,
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.get(
                    "/api/v1/rebalancing/drift-summary",
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code == 200
            summaries = resp.json()
            assert len(summaries) == 1
            assert summaries[0]["has_composite_signal"] is False
            mock_fetch.assert_not_called()
        finally:
            from app.api.deps import get_current_user
            from app.database import get_db

            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)


class TestCompositeSignalStatus:
    def test_returns_401_without_auth(self, override_settings):
        from app.api.deps import get_current_user
        from app.main import app

        app.dependency_overrides.pop(get_current_user, None)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/rebalancing/composite-signal")
        assert resp.status_code == 401

    def test_disabled_returns_enabled_false_and_skips_signal_fetch(self, override_settings):
        """UserSettings 행이 없으면 enabled 기본값 True. 명시적으로 꺼둔 경우엔 신호 조회를 스킵한다."""
        user = _make_user()
        db = _make_mock_db()
        settings_row = SimpleNamespace(composite_signal_alerts_enabled=False)
        db.scalar = AsyncMock(return_value=settings_row)

        app = _setup_app(user, db)
        try:
            with (
                patch(
                    "app.api.v1.rebalancing.fetch_market_and_risk_signal",
                    new_callable=AsyncMock,
                ) as mock_fetch,
                patch(
                    "app.api.v1.rebalancing.get_redis",
                    new_callable=AsyncMock,
                    return_value=AsyncMock(),
                ),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.get(
                    "/api/v1/rebalancing/composite-signal",
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code == 200
            data = resp.json()
            assert data["enabled"] is False
            assert data["triggered"] is False
            mock_fetch.assert_not_called()
        finally:
            from app.api.deps import get_current_user
            from app.database import get_db

            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)

    def test_no_settings_row_defaults_enabled_true_and_reports_trigger(self, override_settings):
        """UserSettings 행이 없으면(신규 유저) enabled 기본값 True로 신호를 평가한다."""
        user = _make_user()
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=None)

        app = _setup_app(user, db)
        try:
            with (
                patch(
                    "app.api.v1.rebalancing.fetch_market_and_risk_signal",
                    new_callable=AsyncMock,
                    return_value=("RED", {"data_available": False}),
                ),
                patch(
                    "app.api.v1.rebalancing.get_redis",
                    new_callable=AsyncMock,
                    return_value=AsyncMock(),
                ),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.get(
                    "/api/v1/rebalancing/composite-signal",
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code == 200
            data = resp.json()
            assert data["enabled"] is True
            assert data["triggered"] is True
            assert data["reason"] is not None
        finally:
            from app.api.deps import get_current_user
            from app.database import get_db

            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)

    def test_has_active_alert_false_when_no_active_rebalancing_alert(self, override_settings):
        """활성 리밸런싱 알림이 없으면 enabled 여부와 무관하게 has_active_alert=False."""
        user = _make_user()
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=SimpleNamespace(composite_signal_alerts_enabled=False))

        app = _setup_app(user, db)
        try:
            with (
                patch(
                    "app.api.v1.rebalancing.fetch_market_and_risk_signal",
                    new_callable=AsyncMock,
                ),
                patch(
                    "app.api.v1.rebalancing.get_redis",
                    new_callable=AsyncMock,
                    return_value=AsyncMock(),
                ),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.get(
                    "/api/v1/rebalancing/composite-signal",
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code == 200
            assert resp.json()["has_active_alert"] is False
        finally:
            from app.api.deps import get_current_user
            from app.database import get_db

            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)

    def test_has_active_alert_true_when_active_rebalancing_alert_exists(self, override_settings):
        """활성 리밸런싱 알림이 1개 이상 있으면 has_active_alert=True."""
        user = _make_user()
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=SimpleNamespace(composite_signal_alerts_enabled=True))
        execute_result = MagicMock()
        execute_result.all.return_value = [(uuid.uuid4(), 5.0)]
        db.execute = AsyncMock(return_value=execute_result)

        app = _setup_app(user, db)
        try:
            with (
                patch(
                    "app.api.v1.rebalancing.fetch_market_and_risk_signal",
                    new_callable=AsyncMock,
                    return_value=("GREEN", {"data_available": True}),
                ),
                patch(
                    "app.api.v1.rebalancing.get_redis",
                    new_callable=AsyncMock,
                    return_value=AsyncMock(),
                ),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.get(
                    "/api/v1/rebalancing/composite-signal",
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code == 200
            assert resp.json()["has_active_alert"] is True
        finally:
            from app.api.deps import get_current_user
            from app.database import get_db

            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)


class TestBrokerBalance:
    def test_returns_401_without_auth(self, override_settings):
        from app.api.deps import get_current_user
        from app.main import app

        app.dependency_overrides.pop(get_current_user, None)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get(f"/api/v1/rebalancing/broker-balance/{uuid.uuid4()}")
        assert resp.status_code == 401

    def test_returns_404_for_nonexistent_account(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=None)

        app = _setup_app(user, db)
        try:
            with (
                patch(
                    "app.api.v1.rebalancing.get_redis",
                    new_callable=AsyncMock,
                    return_value=AsyncMock(get=AsyncMock(return_value=None)),
                ),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.get(
                    f"/api/v1/rebalancing/broker-balance/{uuid.uuid4()}",
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code in (404, 422, 400)
        finally:
            from app.api.deps import get_current_user
            from app.database import get_db

            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)

    def test_returns_400_on_provider_api_error(self, override_settings):
        """KIS API 오류(ProviderApiError)는 provider 레이어에서 변환되어 전역 핸들러가 처리한다."""
        from types import SimpleNamespace

        from app.exceptions import ProviderApiError

        user = _make_user()
        db = _make_mock_db()
        account = SimpleNamespace(
            id=uuid.uuid4(),
            user_id=user.id,
            name="테스트 KIS",
            asset_type="STOCK_KIS",
            is_mock_mode=False,
            kis_account_no="12345678-01",
            kis_app_key="encrypted_key",
            kis_app_secret="encrypted_secret",
        )
        db.scalar = AsyncMock(return_value=account)

        app = _setup_app(user, db)
        try:
            with (
                patch(
                    "app.api.v1.rebalancing.get_redis",
                    new_callable=AsyncMock,
                    return_value=AsyncMock(get=AsyncMock(return_value=None)),
                ),
                patch(
                    "app.api.v1.rebalancing._fetch_broker_balance",
                    new_callable=AsyncMock,
                    side_effect=ProviderApiError("KIS 계좌 조회 실패: 호출 후처리(MCI전송) 오류 입니다. (rt_cd=1)."),
                ),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.get(
                    f"/api/v1/rebalancing/broker-balance/{account.id}",
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code == 400
            assert "KIS 계좌 조회 실패" in resp.json()["detail"]
        finally:
            from app.api.deps import get_current_user
            from app.database import get_db

            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)

    def test_returns_400_when_kiwoom_account_no_missing(self, override_settings):
        """kiwoom_account_no가 없으면 400을 반환한다 (nullable 계좌번호 가드)."""
        user = _make_user()
        db = _make_mock_db()
        account = SimpleNamespace(
            id=uuid.uuid4(),
            user_id=user.id,
            name="테스트 키움",
            asset_type="STOCK_KIWOOM",
            is_mock_mode=False,
            kiwoom_app_key="encrypted_key",
            kiwoom_app_secret="encrypted_secret",
            kiwoom_account_no=None,
        )
        db.scalar = AsyncMock(return_value=account)

        app = _setup_app(user, db)
        try:
            with (
                patch(
                    "app.api.v1.rebalancing.get_redis",
                    new_callable=AsyncMock,
                    return_value=AsyncMock(get=AsyncMock(return_value=None)),
                ),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.get(
                    f"/api/v1/rebalancing/broker-balance/{account.id}",
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code == 400
            assert "키움 계좌번호" in resp.json()["detail"]
        finally:
            from app.api.deps import get_current_user
            from app.database import get_db

            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)


class TestCollectDividendMap:
    """_collect_dividend_map이 fetch_ticker_dividend_info(캐시된 멀티소스 폴백)에
    올바르게 위임하는지 검증 — Naver/Yahoo 직접 호출 시절의 회귀 방지용."""

    @staticmethod
    def _make_portfolio(items):
        return SimpleNamespace(items=items)

    async def test_skips_cash_and_property_and_existing_tickers(self):
        from app.api.v1.rebalancing import _collect_dividend_map

        portfolio = self._make_portfolio(
            [
                {"ticker": "CASH", "market": "KRW"},
                {"ticker": "101", "market": "KR_PROPERTY"},
                {"ticker": "AAPL", "market": "NASDAQ"},  # 이미 base_dividend_map에 존재
            ]
        )
        base_map = {("AAPL", "NASDAQ"): {"ticker": "AAPL", "market": "NASDAQ", "dividend_yield": 0.5}}

        with (
            patch("app.api.v1.rebalancing.get_kis_user_credentials", new_callable=AsyncMock, return_value=None),
            patch("app.api.v1.rebalancing.fetch_dart_api_key", new_callable=AsyncMock, return_value=""),
            patch("app.api.v1.rebalancing.load_user_dividend_overrides", new_callable=AsyncMock, return_value={}),
            patch("app.api.v1.rebalancing.fetch_ticker_dividend_info", new_callable=AsyncMock) as mock_fetch,
        ):
            result = await _collect_dividend_map(uuid.uuid4(), MagicMock(), AsyncMock(), portfolio, base_map)

        mock_fetch.assert_not_called()
        assert result == base_map

    async def test_fetches_new_ticker_once_and_scales_yield_to_percent(self):
        from app.api.v1.rebalancing import _collect_dividend_map

        portfolio = self._make_portfolio([{"ticker": "SPY", "market": "NYSE"}])
        kis_creds = {"app_key": "x"}
        dart_key = "dart-key"
        overrides = {("SPY", "NYSE"): [3, 6, 9, 12]}

        with (
            patch(
                "app.api.v1.rebalancing.get_kis_user_credentials",
                new_callable=AsyncMock,
                return_value=kis_creds,
            ),
            patch("app.api.v1.rebalancing.fetch_dart_api_key", new_callable=AsyncMock, return_value=dart_key),
            patch(
                "app.api.v1.rebalancing.load_user_dividend_overrides",
                new_callable=AsyncMock,
                return_value=overrides,
            ),
            patch(
                "app.api.v1.rebalancing.fetch_ticker_dividend_info",
                new_callable=AsyncMock,
                return_value=(0.015, 3.5, [3, 6, 9, 12], "2026-03-15"),
            ) as mock_fetch,
        ):
            redis = AsyncMock()
            result = await _collect_dividend_map(uuid.uuid4(), MagicMock(), redis, portfolio, {})

        mock_fetch.assert_called_once()
        call_args = mock_fetch.call_args.args
        assert call_args[0] == "SPY"
        assert call_args[1] == "NYSE"
        assert call_args[2] is redis
        assert call_args[4] == kis_creds
        assert call_args[5] == dart_key
        assert call_args[6] == overrides
        assert result[("SPY", "NYSE")]["dividend_yield"] == 1.5
