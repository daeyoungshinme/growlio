"""circuit_breaker.py 상태 머신 단위 테스트."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock

import pytest

from app.utils.circuit_breaker import CircuitBreaker, CircuitOpenError


class TestCircuitBreakerStates:
    def test_initial_state_is_closed(self, override_settings):
        cb = CircuitBreaker("test", fail_max=3, reset_timeout=60)
        assert cb.is_available()

    def test_failures_below_max_keeps_closed(self, override_settings):
        cb = CircuitBreaker("test", fail_max=3, reset_timeout=60)
        cb.record_failure()
        cb.record_failure()
        assert cb.is_available()

    def test_failures_at_max_opens_circuit(self, override_settings):
        cb = CircuitBreaker("test", fail_max=3, reset_timeout=60)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        assert not cb.is_available()

    def test_success_resets_to_closed(self, override_settings):
        cb = CircuitBreaker("test", fail_max=2, reset_timeout=60)
        cb.record_failure()
        cb.record_failure()
        assert not cb.is_available()
        cb.record_success()
        assert cb.is_available()

    def test_success_resets_failure_count(self, override_settings):
        cb = CircuitBreaker("test", fail_max=3, reset_timeout=60)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        # After success, need fail_max failures to open again
        cb.record_failure()
        cb.record_failure()
        assert cb.is_available()

    def test_open_transitions_to_half_open_after_timeout(self, override_settings):
        cb = CircuitBreaker("test", fail_max=1, reset_timeout=0.01)
        cb.record_failure()
        assert not cb.is_available()
        time.sleep(0.05)
        # After timeout, state property transitions to HALF_OPEN → is_available = True
        assert cb.is_available()

    def test_half_open_failure_reopens_circuit(self, override_settings):
        cb = CircuitBreaker("test", fail_max=1, reset_timeout=0.01)
        cb.record_failure()
        time.sleep(0.05)
        cb.is_available()  # trigger HALF_OPEN transition
        cb.record_failure()  # fail in HALF_OPEN → OPEN again
        assert not cb.is_available()

    def test_half_open_success_closes_circuit(self, override_settings):
        cb = CircuitBreaker("test", fail_max=1, reset_timeout=0.01)
        cb.record_failure()
        time.sleep(0.05)
        cb.is_available()  # trigger HALF_OPEN
        cb.record_success()
        assert cb.is_available()


class TestCircuitBreakerCall:
    @pytest.mark.asyncio
    async def test_call_succeeds_and_records_success(self, override_settings):
        cb = CircuitBreaker("test", fail_max=3, reset_timeout=60)
        mock_func = AsyncMock(return_value="ok")
        result = await cb.call(mock_func)
        assert result == "ok"
        mock_func.assert_called_once()

    @pytest.mark.asyncio
    async def test_call_open_raises_circuit_open_error(self, override_settings):
        cb = CircuitBreaker("test", fail_max=1, reset_timeout=60)
        cb.record_failure()
        with pytest.raises(CircuitOpenError):
            await cb.call(AsyncMock())

    @pytest.mark.asyncio
    async def test_call_exception_records_failure(self, override_settings):
        cb = CircuitBreaker("test", fail_max=2, reset_timeout=60)
        mock_func = AsyncMock(side_effect=RuntimeError("fail"))
        with pytest.raises(RuntimeError):
            await cb.call(mock_func)
        assert cb._failures == 1

    @pytest.mark.asyncio
    async def test_call_bypasses_credential_error(self, override_settings):
        cb = CircuitBreaker("test", fail_max=3, reset_timeout=60)
        from app.exceptions import ProviderCredentialError

        mock_func = AsyncMock(side_effect=ProviderCredentialError("bad cred"))
        with pytest.raises(ProviderCredentialError):
            await cb.call(mock_func)
        # ProviderCredentialError should not count as failure
        assert cb._failures == 0


class TestCircuitBreakerHalfOpenProbeGating:
    """asyncio.gather로 여러 호출이 같은 서킷을 동시에 쓰는 상황(예: market_signal_service의
    FRED 신호 7개 동시 조회) — HALF_OPEN 진입 시 프로브 하나만 실제로 시도되고, 그 프로브의
    성공/실패 결과만으로 회로 상태가 결정돼야 한다. 이 게이팅이 없으면 동시 호출 중 하나만
    실패해도 나머지가 성공했는지와 무관하게 즉시 재오픈되어 회로가 회복하지 못하고
    계속 열린 채로 "플래핑"할 수 있다."""

    @pytest.mark.asyncio
    async def test_only_one_concurrent_call_attempts_the_probe(self, override_settings):
        cb = CircuitBreaker("test", fail_max=1, reset_timeout=0.01)
        cb.record_failure()
        await asyncio.sleep(0.05)  # reset_timeout 경과 → 다음 접근 시 HALF_OPEN 전환

        attempted = []

        async def slow_success() -> str:
            attempted.append(1)
            await asyncio.sleep(0.05)
            return "ok"

        results = await asyncio.gather(
            *[cb.call(slow_success) for _ in range(5)],
            return_exceptions=True,
        )

        # func 자체는 단 1회만 실제로 호출됨 — 나머지 4개는 CircuitOpenError로 즉시 차단
        assert len(attempted) == 1
        assert sum(1 for r in results if r == "ok") == 1
        assert sum(1 for r in results if isinstance(r, CircuitOpenError)) == 4
        # 프로브가 성공했으므로 나머지 결과와 무관하게 회로는 닫힌다
        assert cb.is_available()
        assert cb._failures == 0

    @pytest.mark.asyncio
    async def test_probe_failure_reopens_circuit_without_letting_others_retry(self, override_settings):
        cb = CircuitBreaker("test", fail_max=1, reset_timeout=0.01)
        cb.record_failure()
        await asyncio.sleep(0.05)

        attempted = []

        async def slow_fail() -> str:
            attempted.append(1)
            await asyncio.sleep(0.05)
            raise RuntimeError("still down")

        results = await asyncio.gather(
            *[cb.call(slow_fail) for _ in range(5)],
            return_exceptions=True,
        )

        assert len(attempted) == 1
        assert all(isinstance(r, RuntimeError | CircuitOpenError) for r in results)
        assert not cb.is_available()

    @pytest.mark.asyncio
    async def test_bypass_exception_during_probe_releases_slot_for_next_call(self, override_settings):
        from app.exceptions import ProviderCredentialError

        cb = CircuitBreaker("test", fail_max=1, reset_timeout=0.01)
        cb.record_failure()
        await asyncio.sleep(0.05)

        cred_error = AsyncMock(side_effect=ProviderCredentialError("bad cred"))
        with pytest.raises(ProviderCredentialError):
            await cb.call(cred_error)

        # 인증 오류는 실패로 카운트되지 않지만, 프로브 슬롯을 점유한 채 남으면 이후
        # 모든 호출이 영구히 "다른 요청이 재시도 중"으로 차단된다 — 해제돼야 한다.
        ok = AsyncMock(return_value="ok")
        assert await cb.call(ok) == "ok"
