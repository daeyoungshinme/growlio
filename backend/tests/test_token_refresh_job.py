"""token_refresh Job 테스트."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_account(account_id=None, user_id=None, kis_app_key="encrypted_key"):
    return SimpleNamespace(
        id=account_id or uuid.uuid4(),
        user_id=user_id or uuid.uuid4(),
        kis_app_key=kis_app_key,
        kis_app_secret="encrypted_secret",
        is_mock_mode=True,
        is_active=True,
        data_source="KIS_API",
    )


class TestRefreshAllUserTokens:
    @pytest.mark.asyncio
    async def test_no_accounts_does_nothing(self):
        """계좌 없을 때 토큰 갱신하지 않는다."""
        mock_session = AsyncMock()
        execute_result = MagicMock()
        execute_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=execute_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("app.jobs.token_refresh.AsyncSessionLocal", return_value=mock_session),
            patch("app.jobs.token_refresh.get_cache_store", new_callable=AsyncMock, return_value=AsyncMock()),
        ):
            from app.jobs.token_refresh import refresh_all_user_tokens

            await refresh_all_user_tokens()

    @pytest.mark.asyncio
    async def test_kis_token_refresh_called_for_accounts_with_creds(self):
        """KIS 자격증명 있는 계좌는 토큰 갱신 시도."""
        account = _make_account()

        mock_session = AsyncMock()
        account_execute_result = MagicMock()
        account_execute_result.scalars.return_value.all.return_value = [account]
        mock_session.execute = AsyncMock(return_value=account_execute_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("app.jobs.token_refresh.AsyncSessionLocal", return_value=mock_session),
            patch("app.jobs.token_refresh.get_cache_store", new_callable=AsyncMock, return_value=AsyncMock()),
            patch("app.jobs.token_refresh.decrypt_kis_credentials", return_value=("decrypted", "decrypted")),
            patch("app.jobs.token_refresh._fetch_and_store_token", new_callable=AsyncMock) as mock_token,
        ):
            from app.jobs.token_refresh import refresh_all_user_tokens

            await refresh_all_user_tokens()

        assert mock_token.call_count == 1

    @pytest.mark.asyncio
    async def test_kis_refresh_failure_logged_but_continues(self):
        """KIS 토큰 갱신 실패해도 예외 전파 없이 계속 진행."""
        account = _make_account()

        mock_session = AsyncMock()
        account_execute_result = MagicMock()
        account_execute_result.scalars.return_value.all.return_value = [account]
        mock_session.execute = AsyncMock(return_value=account_execute_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        async def fail_token(*args, **kwargs):
            raise Exception("KIS API 오류")

        with (
            patch("app.jobs.token_refresh.AsyncSessionLocal", return_value=mock_session),
            patch("app.jobs.token_refresh.get_cache_store", new_callable=AsyncMock, return_value=AsyncMock()),
            patch("app.jobs.token_refresh.decrypt_kis_credentials", return_value=("decrypted", "decrypted")),
            patch("app.jobs.token_refresh._fetch_and_store_token", side_effect=fail_token),
        ):
            from app.jobs.token_refresh import refresh_all_user_tokens

            await refresh_all_user_tokens()  # 예외 전파 없어야 함
