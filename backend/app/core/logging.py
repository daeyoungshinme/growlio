"""로그 이벤트에서 시크릿 패턴을 마스킹하는 structlog 프로세서.

structlog.configure()를 한 번도 호출하지 않으면 structlog는 지연 기본 프로세서
체인(merge_contextvars, add_log_level, StackInfoRenderer, set_exc_info, TimeStamper,
ConsoleRenderer)을 그대로 사용한다. `configure_logging()`은 그 체인을 그대로 가져와
렌더러 바로 앞에 redact 프로세서만 끼워 넣어 기존 로그 포맷을 그대로 유지한다.
"""

import logging
import re

import structlog

_SECRET_PATTERN = re.compile(
    r"(appkey|appsecret|secretkey|access_token|refresh_token|Bearer|password|Authorization"
    r"|api_key|apikey|dart_api_key|encryption_key|jwt_secret|supabase_key|database_url)"
    # "Authorization: Bearer <토큰>"은 "Bearer"만 값으로 잡혀 토큰이 남았다 — Bearer 접두를 건너뛴다
    r"[=:\s\"']+(?:Bearer\s+)?[A-Za-z0-9+/=_\-\.]{4,}",
    re.IGNORECASE,
)


def redact_secrets(text: str) -> str:
    return _SECRET_PATTERN.sub(r"\1=[REDACTED]", text)


SYNC_ERROR_MESSAGE_MAX_LENGTH = 200


def format_sync_error(error: BaseException | str) -> str:
    """계좌 동기화 실패 사유를 사용자에게 노출 가능한 형태로 가공한다 (비밀정보 redact + 길이 제한).

    asset_service.sync_account()/sync_all_service.run_sync_all() 양쪽에서 각자
    `redact_secrets(str(e))[:200]`을 독립 구현하고 있던 것을 공용화한 것. 예외 객체와, 이미
    str(e)로 변환되어 저장된 값(jobs/asset_sync.py의 failed 리스트) 양쪽을 모두 받는다."""
    return redact_secrets(str(error))[:SYNC_ERROR_MESSAGE_MAX_LENGTH]


def public_error_message(error: BaseException) -> str:
    """응답·DB·알림에 남길 예외 사유 — 우리가 쓴 메시지만 노출하고 나머지는 타입명으로 대체한다.

    SQLAlchemy 오류 문자열에는 SQL과 바인드 파라미터(토큰 등)가, httpx 오류에는 쿼리스트링(계좌번호)이 담긴
    URL이 들어 있어 `str(e)`를 그대로 내보내면 안 된다. 원문은 로그(redact 적용)에만 남긴다.
    """
    from fastapi import HTTPException

    from app.exceptions import AppError, BalancePaginationError, BrokerOrderRejectedError, SyncError
    from app.kis.client import KisApiError
    from app.kiwoom.client import KiwoomApiError, KiwoomTokenIssueError
    from app.providers.http_client import BrokerRequestError

    if isinstance(error, HTTPException):
        return format_sync_error(str(error.detail))
    if isinstance(
        error,
        AppError
        | SyncError
        | BalancePaginationError
        | BrokerOrderRejectedError
        | BrokerRequestError
        | KisApiError
        | KiwoomApiError
        | KiwoomTokenIssueError
        | ValueError,
    ):
        return format_sync_error(error)
    return f"내부 오류가 발생했습니다({type(error).__name__})"


# dict 키 이름만으로 값을 통째로 가린다 — 브로커 응답 본문(body=error_body, response=data)처럼
# 구조화된 값은 "키=값" 문자열 패턴이 없어 _SECRET_PATTERN에 걸리지 않는다.
_SENSITIVE_KEY_PATTERN = re.compile(r"token|secret|appkey|app_key|password|authorization|api_key", re.IGNORECASE)
_MAX_REDACT_DEPTH = 6


def _redact_value(value, depth: int = 0):
    if isinstance(value, str):
        return redact_secrets(value)
    if depth >= _MAX_REDACT_DEPTH:
        return value
    if isinstance(value, dict):
        return {
            k: "[REDACTED]" if isinstance(k, str) and _SENSITIVE_KEY_PATTERN.search(k) else _redact_value(v, depth + 1)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact_value(v, depth + 1) for v in value]
    if isinstance(value, tuple):
        # namedtuple 등 서브클래스는 생성자 시그니처가 달라 type(value)(gen)이 TypeError — 일반 tuple로 돌려준다
        return tuple(_redact_value(v, depth + 1) for v in value)
    return value


def _redact_processor(logger, method_name, event_dict):
    for key, value in event_dict.items():
        event_dict[key] = _redact_value(value)
    return event_dict


_BENIGN_YF_PATTERNS = ("No fundamentals data found for symbol", "Quote not found for symbol")


class _DropBenignYFinance404(logging.Filter):
    """yfinance가 quoteSummary 404(상장폐지·OTC·비미국·일부 ETF 심볼에서 `.info`/`.calendar`
    조회 시 정상 발생 — "No fundamentals data found for symbol ..." / "Quote not found for symbol ...")를
    ERROR로 남기는 것을 억제한다. 배당/팩터 폴백 체인이 이미 처리하므로 순수 소음이다. 레이트리밋이나 가격
    조회(`.history()`) 404 등 다른 yfinance 로그는 통과시킨다.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return not any(p in msg for p in _BENIGN_YF_PATTERNS)


def _quiet_yfinance_noise() -> None:
    yf_logger = logging.getLogger("yfinance")
    if not any(isinstance(f, _DropBenignYFinance404) for f in yf_logger.filters):
        yf_logger.addFilter(_DropBenignYFinance404())


def configure_logging() -> None:
    """앱 로거를 최초로 사용하기 전에 호출.

    테스트(`tests/conftest.py`)는 CI Rich 렌더러 hang을 막기 위해 이미
    `structlog.configure()`를 호출해두므로, 그 경우 여기서는 아무 것도 하지 않는다
    — 무조건 재설정하면 conftest의 설정을 덮어써 hang이 재발한다.
    """
    _quiet_yfinance_noise()
    if structlog.is_configured():
        return
    processors = list(structlog.get_config()["processors"])
    processors.insert(-1, _redact_processor)
    console_renderer = processors[-1]
    if isinstance(console_renderer, structlog.dev.ConsoleRenderer):
        console_renderer.exception_formatter = structlog.dev.plain_traceback
    structlog.configure(processors=processors)
