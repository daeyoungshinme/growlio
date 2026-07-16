"""백테스트 API 테스트 (GET/POST /api/v1/backtest/...)."""

from __future__ import annotations

import contextlib
import uuid
from datetime import UTC, datetime
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


_MOCK_BACKTEST_PORTFOLIO = {
    "id": str(uuid.uuid4()),
    "name": "테스트 포트폴리오",
    "holdings": [],
    "created_at": datetime.now(UTC).isoformat(),
    "updated_at": datetime.now(UTC).isoformat(),
}


def _make_backtest_result():
    from app.schemas.backtest import BacktestResult

    return BacktestResult(dates=["2020-01-01"], series=[], metrics=[])


class TestBacktestPortfolios:
    def test_returns_401_without_auth(self, override_settings):
        from app.api.deps import get_current_user
        from app.main import app

        app.dependency_overrides.pop(get_current_user, None)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/backtest/portfolios")
        assert resp.status_code == 401

    def test_list_portfolios_returns_200(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/backtest/portfolios")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_create_portfolio(self, override_settings):
        user = _make_user()
        db = _make_mock_db()

        portfolio_orm = SimpleNamespace(
            id=uuid.uuid4(),
            user_id=user.id,
            name="새 포트폴리오",
            holdings=[{"ticker": "005930", "market": "KOSPI", "weight": 100.0}],
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        async def mock_refresh(obj):
            for k, v in vars(portfolio_orm).items():
                if not k.startswith("_"):
                    with contextlib.suppress(Exception):
                        setattr(obj, k, v)

        db.refresh = AsyncMock(side_effect=mock_refresh)
        app = _setup_app(user, db)
        payload = {
            "name": "새 포트폴리오",
            "holdings": [{"ticker": "005930", "market": "KOSPI", "weight": 100.0}],
        }
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post("/api/v1/backtest/portfolios", json=payload)
        assert resp.status_code in (200, 201)

    def test_delete_portfolio_returns_404(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=None)
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.delete(f"/api/v1/backtest/portfolios/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestUpdateBacktestPortfolio:
    def test_update_portfolio_name_success(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        portfolio_orm = SimpleNamespace(
            id=uuid.uuid4(),
            user_id=user.id,
            name="원래 이름",
            holdings=[],
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db.scalar = AsyncMock(return_value=portfolio_orm)
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.put(
                f"/api/v1/backtest/portfolios/{portfolio_orm.id}",
                json={"name": "업데이트된 이름"},
            )
        assert resp.status_code == 200

    def test_update_returns_404_when_not_found(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=None)
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.put(
                f"/api/v1/backtest/portfolios/{uuid.uuid4()}",
                json={"name": "새 이름"},
            )
        assert resp.status_code == 404

    def test_delete_portfolio_success(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        portfolio_orm = SimpleNamespace(
            id=uuid.uuid4(),
            user_id=user.id,
            name="삭제 포트폴리오",
            holdings=[],
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db.scalar = AsyncMock(return_value=portfolio_orm)
        db.delete = AsyncMock()
        app = _setup_app(user, db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.delete(f"/api/v1/backtest/portfolios/{portfolio_orm.id}")
        assert resp.status_code == 204


class TestRunCorrelation:
    def test_run_correlation_returns_200(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        payload = {
            "portfolio_ids": [str(uuid.uuid4())],
            "start_date": "2020-01-01",
            "end_date": "2023-12-31",
        }
        from app.schemas.backtest import CorrelationResult

        mock_result = CorrelationResult(labels=["AAPL"], matrix=[[1.0]])
        with (
            patch(
                "app.api.v1.backtest.compute_correlation",
                AsyncMock(return_value=mock_result),
            ),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.post("/api/v1/backtest/correlation", json=payload)
        assert resp.status_code == 200

    def test_run_correlation_returns_400_without_portfolios(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        payload = {
            "portfolio_ids": [],
            "start_date": "2020-01-01",
            "end_date": "2023-12-31",
        }
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post("/api/v1/backtest/correlation", json=payload)
        assert resp.status_code in (400, 422)


class TestRunBacktest:
    def test_run_backtest_returns_200(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        payload = {
            "portfolio_ids": [str(uuid.uuid4())],
            "start_date": "2020-01-01",
            "end_date": "2023-12-31",
            "include_spy": True,
            "include_real_portfolio": True,
            "reinvest_dividends": True,
        }
        with (
            patch(
                "app.api.v1.backtest.run_backtest",
                AsyncMock(return_value=_make_backtest_result()),
            ),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.post("/api/v1/backtest/run", json=payload)
        assert resp.status_code == 200
