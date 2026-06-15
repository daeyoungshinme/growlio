"""공통 테스트 픽스처."""

import uuid
from datetime import date, datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession


# ── 테스트용 설정 오버라이드 ─────────────────────────────────

@pytest.fixture(autouse=True)
def override_settings(monkeypatch):
    """테스트 중 실제 환경 변수 없이 동작하도록 설정 오버라이드."""
    monkeypatch.setenv("KIS_CRED_ENCRYPTION_KEY", "a" * 64)
    monkeypatch.setenv("APP_SECRET_KEY", "test-secret-key-for-pytest-at-least-32")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/test")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("DART_API_KEY", "test-dart-key")
    from app.config import settings as _settings
    monkeypatch.setattr(_settings, "app_env", "test")


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """slowapi 인메모리 레이트 리미터 카운터를 각 테스트 전에 초기화한다.

    레이트 리미터가 모듈 싱글톤으로 작동하므로 전체 스위트 실행 시
    카운터가 누적되어 포트폴리오 요약 등 다수 호출 테스트가 오동작한다.
    """
    from app.limiter import limiter
    limiter._storage.reset()
    yield


# ── DB 세션 Mock ────────────────────────────────────────────

@pytest.fixture
def mock_db() -> AsyncMock:
    """AsyncSession mock."""
    session = AsyncMock(spec=AsyncSession)
    session.scalar = AsyncMock(return_value=None)

    # execute 결과: scalars().all() 체이닝 지원
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = []
    execute_result.scalar_one.return_value = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    execute_result.all.return_value = []
    session.execute = AsyncMock(return_value=execute_result)

    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


# ── Redis Mock ──────────────────────────────────────────────

@pytest.fixture
def mock_redis() -> AsyncMock:
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()
    redis.setex = AsyncMock()
    return redis


# ── 모델 팩토리 ─────────────────────────────────────────────

@pytest.fixture
def make_user_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def make_account(make_user_id):
    """AssetAccount 유사 객체 (DB 불필요)."""
    from types import SimpleNamespace
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=make_user_id,
        name="테스트 계좌",
        asset_type="STOCK_KIS",
        data_source="KIS_API",
        is_active=True,
        is_mock_mode=True,
        kis_account_no="12345678-01",
        kis_app_key=None,
        kis_app_secret=None,
        ob_fintech_use_no=None,
        manual_amount=None,
        manual_positions=None,
        manual_currency="KRW",
        deposit_krw=None,
        deposit_usd=None,
    )


@pytest.fixture
def make_snapshot(make_user_id):
    """AssetSnapshot 유사 객체."""
    from types import SimpleNamespace
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=make_user_id,
        account_id=uuid.uuid4(),
        snapshot_date=date.today(),
        amount_krw=10_000_000.0,
        invested_amount=9_000_000.0,
        unrealized_pnl=1_000_000.0,
        positions=[],
        source="MANUAL",
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def make_user_settings(make_user_id):
    """UserSettings 유사 객체."""
    from types import SimpleNamespace
    return SimpleNamespace(
        user_id=make_user_id,
        kis_app_key=None,
        kis_app_secret=None,
        kis_account_no=None,
        kis_is_mock=True,
        dart_api_key=None,
        ob_access_token=None,
        ob_refresh_token=None,
        ob_token_expires_at=None,
        ob_user_seq_no=None,
        goal_amount=None,
        goal_annual_return_pct=None,
        annual_deposit_goal=None,
        monthly_deposit_amount=None,
        retirement_target_year=None,
        monthly_report_enabled=True,
    )


@pytest.fixture
def mock_request():
    """slowapi @limiter.limit() 테스트에서 필요한 최소 Starlette Request 객체."""
    from starlette.requests import Request
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/test",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("localhost", 8000),
    }
    return Request(scope=scope)


@pytest.fixture(autouse=True)
def _mock_redis_singleton():
    """Redis singleton을 AsyncMock으로 교체 — Docker 없이 모든 테스트 실행 가능."""
    import app.redis_client as _rc

    redis_mock = AsyncMock()
    redis_mock.ping = AsyncMock(return_value=True)
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.set = AsyncMock()
    redis_mock.setex = AsyncMock()
    redis_mock.delete = AsyncMock()
    redis_mock.exists = AsyncMock(return_value=0)
    redis_mock.expire = AsyncMock()

    old = _rc.redis_client
    _rc.redis_client = redis_mock
    yield redis_mock
    _rc.redis_client = old


@pytest.fixture
def mock_redis_for_app():
    """FastAPI app lifespan의 Redis 연결을 무력화하는 패치 컨텍스트."""
    from unittest.mock import AsyncMock, patch
    redis_mock = AsyncMock()
    redis_mock.ping = AsyncMock(return_value=True)
    return patch("app.redis_client.get_redis", return_value=redis_mock)
