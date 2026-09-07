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
    r"[=:\s\"']+[A-Za-z0-9+/=_\-\.]{4,}",
    re.IGNORECASE,
)


def redact_secrets(text: str) -> str:
    return _SECRET_PATTERN.sub(r"\1=[REDACTED]", text)


def _redact_processor(logger, method_name, event_dict):
    for key, value in event_dict.items():
        if isinstance(value, str):
            event_dict[key] = redact_secrets(value)
    return event_dict


_BENIGN_YF_PATTERNS = (
    "No fundamentals data found for symbol",
    "HTTP Error 404",
)


class _DropBenignYFinance404(logging.Filter):
    """yfinance가 quoteSummary 404(상장폐지·OTC·비미국·일부 ETF 심볼에서 정상 발생)를
    ERROR로 남기는 것을 억제한다. 배당/팩터 폴백 체인이 이미 처리하므로 순수 소음이다.
    레이트리밋 등 다른 yfinance 로그는 통과시킨다.
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
    structlog.configure(processors=processors)
