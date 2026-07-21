"""키움 클라이언트 테스트 — rate limiter 배선 확인."""

from unittest.mock import AsyncMock, patch

import pytest

from app.kiwoom.client import kiwoom_request


@pytest.fixture
def mock_rate_limiter(monkeypatch):
    from app.kiwoom import client as kiwoom_client

    mock = AsyncMock()
    monkeypatch.setattr(kiwoom_client, "_rate_limiter", mock)
    return mock


class TestKiwoomRequestRateLimiter:
    @pytest.mark.asyncio
    async def test_acquires_rate_limiter_before_request(self, mock_rate_limiter, override_settings):
        """broker_request 호출 전에 rate limiter를 반드시 acquire해야 한다 —
        키움은 초당 요청 한도(429)가 엄격해 세마포어만으로는 부족함."""
        success_data = {"return_code": "0"}

        with patch("app.kiwoom.client.broker_request", AsyncMock(return_value=success_data)):
            result = await kiwoom_request(
                "POST",
                "/path",
                is_mock=True,
                headers={"authorization": "Bearer token"},
            )

        assert result == success_data
        mock_rate_limiter.acquire.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_acquires_rate_limiter_even_when_request_fails(self, mock_rate_limiter, override_settings):
        with (
            patch("app.kiwoom.client.broker_request", AsyncMock(side_effect=RuntimeError("boom"))),
            pytest.raises(RuntimeError),
        ):
            await kiwoom_request(
                "POST",
                "/path",
                is_mock=True,
                headers={"authorization": "Bearer token"},
            )

        mock_rate_limiter.acquire.assert_awaited_once()
