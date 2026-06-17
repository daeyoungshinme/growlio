"""KIS 클라이언트 테스트 — KisApiError 처리 및 transient 재시도."""

from unittest.mock import AsyncMock, patch

import pytest

from app.kis.client import KisApiError, kis_request


@pytest.fixture
def mock_rate_limiter(monkeypatch):
    from app.kis import client as kis_client

    mock = AsyncMock()
    monkeypatch.setattr(kis_client, "_rate_limiter", mock)
    return mock


class TestKisApiError:
    def test_str_representation(self):
        err = KisApiError("1", "MCI전송 오류")
        assert "KIS API 오류 [1]" in str(err)
        assert "MCI전송 오류" in str(err)

    def test_attributes(self):
        err = KisApiError("EGW00201", "rate limit")
        assert err.rt_cd == "EGW00201"
        assert err.msg == "rate limit"


class TestKisRequestTransientRetry:
    @pytest.mark.asyncio
    async def test_retries_on_transient_rt_cd_1(self, mock_rate_limiter, override_settings):
        """rt_cd='1' (MCI오류) 발생 시 1회 재시도 후 성공한다."""
        success_data = {"rt_cd": "0", "output": []}

        call_count = 0

        async def flaky_broker_request(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise KisApiError("1", "호출 후처리(MCI전송) 오류 입니다.")
            return success_data

        with patch("app.kis.client.broker_request", side_effect=flaky_broker_request):
            result = await kis_request(
                "GET",
                "/path",
                is_mock=True,
                headers={"Authorization": "Bearer token"},
            )

        assert result == success_data
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_does_not_retry_non_transient_rt_cd(self, mock_rate_limiter, override_settings):
        """transient하지 않은 rt_cd (예: '7') 는 재시도 없이 즉시 예외를 발생시킨다."""
        call_count = 0

        async def always_fail(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise KisApiError("7", "권한 없음")

        with (
            patch("app.kis.client.broker_request", side_effect=always_fail),
            pytest.raises(KisApiError) as exc_info,
        ):
            await kis_request(
                "GET",
                "/path",
                is_mock=True,
                headers={"Authorization": "Bearer token"},
            )

        assert exc_info.value.rt_cd == "7"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_raises_after_two_transient_failures(self, mock_rate_limiter, override_settings):
        """transient 오류가 2회 연속 발생하면 예외를 전파한다."""

        async def always_fail(*args, **kwargs):
            raise KisApiError("1", "MCI오류")

        with (
            patch("app.kis.client.broker_request", side_effect=always_fail),
            pytest.raises(KisApiError),
        ):
            await kis_request(
                "GET",
                "/path",
                is_mock=True,
                headers={"Authorization": "Bearer token"},
            )
