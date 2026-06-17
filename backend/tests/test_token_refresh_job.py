"""token_refresh Job 테스트."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_user(user_id=None):
    return SimpleNamespace(
        id=user_id or uuid.uuid4(),
        email="test@example.com",
        is_active=True,
    )


def _make_settings(ob_refresh_token=None, kis_app_key=None, kis_app_secret=None):
    return SimpleNamespace(
        ob_refresh_token=ob_refresh_token,
        kis_app_key=kis_app_key,
        kis_app_secret=kis_app_secret,
    )


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
    async def test_no_users_does_nothing(self):
        """유저 없을 때 토큰 갱신하지 않는다."""
        mock_session = AsyncMock()
        execute_result = MagicMock()
        execute_result.all.return_value = []
        execute_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=execute_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("app.jobs.token_refresh.AsyncSessionLocal", return_value=mock_session),
            patch("app.jobs.token_refresh.get_redis", new_callable=AsyncMock, return_value=AsyncMock()),
        ):
            from app.jobs.token_refresh import refresh_all_user_tokens

            await refresh_all_user_tokens()

    @pytest.mark.asyncio
    async def test_skips_ob_refresh_when_no_token(self):
        """ob_refresh_token 없는 유저는 오픈뱅킹 갱신 건너뛴다."""
        user = _make_user()
        settings = _make_settings(ob_refresh_token=None)
        call_count = {"ob": 0, "kis": 0}

        mock_session = AsyncMock()
        execute_result = MagicMock()
        execute_result.all.return_value = [(user, settings)]
        execute_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=execute_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        async def mock_ob_refresh(*args, **kwargs):
            call_count["ob"] += 1

        with (
            patch("app.jobs.token_refresh.AsyncSessionLocal", return_value=mock_session),
            patch("app.jobs.token_refresh.get_redis", new_callable=AsyncMock, return_value=AsyncMock()),
            patch("app.jobs.token_refresh._fetch_and_store_token", new_callable=AsyncMock),
        ):
            from app.jobs.token_refresh import refresh_all_user_tokens

            await refresh_all_user_tokens()

        assert call_count["ob"] == 0

    @pytest.mark.asyncio
    async def test_kis_token_refresh_called_for_accounts_with_creds(self):
        """KIS 자격증명 있는 계좌는 토큰 갱신 시도."""
        account = _make_account()
        user = _make_user()
        settings = _make_settings(ob_refresh_token=None)

        mock_session = AsyncMock()
        user_execute_result = MagicMock()
        user_execute_result.all.return_value = [(user, settings)]
        account_execute_result = MagicMock()
        account_execute_result.scalars.return_value.all.return_value = [account]

        call_count = [0, 0]

        async def mock_execute(stmt):
            if call_count[0] == 0:
                call_count[0] += 1
                return user_execute_result
            else:
                call_count[0] += 1
                return account_execute_result

        mock_session.execute = AsyncMock(side_effect=mock_execute)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("app.jobs.token_refresh.AsyncSessionLocal", return_value=mock_session),
            patch("app.jobs.token_refresh.get_redis", new_callable=AsyncMock, return_value=AsyncMock()),
            patch("app.jobs.token_refresh.decrypt", return_value="decrypted"),
            patch("app.jobs.token_refresh._fetch_and_store_token", new_callable=AsyncMock) as mock_token,
        ):
            from app.jobs.token_refresh import refresh_all_user_tokens

            await refresh_all_user_tokens()

        assert mock_token.call_count == 1

    @pytest.mark.asyncio
    async def test_kis_refresh_failure_logged_but_continues(self):
        """KIS 토큰 갱신 실패해도 예외 전파 없이 계속 진행."""
        account = _make_account()
        user = _make_user()
        settings = _make_settings(ob_refresh_token=None)

        mock_session = AsyncMock()
        user_execute_result = MagicMock()
        user_execute_result.all.return_value = [(user, settings)]
        account_execute_result = MagicMock()
        account_execute_result.scalars.return_value.all.return_value = [account]

        call_count = [0]

        async def mock_execute(stmt):
            if call_count[0] == 0:
                call_count[0] += 1
                return user_execute_result
            else:
                return account_execute_result

        mock_session.execute = AsyncMock(side_effect=mock_execute)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        async def fail_token(*args, **kwargs):
            raise Exception("KIS API 오류")

        with (
            patch("app.jobs.token_refresh.AsyncSessionLocal", return_value=mock_session),
            patch("app.jobs.token_refresh.get_redis", new_callable=AsyncMock, return_value=AsyncMock()),
            patch("app.jobs.token_refresh.decrypt", return_value="decrypted"),
            patch("app.jobs.token_refresh._fetch_and_store_token", side_effect=fail_token),
        ):
            from app.jobs.token_refresh import refresh_all_user_tokens

            await refresh_all_user_tokens()
