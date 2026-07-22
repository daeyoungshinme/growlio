"""market_signal_service.py 순수 함수 단위 테스트."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.market_signal_service import (
    _FNG_CLASSIFICATION_MAP,
    compute_composite_signal,
    fetch_dollar_index_signal,
    fetch_exchange_rate_signal,
    fetch_fear_greed_signal,
    fetch_high_yield_spread_signal,
    fetch_oil_price_signal,
    fetch_rate_cut_expectation_signal,
    get_market_signal,
)


def _vix(sub_score: int) -> dict:
    return {"sub_score": sub_score, "value": 20.0, "level": "MODERATE"}


def _yc(sub_score: int) -> dict:
    return {"sub_score": sub_score, "spread": 0.5, "level": "NORMAL"}


def _fg(sub_score: int, value: int = 50) -> dict:
    return {"sub_score": sub_score, "value": value, "level": "NEUTRAL"}


def _hy(sub_score: int) -> dict:
    return {"sub_score": sub_score, "value": 4.5, "level": "ELEVATED"}


def _usd(sub_score: int) -> dict:
    return {"sub_score": sub_score, "value": 105.0, "deviation_pct": 2.0, "level": "ELEVATED"}


def _rate(sub_score: int) -> dict:
    return {"sub_score": sub_score, "value": -0.5, "level": "MILD_CUT_EXPECTED"}


def _fx(sub_score: int) -> dict:
    return {"sub_score": sub_score, "value": 1380.0, "deviation_pct": 2.0, "level": "ELEVATED"}


def _oil(sub_score: int) -> dict:
    return {"sub_score": sub_score, "value": 78.0, "deviation_pct": 6.0, "level": "ELEVATED"}


class TestCompositeLevel:
    """임계값(GREEN 0-6 / YELLOW 7-14 / RED 15-26)은 기존 7신호(상한 23) 배점 비율을
    유가 신호(상한 3) 추가로 상한 26까지 재확장한 값 — market_signal_service._GREEN_MAX/_YELLOW_MAX 참고."""

    def test_green_when_total_le_6(self):
        result = compute_composite_signal(_vix(2), _yc(1), _fg(2), _hy(0), _usd(0), _rate(0), _fx(1), _oil(0))
        assert result["composite_level"] == "GREEN"
        assert result["composite_score"] == 6

    def test_yellow_when_total_7_to_14(self):
        result = compute_composite_signal(_vix(3), _yc(3), _fg(2), _hy(1), _usd(1), _rate(0), _fx(2), _oil(2))
        assert result["composite_level"] == "YELLOW"
        assert result["composite_score"] == 14

    def test_red_when_total_gt_14(self):
        result = compute_composite_signal(_vix(4), _yc(3), _fg(3), _hy(2), None, None, _fx(1), _oil(2))
        assert result["composite_level"] == "RED"
        assert result["composite_score"] == 15

    def test_green_boundary_at_exactly_6(self):
        result = compute_composite_signal(_vix(4), None, None, None, None, None, _fx(1), _oil(1))
        assert result["composite_level"] == "GREEN"
        assert result["composite_score"] == 6

    def test_yellow_boundary_at_exactly_7(self):
        result = compute_composite_signal(_vix(2), _yc(2), _fg(1), None, None, None, _fx(1), _oil(1))
        assert result["composite_level"] == "YELLOW"
        assert result["composite_score"] == 7

    def test_red_boundary_at_exactly_15(self):
        result = compute_composite_signal(_vix(4), _yc(3), _fg(3), _hy(2), None, None, _fx(2), _oil(1))
        assert result["composite_level"] == "RED"
        assert result["composite_score"] == 15

    def test_new_signals_alone_can_push_to_red(self):
        """VIX/YC/FG가 전부 정상이어도 나머지 5신호 상한(HY4+USD3+RATE3+FX3+OIL3=16)만으로 RED에 도달 가능."""
        result = compute_composite_signal(_vix(0), _yc(0), _fg(0), _hy(4), _usd(3), _rate(3), _fx(3), _oil(3))
        assert result["composite_score"] == 16
        assert result["composite_level"] == "RED"


class TestDataFreshness:
    def test_live_when_all_signals_present(self):
        result = compute_composite_signal(_vix(0), _yc(0), _fg(0), _hy(0), _usd(0), _rate(0), _fx(0), _oil(0))
        assert result["data_freshness"] == "LIVE"

    def test_partial_when_one_signal_missing(self):
        result = compute_composite_signal(_vix(0), None, _fg(0), _hy(0), _usd(0), _rate(0), _fx(0), _oil(0))
        assert result["data_freshness"] == "PARTIAL"

    def test_stale_when_all_signals_missing(self):
        result = compute_composite_signal(None, None, None)
        assert result["data_freshness"] == "STALE"
        assert result["composite_level"] == "GREEN"
        assert result["composite_score"] == 0

    def test_stale_when_available_signals_below_reliable_minimum(self):
        """FRED_API_KEY 미설정 등으로 8개 중 1개만 남으면 PARTIAL이 아닌 STALE로 취급해야
        AUTO 게이트가 이를 '판단 불가'로 인식하고 CAUTIOUS/STRICT에서 보수적으로 차단할 수 있다.
        (회귀 테스트 — 과거에는 이 경우도 PARTIAL로 분류되어 GREEN 오판 위험이 있었다)"""
        result = compute_composite_signal(_vix(0), None, None, None, None, None, None, None)
        assert result["data_freshness"] == "STALE"

    def test_partial_when_exactly_min_reliable_signals_available(self):
        """가용 신호가 정확히 최소 신뢰 기준(3개)이면 STALE이 아닌 PARTIAL로 취급된다."""
        result = compute_composite_signal(_vix(0), _yc(0), _fg(0), None, None, None, None, None)
        assert result["data_freshness"] == "PARTIAL"


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
            "composite_score_max",
            "fear_greed_contrarian_buy",
            "fear_greed_extreme_greed",
            "signals",
            "computed_at",
            "data_freshness",
        }
        assert required_keys.issubset(result.keys())
        assert result["composite_score_max"] == 26

    def test_signals_nested_structure(self):
        vix = _vix(1)
        yc = _yc(1)
        fg = _fg(1)
        hy = _hy(1)
        usd = _usd(1)
        rate = _rate(1)
        fx = _fx(1)
        oil = _oil(1)
        result = compute_composite_signal(vix, yc, fg, hy, usd, rate, fx, oil)
        assert result["signals"]["vix"] is vix
        assert result["signals"]["yield_curve"] is yc
        assert result["signals"]["fear_greed"] is fg
        assert result["signals"]["high_yield_spread"] is hy
        assert result["signals"]["dollar_index"] is usd
        assert result["signals"]["rate_cut_expectation"] is rate
        assert result["signals"]["exchange_rate"] is fx
        assert result["signals"]["oil_price"] is oil

    def test_signals_nested_structure_new_signals_default_none(self):
        result = compute_composite_signal(_vix(0), _yc(0), _fg(0))
        assert result["signals"]["high_yield_spread"] is None
        assert result["signals"]["dollar_index"] is None
        assert result["signals"]["rate_cut_expectation"] is None
        assert result["signals"]["exchange_rate"] is None
        assert result["signals"]["oil_price"] is None

    def test_computed_at_is_iso_string(self):
        result = compute_composite_signal(None, None, None)
        assert isinstance(result["computed_at"], str)
        assert "T" in result["computed_at"]


class TestHighYieldSpreadSignal:
    @pytest.mark.asyncio
    async def test_normal_below_4(self):
        obs = [{"date": "2026-07-03", "value": "3.2"}]
        with patch(
            "app.services.economic_indicator_service._fred_get_observations",
            AsyncMock(return_value=obs),
        ):
            result = await fetch_high_yield_spread_signal()
        assert result is not None
        assert result["level"] == "NORMAL"
        assert result["sub_score"] == 0

    @pytest.mark.asyncio
    async def test_stressed_between_5_and_7(self):
        obs = [{"date": "2026-07-03", "value": "6.2"}]
        with patch(
            "app.services.economic_indicator_service._fred_get_observations",
            AsyncMock(return_value=obs),
        ):
            result = await fetch_high_yield_spread_signal()
        assert result is not None
        assert result["level"] == "STRESSED"
        assert result["sub_score"] == 2

    @pytest.mark.asyncio
    async def test_crisis_above_7(self):
        obs = [{"date": "2026-07-03", "value": "8.5"}]
        with patch(
            "app.services.economic_indicator_service._fred_get_observations",
            AsyncMock(return_value=obs),
        ):
            result = await fetch_high_yield_spread_signal()
        assert result is not None
        assert result["level"] == "CRISIS"
        assert result["sub_score"] == 4

    @pytest.mark.asyncio
    async def test_returns_none_when_circuit_open(self):
        from app.services import market_signal_service

        with patch.object(market_signal_service.fred_circuit, "is_available", return_value=False):
            result = await fetch_high_yield_spread_signal()
        assert result is None


class TestDollarIndexSignal:
    @staticmethod
    def _make_obs(latest_value: float, base_value: float = 100.0, n: int = 19) -> list[dict]:
        """FRED desc 정렬 응답을 흉내낸다 — 최신값 1개 + 과거 n개(base_value 고정)."""
        obs = [{"date": "2026-07-03", "value": str(latest_value)}]
        obs += [{"date": f"2026-06-{d:02d}", "value": str(base_value)} for d in range(1, n + 1)]
        return obs

    @pytest.mark.asyncio
    async def test_normal_within_1_pct(self):
        obs = self._make_obs(latest_value=100.5, base_value=100.0)
        with patch(
            "app.services.economic_indicator_service._fred_get_observations",
            AsyncMock(return_value=obs),
        ):
            result = await fetch_dollar_index_signal()
        assert result is not None
        assert result["level"] == "NORMAL"
        assert result["sub_score"] == 0

    @pytest.mark.asyncio
    async def test_breakout_above_5_pct(self):
        obs = self._make_obs(latest_value=120.0, base_value=100.0)
        with patch(
            "app.services.economic_indicator_service._fred_get_observations",
            AsyncMock(return_value=obs),
        ):
            result = await fetch_dollar_index_signal()
        assert result is not None
        assert result["level"] == "BREAKOUT"
        assert result["sub_score"] == 3
        assert result["deviation_pct"] > 5

    @pytest.mark.asyncio
    async def test_returns_none_when_insufficient_history(self):
        obs = [{"date": "2026-07-03", "value": "105.0"}]
        with patch(
            "app.services.economic_indicator_service._fred_get_observations",
            AsyncMock(return_value=obs),
        ):
            result = await fetch_dollar_index_signal()
        assert result is None


class TestRateCutExpectationSignal:
    @staticmethod
    def _patch_dgs2_fedfunds(dgs2: str, fedfunds: str):
        async def _fake(series_id: str, limit: int = 5) -> list[dict]:
            value = dgs2 if series_id == "DGS2" else fedfunds
            return [{"date": "2026-07-03", "value": value}]

        return patch(
            "app.services.economic_indicator_service._fred_get_observations",
            AsyncMock(side_effect=_fake),
        )

    @pytest.mark.asyncio
    async def test_neutral_when_spread_non_negative(self):
        with self._patch_dgs2_fedfunds(dgs2="5.6", fedfunds="5.5"):
            result = await fetch_rate_cut_expectation_signal()
        assert result is not None
        assert result["level"] == "NEUTRAL"
        assert result["sub_score"] == 0

    @pytest.mark.asyncio
    async def test_deep_cut_expected_when_spread_below_minus_1_5(self):
        with self._patch_dgs2_fedfunds(dgs2="3.5", fedfunds="5.5"):
            result = await fetch_rate_cut_expectation_signal()
        assert result is not None
        assert result["level"] == "DEEP_CUT_EXPECTED"
        assert result["sub_score"] == 3
        assert result["value"] == -2.0

    @pytest.mark.asyncio
    async def test_returns_none_when_circuit_open(self):
        from app.services import market_signal_service

        with patch.object(market_signal_service.fred_circuit, "is_available", return_value=False):
            result = await fetch_rate_cut_expectation_signal()
        assert result is None


class TestExchangeRateSignal:
    @staticmethod
    def _make_obs(latest_value: float, base_value: float = 1350.0, n: int = 19) -> list[dict]:
        """FRED desc 정렬 응답을 흉내낸다 — 최신값 1개 + 과거 n개(base_value 고정)."""
        obs = [{"date": "2026-07-03", "value": str(latest_value)}]
        obs += [{"date": f"2026-06-{d:02d}", "value": str(base_value)} for d in range(1, n + 1)]
        return obs

    @pytest.mark.asyncio
    async def test_normal_within_1_pct(self):
        obs = self._make_obs(latest_value=1355.0, base_value=1350.0)
        with (
            patch(
                "app.services.economic_indicator_service._fred_get_observations",
                AsyncMock(return_value=obs),
            ),
            patch(
                "app.utils.currency.get_usd_krw_rate",
                AsyncMock(return_value=1355.0),
            ),
        ):
            result = await fetch_exchange_rate_signal()
        assert result is not None
        assert result["level"] == "NORMAL"
        assert result["sub_score"] == 0
        assert result["value"] == 1355.0

    @pytest.mark.asyncio
    async def test_breakout_above_5_pct(self):
        obs = self._make_obs(latest_value=1450.0, base_value=1350.0)
        with (
            patch(
                "app.services.economic_indicator_service._fred_get_observations",
                AsyncMock(return_value=obs),
            ),
            patch(
                "app.utils.currency.get_usd_krw_rate",
                AsyncMock(return_value=1450.0),
            ),
        ):
            result = await fetch_exchange_rate_signal()
        assert result is not None
        assert result["level"] == "BREAKOUT"
        assert result["sub_score"] == 3
        assert result["deviation_pct"] > 5
        assert result["value"] == 1450.0

    @pytest.mark.asyncio
    async def test_returns_none_when_insufficient_history(self):
        obs = [{"date": "2026-07-03", "value": "1380.0"}]
        with patch(
            "app.services.economic_indicator_service._fred_get_observations",
            AsyncMock(return_value=obs),
        ):
            result = await fetch_exchange_rate_signal()
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_circuit_open(self):
        from app.services import market_signal_service

        with patch.object(market_signal_service.fred_circuit, "is_available", return_value=False):
            result = await fetch_exchange_rate_signal()
        assert result is None


class TestOilPriceSignal:
    @staticmethod
    def _make_obs(latest_value: float, base_value: float = 75.0, n: int = 19) -> list[dict]:
        """FRED desc 정렬 응답을 흉내낸다 — 최신값 1개 + 과거 n개(base_value 고정)."""
        obs = [{"date": "2026-07-19", "value": str(latest_value)}]
        obs += [{"date": f"2026-06-{d:02d}", "value": str(base_value)} for d in range(1, n + 1)]
        return obs

    @pytest.mark.asyncio
    async def test_normal_within_5_pct(self):
        obs = self._make_obs(latest_value=77.0, base_value=75.0)
        with patch(
            "app.services.economic_indicator_service._fred_get_observations",
            AsyncMock(return_value=obs),
        ):
            result = await fetch_oil_price_signal()
        assert result is not None
        assert result["level"] == "NORMAL"
        assert result["sub_score"] == 0

    @pytest.mark.asyncio
    async def test_breakout_above_15_pct_on_spike(self):
        obs = self._make_obs(latest_value=95.0, base_value=75.0)
        with patch(
            "app.services.economic_indicator_service._fred_get_observations",
            AsyncMock(return_value=obs),
        ):
            result = await fetch_oil_price_signal()
        assert result is not None
        assert result["level"] == "BREAKOUT"
        assert result["sub_score"] == 3
        assert result["deviation_pct"] > 15

    @pytest.mark.asyncio
    async def test_breakout_above_15_pct_on_crash(self):
        """유가 급락도 급등과 동일하게 위험 신호로 취급한다(절대 이격도 기준)."""
        obs = self._make_obs(latest_value=55.0, base_value=75.0)
        with patch(
            "app.services.economic_indicator_service._fred_get_observations",
            AsyncMock(return_value=obs),
        ):
            result = await fetch_oil_price_signal()
        assert result is not None
        assert result["level"] == "BREAKOUT"
        assert result["sub_score"] == 3
        assert result["deviation_pct"] < -15

    @pytest.mark.asyncio
    async def test_returns_none_when_insufficient_history(self):
        obs = [{"date": "2026-07-19", "value": "78.0"}]
        with patch(
            "app.services.economic_indicator_service._fred_get_observations",
            AsyncMock(return_value=obs),
        ):
            result = await fetch_oil_price_signal()
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_circuit_open(self):
        from app.services import market_signal_service

        with patch.object(market_signal_service.fred_circuit, "is_available", return_value=False):
            result = await fetch_oil_price_signal()
        assert result is None


class TestGetMarketSignalCachingTtl:
    """일시적 장애(PARTIAL/STALE)가 1시간짜리 캐시에 고착되지 않도록 TTL을 짧게 쓰는지 검증.

    회귀 테스트: 과거에는 data_freshness와 무관하게 항상 TTL_MARKET_SIGNAL(1시간)로 캐싱해,
    한 번의 일시적 FRED 실패로 전 신호가 None인 결과가 최대 1시간 동안 그대로 노출되는
    문제가 있었다.
    """

    @staticmethod
    def _all_none_signals():
        return tuple(None for _ in range(8))

    @pytest.mark.asyncio
    async def test_live_uses_full_ttl(self, mock_cache):
        from app.utils.cache_keys import TTL_MARKET_SIGNAL

        live_signals = (
            _vix(0),
            _yc(0),
            _fg(0),
            {"sub_score": 0},
            {"sub_score": 0},
            {"sub_score": 0},
            _fx(0),
            {"sub_score": 0},
        )
        with patch(
            "app.services.market_signal_service._fetch_all_signals",
            AsyncMock(return_value=live_signals),
        ):
            result = await get_market_signal(mock_cache)

        assert result["data_freshness"] == "LIVE"
        mock_cache.setex.assert_called_once()
        assert mock_cache.setex.call_args[0][1] == TTL_MARKET_SIGNAL

    @pytest.mark.asyncio
    async def test_stale_uses_degraded_ttl(self, mock_cache):
        from app.utils.cache_keys import TTL_MARKET_SIGNAL_DEGRADED

        with patch(
            "app.services.market_signal_service._fetch_all_signals",
            AsyncMock(return_value=self._all_none_signals()),
        ):
            result = await get_market_signal(mock_cache)

        assert result["data_freshness"] == "STALE"
        mock_cache.setex.assert_called_once()
        assert mock_cache.setex.call_args[0][1] == TTL_MARKET_SIGNAL_DEGRADED

    @pytest.mark.asyncio
    async def test_partial_uses_degraded_ttl(self, mock_cache):
        from app.utils.cache_keys import TTL_MARKET_SIGNAL_DEGRADED

        # 최소 신뢰 기준(3개)은 충족하되 일부(5개)는 빠진 상태 — PARTIAL로 분류돼야 함.
        # (3개 미만이면 STALE로 재분류됨 — TestDataFreshness 참고)
        partial_signals = (_vix(0), _yc(0), _fg(0), None, None, None, None, None)
        with patch(
            "app.services.market_signal_service._fetch_all_signals",
            AsyncMock(return_value=partial_signals),
        ):
            result = await get_market_signal(mock_cache)

        assert result["data_freshness"] == "PARTIAL"
        mock_cache.setex.assert_called_once()
        assert mock_cache.setex.call_args[0][1] == TTL_MARKET_SIGNAL_DEGRADED
