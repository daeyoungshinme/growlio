"""인메모리 서킷 브레이커 — 외부 API 장애 시 빠른 실패(fast fail)와 자동 복구."""

from __future__ import annotations

import time
from collections.abc import Callable
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.core.config import Settings

import structlog

logger = structlog.get_logger()


class CircuitOpenError(Exception):
    """서킷이 열려 있어 외부 API 호출이 차단됨."""


class _State(StrEnum):
    CLOSED = "closed"  # 정상 운영
    OPEN = "open"  # 차단 중 (빠른 실패)
    HALF_OPEN = "half_open"  # 복구 테스트 중


class CircuitBreaker:
    """실패 횟수 기반 비동기 서킷 브레이커.

    CLOSED → 실패 누적(fail_max) → OPEN → reset_timeout 경과 → HALF_OPEN → 성공 → CLOSED
    HALF_OPEN → 실패 → OPEN (타이머 재시작)
    """

    def __init__(self, name: str, fail_max: int = 5, reset_timeout: float = 60.0) -> None:
        self.name = name
        self.fail_max = fail_max
        self.reset_timeout = reset_timeout
        self._failures = 0
        self._opened_at: float = 0.0
        self._state = _State.CLOSED

    @property
    def state(self) -> _State:
        if self._state == _State.OPEN and time.monotonic() - self._opened_at >= self.reset_timeout:
            self._state = _State.HALF_OPEN
            logger.info("circuit_half_open", name=self.name)
        return self._state

    def is_available(self) -> bool:
        """CLOSED 또는 HALF_OPEN → True, OPEN → False."""
        return self.state != _State.OPEN

    def record_success(self) -> None:
        if self._state == _State.HALF_OPEN:
            logger.info("circuit_closed", name=self.name)
        self._failures = 0
        self._state = _State.CLOSED

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.fail_max or self._state == _State.HALF_OPEN:
            self._state = _State.OPEN
            self._opened_at = time.monotonic()
            logger.warning(
                "circuit_opened",
                name=self.name,
                failures=self._failures,
                reset_in_s=int(self.reset_timeout),
            )

    async def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """func을 서킷 브레이커로 보호해서 호출한다.

        OPEN 상태면 즉시 CircuitOpenError를 raise한다.
        설정/인증 오류(ProviderCredentialError, *AuthError)는 실패로 카운트하지 않는다.
        """
        if not self.is_available():
            raise CircuitOpenError(
                f"{self.name} API가 일시적으로 응답하지 않습니다 ({self.reset_timeout:.0f}초 후 자동 재시도)."
            )
        try:
            result = await func(*args, **kwargs)
            self.record_success()
            return result
        except Exception as exc:
            if _is_bypass(exc):
                raise
            self.record_failure()
            raise


def _is_bypass(exc: BaseException) -> bool:
    """설정/인증 오류는 실패 카운트에서 제외한다 (재시도해도 의미 없음). 지연 import."""
    from app.exceptions import KisAuthError, KiwoomAuthError, ProviderCredentialError

    return isinstance(exc, (ProviderCredentialError, KisAuthError, KiwoomAuthError))


# ── 서비스별 사전 설정 인스턴스 ──────────────────────────────────────────────────
# 임계값은 config.py의 cb_* 필드로 조정 가능
def _cfg() -> Settings:
    from app.core.config import settings

    return settings


def _make(name: str, fail_max: int, reset_timeout: float) -> CircuitBreaker:
    return CircuitBreaker(name, fail_max=fail_max, reset_timeout=reset_timeout)


kis_circuit = _make("KIS", _cfg().cb_default_fail_max, _cfg().cb_default_reset_timeout)
kiwoom_circuit = _make("Kiwoom", _cfg().cb_default_fail_max, _cfg().cb_default_reset_timeout)
yahoo_circuit = _make("YahooFinance", _cfg().cb_ext_fail_max, _cfg().cb_ext_reset_timeout)
dart_circuit = _make("DART", _cfg().cb_default_fail_max, _cfg().cb_ext_reset_timeout)
naver_circuit = _make("NaverFinance", _cfg().cb_ext_fail_max, _cfg().cb_ext_reset_timeout)
fdr_circuit = _make("FinanceDataReader", _cfg().cb_ext_fail_max, _cfg().cb_ext_reset_timeout)
fear_greed_circuit = _make("FearGreedAPI", _cfg().cb_fng_fail_max, _cfg().cb_fng_reset_timeout)
fred_circuit = _make("FREDAPI", _cfg().cb_fred_fail_max, _cfg().cb_fred_reset_timeout)
