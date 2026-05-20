import asyncio
from typing import Any

import httpx
import structlog

from app.kis.constants import KIS_MOCK_BASE_URL, KIS_REAL_BASE_URL

logger = structlog.get_logger()

_semaphore = asyncio.Semaphore(5)  # KIS API 동시 요청 제한


class KisTokenExpiredError(Exception):
    """KIS 토큰 만료 오류 (EGW00123)."""


class KisApiError(Exception):
    """KIS API 논리 오류 (rt_cd != "0")."""

    def __init__(self, rt_cd: str, msg: str) -> None:
        self.rt_cd = rt_cd
        self.msg = msg
        super().__init__(f"KIS API 오류 [{rt_cd}]: {msg}")


async def kis_request(
    method: str,
    path: str,
    *,
    is_mock: bool,
    headers: dict[str, str],
    params: dict[str, str] | None = None,
    json: dict[str, Any] | None = None,
    retries: int = 3,
) -> dict[str, Any]:
    """KIS OpenAPI 기본 HTTP 클라이언트 — 속도제한 + 재시도 포함."""
    base_url = KIS_MOCK_BASE_URL if is_mock else KIS_REAL_BASE_URL

    async with _semaphore:
        for attempt in range(retries):
            try:
                async with httpx.AsyncClient(timeout=30.0, verify=not is_mock) as client:
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
                            logger.error("kis_http_error", status=response.status_code, body=error_body, path=path)
                            if error_body.get("msg_cd") == "EGW00123":
                                raise KisTokenExpiredError("KIS 토큰이 만료되었습니다")
                        except KisTokenExpiredError:
                            raise
                        except Exception:
                            logger.error("kis_http_error", status=response.status_code, body=response.text, path=path)
                        response.raise_for_status()
                    data = response.json()

                    if data.get("rt_cd") not in ("0", None):
                        rt_cd = data.get("rt_cd", "?")
                        msg = data.get("msg1", "알 수 없는 오류")
                        logger.warning("kis_api_error", rt_cd=rt_cd, msg=msg, path=path)
                        raise KisApiError(rt_cd, msg)

                    await asyncio.sleep(0.05)
                    return data

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    wait = 2 ** attempt
                    logger.warning("kis_rate_limit", attempt=attempt, wait=wait)
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
                    raise RuntimeError(f"KIS API 요청 실패: {e}") from e

    raise RuntimeError("KIS API 최대 재시도 초과")
