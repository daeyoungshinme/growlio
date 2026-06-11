"""DCA 자동매매 Job 테스트."""
import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_settings(user_id=None, enabled=True, day=1, amount=1_000_000):
    return SimpleNamespace(
        user_id=user_id or uuid.uuid4(),
        auto_dca_enabled=enabled,
        auto_dca_day=day,
        auto_dca_portfolio_id=uuid.uuid4(),
        auto_dca_account_id=uuid.uuid4(),
        auto_dca_amount=amount,
        auto_dca_last_executed_at=None,
    )


def _make_account(user_id=None):
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id or uuid.uuid4(),
        asset_type="STOCK_KIS",
        kis_app_key="encrypted_key",
        kis_app_secret="encrypted_secret",
        is_mock_mode=True,
        is_active=True,
    )


def _make_portfolio_item(ticker="005930", market="KOSPI", target_pct=100.0):
    return SimpleNamespace(
        ticker=ticker,
        market=market,
        target_pct=target_pct,
        name="삼성전자",
    )


class TestRunDcaAutoExecution:
    @pytest.mark.asyncio
    async def test_no_eligible_settings_does_nothing(self):
        """해당 날짜에 DCA 설정 없으면 매수하지 않는다."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()
        mock_redis.__aenter__ = AsyncMock(return_value=None)
        mock_redis.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        execute_result = MagicMock()
        execute_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=execute_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("app.jobs.dca_auto_buy.AsyncSessionLocal", return_value=mock_session),
            patch("app.jobs.dca_auto_buy.get_redis", new_callable=AsyncMock, return_value=mock_redis),
            patch("app.jobs.dca_auto_buy.redis_lock") as mock_lock,
        ):
            mock_lock.return_value.__aenter__ = AsyncMock(return_value=True)
            mock_lock.return_value.__aexit__ = AsyncMock(return_value=None)

            from app.jobs.dca_auto_buy import run_dca_auto_execution
            await run_dca_auto_execution()

    @pytest.mark.asyncio
    async def test_skips_when_lock_not_acquired(self):
        """분산 락 획득 실패 시 실행하지 않는다."""
        mock_redis = AsyncMock()

        with (
            patch("app.jobs.dca_auto_buy.get_redis", new_callable=AsyncMock, return_value=mock_redis),
            patch("app.jobs.dca_auto_buy.redis_lock") as mock_lock,
            patch("app.jobs.dca_auto_buy._run_dca_auto_execution", new_callable=AsyncMock) as mock_run,
        ):
            mock_lock.return_value.__aenter__ = AsyncMock(return_value=False)
            mock_lock.return_value.__aexit__ = AsyncMock(return_value=None)

            from app.jobs.dca_auto_buy import run_dca_auto_execution
            await run_dca_auto_execution()

        mock_run.assert_not_called()


class TestExecuteDcaForUser:
    @pytest.mark.asyncio
    async def test_returns_early_if_portfolio_not_found(self):
        """포트폴리오 없으면 매수 없이 종료."""
        settings = _make_settings()
        mock_db = AsyncMock()
        mock_db.scalar = AsyncMock(return_value=None)
        mock_redis = AsyncMock()

        with patch("app.jobs.dca_auto_buy.fetch_prices_batch", new_callable=AsyncMock):
            from app.jobs.dca_auto_buy import _execute_dca_for_user
            await _execute_dca_for_user(settings, mock_db, mock_redis)

    @pytest.mark.asyncio
    async def test_returns_early_if_account_not_found(self):
        """계좌 없으면 매수 없이 종료."""
        settings = _make_settings()

        portfolio = SimpleNamespace(
            id=settings.auto_dca_portfolio_id,
            items=[_make_portfolio_item()],
        )

        mock_db = AsyncMock()
        call_count = [0]

        async def mock_scalar(stmt):
            call_count[0] += 1
            if call_count[0] == 1:
                return portfolio
            return None

        mock_db.scalar = AsyncMock(side_effect=mock_scalar)
        mock_redis = AsyncMock()

        with patch("app.jobs.dca_auto_buy.fetch_prices_batch", new_callable=AsyncMock, return_value={}):
            from app.jobs.dca_auto_buy import _execute_dca_for_user
            await _execute_dca_for_user(settings, mock_db, mock_redis)
