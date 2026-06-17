"""economic_indicator_service._parse_fred_obs 단위 테스트."""

from __future__ import annotations

import pytest

from app.services.economic_indicator_service import _parse_fred_obs


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
