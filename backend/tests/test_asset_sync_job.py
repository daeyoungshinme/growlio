"""asset_sync Job 테스트."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


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
            patch("app.services.accounts.sync_all_service.AsyncSessionLocal", return_value=mock_session),
            patch(
                "app.services.accounts.sync_all_service.get_cache_store",
                new_callable=AsyncMock,
                return_value=AsyncMock(),
            ),
            patch("app.services.accounts.sync_all_service.sync_account", new_callable=AsyncMock) as mock_sync,
        ):
            from app.jobs.asset_sync import run_daily_asset_sync

            await run_daily_asset_sync()

        mock_sync.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_calls_sync_for_each_account(self, make_account):
        """계좌가 있으면 각 계좌에 대해 sync_account 호출."""
        accounts = [make_account(), make_account()]
        mock_session = AsyncMock()
        execute_result = MagicMock()
        execute_result.scalars.return_value.all.return_value = accounts
        mock_session.execute = AsyncMock(return_value=execute_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("app.jobs.asset_sync.AsyncSessionLocal", return_value=mock_session),
            patch("app.services.accounts.sync_all_service.AsyncSessionLocal", return_value=mock_session),
            patch(
                "app.services.accounts.sync_all_service.get_cache_store",
                new_callable=AsyncMock,
                return_value=AsyncMock(),
            ),
            patch("app.services.accounts.sync_all_service.sync_account", new_callable=AsyncMock) as mock_sync,
        ):
            from app.jobs.asset_sync import run_daily_asset_sync

            await run_daily_asset_sync()

        assert mock_sync.call_count == 2

    @pytest.mark.asyncio
    async def test_sync_continues_when_one_account_fails(self, make_account):
        """한 계좌 실패해도 나머지 계좌는 계속 시도한다."""
        accounts = [make_account(name="계좌A"), make_account(name="계좌B")]
        mock_session = AsyncMock()
        execute_result = MagicMock()
        execute_result.scalars.return_value.all.return_value = accounts
        mock_session.execute = AsyncMock(return_value=execute_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        call_count = 0

        async def mock_sync_side_effect(account, db, cache):
            nonlocal call_count
            call_count += 1
            if account.name == "계좌A":
                raise Exception("KIS 연결 실패")

        with (
            patch("app.jobs.asset_sync.AsyncSessionLocal", return_value=mock_session),
            patch("app.services.accounts.sync_all_service.AsyncSessionLocal", return_value=mock_session),
            patch(
                "app.services.accounts.sync_all_service.get_cache_store",
                new_callable=AsyncMock,
                return_value=AsyncMock(),
            ),
            patch("app.services.accounts.sync_all_service.sync_account", side_effect=mock_sync_side_effect),
        ):
            from app.jobs.asset_sync import run_daily_asset_sync

            await run_daily_asset_sync()

        assert call_count == 2


class TestRunIntradayAssetSync:
    @pytest.mark.asyncio
    async def test_intraday_only_syncs_stock_accounts(self, make_account):
        """intraday sync는 증권사 API 주식 계좌(KIS/키움/토스)만 동기화한다."""
        accounts = [make_account(data_source="KIS_API"), make_account(data_source="KIWOOM_API")]
        mock_session = AsyncMock()
        execute_result = MagicMock()
        execute_result.scalars.return_value.all.return_value = accounts
        mock_session.execute = AsyncMock(return_value=execute_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("app.jobs.asset_sync.AsyncSessionLocal", return_value=mock_session),
            patch("app.services.accounts.sync_all_service.AsyncSessionLocal", return_value=mock_session),
            patch(
                "app.services.accounts.sync_all_service.get_cache_store",
                new_callable=AsyncMock,
                return_value=AsyncMock(),
            ),
            patch("app.services.accounts.sync_all_service.sync_account", new_callable=AsyncMock) as mock_sync,
        ):
            from app.jobs.asset_sync import run_intraday_asset_sync

            await run_intraday_asset_sync()

        assert mock_sync.call_count == 2

    def test_intraday_sources_include_all_broker_sync_sources(self):
        """토스도 잔고 동기화 대상이다(주문 실행 대상만 KIS/키움). 15:30 스냅샷에서 빠지면
        18:00 전까지 토스 포지션이 오래된 값으로 남는다."""
        from app.constants import BROKER_API_DATA_SOURCES

        assert {"KIS_API", "KIWOOM_API", "TOSS_API"} == BROKER_API_DATA_SOURCES


class TestSyncAccountsLock:
    @pytest.mark.asyncio
    async def test_skips_account_whose_sync_lock_is_held(self, make_account):
        """단건 /sync가 잡은 계좌 락은 배치 동기화도 존중한다 — 병렬 delete→insert로 보유 종목이 중복되지 않게
        (plans/115 A1). 락이 잡힌 계좌는 실패가 아닌 skip으로 처리한다."""
        from app.core.cache_store import CacheStore
        from app.services.accounts.sync_all_service import sync_accounts
        from app.utils.cache_keys import sync_lock_key

        busy, free = make_account(name="진행중"), make_account(name="대기")
        cache = CacheStore()
        await cache.set(sync_lock_key(busy.id), "other-request", nx=True, ex=120)
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.merge = AsyncMock(side_effect=lambda a: a)

        with (
            patch("app.services.accounts.sync_all_service.AsyncSessionLocal", return_value=mock_session),
            patch("app.services.accounts.sync_all_service.get_cache_store", AsyncMock(return_value=cache)),
            patch("app.services.accounts.sync_all_service.sync_account", new_callable=AsyncMock) as mock_sync,
        ):
            failed = await sync_accounts([busy, free], "test")

        assert failed == []
        assert [c.args[0] for c in mock_sync.await_args_list] == [free]
        assert await cache.get(sync_lock_key(busy.id)) == "other-request"  # 남의 락은 풀지 않는다
        assert await cache.get(sync_lock_key(free.id)) is None  # 자기 락은 해제
