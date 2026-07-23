"""키움 클라이언트 테스트 — rate limiter 배선 확인 + API 오류 분류."""

from unittest.mock import AsyncMock, patch

import pytest

from app.kiwoom.client import KiwoomApiError, KiwoomTokenExpiredError, _check_kiwoom_api_error, kiwoom_request


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


class TestCheckKiwoomApiError:
    def test_token_invalid_8005_raises_token_expired_error(self):
        """return_code=3 + 메시지 내 8005 서브코드는 토큰 무효 — 일반 KiwoomApiError가 아닌
        KiwoomTokenExpiredError로 분류돼야 with_token_refresh()의 강제 갱신+재시도가 동작한다."""
        data = {"return_code": "3", "return_msg": "인증에 실패했습니다[8005:Token이 유효하지 않습니다]"}

        with pytest.raises(KiwoomTokenExpiredError):
            _check_kiwoom_api_error(data, "/api/dostk/acnt")

    def test_other_return_code_3_raises_generic_api_error(self):
        """8005 서브코드가 없는 return_code=3은 일반 API 오류로 그대로 유지돼야 한다."""
        data = {"return_code": "3", "return_msg": "인증에 실패했습니다[8001:앱키가 유효하지 않습니다]"}

        with pytest.raises(KiwoomApiError):
            _check_kiwoom_api_error(data, "/api/dostk/acnt")

    def test_success_return_code_does_not_raise(self):
        _check_kiwoom_api_error({"return_code": "0"}, "/api/dostk/acnt")
