"""providers/http_client.py 단위 테스트."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.providers.http_client import (
    AsyncRateLimiter,
    MaxRetriesExceededError,
    _is_rate_limit_body,
    broker_request,
    close_http_client,
)


class TestIsRateLimitBody:
    def test_detects_egw00201(self):
        resp = MagicMock()
        resp.json.return_value = {"msg_cd": "EGW00201"}
        assert _is_rate_limit_body(resp) is True

    def test_returns_false_for_other_codes(self):
        resp = MagicMock()
        resp.json.return_value = {"msg_cd": "EGW00101"}
        assert _is_rate_limit_body(resp) is False

    def test_returns_false_when_json_fails(self):
        resp = MagicMock()
        resp.json.side_effect = Exception("parse error")
        assert _is_rate_limit_body(resp) is False

    def test_returns_false_for_empty_body(self):
        resp = MagicMock()
        resp.json.return_value = {}
        assert _is_rate_limit_body(resp) is False


class TestAsyncRateLimiter:
    @pytest.mark.asyncio
    async def test_first_acquire_returns_immediately(self, override_settings):
        limiter = AsyncRateLimiter(rate=100.0)
        import time
        start = time.monotonic()
        await limiter.acquire()
        elapsed = time.monotonic() - start
        assert elapsed < 0.1

    @pytest.mark.asyncio
    async def test_creates_lock_on_first_use(self, override_settings):
        limiter = AsyncRateLimiter(rate=10.0)
        assert limiter._lock is None
        await limiter.acquire()
        assert limiter._lock is not None


class TestCloseHttpClient:
    @pytest.mark.asyncio
    async def test_close_with_no_clients(self, override_settings):
        import app.providers.http_client as mod
        mod._ssl_client = None
        mod._nossl_client = None
        await close_http_client()  # should not raise

    @pytest.mark.asyncio
    async def test_close_sets_clients_to_none(self, override_settings):
        import app.providers.http_client as mod
        mock_client = AsyncMock()
        mock_client.aclose = AsyncMock()
        mod._ssl_client = mock_client
        mod._nossl_client = None
        await close_http_client()
        assert mod._ssl_client is None


class TestBrokerRequest:
    def _make_semaphore(self):
        return asyncio.Semaphore(5)

    def _make_mock_response(self, data: dict, status_code: int = 200):
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = status_code
        resp.json.return_value = data
        resp.text = str(data)
        resp.raise_for_status = MagicMock()
        return resp

    @pytest.mark.asyncio
    async def test_successful_request(self, override_settings):
        mock_resp = self._make_mock_response({"result": "ok"})
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_resp)

        with patch("app.providers.http_client._get_client", return_value=mock_client):
            result = await broker_request(
                "GET", "/test",
                base_url="https://api.example.com",
                headers={},
                semaphore=self._make_semaphore(),
                log_prefix="test",
                check_token_expired=lambda data, status: False,
                check_api_error=lambda data, path: None,
                token_expired_exc=RuntimeError,
            )
        assert result == {"result": "ok"}

    @pytest.mark.asyncio
    async def test_raises_max_retries_on_repeated_429(self, override_settings):
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 429
        mock_resp.json.return_value = {}
        exc = httpx.HTTPStatusError("rate limit", request=MagicMock(), response=mock_resp)

        mock_client = AsyncMock()
        mock_client.request = AsyncMock(side_effect=exc)

        with patch("app.providers.http_client._get_client", return_value=mock_client):
            with patch("asyncio.sleep", AsyncMock()):
                with pytest.raises(MaxRetriesExceededError):
                    await broker_request(
                        "GET", "/test",
                        base_url="https://api.example.com",
                        headers={},
                        retries=2,
                        semaphore=self._make_semaphore(),
                        log_prefix="test",
                        check_token_expired=lambda data, status: False,
                        check_api_error=lambda data, path: None,
                        token_expired_exc=RuntimeError,
                    )

    @pytest.mark.asyncio
    async def test_raises_token_expired(self, override_settings):
        class MyTokenExpiredError(Exception):
            pass

        mock_resp = self._make_mock_response({}, status_code=401)
        mock_resp.raise_for_status = MagicMock(side_effect=httpx.HTTPStatusError(
            "401", request=MagicMock(), response=mock_resp
        ))

        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_resp)

        with patch("app.providers.http_client._get_client", return_value=mock_client):
            with pytest.raises((MyTokenExpiredError, httpx.HTTPStatusError, Exception)):
                await broker_request(
                    "GET", "/test",
                    base_url="https://api.example.com",
                    headers={},
                    semaphore=self._make_semaphore(),
                    log_prefix="test",
                    check_token_expired=lambda data, status: True,
                    check_api_error=lambda data, path: None,
                    token_expired_exc=MyTokenExpiredError,
                )
