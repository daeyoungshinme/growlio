"""circuit_breaker.py 상태 머신 단위 테스트."""

from __future__ import annotations

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
