"""asset_sync Job 테스트."""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_account(account_id=None, user_id=None, name="테스트 계좌", source="KIS_API"):
    return SimpleNamespace(
        id=account_id or uuid.uuid4(),
        user_id=user_id or uuid.uuid4(),
        name=name,
        asset_type="STOCK_KIS",
        data_source=source,
        is_active=True,
    )


class TestRunDailyAssetSync:
    @pytest.mark.asyncio
    async def test_sync_with_no_accounts(self):
        """활성 계좌 없을 때 아무것도 하지 않아야 한다."""
        mock_session = AsyncMock()
        execute_result = MagicMock()
        execute_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=execute_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("app.jobs.asset_sync.AsyncSessionLocal", return_value=mock_session),
            patch("app.jobs.asset_sync.get_redis", new_callable=AsyncMock, return_value=AsyncMock()),
            patch("app.jobs.asset_sync.sync_account", new_callable=AsyncMock) as mock_sync,
        ):
            from app.jobs.asset_sync import run_daily_asset_sync
            await run_daily_asset_sync()

        mock_sync.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_calls_sync_for_each_account(self):
        """계좌가 있으면 각 계좌에 대해 sync_account 호출."""
        accounts = [_make_account(), _make_account()]
        mock_session = AsyncMock()
        execute_result = MagicMock()
        execute_result.scalars.return_value.all.return_value = accounts
        mock_session.execute = AsyncMock(return_value=execute_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("app.jobs.asset_sync.AsyncSessionLocal", return_value=mock_session),
            patch("app.jobs.asset_sync.get_redis", new_callable=AsyncMock, return_value=AsyncMock()),
            patch("app.jobs.asset_sync.sync_account", new_callable=AsyncMock) as mock_sync,
        ):
            from app.jobs.asset_sync import run_daily_asset_sync
            await run_daily_asset_sync()

        assert mock_sync.call_count == 2

    @pytest.mark.asyncio
    async def test_sync_continues_when_one_account_fails(self):
        """한 계좌 실패해도 나머지 계좌는 계속 시도한다."""
        accounts = [_make_account(name="계좌A"), _make_account(name="계좌B")]
        mock_session = AsyncMock()
        execute_result = MagicMock()
        execute_result.scalars.return_value.all.return_value = accounts
        mock_session.execute = AsyncMock(return_value=execute_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        call_count = 0

        async def mock_sync_side_effect(account, db, redis):
            nonlocal call_count
            call_count += 1
            if account.name == "계좌A":
                raise Exception("KIS 연결 실패")

        with (
            patch("app.jobs.asset_sync.AsyncSessionLocal", return_value=mock_session),
            patch("app.jobs.asset_sync.get_redis", new_callable=AsyncMock, return_value=AsyncMock()),
            patch("app.jobs.asset_sync.sync_account", side_effect=mock_sync_side_effect),
        ):
            from app.jobs.asset_sync import run_daily_asset_sync
            await run_daily_asset_sync()

        assert call_count == 2


class TestRunIntradayAssetSync:
    @pytest.mark.asyncio
    async def test_intraday_only_syncs_stock_accounts(self):
        """intraday sync는 KIS/Kiwoom 주식 계좌만 동기화한다."""
        accounts = [_make_account(source="KIS_API"), _make_account(source="KIWOOM_API")]
        mock_session = AsyncMock()
        execute_result = MagicMock()
        execute_result.scalars.return_value.all.return_value = accounts
        mock_session.execute = AsyncMock(return_value=execute_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("app.jobs.asset_sync.AsyncSessionLocal", return_value=mock_session),
            patch("app.jobs.asset_sync.get_redis", new_callable=AsyncMock, return_value=AsyncMock()),
            patch("app.jobs.asset_sync.sync_account", new_callable=AsyncMock) as mock_sync,
        ):
            from app.jobs.asset_sync import run_intraday_asset_sync
            await run_intraday_asset_sync()

        assert mock_sync.call_count == 2
