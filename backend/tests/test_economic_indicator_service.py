"""economic_indicator_service._parse_fred_obs / fetch_inflation_summary 단위 테스트."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.economic_indicator_service import (
    _fred_get_observations,
    _parse_fred_obs,
    fetch_indicator_history,
    fetch_inflation_summary,
)
from app.utils.circuit_breaker import CircuitBreaker


class TestParseFredObs:
    def test_normal_observation_parsed(self):
        obs = [{"date": "2024-01-01", "value": "5.25"}]
        result = _parse_fred_obs(obs)
        assert len(result) == 1
        assert result[0]["date"] == "2024-01-01"
        assert result[0]["value"] == pytest.approx(5.25)

    def test_dot_value_skipped(self):
        obs = [
            {"date": "2024-01-01", "value": "."},
            {"date": "2024-02-01", "value": "5.25"},
        ]
        result = _parse_fred_obs(obs)
        assert len(result) == 1
        assert result[0]["value"] == pytest.approx(5.25)

    def test_multiple_valid_observations(self):
        obs = [
            {"date": "2024-03-01", "value": "3.0"},
            {"date": "2024-02-01", "value": "2.5"},
            {"date": "2024-01-01", "value": "2.0"},
        ]
        result = _parse_fred_obs(obs)
        assert len(result) == 3
        assert result[0]["date"] == "2024-01-01"
        assert result[-1]["date"] == "2024-03-01"

    def test_empty_input_returns_empty(self):
        assert _parse_fred_obs([]) == []

    def test_all_dot_values_returns_empty(self):
        obs = [{"date": "2024-01-01", "value": "."} for _ in range(5)]
        assert _parse_fred_obs(obs) == []

    def test_non_numeric_value_skipped(self):
        obs = [
            {"date": "2024-01-01", "value": "N/A"},
            {"date": "2024-02-01", "value": "1.5"},
        ]
        result = _parse_fred_obs(obs)
        assert len(result) == 1
        assert result[0]["value"] == pytest.approx(1.5)

    def test_result_is_chronological_ascending(self):
        obs = [
            {"date": "2024-12-01", "value": "4.0"},
            {"date": "2024-06-01", "value": "3.5"},
            {"date": "2024-01-01", "value": "3.0"},
        ]
        result = _parse_fred_obs(obs)
        dates = [r["date"] for r in result]
        assert dates == sorted(dates)


def _monthly_points(start_value: float, months: int, monthly_step: float = 0.5) -> list[dict]:
    """2024-01-01부터 매월 monthly_step씩 증가하는 시계열 fixture."""
    points = []
    for i in range(months):
        year = 2024 + (i // 12)
        month = (i % 12) + 1
        points.append({"date": f"{year}-{month:02d}-01", "value": start_value + i * monthly_step})
    return points


class TestFetchInflationSummary:
    async def test_computes_mom_and_yoy_change(self):
        points = _monthly_points(300.0, 13)  # 13개월치 → YoY 계산 가능
        calendar_events = [
            {"event": "미국 CPI", "date": "2025-02-13"},
            {"event": "미국 Core CPI", "date": "2025-02-13"},
            {"event": "미국 PCE", "date": "2025-02-28"},
        ]
        with (
            patch(
                "app.services.economic_indicator_service.fetch_indicator_history",
                new=AsyncMock(return_value=points),
            ),
            patch(
                "app.services.economic_indicator_service.get_calendar_events",
                new=AsyncMock(return_value=calendar_events),
            ),
        ):
            result = await fetch_inflation_summary(cache=None)

        assert len(result) == 3  # CPI_US + CORE_CPI_US + PCE_US
        cpi = result[0]
        assert cpi["code"] == "CPI_US"
        assert cpi["latest_value"] == pytest.approx(306.0)
        assert cpi["mom_change_pct"] == pytest.approx((306.0 - 305.5) / 305.5 * 100)
        assert cpi["yoy_change_pct"] == pytest.approx((306.0 - 300.0) / 300.0 * 100)
        assert cpi["next_release_date"] == "2025-02-13"

    async def test_fewer_than_13_months_yoy_is_none(self):
        points = _monthly_points(300.0, 6)
        with (
            patch(
                "app.services.economic_indicator_service.fetch_indicator_history",
                new=AsyncMock(return_value=points),
            ),
            patch(
                "app.services.economic_indicator_service.get_calendar_events",
                new=AsyncMock(return_value=[]),
            ),
        ):
            result = await fetch_inflation_summary(cache=None)

        for item in result:
            assert item["yoy_change_pct"] is None
            assert item["mom_change_pct"] is not None
            assert item["next_release_date"] is None

    async def test_no_history_skips_indicator(self):
        with (
            patch(
                "app.services.economic_indicator_service.fetch_indicator_history",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "app.services.economic_indicator_service.get_calendar_events",
                new=AsyncMock(return_value=[]),
            ),
        ):
            result = await fetch_inflation_summary(cache=None)

        assert result == []


class TestFredGetObservations:
    """403 등 HTTP 오류가 삼켜지지 않고 그대로 propagate되는지 검증
    (fred_circuit이 실패를 감지하려면 예외가 밖으로 나가야 한다)."""

    async def test_http_status_error_propagates(self):
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "403 Forbidden", request=MagicMock(), response=mock_response
        )
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with (
            patch("httpx.AsyncClient", return_value=mock_client),
            patch("app.services.economic_indicator_service.settings.fred_api_key", "test-key"),
            pytest.raises(httpx.HTTPStatusError),
        ):
            await _fred_get_observations("PCEPI")

    async def test_no_api_key_returns_empty_without_raising(self):
        with patch("app.services.economic_indicator_service.settings.fred_api_key", ""):
            result = await _fred_get_observations("PCEPI")

        assert result == []


class TestFetchIndicatorHistoryCircuitBreaker:
    """fetch_indicator_history가 나머지 FRED 소비처(market_signal_service.py)와 동일하게
    fred_circuit으로 보호받는지 검증 — 실제 전역 fred_circuit 상태 오염을 피하려고
    테스트 전용 CircuitBreaker 인스턴스로 교체해 사용한다."""

    async def test_returns_empty_when_fred_call_fails(self):
        test_circuit = CircuitBreaker("FREDAPI", fail_max=4, reset_timeout=300)
        with (
            patch("app.services.economic_indicator_service.fred_circuit", test_circuit),
            patch(
                "app.services.economic_indicator_service._fred_get_observations",
                new=AsyncMock(side_effect=httpx.HTTPStatusError("403", request=MagicMock(), response=MagicMock())),
            ),
        ):
            result = await fetch_indicator_history("CPI_US", months=13, cache=None)

        assert result == []

    async def test_skips_live_call_when_circuit_open(self):
        test_circuit = CircuitBreaker("FREDAPI", fail_max=4, reset_timeout=300)
        mock_fetch = AsyncMock(side_effect=AssertionError("circuit open인데도 라이브 호출을 시도함"))
        with (
            patch("app.services.economic_indicator_service.fred_circuit", test_circuit),
            patch.object(test_circuit, "is_available", return_value=False),
            patch("app.services.economic_indicator_service._fred_get_observations", new=mock_fetch),
        ):
            result = await fetch_indicator_history("CPI_US", months=13, cache=None)

        assert result == []
        mock_fetch.assert_not_called()
