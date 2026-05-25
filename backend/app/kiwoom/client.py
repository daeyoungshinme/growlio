"""키움증권 REST API 기본 HTTP 클라이언트 — 속도제한 + 재시도 포함."""
import asyncio
from typing import Any

import httpx
import structlog

from app.kiwoom.constants import KIWOOM_MOCK_BASE_URL, KIWOOM_REAL_BASE_URL

logger = structlog.get_logger()

_semaphore = asyncio.Semaphore(5)


class KiwoomTokenExpiredError(Exception):
    """키움 토큰 만료 오류."""


class KiwoomApiError(Exception):
    """키움 API 논리 오류 (return_code != "0")."""

    def __init__(self, return_code: str, msg: str) -> None:
        self.return_code = return_code
        self.msg = msg
        super().__init__(f"키움 API 오류 [{return_code}]: {msg}")


async def kiwoom_request(
    method: str,
    path: str,
    *,
    is_mock: bool,
    headers: dict[str, str],
    params: dict[str, str] | None = None,
    json: dict[str, Any] | None = None,
    retries: int = 1,
) -> dict[str, Any]:
    """키움 OpenAPI+ 기본 HTTP 클라이언트."""
    base_url = KIWOOM_MOCK_BASE_URL if is_mock else KIWOOM_REAL_BASE_URL

    async with _semaphore:
        for attempt in range(retries):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.request(
                        method,
                        f"{base_url}{path}",
                        headers=headers,
                        params=params,
                        json=json,
                    )
                    if response.status_code >= 400:
                        try:
                            error_body = response.json()
                            logger.error("kiwoom_http_error", status=response.status_code, body=error_body, path=path)
                            # 토큰 만료: HTTP 401 또는 return_code로 감지
                            if response.status_code == 401:
                                raise KiwoomTokenExpiredError("키움 토큰이 만료되었습니다")
                        except KiwoomTokenExpiredError:
                            raise
                        except Exception:
                            logger.error("kiwoom_http_error", status=response.status_code, body=response.text, path=path)
                        response.raise_for_status()

                    data = response.json()

                    # 키움 응답: return_code != "0" 이면 API 오류
                    return_code = data.get("return_code")
                    if return_code is not None and str(return_code) != "0":
                        msg = data.get("return_msg", "알 수 없는 오류")
                        logger.warning("kiwoom_api_error", return_code=return_code, msg=msg, path=path)
                        raise KiwoomApiError(str(return_code), msg)

                    await asyncio.sleep(0.05)
                    return data

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    wait = 2 ** attempt
                    logger.warning("kiwoom_rate_limit", attempt=attempt, wait=wait)
                    await asyncio.sleep(wait)
                elif 400 <= e.response.status_code < 500:
                    raise
                elif attempt < retries - 1:
                    await asyncio.sleep(1)
                else:
                    raise
            except httpx.RequestError as e:
                if attempt < retries - 1:
                    await asyncio.sleep(1)
                else:
                    raise RuntimeError(f"키움 API 요청 실패: {e}") from e

    raise RuntimeError("키움 API 최대 재시도 초과")
