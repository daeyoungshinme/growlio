"""토스 클라이언트/인증 테스트 — rate limiter 배선 · 오류 분류 · 토큰 파싱."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.toss.client import (
    TossApiError,
    TossTokenExpiredError,
    _check_toss_api_error,
    _check_toss_token_expired,
    toss_request,
)


@pytest.fixture
def mock_rate_limiter(monkeypatch):
    from app.toss import client as toss_client

    mock = AsyncMock()
    monkeypatch.setattr(toss_client, "_rate_limiter", mock)
    return mock


class TestTossRequestRateLimiter:
    @pytest.mark.asyncio
    async def test_acquires_rate_limiter_before_request(self, mock_rate_limiter, override_settings):
        payload = {"result": {"ok": True}}
        with patch("app.toss.client.broker_request", AsyncMock(return_value=payload)):
            result = await toss_request("GET", "/api/v1/accounts", headers={"Authorization": "Bearer t"})
        assert result == payload
        mock_rate_limiter.acquire.assert_awaited_once()


class TestCheckTossErrors:
    def test_token_expired_code_raises_token_expired_error(self):
        with pytest.raises(TossTokenExpiredError):
            _check_toss_api_error({"error": {"code": "expired-token", "message": "만료"}}, "/api/v1/holdings")

    def test_generic_error_code_raises_api_error(self):
        with pytest.raises(TossApiError):
            _check_toss_api_error({"error": {"code": "edge-blocked", "message": "IP"}}, "/api/v1/holdings")

    def test_success_body_does_not_raise(self):
        _check_toss_api_error({"result": {"items": []}}, "/api/v1/holdings")

    def test_check_token_expired_by_status(self):
        assert _check_toss_token_expired({}, 401) is True
        assert _check_toss_token_expired({"error": {"code": "invalid-token"}}, 200) is True
        assert _check_toss_token_expired({"error": {"code": "forbidden"}}, 403) is False


class TestTossAuthTokenParsing:
    @pytest.mark.asyncio
    async def test_request_token_parses_standard_oauth_response(self, override_settings):
        from app.toss import auth

        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"access_token": "abc", "token_type": "Bearer", "expires_in": 3600}
        client = MagicMock()
        client.post = AsyncMock(return_value=resp)

        with patch("app.toss.auth._get_client", return_value=client):
            token, expires_in = await auth._request_token("cid", "csecret")

        assert token == "abc"
        assert expires_in == 3600
        # form-encoded 로 보냈는지 확인
        _, kwargs = client.post.call_args
        assert kwargs["data"]["grant_type"] == "client_credentials"

    @pytest.mark.asyncio
    async def test_request_token_raises_on_error_envelope(self, override_settings):
        from app.toss import auth

        resp = MagicMock()
        resp.status_code = 401
        resp.json.return_value = {"error": {"code": "invalid-client", "message": "bad"}}
        client = MagicMock()
        client.post = AsyncMock(return_value=resp)

        with patch("app.toss.auth._get_client", return_value=client), pytest.raises(TossApiError):
            await auth._request_token("cid", "csecret")
