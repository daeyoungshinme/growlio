"""Naver 스크래핑 재시도 정책 — 일시 장애만 재시도 (docs/plans/39 #8)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from app.utils.naver_retry import is_retryable_naver_error


def _http_error(status: int) -> requests.HTTPError:
    resp = requests.Response()
    resp.status_code = status
    return requests.HTTPError(response=resp)


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (_http_error(404), False),
        (_http_error(400), False),
        (_http_error(429), True),
        (_http_error(503), True),
        (requests.HTTPError(), True),  # 응답 없는 HTTPError — 판단 불가라 재시도
        (requests.ConnectionError(), True),
        (requests.Timeout(), True),
        (ValueError("bad json"), False),
    ],
)
def test_is_retryable(exc, expected):
    assert is_retryable_naver_error(exc) is expected


def test_404_fails_fast_without_retry():
    """없는 종목(404)은 한 번만 호출하고 None으로 폴백한다 — 과거엔 3회·~3초."""
    from app.services.price_sync_sources import sync_naver_price

    resp = MagicMock()
    resp.raise_for_status.side_effect = _http_error(404)
    with patch("requests.get", return_value=resp) as get:
        assert sync_naver_price("999999") is None
    assert get.call_count == 1
