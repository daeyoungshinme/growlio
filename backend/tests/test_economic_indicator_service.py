"""economic_indicator_service._parse_fred_obs / fetch_inflation_summary 단위 테스트."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.economic_indicator_service import _parse_fred_obs, fetch_inflation_summary


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

        assert len(result) == 2  # CPI_US + CORE_CPI_US
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
