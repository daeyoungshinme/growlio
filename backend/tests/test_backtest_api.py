"""백테스트 API 테스트 (GET/POST /api/v1/backtest/...)."""

from __future__ import annotations

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
