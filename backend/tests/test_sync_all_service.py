"""sync_all_service 테스트 — "전체 갱신" 백그라운드 배치 서비스."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


class TestGetSyncAllStatus:
    @pytest.mark.asyncio
    async def test_returns_idle_when_no_record(self, make_user_id, mock_cache):
        from app.services.sync_all_service import get_sync_all_status

        mock_cache.get = AsyncMock(return_value=None)
        with patch("app.services.sync_all_service.get_cache_store", AsyncMock(return_value=mock_cache)):
            status = await get_sync_all_status(make_user_id)

        assert status == {"status": "idle"}

    @pytest.mark.asyncio
    async def test_returns_stored_status(self, make_user_id, mock_cache):
        import json

        from app.services.sync_all_service import get_sync_all_status

        stored = {"status": "running", "total": 3, "done": 1, "failed": 0}
        mock_cache.get = AsyncMock(return_value=json.dumps(stored))
        with patch("app.services.sync_all_service.get_cache_store", AsyncMock(return_value=mock_cache)):
            status = await get_sync_all_status(make_user_id)

        assert status == stored


class TestIsSyncAllRunning:
    @pytest.mark.asyncio
    async def test_false_when_no_lock(self, make_user_id, mock_cache):
        from app.services.sync_all_service import is_sync_all_running

        mock_cache.get = AsyncMock(return_value=None)
        with patch("app.services.sync_all_service.get_cache_store", AsyncMock(return_value=mock_cache)):
            assert await is_sync_all_running(make_user_id) is False

    @pytest.mark.asyncio
    async def test_true_when_lock_present(self, make_user_id, mock_cache):
        from app.services.sync_all_service import is_sync_all_running

        mock_cache.get = AsyncMock(return_value="some-lock-value")
        with patch("app.services.sync_all_service.get_cache_store", AsyncMock(return_value=mock_cache)):
            assert await is_sync_all_running(make_user_id) is True


class TestRunSyncAll:
    @pytest.mark.asyncio
    async def test_skips_when_lock_already_held(self, make_user_id, make_account, mock_cache):
        """이미 락이 걸려 있으면 _sync_accounts를 호출하지 않고 조용히 반환한다."""
        from app.services.sync_all_service import run_sync_all

        mock_cache.set = AsyncMock(return_value=None)  # SET NX 실패 → 락 획득 실패
        accounts = [make_account()]

        with (
            patch("app.services.sync_all_service.get_cache_store", AsyncMock(return_value=mock_cache)),
            patch("app.services.sync_all_service._sync_accounts", new_callable=AsyncMock) as mock_sync,
        ):
            await run_sync_all(make_user_id, accounts)

        mock_sync.assert_not_called()

    @pytest.mark.asyncio
    async def test_runs_batch_sync_and_marks_done(self, make_user_id, make_account, mock_cache):
        """락 획득에 성공하면 _sync_accounts를 실행하고 상태를 done으로 남긴다."""
        from app.services.sync_all_service import run_sync_all

        mock_cache.set = AsyncMock(return_value=True)  # SET NX 성공 → 락 획득
        mock_cache.get = AsyncMock(return_value="lock-value")  # inproc_lock 해제 시 자기 락인지 확인용
        accounts = [make_account(), make_account()]

        with (
            patch("app.services.sync_all_service.get_cache_store", AsyncMock(return_value=mock_cache)),
            patch("app.services.sync_all_service._sync_accounts", new_callable=AsyncMock, return_value=[]) as mock_sync,
        ):
            await run_sync_all(make_user_id, accounts)

        assert mock_sync.call_count == 1
        called_accounts = mock_sync.call_args.args[0]
        assert len(called_accounts) == 2
        # setex(status_key, ttl, json) 호출로 최소 1회 이상 상태 기록
        assert mock_cache.setex.await_count >= 1

    @pytest.mark.asyncio
    async def test_marks_error_status_when_sync_raises(self, make_user_id, make_account, mock_cache):
        """_sync_accounts가 예외를 던지면 status를 error로 남기고 예외를 흡수한다."""
        from app.services.sync_all_service import run_sync_all

        mock_cache.set = AsyncMock(return_value=True)
        mock_cache.get = AsyncMock(return_value="lock-value")
        accounts = [make_account()]

        with (
            patch("app.services.sync_all_service.get_cache_store", AsyncMock(return_value=mock_cache)),
            patch(
                "app.services.sync_all_service._sync_accounts",
                new_callable=AsyncMock,
                side_effect=Exception("boom"),
            ),
        ):
            await run_sync_all(make_user_id, accounts)  # 예외 전파 없이 종료되어야 함

        last_call = mock_cache.setex.await_args_list[-1]
        import json

        stored = json.loads(last_call.args[2])
        assert stored["status"] == "error"
