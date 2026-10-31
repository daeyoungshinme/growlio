"""Naver Finance 모바일 API 스크래핑 공용 설정 — 재시도 정책·User-Agent.

가격(`price_sync_sources`)·배당(`dividend/sync_sources`) 조회가 같은 엔드포인트 계열을 쓰므로 한 곳에 둔다.
재시도는 일시 장애(연결·타임아웃·429·5xx)에만 — 404(종목 없음·비ETF) 같은 4xx는 다시 불러도 같으므로
즉시 실패시켜 호출부 폴백으로 넘긴다(과거엔 모든 예외를 3회 재시도해 없는 종목마다 ~3초를 낭비했다).
"""

from __future__ import annotations

from typing import Any

import requests
import structlog
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

logger = structlog.get_logger()

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


NAVER_FAILURES: tuple[type[Exception], ...] = (requests.RequestException, ValueError, KeyError, TypeError)
"""`naver_get_json` + 응답 파싱에서 나올 수 있는 예외 — 호출부는 이것만 잡고 `log_naver_failure`로 넘긴다."""


def naver_get_json(ticker: str, endpoint: str) -> Any:
    """`m.stock.naver.com/api/stock/{ticker}/{endpoint}` JSON 조회(일시 장애만 재시도).

    `@retry(**NAVER_RETRY)`를 호출마다 데코레이트한다 — 테스트가 NAVER_RETRY dict를 패치해 백오프를 끈다.
    """

    @retry(**NAVER_RETRY)
    def _fetch() -> requests.Response:
        url = f"https://m.stock.naver.com/api/stock/{ticker}/{endpoint}"
        r = requests.get(url, headers={"User-Agent": NAVER_MOBILE_UA}, timeout=10)
        r.raise_for_status()
        return r

    return _fetch().json()


def log_naver_failure(event: str, ticker: str, exc: Exception) -> None:
    """`{event}_http_error` / `_network_error` / `_parse_error` 중 하나로 경고 로그를 남긴다."""
    if isinstance(exc, requests.HTTPError):
        status = exc.response.status_code if exc.response is not None else None
        logger.warning(f"{event}_http_error", ticker=ticker, status=status)
    elif isinstance(exc, requests.RequestException):
        logger.warning(f"{event}_network_error", ticker=ticker, error=str(exc))
    else:
        logger.warning(f"{event}_parse_error", ticker=ticker, error=str(exc))
