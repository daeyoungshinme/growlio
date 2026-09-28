"""Naver Finance 모바일 API 스크래핑 공용 설정 — 재시도 정책·User-Agent.

가격(`price_sync_sources`)·배당(`dividend/sync_sources`) 조회가 같은 엔드포인트 계열을 쓰므로 한 곳에 둔다.
재시도는 일시 장애(연결·타임아웃·429·5xx)에만 — 404(종목 없음·비ETF) 같은 4xx는 다시 불러도 같으므로
즉시 실패시켜 호출부 폴백으로 넘긴다(과거엔 모든 예외를 3회 재시도해 없는 종목마다 ~3초를 낭비했다).
"""

from __future__ import annotations

from typing import Any

import requests
from tenacity import retry_if_exception, stop_after_attempt, wait_exponential

NAVER_MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
)


def is_retryable_naver_error(exc: BaseException) -> bool:
    if isinstance(exc, requests.HTTPError):
        status = exc.response.status_code if exc.response is not None else None
        return status is None or status == 429 or status >= 500
    return isinstance(exc, (requests.ConnectionError, requests.Timeout))


NAVER_RETRY: dict[str, Any] = dict(
    retry=retry_if_exception(is_retryable_naver_error),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    stop=stop_after_attempt(3),
    reraise=True,
)
