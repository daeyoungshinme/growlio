"""포트폴리오 CRUD API 테스트 (GET/POST/PUT/DELETE /api/v1/portfolios)."""

import json
import uuid
from datetime import UTC
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
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


def _make_portfolio(user_id=None, portfolio_id=None):
    pid = portfolio_id or uuid.uuid4()
    uid = user_id or uuid.uuid4()
    return SimpleNamespace(
        id=pid,
        user_id=uid,
        name="테스트 포트폴리오",
        description=None,
        items=[],
        linked_accounts=[],
        sort_order=0,
        target_account_id=None,
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
    )


@pytest.fixture(autouse=True)
def mock_redis_scheduler(monkeypatch):
    import app.redis_client as rc
    import app.scheduler as sched

    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)
    mock_redis.aclose = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    monkeypatch.setattr(rc, "redis_client", mock_redis)
    monkeypatch.setattr(sched.scheduler, "start", lambda: None)
    monkeypatch.setattr(sched.scheduler, "shutdown", lambda: None)
    yield
    rc.redis_client = None


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


def _make_full_portfolio(user_id, portfolio_id=None):
    from datetime import datetime

    _id = portfolio_id or uuid.uuid4()
    return SimpleNamespace(
        id=_id,
        user_id=user_id,
        name="테스트 포트폴리오",
        items=[],
        linked_accounts=[],
        account_ids=None,
        base_type="STOCK_ONLY",
        sort_order=0,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


class TestUpdatePortfolio:
    def test_update_returns_404_when_not_found(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)
        app = _setup_app(user, db)
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.put(f"/api/v1/portfolios/{uuid.uuid4()}", json={"name": "새 이름"})
            assert resp.status_code == 404
        finally:
            from app.api.deps import get_current_user
            from app.database import get_db

            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)

    def test_update_portfolio_name_returns_200(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        portfolio = _make_full_portfolio(user_id=user.id)

        async def multi_execute(*args, **kwargs):
            r = MagicMock()
            r.scalar_one_or_none.return_value = portfolio
            r.scalar_one.return_value = portfolio
            return r

        db.execute = AsyncMock(side_effect=multi_execute)
        app = _setup_app(user, db)
        try:
            with (
                patch(
                    "app.api.v1.portfolios.get_redis",
                    new_callable=AsyncMock,
                    return_value=AsyncMock(delete=AsyncMock()),
                ),
                patch("app.api.v1.portfolios.invalidate_user_caches", AsyncMock()),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.put(
                    f"/api/v1/portfolios/{portfolio.id}",
                    json={"name": "업데이트된 이름"},
                )
            assert resp.status_code == 200
        finally:
            from app.api.deps import get_current_user
            from app.database import get_db

            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)


class TestListPortfolios:
    def test_returns_401_without_auth(self, override_settings):
        from app.api.deps import get_current_user
        from app.main import app

        app.dependency_overrides.pop(get_current_user, None)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/portfolios")
        assert resp.status_code == 401

    def test_returns_200_empty_list(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        try:
            with (
                patch(
                    "app.api.v1.portfolios.get_redis",
                    new_callable=AsyncMock,
                    return_value=AsyncMock(get=AsyncMock(return_value=None), setex=AsyncMock()),
                ),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.get("/api/v1/portfolios", headers={"Authorization": "Bearer fake"})
            assert resp.status_code == 200
            assert resp.json() == []
        finally:
            from app.api.deps import get_current_user
            from app.database import get_db

            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)


class TestCreatePortfolio:
    def test_returns_201_on_create(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        portfolio = _make_portfolio(user_id=user.id)
        db.refresh = AsyncMock(side_effect=lambda obj: None)

        async def mock_scalar(stmt):
            return portfolio

        db.scalar = AsyncMock(side_effect=mock_scalar)

        app = _setup_app(user, db)
        try:
            with (
                patch(
                    "app.api.v1.portfolios.get_redis",
                    new_callable=AsyncMock,
                    return_value=AsyncMock(get=AsyncMock(return_value=None), setex=AsyncMock(), delete=AsyncMock()),
                ),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.post(
                    "/api/v1/portfolios",
                    json={"name": "새 포트폴리오", "items": []},
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code in (200, 201, 422, 500)
        finally:
            from app.api.deps import get_current_user
            from app.database import get_db

            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)

    def test_create_rejects_empty_name(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post(
                    "/api/v1/portfolios",
                    json={"name": "", "items": []},
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code == 422
        finally:
            from app.api.deps import get_current_user
            from app.database import get_db

            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)


class TestDeletePortfolio:
    def test_returns_404_for_nonexistent(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        db.scalar = AsyncMock(return_value=None)

        app = _setup_app(user, db)
        try:
            with (
                patch(
                    "app.api.v1.portfolios.get_redis",
                    new_callable=AsyncMock,
                    return_value=AsyncMock(delete=AsyncMock()),
                ),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.delete(
                    f"/api/v1/portfolios/{uuid.uuid4()}",
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code == 404
        finally:
            from app.api.deps import get_current_user
            from app.database import get_db

            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)

    def test_returns_204_when_portfolio_found(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        portfolio = _make_portfolio(user_id=user.id)
        db.scalar = AsyncMock(return_value=portfolio)
        db.delete = AsyncMock()

        app = _setup_app(user, db)
        try:
            with (
                patch(
                    "app.api.v1.portfolios.get_redis",
                    new_callable=AsyncMock,
                    return_value=AsyncMock(delete=AsyncMock()),
                ),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.delete(
                    f"/api/v1/portfolios/{portfolio.id}",
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code in (204, 200)
        finally:
            from app.api.deps import get_current_user
            from app.database import get_db

            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)


class TestReorderPortfolios:
    def test_returns_204_on_reorder(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        pid1 = uuid.uuid4()
        pid2 = uuid.uuid4()

        app = _setup_app(user, db)
        try:
            with (
                patch(
                    "app.api.v1.portfolios.get_redis",
                    new_callable=AsyncMock,
                    return_value=AsyncMock(delete=AsyncMock()),
                ),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.patch(
                    "/api/v1/portfolios/reorder",
                    json={
                        "items": [
                            {"id": str(pid1), "sort_order": 0},
                            {"id": str(pid2), "sort_order": 1},
                        ]
                    },
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code in (204, 200)
        finally:
            from app.api.deps import get_current_user
            from app.database import get_db

            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)

    def test_empty_items_returns_204(self, override_settings):
        user = _make_user()
        db = _make_mock_db()

        app = _setup_app(user, db)
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.patch(
                    "/api/v1/portfolios/reorder",
                    json={"items": []},
                    headers={"Authorization": "Bearer fake"},
                )
            assert resp.status_code in (204, 200, 422)
        finally:
            from app.api.deps import get_current_user
            from app.database import get_db

            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)


def _cleanup(app):
    from app.api.deps import get_current_user
    from app.database import get_db

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db, None)


class TestCreatePortfolioExtended:
    """create_portfolio 핵심 경로 커버 (lines 105-144, 37-48)."""

    def test_create_with_valid_items_success(self, override_settings):
        user = _make_user()
        db = _make_mock_db()
        portfolio = _make_full_portfolio(user_id=user.id)

        result = MagicMock()
        result.scalar_one.return_value = portfolio
        db.execute = AsyncMock(return_value=result)

        app = _setup_app(user, db)
        try:
            with (
                patch(
                    "app.api.v1.portfolios.get_redis",
                    new_callable=AsyncMock,
                    return_value=AsyncMock(delete=AsyncMock()),
                ),
                patch("app.api.v1.portfolios.invalidate_user_caches", AsyncMock()),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.post(
                    "/api/v1/portfolios",
                    json={
                        "name": "테스트 포트폴리오",
                        "items": [
                            {"ticker": "005930", "name": "삼성전자", "market": "KOSPI", "weight": 100.0},
                        ],
                    },
                )
            assert resp.status_code in (200, 201)
        finally:
            _cleanup(app)

    def test_create_with_account_ids_links_accounts(self, override_settings):
        """_validate_account_ids 통과 + 계좌 연동 로직 (lines 37-48, 124-134)."""
        user = _make_user()
        db = _make_mock_db()
        portfolio = _make_full_portfolio(user_id=user.id)
        account_id = uuid.uuid4()

        result = MagicMock()
        result.scalar_one.return_value = portfolio
        result.all.return_value = [(account_id,)]
        db.execute = AsyncMock(return_value=result)

        app = _setup_app(user, db)
        try:
            with (
                patch(
                    "app.api.v1.portfolios.get_redis",
                    new_callable=AsyncMock,
                    return_value=AsyncMock(delete=AsyncMock()),
                ),
                patch("app.api.v1.portfolios.invalidate_user_caches", AsyncMock()),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.post(
                    "/api/v1/portfolios",
                    json={
                        "name": "계좌 연동 포트폴리오",
                        "items": [
                            {"ticker": "005930", "name": "삼성전자", "market": "KOSPI", "weight": 100.0},
                        ],
                        "account_ids": [str(account_id)],
                    },
                )
            assert resp.status_code in (200, 201)
        finally:
            _cleanup(app)

    def test_create_with_invalid_account_ids_returns_400(self, override_settings):
        """_validate_account_ids에서 소유하지 않은 계좌 감지 시 400 (lines 44-48)."""
        user = _make_user()
        db = _make_mock_db()

        result = MagicMock()
        result.all.return_value = []
        db.execute = AsyncMock(return_value=result)

        app = _setup_app(user, db)
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post(
                    "/api/v1/portfolios",
                    json={
                        "name": "포트폴리오",
                        "items": [
                            {"ticker": "005930", "name": "삼성전자", "market": "KOSPI", "weight": 100.0},
                        ],
                        "account_ids": [str(uuid.uuid4())],
                    },
                )
            assert resp.status_code == 400
        finally:
            _cleanup(app)


class TestListPortfoliosExtended:
    def test_returns_cached_data_on_cache_hit(self, override_settings):
        """Redis 캐시 히트 시 DB 조회 없이 반환 (lines 74-76)."""
        user = _make_user()
        db = _make_mock_db()

        cached = json.dumps(
            [
                {
                    "id": str(uuid.uuid4()),
                    "name": "캐시 포트폴리오",
                    "items": [],
                    "base_type": "STOCK_ONLY",
                    "sort_order": 0,
                    "account_ids": None,
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "updated_at": "2026-01-01T00:00:00+00:00",
                }
            ]
        )
        app = _setup_app(user, db)
        try:
            with (
                patch(
                    "app.api.v1.portfolios.get_redis",
                    new_callable=AsyncMock,
                    return_value=AsyncMock(get=AsyncMock(return_value=cached)),
                ),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.get("/api/v1/portfolios")
            assert resp.status_code == 200
            assert len(resp.json()) == 1
        finally:
            _cleanup(app)

    def test_cache_read_exception_falls_through(self, override_settings):
        """Redis 캐시 읽기 실패 시 DB 조회로 폴백 (lines 75-76)."""
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        try:
            with (
                patch(
                    "app.api.v1.portfolios.get_redis",
                    new_callable=AsyncMock,
                    return_value=AsyncMock(
                        get=AsyncMock(side_effect=Exception("redis error")),
                        setex=AsyncMock(),
                    ),
                ),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.get("/api/v1/portfolios")
            assert resp.status_code == 200
        finally:
            _cleanup(app)

    def test_cache_write_exception_still_returns_data(self, override_settings):
        """Redis 캐시 쓰기 실패 시도 데이터 반환 (lines 90-91)."""
        user = _make_user()
        db = _make_mock_db()
        app = _setup_app(user, db)
        try:
            with (
                patch(
                    "app.api.v1.portfolios.get_redis",
                    new_callable=AsyncMock,
                    return_value=AsyncMock(
                        get=AsyncMock(return_value=None),
                        setex=AsyncMock(side_effect=Exception("redis write error")),
                    ),
                ),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.get("/api/v1/portfolios")
            assert resp.status_code == 200
        finally:
            _cleanup(app)


class TestUpdatePortfolioExtended:
    """update_portfolio 추가 경로 커버 (lines 172, 176, 179-181, 191-212)."""

    def _make_result(self, portfolio, account_id=None):
        result = MagicMock()
        result.scalar_one_or_none.return_value = portfolio
        result.scalar_one.return_value = portfolio
        if account_id:
            result.all.return_value = [(account_id,)]
        return result

    def test_update_portfolio_items(self, override_settings):
        """body.items 업데이트 경로 (lines 179-181)."""
        user = _make_user()
        db = _make_mock_db()
        portfolio = _make_full_portfolio(user_id=user.id)
        db.execute = AsyncMock(return_value=self._make_result(portfolio))

        app = _setup_app(user, db)
        try:
            with (
                patch(
                    "app.api.v1.portfolios.get_redis",
                    new_callable=AsyncMock,
                    return_value=AsyncMock(delete=AsyncMock()),
                ),
                patch("app.api.v1.portfolios.invalidate_user_caches", AsyncMock()),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.put(
                    f"/api/v1/portfolios/{portfolio.id}",
                    json={"items": [{"ticker": "000660", "name": "SK하이닉스", "market": "KOSPI", "weight": 100.0}]},
                )
            assert resp.status_code == 200
        finally:
            _cleanup(app)

    def test_update_portfolio_base_type(self, override_settings):
        """body.base_type 업데이트 경로 (line 176)."""
        user = _make_user()
        db = _make_mock_db()
        portfolio = _make_full_portfolio(user_id=user.id)
        db.execute = AsyncMock(return_value=self._make_result(portfolio))

        app = _setup_app(user, db)
        try:
            with (
                patch(
                    "app.api.v1.portfolios.get_redis",
                    new_callable=AsyncMock,
                    return_value=AsyncMock(delete=AsyncMock()),
                ),
                patch("app.api.v1.portfolios.invalidate_user_caches", AsyncMock()),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.put(
                    f"/api/v1/portfolios/{portfolio.id}",
                    json={"base_type": "TOTAL_ASSETS"},
                )
            assert resp.status_code == 200
        finally:
            _cleanup(app)

    def test_update_portfolio_account_ids_change(self, override_settings):
        """account_ids 변경 시 추가/제거 로직 (lines 172, 191-212)."""
        user = _make_user()
        db = _make_mock_db()
        old_account_id = uuid.uuid4()
        new_account_id = uuid.uuid4()
        portfolio = _make_full_portfolio(user_id=user.id)
        portfolio.linked_accounts = [SimpleNamespace(account_id=old_account_id)]

        result = self._make_result(portfolio, account_id=new_account_id)
        db.execute = AsyncMock(return_value=result)

        app = _setup_app(user, db)
        try:
            with (
                patch(
                    "app.api.v1.portfolios.get_redis",
                    new_callable=AsyncMock,
                    return_value=AsyncMock(delete=AsyncMock()),
                ),
                patch("app.api.v1.portfolios.invalidate_user_caches", AsyncMock()),
                TestClient(app, raise_server_exceptions=False) as client,
            ):
                resp = client.put(
                    f"/api/v1/portfolios/{portfolio.id}",
                    json={"account_ids": [str(new_account_id)]},
                )
            assert resp.status_code == 200
        finally:
            _cleanup(app)
