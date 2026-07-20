"""KIS/키움 provider 공용 HTTP 에러 매핑 — 브로커별 에러 메시지 키(msg1 vs return_msg)만 다르고 구조는 동일."""

from __future__ import annotations

import httpx

from app.exceptions import ProviderApiError, ProviderNetworkError


def map_http_status_error(e: httpx.HTTPStatusError, *, broker_name: str, message_key: str) -> ProviderApiError:
    if e.response.status_code >= 500:
        return ProviderApiError(f"{broker_name} API 오류: 모의투자/실계좌 설정을 확인하세요.", http_status=502)
    try:
        msg = e.response.json().get(message_key) or str(e)
    except Exception:
        msg = str(e)
    return ProviderApiError(f"{broker_name} API 오류: {msg}")


def map_network_error(broker_name: str) -> ProviderNetworkError:
    return ProviderNetworkError(f"{broker_name} 서버에 연결할 수 없습니다. 잠시 후 다시 시도하세요.")
