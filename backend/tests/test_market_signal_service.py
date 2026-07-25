"""market_signal_service.py 순수 함수 단위 테스트."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.services.market_signal_service import (
    compute_composite_signal,
    fetch_cpi_inflation_signal,
    fetch_dollar_index_signal,
    fetch_employment_signal,
    fetch_exchange_rate_signal,
    fetch_high_yield_spread_signal,
    fetch_inflation_signal,
    fetch_oil_price_signal,
    fetch_pce_inflation_signal,
    fetch_rate_cut_expectation_signal,
    fetch_us_rate_curve_signal,
    get_confirmed_composite_level,
    get_market_signal,
)


def _vix(sub_score: int) -> dict:
    return {"sub_score": sub_score, "value": 20.0, "level": "MODERATE"}


def _rate_curve(sub_score: int) -> dict:
    return {
        "sub_score": sub_score,
        "yield_curve_value": 0.3,
        "yield_curve_state": "FLAT",
        "rate_cut_value": -0.5,
        "rate_cut_level": "MILD_CUT_EXPECTED",
    }


def _hy(sub_score: int) -> dict:
    return {"sub_score": sub_score, "value": 4.5, "level": "ELEVATED"}


def _usd(sub_score: int) -> dict:
    return {"sub_score": sub_score, "value": 105.0, "deviation_pct": 2.0, "level": "ELEVATED"}


def _fx(sub_score: int) -> dict:
    return {"sub_score": sub_score, "value": 1380.0, "deviation_pct": 2.0, "level": "ELEVATED"}


def _oil(sub_score: int) -> dict:
    return {"sub_score": sub_score, "value": 78.0, "deviation_pct": 6.0, "level": "ELEVATED"}


def _inflation(sub_score: int) -> dict:
    return {
        "sub_score": sub_score,
        "cpi_yoy_pct": 3.0,
        "cpi_level": "NORMAL",
        "pce_yoy_pct": 3.0,
        "pce_level": "NORMAL",
    }


def _employment(sub_score: int) -> dict:
    return {"sub_score": sub_score, "value": 4.0, "rise_from_low_pp": 0.1, "level": "NORMAL"}


class TestCompositeLevel:
    """임계값(GREEN 0-6 / YELLOW 7-15 / RED 16-27)은 인플레이션(CPI+PCE 병합)·고용(실업률)
    신호 추가로 8신호(상한 27)가 된 뒤 기존 비율(23.08%/53.85%)을 유지해 재계산한 값 —
    market_signal_service._GREEN_MAX/_YELLOW_MAX 참고."""

    def test_green_when_total_le_6(self):
        result = compute_composite_signal(
            _vix(2), _rate_curve(1), _hy(0), _usd(0), _fx(1), _oil(1), _inflation(1), None
        )
        assert result["composite_level"] == "GREEN"
        assert result["composite_score"] == 6

    def test_yellow_when_total_7_to_15(self):
        result = compute_composite_signal(
            _vix(3), _rate_curve(2), _hy(1), _usd(1), _fx(2), _oil(2), _inflation(1), _employment(1)
        )
        assert result["composite_level"] == "YELLOW"
        assert result["composite_score"] == 13

    def test_red_when_total_gt_15(self):
        result = compute_composite_signal(
            _vix(4), _rate_curve(3), _hy(2), _usd(0), _fx(2), _oil(1), _inflation(2), _employment(2)
        )
        assert result["composite_level"] == "RED"
        assert result["composite_score"] == 16

    def test_green_boundary_at_exactly_6(self):
        result = compute_composite_signal(_vix(4), None, None, None, _fx(1), None, _inflation(1), None)
        assert result["composite_level"] == "GREEN"
        assert result["composite_score"] == 6

    def test_yellow_boundary_at_exactly_7(self):
        result = compute_composite_signal(_vix(2), _rate_curve(2), _hy(1), None, None, _oil(1), _inflation(1), None)
        assert result["composite_level"] == "YELLOW"
        assert result["composite_score"] == 7

    def test_yellow_boundary_at_exactly_15(self):
        result = compute_composite_signal(_vix(4), _rate_curve(3), _hy(4), None, _fx(2), _oil(1), _inflation(1), None)
        assert result["composite_level"] == "YELLOW"
        assert result["composite_score"] == 15

    def test_red_boundary_at_exactly_16(self):
        result = compute_composite_signal(
            _vix(4), _rate_curve(3), _hy(4), None, _fx(2), _oil(1), _inflation(1), _employment(1)
        )
        assert result["composite_level"] == "RED"
        assert result["composite_score"] == 16

    def test_remaining_signals_alone_can_push_to_red(self):
        """VIX/금리커브가 전부 정상이어도 나머지 신호 상한
        (HY4+USD3+FX3+OIL3+INFLATION3+EMPLOYMENT4=20)만으로 RED에 도달 가능."""
        result = compute_composite_signal(
            _vix(0), _rate_curve(0), _hy(4), _usd(3), _fx(3), _oil(3), _inflation(3), _employment(4)
        )
        assert result["composite_score"] == 20
        assert result["composite_level"] == "RED"


class TestDataFreshness:
    def test_live_when_all_signals_present(self):
        result = compute_composite_signal(
            _vix(0), _rate_curve(0), _hy(0), _usd(0), _fx(0), _oil(0), _inflation(0), _employment(0)
        )
        assert result["data_freshness"] == "LIVE"

    def test_partial_when_one_signal_missing(self):
        result = compute_composite_signal(
            _vix(0), None, _hy(0), _usd(0), _fx(0), _oil(0), _inflation(0), _employment(0)
        )
        assert result["data_freshness"] == "PARTIAL"

    def test_stale_when_all_signals_missing(self):
        result = compute_composite_signal(None, None)
        assert result["data_freshness"] == "STALE"
        assert result["composite_level"] == "GREEN"
        assert result["composite_score"] == 0

    def test_stale_when_available_signals_below_reliable_minimum(self):
        """8개 중 3개만 남으면(최소 신뢰 기준 4 미만) PARTIAL이 아닌 STALE로 취급해야
        AUTO 게이트가 이를 '판단 불가'로 인식하고 CAUTIOUS/STRICT에서 보수적으로 차단할 수 있다."""
        result = compute_composite_signal(_vix(0), _rate_curve(0), _hy(0))
        assert result["data_freshness"] == "STALE"

    def test_partial_when_exactly_min_reliable_signals_available(self):
        """가용 신호가 정확히 최소 신뢰 기준(4개)이면 STALE이 아닌 PARTIAL로 취급된다."""
        result = compute_composite_signal(_vix(0), _rate_curve(0), _hy(0), _usd(0))
        assert result["data_freshness"] == "PARTIAL"


class TestResultStructure:
    def test_all_required_keys_present(self):
        result = compute_composite_signal(_vix(0), _rate_curve(0))
        required_keys = {
            "composite_level",
            "composite_score",
            "composite_score_max",
            "signals",
            "computed_at",
            "data_freshness",
        }
        assert required_keys.issubset(result.keys())
        assert result["composite_score_max"] == 27
        # Fear & Greed 완전 제거 — 관련 플래그는 응답에 없어야 한다.
        assert "fear_greed_contrarian_buy" not in result
        assert "fear_greed_extreme_greed" not in result

    def test_signals_nested_structure(self):
        vix = _vix(1)
        rate_curve = _rate_curve(1)
        hy = _hy(1)
        usd = _usd(1)
        fx = _fx(1)
        oil = _oil(1)
        inflation = _inflation(1)
        employment = _employment(1)
        result = compute_composite_signal(vix, rate_curve, hy, usd, fx, oil, inflation, employment)
        assert result["signals"]["vix"] is vix
        assert result["signals"]["us_rate_curve"] is rate_curve
        assert result["signals"]["high_yield_spread"] is hy
        assert result["signals"]["dollar_index"] is usd
        assert result["signals"]["exchange_rate"] is fx
        assert result["signals"]["oil_price"] is oil
        assert result["signals"]["inflation"] is inflation
        assert result["signals"]["employment"] is employment
        assert "fear_greed" not in result["signals"]
        assert "yield_curve" not in result["signals"]
        assert "rate_cut_expectation" not in result["signals"]

    def test_signals_nested_structure_new_signals_default_none(self):
        result = compute_composite_signal(_vix(0), _rate_curve(0))
        assert result["signals"]["high_yield_spread"] is None
        assert result["signals"]["dollar_index"] is None
        assert result["signals"]["exchange_rate"] is None
        assert result["signals"]["oil_price"] is None
        assert result["signals"]["inflation"] is None
        assert result["signals"]["employment"] is None

    def test_computed_at_is_iso_string(self):
        result = compute_composite_signal(None, None)
        assert isinstance(result["computed_at"], str)
        assert "T" in result["computed_at"]


class TestUsRateCurveSignal:
    """장단기금리차(T10Y2Y)+금리인하기대(DGS2-FEDFUNDS) 병합 신호 — worst-case(max) 채택 검증."""

    @pytest.mark.asyncio
    async def test_worst_case_picks_higher_sub_score(self):
        yc_signal = {"value": 0.3, "state": "FLAT", "date": "2026-07-03", "sub_score": 1}
        rate_signal = {
            "value": -2.0,
            "dgs2": 3.5,
            "fedfunds": 5.5,
            "level": "DEEP_CUT_EXPECTED",
            "date": "2026-07-03",
            "sub_score": 3,
        }
        with (
            patch(
                "app.services.market_signal_service.fetch_yield_curve_signal",
                AsyncMock(return_value=yc_signal),
            ),
            patch(
                "app.services.market_signal_service.fetch_rate_cut_expectation_signal",
                AsyncMock(return_value=rate_signal),
            ),
        ):
            result = await fetch_us_rate_curve_signal()
        assert result is not None
        assert result["sub_score"] == 3  # max(1, 3)
        assert result["yield_curve_state"] == "FLAT"
        assert result["rate_cut_level"] == "DEEP_CUT_EXPECTED"

    @pytest.mark.asyncio
    async def test_returns_none_when_both_signals_unavailable(self):
        with (
            patch("app.services.market_signal_service.fetch_yield_curve_signal", AsyncMock(return_value=None)),
            patch(
                "app.services.market_signal_service.fetch_rate_cut_expectation_signal",
                AsyncMock(return_value=None),
            ),
        ):
            result = await fetch_us_rate_curve_signal()
        assert result is None

    @pytest.mark.asyncio
    async def test_partial_availability_still_returns_combined_signal(self):
        yc_signal = {"value": 0.6, "state": "POSITIVE", "date": "2026-07-03", "sub_score": 0}
        with (
            patch(
                "app.services.market_signal_service.fetch_yield_curve_signal",
                AsyncMock(return_value=yc_signal),
            ),
            patch(
                "app.services.market_signal_service.fetch_rate_cut_expectation_signal",
                AsyncMock(return_value=None),
            ),
        ):
            result = await fetch_us_rate_curve_signal()
        assert result is not None
        assert result["sub_score"] == 0
        assert result["rate_cut_value"] is None
        assert result["rate_cut_level"] is None


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


class TestInflationSignal:
    """CPI(CPIAUCSL)+PCE(PCEPI) YoY 병합 신호 — Fed 목표 2% 대비 이격도 버킷 + worst-case 병합 검증."""

    @staticmethod
    def _points(base_value: float, latest_value: float) -> list[dict]:
        """13개월치 지수 시계열(YoY 계산용) — 앞 12개월은 base_value 고정, 마지막이 latest_value."""
        points = [{"date": f"2025-{i + 1:02d}-01", "value": base_value} for i in range(12)]
        points.append({"date": "2026-01-01", "value": latest_value})
        return points

    @pytest.mark.asyncio
    async def test_cpi_normal_within_1pp_of_target(self):
        points = self._points(base_value=300.0, latest_value=309.0)  # YoY 3.0% → 이격 1.0pp
        with patch(
            "app.services.economic_indicator_service.fetch_indicator_history",
            AsyncMock(return_value=points),
        ):
            result = await fetch_cpi_inflation_signal()
        assert result is not None
        assert result["level"] == "NORMAL"
        assert result["sub_score"] == 0
        assert result["yoy_change_pct"] == pytest.approx(3.0)

    @pytest.mark.asyncio
    async def test_cpi_breakout_above_5_5_pct_yoy(self):
        points = self._points(base_value=300.0, latest_value=318.0)  # YoY 6.0%
        with patch(
            "app.services.economic_indicator_service.fetch_indicator_history",
            AsyncMock(return_value=points),
        ):
            result = await fetch_cpi_inflation_signal()
        assert result is not None
        assert result["level"] == "BREAKOUT"
        assert result["sub_score"] == 3

    @pytest.mark.asyncio
    async def test_cpi_returns_none_when_insufficient_history(self):
        with patch(
            "app.services.economic_indicator_service.fetch_indicator_history",
            AsyncMock(return_value=self._points(300.0, 309.0)[:5]),
        ):
            result = await fetch_cpi_inflation_signal()
        assert result is None

    @pytest.mark.asyncio
    async def test_pce_elevated_between_1pp_and_2pp(self):
        points = self._points(base_value=300.0, latest_value=312.0)  # YoY 4.0% → 이격 2.0pp
        with patch(
            "app.services.economic_indicator_service.fetch_indicator_history",
            AsyncMock(return_value=points),
        ):
            result = await fetch_pce_inflation_signal()
        assert result is not None
        assert result["level"] == "ELEVATED"
        assert result["sub_score"] == 1

    @pytest.mark.asyncio
    async def test_merged_signal_picks_worst_case(self):
        cpi_signal = {"yoy_change_pct": 3.0, "level": "NORMAL", "date": "2026-01-01", "sub_score": 0}
        pce_signal = {"yoy_change_pct": 6.0, "level": "BREAKOUT", "date": "2026-01-01", "sub_score": 3}
        with (
            patch(
                "app.services.market_signal_service.fetch_cpi_inflation_signal",
                AsyncMock(return_value=cpi_signal),
            ),
            patch(
                "app.services.market_signal_service.fetch_pce_inflation_signal",
                AsyncMock(return_value=pce_signal),
            ),
        ):
            result = await fetch_inflation_signal()
        assert result is not None
        assert result["sub_score"] == 3  # max(0, 3)
        assert result["cpi_level"] == "NORMAL"
        assert result["pce_level"] == "BREAKOUT"

    @pytest.mark.asyncio
    async def test_merged_signal_returns_none_when_both_unavailable(self):
        with (
            patch("app.services.market_signal_service.fetch_cpi_inflation_signal", AsyncMock(return_value=None)),
            patch("app.services.market_signal_service.fetch_pce_inflation_signal", AsyncMock(return_value=None)),
        ):
            result = await fetch_inflation_signal()
        assert result is None


class TestEmploymentSignal:
    """FRED UNRATE(미국 실업률) 기반 Sahm Rule-lite 신호 — 최근 12개월 최저치 대비 상승폭 버킷 검증."""

    @staticmethod
    def _make_obs(latest_value: float, historical_low: float) -> list[dict]:
        """FRED desc 정렬 응답을 흉내낸다 — 최신값 1개 + 과거 12개(historical_low 고정)."""
        obs = [{"date": "2026-01-01", "value": str(latest_value)}]
        obs += [{"date": f"2025-{m:02d}-01", "value": str(historical_low)} for m in range(1, 13)]
        return obs

    @pytest.mark.asyncio
    async def test_normal_when_rise_below_0_3pp(self):
        obs = self._make_obs(latest_value=4.1, historical_low=4.0)
        with patch(
            "app.services.economic_indicator_service._fred_get_observations",
            AsyncMock(return_value=obs),
        ):
            result = await fetch_employment_signal()
        assert result is not None
        assert result["level"] == "NORMAL"
        assert result["sub_score"] == 0

    @pytest.mark.asyncio
    async def test_sahm_triggered_between_0_5pp_and_1pp(self):
        obs = self._make_obs(latest_value=4.1, historical_low=3.5)  # rise 0.6pp
        with patch(
            "app.services.economic_indicator_service._fred_get_observations",
            AsyncMock(return_value=obs),
        ):
            result = await fetch_employment_signal()
        assert result is not None
        assert result["level"] == "SAHM_TRIGGERED"
        assert result["sub_score"] == 2

    @pytest.mark.asyncio
    async def test_high_when_rise_at_least_1pp(self):
        obs = self._make_obs(latest_value=4.6, historical_low=3.5)  # rise 1.1pp
        with patch(
            "app.services.economic_indicator_service._fred_get_observations",
            AsyncMock(return_value=obs),
        ):
            result = await fetch_employment_signal()
        assert result is not None
        assert result["level"] == "HIGH"
        assert result["sub_score"] == 4

    @pytest.mark.asyncio
    async def test_returns_none_when_insufficient_history(self):
        obs = [{"date": "2026-01-01", "value": "4.1"}]
        with patch(
            "app.services.economic_indicator_service._fred_get_observations",
            AsyncMock(return_value=obs),
        ):
            result = await fetch_employment_signal()
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_circuit_open(self):
        from app.services import market_signal_service

        with patch.object(market_signal_service.fred_circuit, "is_available", return_value=False):
            result = await fetch_employment_signal()
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
            _rate_curve(0),
            {"sub_score": 0},
            {"sub_score": 0},
            _fx(0),
            {"sub_score": 0},
            {"sub_score": 0},
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

        # 최소 신뢰 기준(4개)은 충족하되 나머지(4개)는 빠진 상태 — PARTIAL로 분류돼야 함.
        # (4개 미만이면 STALE로 재분류됨 — TestDataFreshness 참고)
        partial_signals = (_vix(0), _rate_curve(0), _hy(0), _usd(0), None, None, None, None)
        with patch(
            "app.services.market_signal_service._fetch_all_signals",
            AsyncMock(return_value=partial_signals),
        ):
            result = await get_market_signal(mock_cache)

        assert result["data_freshness"] == "PARTIAL"
        mock_cache.setex.assert_called_once()
        assert mock_cache.setex.call_args[0][1] == TTL_MARKET_SIGNAL_DEGRADED


class TestConfirmedCompositeLevel:
    """AUTO 게이트·등급전환 알림 전용 hysteresis(get_confirmed_composite_level) 검증."""

    @staticmethod
    def _raw_signal(level: str, freshness: str = "LIVE", observed_at: str = "2026-07-23T00:00:00+00:00") -> dict:
        return {"composite_level": level, "data_freshness": freshness, "computed_at": observed_at}

    @pytest.mark.asyncio
    async def test_stale_returns_raw_immediately_without_db_lookup(self, mock_db, mock_cache):
        with patch(
            "app.services.market_signal_service.get_market_signal",
            AsyncMock(return_value=self._raw_signal("RED", "STALE")),
        ):
            level, freshness = await get_confirmed_composite_level(mock_cache, mock_db)
        assert (level, freshness) == ("RED", "STALE")
        mock_db.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_first_run_bootstraps_confirmed_to_raw(self, mock_db, mock_cache):
        mock_db.get = AsyncMock(return_value=None)
        with patch(
            "app.services.market_signal_service.get_market_signal",
            AsyncMock(return_value=self._raw_signal("YELLOW")),
        ):
            level, freshness = await get_confirmed_composite_level(mock_cache, mock_db)
        assert (level, freshness) == ("YELLOW", "LIVE")
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_raw_matches_confirmed_returns_confirmed(self, mock_db, mock_cache):
        from app.models.app_state import AppState

        async def db_get(_model, key):
            if "pending_confirmation" in key:
                return None
            return AppState(key=key, value="GREEN", expires_at=None)

        mock_db.get = AsyncMock(side_effect=db_get)
        with patch(
            "app.services.market_signal_service.get_market_signal",
            AsyncMock(return_value=self._raw_signal("GREEN")),
        ):
            level, freshness = await get_confirmed_composite_level(mock_cache, mock_db)
        assert (level, freshness) == ("GREEN", "LIVE")

    @pytest.mark.asyncio
    async def test_first_deviation_does_not_promote_yet(self, mock_db, mock_cache):
        """confirmed=GREEN인데 raw=RED가 처음 관측되면 아직 승격하지 않고 이전 confirmed를 유지한다."""
        from app.models.app_state import AppState

        async def db_get(_model, key):
            if "pending_confirmation" in key:
                return None
            return AppState(key=key, value="GREEN", expires_at=None)

        mock_db.get = AsyncMock(side_effect=db_get)
        with patch(
            "app.services.market_signal_service.get_market_signal",
            AsyncMock(return_value=self._raw_signal("RED")),
        ):
            level, freshness = await get_confirmed_composite_level(mock_cache, mock_db)
        assert level == "GREEN"

    @pytest.mark.asyncio
    async def test_second_consecutive_deviation_promotes(self, mock_db, mock_cache):
        """연속 2회(CONFIRM_STREAK_REQUIRED) 같은 raw 레벨이 다른 세대에서 관측되면 confirmed로 승격한다."""
        from app.models.app_state import AppState

        pending_value = json.dumps({"candidate": "RED", "streak": 1, "last_observed_at": "2026-07-23T00:00:00+00:00"})

        async def db_get(_model, key):
            if "pending_confirmation" in key:
                return AppState(key=key, value=pending_value, expires_at=None)
            return AppState(key=key, value="GREEN", expires_at=None)

        mock_db.get = AsyncMock(side_effect=db_get)
        with patch(
            "app.services.market_signal_service.get_market_signal",
            AsyncMock(return_value=self._raw_signal("RED", observed_at="2026-07-23T01:00:00+00:00")),
        ):
            level, freshness = await get_confirmed_composite_level(mock_cache, mock_db)
        assert level == "RED"

    @pytest.mark.asyncio
    async def test_duplicate_call_within_same_generation_does_not_double_increment(self, mock_db, mock_cache):
        """같은 raw-fetch 세대(computed_at 동일) 내 중복 호출은 streak을 재증가시키지 않는다."""
        from app.models.app_state import AppState

        observed_at = "2026-07-23T00:00:00+00:00"
        pending_value = json.dumps({"candidate": "RED", "streak": 1, "last_observed_at": observed_at})

        async def db_get(_model, key):
            if "pending_confirmation" in key:
                return AppState(key=key, value=pending_value, expires_at=None)
            return AppState(key=key, value="GREEN", expires_at=None)

        mock_db.get = AsyncMock(side_effect=db_get)
        with patch(
            "app.services.market_signal_service.get_market_signal",
            AsyncMock(return_value=self._raw_signal("RED", observed_at=observed_at)),
        ):
            level, freshness = await get_confirmed_composite_level(mock_cache, mock_db)
        # streak이 1로 유지되어(재증가 없이) CONFIRM_STREAK_REQUIRED(2) 미달 -> 아직 미승격
        assert level == "GREEN"

    @pytest.mark.asyncio
    async def test_candidate_changes_resets_streak(self, mock_db, mock_cache):
        """직전 후보와 다른 raw 레벨이 관측되면 스트릭을 1로 리셋한다."""
        from app.models.app_state import AppState

        pending_value = json.dumps(
            {"candidate": "YELLOW", "streak": 1, "last_observed_at": "2026-07-23T00:00:00+00:00"}
        )

        async def db_get(_model, key):
            if "pending_confirmation" in key:
                return AppState(key=key, value=pending_value, expires_at=None)
            return AppState(key=key, value="GREEN", expires_at=None)

        mock_db.get = AsyncMock(side_effect=db_get)
        with patch(
            "app.services.market_signal_service.get_market_signal",
            AsyncMock(return_value=self._raw_signal("RED", observed_at="2026-07-23T01:00:00+00:00")),
        ):
            level, freshness = await get_confirmed_composite_level(mock_cache, mock_db)
        assert level == "GREEN"  # streak 1(reset)이라 아직 미승격

    @pytest.mark.asyncio
    async def test_fetch_failure_falls_back_to_green_stale(self, mock_db, mock_cache):
        with patch(
            "app.services.market_signal_service.get_market_signal",
            AsyncMock(side_effect=RuntimeError("boom")),
        ):
            level, freshness = await get_confirmed_composite_level(mock_cache, mock_db)
        assert (level, freshness) == ("GREEN", "STALE")
