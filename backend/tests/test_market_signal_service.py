"""market_signal_service.py 순수 함수 단위 테스트."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.market_signal_service import (
    _FNG_CLASSIFICATION_MAP,
    compute_composite_signal,
    fetch_fear_greed_signal,
)


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


class TestFearGreedClassificationMapping:
    """fetch_fear_greed_signal()이 API value_classification을 우선 사용하는지 검증."""

    def _make_fng_entry(self, value: int, value_classification: str) -> dict:
        return {"value": str(value), "value_classification": value_classification}

    @pytest.mark.asyncio
    async def test_classification_follows_api_not_threshold(self):
        """value=25는 API가 'Fear'를 반환하므로 FEAR여야 함 (EXTREME_FEAR 아님)."""
        entry = self._make_fng_entry(25, "Fear")
        with patch(
            "app.services.market_signal_service._call_fng_api",
            AsyncMock(return_value=entry),
        ):
            result = await fetch_fear_greed_signal()
        assert result is not None
        assert result["classification"] == "FEAR"
        assert result["label"] == "공포"
        assert result["label_en"] == "Fear"

    @pytest.mark.asyncio
    async def test_value_46_fear_via_api(self):
        """value=46은 API가 'Fear' → FEAR (코드 임계값 기준 ≤45이면 NEUTRAL이었음)."""
        entry = self._make_fng_entry(46, "Fear")
        with patch(
            "app.services.market_signal_service._call_fng_api",
            AsyncMock(return_value=entry),
        ):
            result = await fetch_fear_greed_signal()
        assert result is not None
        assert result["classification"] == "FEAR"

    @pytest.mark.asyncio
    async def test_value_52_greed_via_api(self):
        """value=52는 API가 'Greed' → GREED (코드 임계값 기준 ≤55이면 NEUTRAL이었음)."""
        entry = self._make_fng_entry(52, "Greed")
        with patch(
            "app.services.market_signal_service._call_fng_api",
            AsyncMock(return_value=entry),
        ):
            result = await fetch_fear_greed_signal()
        assert result is not None
        assert result["classification"] == "GREED"

    @pytest.mark.asyncio
    async def test_value_75_extreme_greed_via_api(self):
        """value=75는 API가 'Extreme Greed' → EXTREME_GREED (코드 임계값 기준 ≤75이면 GREED였음)."""
        entry = self._make_fng_entry(75, "Extreme Greed")
        with patch(
            "app.services.market_signal_service._call_fng_api",
            AsyncMock(return_value=entry),
        ):
            result = await fetch_fear_greed_signal()
        assert result is not None
        assert result["classification"] == "EXTREME_GREED"
        assert result["label_en"] == "Extreme Greed"

    @pytest.mark.asyncio
    async def test_unknown_api_classification_falls_back_to_neutral(self):
        """API가 예상 외 문자열을 반환하면 NEUTRAL 폴백."""
        entry = self._make_fng_entry(50, "Unknown Value")
        with patch(
            "app.services.market_signal_service._call_fng_api",
            AsyncMock(return_value=entry),
        ):
            result = await fetch_fear_greed_signal()
        assert result is not None
        assert result["classification"] == "NEUTRAL"

    def test_classification_map_covers_all_api_values(self):
        """_FNG_CLASSIFICATION_MAP이 Alternative.me의 모든 분류를 포함한다."""
        expected_keys = {"extreme fear", "fear", "neutral", "greed", "extreme greed"}
        assert set(_FNG_CLASSIFICATION_MAP.keys()) == expected_keys

    @pytest.mark.asyncio
    async def test_sub_score_still_value_based(self):
        """sub_score는 value 기반 유지 — 분류와 무관하게 복합 점수 일관성 보장."""
        # value=20 (EXTREME_FEAR 구간) → sub_score=2
        entry = self._make_fng_entry(20, "Extreme Fear")
        with patch(
            "app.services.market_signal_service._call_fng_api",
            AsyncMock(return_value=entry),
        ):
            result = await fetch_fear_greed_signal()
        assert result is not None
        assert result["sub_score"] == 2

        # value=80 (EXTREME_GREED 구간) → sub_score=3
        entry2 = self._make_fng_entry(80, "Extreme Greed")
        with patch(
            "app.services.market_signal_service._call_fng_api",
            AsyncMock(return_value=entry2),
        ):
            result2 = await fetch_fear_greed_signal()
        assert result2 is not None
        assert result2["sub_score"] == 3

    @pytest.mark.asyncio
    async def test_label_and_label_en_consistent_with_classification(self):
        """label(한국어)과 label_en이 classification과 일치한다."""
        entry = self._make_fng_entry(30, "Fear")
        with patch(
            "app.services.market_signal_service._call_fng_api",
            AsyncMock(return_value=entry),
        ):
            result = await fetch_fear_greed_signal()
        assert result is not None
        assert result["label"] == "공포"
        assert result["label_en"] == "Fear"


class TestResultStructure:
    def test_all_required_keys_present(self):
        result = compute_composite_signal(_vix(0), _yc(0), _fg(0))
        required_keys = {
            "composite_level",
            "composite_score",
            "fear_greed_contrarian_buy",
            "fear_greed_extreme_greed",
            "signals",
            "computed_at",
            "data_freshness",
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
