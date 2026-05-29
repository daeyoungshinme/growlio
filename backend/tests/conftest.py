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


# ── DB 세션 Mock ────────────────────────────────────────────

@pytest.fixture
def mock_db() -> AsyncMock:
    """AsyncSession mock."""
    session = AsyncMock(spec=AsyncSession)
    session.scalar = AsyncMock(return_value=None)
    session.execute = AsyncMock()
    session.add = MagicMock()
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
    )
