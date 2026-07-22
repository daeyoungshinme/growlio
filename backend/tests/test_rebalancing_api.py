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
    from app.core.database import get_db
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
                    "app.api.v1.rebalancing.get_cache_store",
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
            from app.core.database import get_db

            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)

    def test_dividend_summary_scoped_to_same_accounts_as_overview(self, override_settings):
        """포트폴리오가 계좌 일부에만 연결된 경우, 배당 조회(get_ticker_dividend_summary)도
        overview(build_portfolio_overview)와 동일한 계좌 범위로 스코프되어야 한다.

        회귀 대상 버그: 예전에는 get_ticker_dividend_summary가 계좌 필터 없이(전체 계좌 기준) 호출되어,
        포트폴리오에 연결되지 않은 계좌에도 동일 종목(특히 해외 주식)을 보유한 경우 배당 총액과
        평가금액의 계좌 범위가 어긋나 "리밸런싱 후 배당" 금액이 왜곡됐다.
        """
        user = _make_user()
        db = _make_mock_db()

        scoped_account_id = uuid.uuid4()
        portfolio_id = uuid.uuid4()
        portfolio = SimpleNamespace(
            id=portfolio_id,
            name="해외주식 포트폴리오",
            base_type="STOCK_ONLY",
            account_ids=[str(scoped_account_id)],
            items=[{"ticker": "AAPL", "name": "Apple", "market": "NASDAQ", "weight": 100.0}],
        )
        db.scalar = AsyncMock(return_value=portfolio)

        overview = {
            "total_assets_krw": 1_000_000.0,
            "total_stock_krw": 1_000_000.0,
            "all_positions": [
                {
                    "ticker": "AAPL",
                    "market": "NASDAQ",
                    "name": "Apple",
                    "value_krw": 1_000_000.0,
                    "current_price": 200_000.0,
                    "qty": 5.0,
                }
            ],
        }

        app = _setup_app(user, db)
        try:
            with (
                patch(
                    "app.api.v1.rebalancing.get_cache_store",
                    new_callable=AsyncMock,
                    return_value=AsyncMock(get=AsyncMock(return_value=None)),
                ),
                patch(
                    "app.api.v1.rebalancing.build_portfolio_overview",
                    new_callable=AsyncMock,
                    return_value=overview,
                ),
                patch(
                    "app.api.v1.rebalancing.get_ticker_dividend_summary",
                    new_callable=AsyncMock,
                    return_value=[],
                ) as mock_dividend_summary,
                patch(
                    "app.api.v1.rebalancing.collect_dividend_map",
                    new_callable=AsyncMock,
                    return_value={},
                ),
                patch(
                    "app.api.v1.rebalancing.get_historical_returns",
                    new_callable=AsyncMock,
                    return_value={},
                ),
                patch(
                    "app.api.v1.rebalancing.enrich_overview_with_prices",
                    new_callable=AsyncMock,
                    return_value=overview,
                ),
                patch(
                    "app.api.v1.rebalancing.get_settings_row",
                    new_callable=AsyncMock,
                    return_value=None,
                ),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.get(
                    f"/api/v1/rebalancing/portfolios/{portfolio_id}/analyze",
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code == 200

            # build_portfolio_overview에 전달된 것과 동일한 account_ids로 배당 조회도 스코프돼야 한다.
            call_kwargs = mock_dividend_summary.call_args.kwargs
            assert call_kwargs.get("account_ids") == [scoped_account_id]
        finally:
            from app.api.deps import get_current_user
            from app.core.database import get_db

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
            from app.core.database import get_db

            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)


class TestGoalRecommendationEndpoint:
    def test_base_krw_excludes_real_estate(self, override_settings):
        """부동산은 목표 역산 추천 MVO 엔진의 후보가 아니고 성장도 모델링되지 않으므로,
        필요 수익률 역산 원금(base_krw)에서 제외되어야 한다."""
        user = _make_user()
        db = _make_mock_db()
        settings_row = SimpleNamespace(goal_amount=100_000_000.0)
        db.scalar = AsyncMock(return_value=settings_row)

        overview = {
            "total_assets_krw": 90_000_000.0,
            "asset_type_allocation": [
                {"type": "STOCK_KIS", "amount_krw": 50_000_000.0},
                {"type": "REAL_ESTATE", "amount_krw": 40_000_000.0},
            ],
        }

        app = _setup_app(user, db)
        try:
            with (
                patch(
                    "app.api.v1.rebalancing.get_cache_store",
                    new_callable=AsyncMock,
                    return_value=AsyncMock(),
                ),
                patch(
                    "app.api.v1.rebalancing.build_portfolio_overview",
                    new_callable=AsyncMock,
                    return_value=overview,
                ),
                patch(
                    "app.api.v1.rebalancing.get_settings_row",
                    new_callable=AsyncMock,
                    return_value=settings_row,
                ),
                patch(
                    "app.api.v1.rebalancing.query_latest_position_map",
                    new_callable=AsyncMock,
                    return_value={},
                ),
                patch(
                    "app.api.v1.rebalancing.get_goal_recommendation",
                    new_callable=AsyncMock,
                    return_value={
                        "generated_at": "2024-01-01T00:00:00Z",
                        "is_configured": True,
                        "required_return_pct": 5.0,
                    },
                ) as mock_get_rec,
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.get(
                    "/api/v1/rebalancing/goal-recommendation",
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code == 200
            # 총자산 90M - 부동산 40M = 투자자산 50M이 필요수익률 역산 원금으로 전달되어야 함
            call_args = mock_get_rec.call_args
            assert call_args.args[1] == 50_000_000.0
        finally:
            from app.api.deps import get_current_user
            from app.core.database import get_db

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
            from app.core.database import get_db

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
                    "app.api.v1.rebalancing.get_cache_store",
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
            from app.core.database import get_db

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
                    "app.api.v1.rebalancing.get_cache_store",
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
            from app.core.database import get_db

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
                    "app.api.v1.rebalancing.get_cache_store",
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
            from app.core.database import get_db

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
                    "app.api.v1.rebalancing.get_cache_store",
                    new_callable=AsyncMock,
                    return_value=AsyncMock(get=AsyncMock(return_value=None)),
                ),
                patch(
                    "app.api.v1.rebalancing.fetch_broker_balance",
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
            from app.core.database import get_db

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
                    "app.api.v1.rebalancing.get_cache_store",
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
            from app.core.database import get_db

            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)


class TestCollectDividendMap:
    """collect_dividend_map이 fetch_ticker_dividend_info(캐시된 멀티소스 폴백)에
    올바르게 위임하는지 검증 — Naver/Yahoo 직접 호출 시절의 회귀 방지용."""

    @staticmethod
    def _make_portfolio(items):
        return SimpleNamespace(items=items)

    async def test_skips_cash_and_property_and_existing_tickers(self):
        from app.services.rebalancing.overview_enrichment import collect_dividend_map

        portfolio = self._make_portfolio(
            [
                {"ticker": "CASH", "market": "KRW"},
                {"ticker": "101", "market": "KR_PROPERTY"},
                {"ticker": "AAPL", "market": "NASDAQ"},  # 이미 base_dividend_map에 존재
            ]
        )
        base_map = {("AAPL", "NASDAQ"): {"ticker": "AAPL", "market": "NASDAQ", "dividend_yield": 0.5}}

        with (
            patch(
                "app.services.rebalancing.overview_enrichment.get_kis_user_credentials",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "app.services.rebalancing.overview_enrichment.fetch_dart_api_key",
                new_callable=AsyncMock,
                return_value="",
            ),
            patch(
                "app.services.rebalancing.overview_enrichment.load_user_dividend_overrides",
                new_callable=AsyncMock,
                return_value={},
            ),
            patch(
                "app.services.rebalancing.overview_enrichment.fetch_ticker_dividend_info", new_callable=AsyncMock
            ) as mock_fetch,
        ):
            result = await collect_dividend_map(uuid.uuid4(), MagicMock(), AsyncMock(), portfolio, base_map)

        mock_fetch.assert_not_called()
        assert result == base_map

    async def test_fetches_new_ticker_once_and_scales_yield_to_percent(self):
        from app.services.rebalancing.overview_enrichment import collect_dividend_map

        portfolio = self._make_portfolio([{"ticker": "SPY", "market": "NYSE"}])
        kis_creds = {"app_key": "x"}
        dart_key = "dart-key"
        overrides = {("SPY", "NYSE"): [3, 6, 9, 12]}

        with (
            patch(
                "app.services.rebalancing.overview_enrichment.get_kis_user_credentials",
                new_callable=AsyncMock,
                return_value=kis_creds,
            ),
            patch(
                "app.services.rebalancing.overview_enrichment.fetch_dart_api_key",
                new_callable=AsyncMock,
                return_value=dart_key,
            ),
            patch(
                "app.services.rebalancing.overview_enrichment.load_user_dividend_overrides",
                new_callable=AsyncMock,
                return_value=overrides,
            ),
            patch(
                "app.services.rebalancing.overview_enrichment.fetch_ticker_dividend_info",
                new_callable=AsyncMock,
                return_value=(0.015, 3.5, [3, 6, 9, 12], "2026-03-15"),
            ) as mock_fetch,
        ):
            cache = AsyncMock()
            result = await collect_dividend_map(uuid.uuid4(), MagicMock(), cache, portfolio, {})

        mock_fetch.assert_called_once()
        call_args = mock_fetch.call_args.args
        assert call_args[0] == "SPY"
        assert call_args[1] == "NYSE"
        assert call_args[2] is cache
        assert call_args[4] == kis_creds
        assert call_args[5] == dart_key
        assert call_args[6] == overrides
        assert result[("SPY", "NYSE")]["dividend_yield"] == 1.5
