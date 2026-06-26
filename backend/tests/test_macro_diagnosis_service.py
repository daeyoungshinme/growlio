"""macro_diagnosis_service 단위 테스트 — 순수 계산 함수 위주."""

from __future__ import annotations

import pytest

from app.services.macro_diagnosis_service import (
    FOMC_DATES_FALLBACK,
    _analyze_cpi_trend,
    _analyze_fed_rate,
    _analyze_fomc_schedule,
    _derive_implication,
)


def _make_hist(values: list[float], start_year: int = 2024, start_month: int = 1) -> list[dict]:
    """테스트용 시계열 데이터 생성 (오름차순)."""
    import datetime

    result = []
    for i, v in enumerate(values):
        total_months = start_month - 1 + i
        year = start_year + total_months // 12
        month = total_months % 12 + 1
        date = datetime.date(year, month, 1)
        result.append({"date": date.isoformat(), "value": v})
    return result


# ---------------------------------------------------------------------------
# _analyze_cpi_trend
# ---------------------------------------------------------------------------


class TestAnalyzeCpiTrend:
    def test_rising_direction(self):
        hist = _make_hist([310.0, 310.5, 311.0, 311.3, 311.8, 312.5])
        result = _analyze_cpi_trend(hist)
        assert result is not None
        assert result["direction"] == "rising"
        assert result["latest_value"] == 312.5

    def test_falling_direction(self):
        hist = _make_hist([312.0, 311.5, 311.0, 310.5, 310.0, 309.5])
        result = _analyze_cpi_trend(hist)
        assert result is not None
        assert result["direction"] == "falling"

    def test_flat_direction(self):
        hist = _make_hist([310.0, 310.05, 310.1, 310.08, 310.06, 310.1])
        result = _analyze_cpi_trend(hist)
        assert result is not None
        assert result["direction"] == "flat"

    def test_too_few_data_returns_none(self):
        hist = _make_hist([310.0])
        result = _analyze_cpi_trend(hist)
        assert result is None

    def test_yoy_pct_calculation(self):
        # 13개월치 데이터: 12개월 전 300.0, 최신 315.0 → 5%
        hist = _make_hist([300.0] + [305.0] * 11 + [315.0])
        result = _analyze_cpi_trend(hist)
        assert result is not None
        assert result["yoy_pct"] == pytest.approx(5.0, abs=0.1)

    def test_yoy_pct_none_when_insufficient(self):
        hist = _make_hist([310.0, 311.0, 312.0])
        result = _analyze_cpi_trend(hist)
        assert result is not None
        assert result["yoy_pct"] is None

    def test_empty_history_returns_none(self):
        assert _analyze_cpi_trend([]) is None


# ---------------------------------------------------------------------------
# _analyze_fed_rate
# ---------------------------------------------------------------------------


class TestAnalyzeFedRate:
    def test_high_rate_flag(self):
        hist = _make_hist([5.0, 5.25, 5.25, 5.5, 5.5, 5.5, 5.5, 5.5])
        result = _analyze_fed_rate(hist)
        assert result is not None
        assert result["is_high"] is True
        assert result["latest_value"] == 5.5

    def test_low_rate_flag(self):
        hist = _make_hist([1.0, 1.0, 1.0, 1.25, 1.25, 1.5, 1.5, 1.5])
        result = _analyze_fed_rate(hist)
        assert result is not None
        assert result["is_high"] is False

    def test_rising_direction(self):
        hist = _make_hist([3.0, 3.25, 3.5, 3.75, 4.0, 4.25, 4.5, 4.75])
        result = _analyze_fed_rate(hist)
        assert result is not None
        assert result["direction"] == "rising"

    def test_falling_direction(self):
        hist = _make_hist([5.5, 5.25, 5.0, 4.75, 4.5, 4.25, 4.0, 3.75])
        result = _analyze_fed_rate(hist)
        assert result is not None
        assert result["direction"] == "falling"

    def test_stable_direction(self):
        hist = _make_hist([5.25, 5.25, 5.25, 5.25, 5.25, 5.25, 5.25, 5.25])
        result = _analyze_fed_rate(hist)
        assert result is not None
        assert result["direction"] == "stable"

    def test_too_few_data_returns_none(self):
        assert _analyze_fed_rate([{"date": "2024-01-01", "value": 5.0}]) is None

    def test_empty_history_returns_none(self):
        assert _analyze_fed_rate([]) is None


# ---------------------------------------------------------------------------
# _analyze_fomc_schedule
# ---------------------------------------------------------------------------


class TestAnalyzeFomcSchedule:
    def test_returns_fallback_source(self):
        result = _analyze_fomc_schedule()
        assert result["source"] in ("fallback", "unknown")

    def test_next_meeting_date_is_future_or_none(self):
        import datetime

        result = _analyze_fomc_schedule()
        if result["next_meeting_date"] is not None:
            d = datetime.date.fromisoformat(result["next_meeting_date"])
            assert d >= datetime.date.today()
            assert result["days_until"] >= 0

    def test_fallback_dates_not_empty(self):
        assert len(FOMC_DATES_FALLBACK) > 0
        import datetime

        for d in FOMC_DATES_FALLBACK:
            datetime.date.fromisoformat(d)

    def test_fallback_dates_sorted_ascending(self):
        import datetime

        dates = [datetime.date.fromisoformat(d) for d in FOMC_DATES_FALLBACK]
        assert dates == sorted(dates)


# ---------------------------------------------------------------------------
# _derive_implication
# ---------------------------------------------------------------------------


class TestDeriveImplication:
    def test_rising_cpi_high_rate_bearish(self):
        cpi = {
            "direction": "rising",
            "latest_value": 312.0,
            "latest_date": "2024-12-01",
            "yoy_pct": 4.2,
            "change_3m": 0.8,
            "month_count": 6,
        }
        fed = {"latest_value": 5.5, "latest_date": "2024-12-01", "direction": "stable", "is_high": True}
        result = _derive_implication(cpi, fed)
        assert result is not None
        assert result["growth_bias"] == "bearish"
        assert "긴축" in result["label"]

    def test_falling_cpi_high_rate_bullish(self):
        cpi = {
            "direction": "falling",
            "latest_value": 308.0,
            "latest_date": "2024-12-01",
            "yoy_pct": 2.1,
            "change_3m": -0.5,
            "month_count": 6,
        }
        fed = {"latest_value": 5.25, "latest_date": "2024-12-01", "direction": "falling", "is_high": True}
        result = _derive_implication(cpi, fed)
        assert result is not None
        assert result["growth_bias"] == "bullish"

    def test_flat_cpi_high_rate_neutral(self):
        cpi = {
            "direction": "flat",
            "latest_value": 310.0,
            "latest_date": "2024-12-01",
            "yoy_pct": 3.0,
            "change_3m": 0.05,
            "month_count": 6,
        }
        fed = {"latest_value": 5.0, "latest_date": "2024-12-01", "direction": "stable", "is_high": True}
        result = _derive_implication(cpi, fed)
        assert result is not None
        assert result["growth_bias"] == "neutral"

    def test_rising_cpi_low_rate_bearish(self):
        cpi = {
            "direction": "rising",
            "latest_value": 312.0,
            "latest_date": "2024-12-01",
            "yoy_pct": 4.5,
            "change_3m": 0.9,
            "month_count": 6,
        }
        fed = {"latest_value": 2.0, "latest_date": "2024-12-01", "direction": "rising", "is_high": False}
        result = _derive_implication(cpi, fed)
        assert result is not None
        assert result["growth_bias"] == "bearish"

    def test_none_cpi_returns_none(self):
        fed = {"latest_value": 5.5, "latest_date": "2024-12-01", "direction": "stable", "is_high": True}
        assert _derive_implication(None, fed) is None

    def test_none_fed_returns_none(self):
        cpi = {
            "direction": "rising",
            "latest_value": 312.0,
            "latest_date": "2024-12-01",
            "yoy_pct": 4.0,
            "change_3m": 0.5,
            "month_count": 6,
        }
        assert _derive_implication(cpi, None) is None
