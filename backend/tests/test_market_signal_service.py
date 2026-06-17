"""market_signal_service.py 순수 함수 단위 테스트."""
from __future__ import annotations

from app.services.market_signal_service import compute_composite_signal


def _vix(sub_score: int) -> dict:
    return {"sub_score": sub_score, "value": 20.0, "level": "MODERATE"}


def _yc(sub_score: int) -> dict:
    return {"sub_score": sub_score, "spread": 0.5, "level": "NORMAL"}


def _fg(sub_score: int, value: int = 50) -> dict:
    return {"sub_score": sub_score, "value": value, "level": "NEUTRAL"}


class TestCompositeLevel:
    def test_green_when_total_le_2(self):
        result = compute_composite_signal(_vix(1), _yc(1), _fg(0))
        assert result["composite_level"] == "GREEN"
        assert result["composite_score"] == 2

    def test_yellow_when_total_3_to_5(self):
        result = compute_composite_signal(_vix(2), _yc(2), _fg(1))
        assert result["composite_level"] == "YELLOW"
        assert result["composite_score"] == 5

    def test_red_when_total_gt_5(self):
        result = compute_composite_signal(_vix(3), _yc(3), _fg(2))
        assert result["composite_level"] == "RED"
        assert result["composite_score"] == 8

    def test_green_boundary_at_exactly_2(self):
        result = compute_composite_signal(_vix(2), None, None)
        assert result["composite_level"] == "GREEN"

    def test_yellow_boundary_at_exactly_3(self):
        result = compute_composite_signal(_vix(3), None, None)
        assert result["composite_level"] == "YELLOW"

    def test_red_boundary_at_exactly_6(self):
        result = compute_composite_signal(_vix(2), _yc(2), _fg(2))
        assert result["composite_level"] == "RED"


class TestDataFreshness:
    def test_live_when_all_signals_present(self):
        result = compute_composite_signal(_vix(0), _yc(0), _fg(0))
        assert result["data_freshness"] == "LIVE"

    def test_partial_when_one_signal_missing(self):
        result = compute_composite_signal(_vix(0), None, _fg(0))
        assert result["data_freshness"] == "PARTIAL"

    def test_stale_when_all_signals_missing(self):
        result = compute_composite_signal(None, None, None)
        assert result["data_freshness"] == "STALE"
        assert result["composite_level"] == "GREEN"
        assert result["composite_score"] == 0


class TestFearGreedFlags:
    def test_contrarian_buy_when_fg_le_25(self):
        result = compute_composite_signal(None, None, _fg(0, value=20))
        assert result["fear_greed_contrarian_buy"] is True
        assert result["fear_greed_extreme_greed"] is False

    def test_extreme_greed_when_fg_ge_75(self):
        result = compute_composite_signal(None, None, _fg(0, value=80))
        assert result["fear_greed_extreme_greed"] is True
        assert result["fear_greed_contrarian_buy"] is False

    def test_neutral_fg_no_flags(self):
        result = compute_composite_signal(None, None, _fg(0, value=50))
        assert result["fear_greed_contrarian_buy"] is False
        assert result["fear_greed_extreme_greed"] is False

    def test_no_fg_signal_no_flags(self):
        result = compute_composite_signal(_vix(0), _yc(0), None)
        assert result["fear_greed_contrarian_buy"] is False
        assert result["fear_greed_extreme_greed"] is False


class TestResultStructure:
    def test_all_required_keys_present(self):
        result = compute_composite_signal(_vix(0), _yc(0), _fg(0))
        required_keys = {
            "composite_level", "composite_score",
            "fear_greed_contrarian_buy", "fear_greed_extreme_greed",
            "signals", "computed_at", "data_freshness",
        }
        assert required_keys.issubset(result.keys())

    def test_signals_nested_structure(self):
        vix = _vix(1)
        yc = _yc(1)
        fg = _fg(1)
        result = compute_composite_signal(vix, yc, fg)
        assert result["signals"]["vix"] is vix
        assert result["signals"]["yield_curve"] is yc
        assert result["signals"]["fear_greed"] is fg

    def test_computed_at_is_iso_string(self):
        result = compute_composite_signal(None, None, None)
        assert isinstance(result["computed_at"], str)
        assert "T" in result["computed_at"]
