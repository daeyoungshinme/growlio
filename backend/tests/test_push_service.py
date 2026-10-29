"""push_service.py 단위 테스트."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestDeliverPush:
    @pytest.mark.asyncio
    async def test_returns_false_when_no_token(self, override_settings):
        from app.services.notifications.push_service import PushResult, deliver_push

        result = await deliver_push(None, "제목", "내용")
        assert result is PushResult.SKIPPED

    @pytest.mark.asyncio
    async def test_returns_false_when_firebase_not_configured(self, override_settings):
        import app.services.notifications.push_service as ps
        from app.services.notifications import push_service

        original_initialized = ps._firebase_initialized
        original_app = ps._firebase_app

        try:
            ps._firebase_initialized = True
            ps._firebase_app = None

            result = await push_service.deliver_push("some-token", "제목", "내용")
            assert result is push_service.PushResult.SKIPPED
        finally:
            ps._firebase_initialized = original_initialized
            ps._firebase_app = original_app

    @pytest.mark.asyncio
    async def test_returns_false_when_empty_token(self, override_settings):
        from app.services.notifications.push_service import PushResult, deliver_push

        result = await deliver_push("", "제목", "내용")
        assert result is PushResult.SKIPPED

    @pytest.mark.asyncio
    async def test_returns_true_on_successful_send(self, override_settings):
        import app.services.notifications.push_service as ps

        original_initialized = ps._firebase_initialized
        original_app = ps._firebase_app

        try:
            mock_app = MagicMock()
            ps._firebase_initialized = True
            ps._firebase_app = mock_app

            with patch("app.services.notifications.push_service.asyncio.get_running_loop") as mock_loop:
                mock_loop.return_value.run_in_executor = AsyncMock(return_value="msg_id")

                with patch.dict(
                    "sys.modules",
                    {
                        "firebase_admin": MagicMock(),
                        "firebase_admin.messaging": MagicMock(),
                    },
                ):
                    result = await ps.deliver_push("valid-token", "제목", "내용")

            assert result is ps.PushResult.SENT
        finally:
            ps._firebase_initialized = original_initialized
            ps._firebase_app = original_app


class TestSendPushToUser:
    @pytest.mark.asyncio
    async def test_no_token_returns_false(self, override_settings):
        from app.services.notifications.push_service import send_push_to_user

        result = await send_push_to_user(uuid.uuid4(), "제목", "내용", None)
        assert result is False

    @pytest.mark.asyncio
    async def test_delegates_to_deliver_push(self, override_settings):
        from app.services.notifications.push_service import PushResult, send_push_to_user

        with patch(
            "app.services.notifications.push_service.deliver_push", new=AsyncMock(return_value=PushResult.FAILED)
        ):
            result = await send_push_to_user(uuid.uuid4(), "제목", "내용", "token")

        assert result is False

    @pytest.mark.asyncio
    async def test_success_logs_delivered(self, override_settings):
        from app.services.notifications.push_service import PushResult, send_push_to_user

        with patch("app.services.notifications.push_service.deliver_push", new=AsyncMock(return_value=PushResult.SENT)):
            result = await send_push_to_user(uuid.uuid4(), "제목", "내용", "token")

        assert result is True


class TestGetFirebaseApp:
    def test_firebase_init_failure_returns_none(self, override_settings):
        import app.core.config as cfg
        import app.services.notifications.push_service as ps

        original_initialized = ps._firebase_initialized
        original_app = ps._firebase_app
        original_creds = cfg.settings.firebase_credentials_json

        try:
            ps._firebase_initialized = False
            ps._firebase_app = None
            cfg.settings.firebase_credentials_json = '{"type": "service_account"}'

            with patch.dict(
                "sys.modules",
                {
                    "firebase_admin": MagicMock(
                        initialize_app=MagicMock(side_effect=Exception("init failed")),
                    ),
                    "firebase_admin.credentials": MagicMock(
                        Certificate=MagicMock(return_value=MagicMock()),
                    ),
                },
            ):
                result = ps._get_firebase_app()

            # After failed init, _firebase_initialized=True, app=None
            assert result is None
        finally:
            ps._firebase_initialized = original_initialized
            ps._firebase_app = original_app
            cfg.settings.firebase_credentials_json = original_creds


class TestSendPushException:
    @pytest.mark.asyncio
    async def test_exception_with_invalid_token_returns_false(self, override_settings):
        import app.services.notifications.push_service as ps

        original_initialized = ps._firebase_initialized
        original_app = ps._firebase_app

        try:
            mock_app = MagicMock()
            ps._firebase_initialized = True
            ps._firebase_app = mock_app

            with (
                patch.dict(
                    "sys.modules",
                    {
                        "firebase_admin.messaging": MagicMock(
                            Message=MagicMock(return_value=MagicMock()),
                            Notification=MagicMock(return_value=MagicMock()),
                            send=MagicMock(side_effect=Exception("registration-token-not-registered")),
                        ),
                        "firebase_admin": MagicMock(),
                    },
                ),
                patch("asyncio.get_running_loop") as mock_loop,
            ):
                mock_loop.return_value.run_in_executor = AsyncMock(
                    side_effect=Exception("registration-token-not-registered")
                )
                result = await ps.deliver_push("invalid-token", "제목", "내용")

            assert result is ps.PushResult.INVALID_TOKEN
        finally:
            ps._firebase_initialized = original_initialized
            ps._firebase_app = original_app

    @pytest.mark.asyncio
    async def test_exception_other_error_returns_false(self, override_settings):
        import app.services.notifications.push_service as ps

        original_initialized = ps._firebase_initialized
        original_app = ps._firebase_app

        try:
            mock_app = MagicMock()
            ps._firebase_initialized = True
            ps._firebase_app = mock_app

            with patch("asyncio.get_running_loop") as mock_loop:
                mock_loop.return_value.run_in_executor = AsyncMock(side_effect=Exception("some other error"))
                result = await ps.deliver_push("valid-token", "제목", "내용")

            assert result is ps.PushResult.FAILED
        finally:
            ps._firebase_initialized = original_initialized
            ps._firebase_app = original_app

    @pytest.mark.asyncio
    async def test_invalid_token_is_cleared(self, override_settings):
        # FCM이 폐기한 토큰은 지운다 — 남기면 5~10분 주기 잡마다 같은 토큰으로 계속 호출한다(plans/61 A4)
        from app.services.notifications.push_service import PushResult, send_push_to_user

        user_id = uuid.uuid4()
        clear = AsyncMock()
        with (
            patch(
                "app.services.notifications.push_service.deliver_push",
                new=AsyncMock(return_value=PushResult.INVALID_TOKEN),
            ),
            patch("app.services.notifications.push_service._clear_invalid_token", new=clear),
        ):
            result = await send_push_to_user(user_id, "제목", "내용", "dead-token")

        assert result is False
        clear.assert_awaited_once_with(user_id, "dead-token")

    @pytest.mark.asyncio
    async def test_other_failures_keep_token(self, override_settings):
        from app.services.notifications.push_service import PushResult, send_push_to_user

        clear = AsyncMock()
        with (
            patch(
                "app.services.notifications.push_service.deliver_push", new=AsyncMock(return_value=PushResult.FAILED)
            ),
            patch("app.services.notifications.push_service._clear_invalid_token", new=clear),
        ):
            await send_push_to_user(uuid.uuid4(), "제목", "내용", "token")

        clear.assert_not_awaited()


class TestDeliverPushClassifiesErrors:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("error", "expected"),
        [
            ("Requested entity was not found. (registration-token-not-registered)", "invalid_token"),
            ("invalid-registration-token", "invalid_token"),
            ("503 unavailable", "failed"),
        ],
    )
    async def test_classifies(self, override_settings, error, expected):
        import app.services.notifications.push_service as ps

        original_initialized, original_app = ps._firebase_initialized, ps._firebase_app
        try:
            ps._firebase_initialized = True
            ps._firebase_app = MagicMock()
            with (
                patch("app.services.notifications.push_service.asyncio.get_running_loop") as mock_loop,
                patch.dict("sys.modules", {"firebase_admin": MagicMock(), "firebase_admin.messaging": MagicMock()}),
            ):
                mock_loop.return_value.run_in_executor = AsyncMock(side_effect=Exception(error))
                result = await ps.deliver_push("token", "제목", "내용")
            assert result == expected
        finally:
            ps._firebase_initialized, ps._firebase_app = original_initialized, original_app
