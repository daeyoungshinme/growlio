"""rebalancing_strategy_service.py 순수 함수 단위 테스트."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.rebalancing.strategy_service import (
    _build_summary,
    _build_trade_recommendations,
    _drift_threshold,
    _factor_reason,
    _overall_direction,
    _per_ticker_factor_reason,
    _sharpe,
)


class TestSharpe:
    def test_positive_result(self):
        result = _sharpe(ret=10.0, risk=5.0)
        assert result == pytest.approx((10.0 - 3.0) / 5.0)

    def test_zero_risk_returns_none(self):
        assert _sharpe(ret=5.0, risk=0.0) is None

    def test_negative_risk_returns_none(self):
        assert _sharpe(ret=5.0, risk=-1.0) is None

    def test_negative_return(self):
        result = _sharpe(ret=1.0, risk=4.0)
        assert result is not None
        assert result < 0


class TestFactorReason:
    def test_positive_delta_positive_label(self):
        changes = {"value": {"delta": 10}, "growth": {"delta": 2}}
        result = _factor_reason(changes)
        assert "가치 팩터 강화" in result

    def test_negative_delta_negative_label(self):
        changes = {"momentum": {"delta": -8}}
        result = _factor_reason(changes)
        assert "모멘텀 팩터 완화" in result

    def test_small_delta_returns_generic(self):
        changes = {"value": {"delta": 3}, "growth": {"delta": -2}}
        result = _factor_reason(changes)
        assert result == "팩터 구성 변화"

    def test_empty_changes(self):
        assert _factor_reason({}) == "팩터 구성 변화"

    def test_multiple_factors(self):
        changes = {
            "value": {"delta": 12},
            "growth": {"delta": -7},
            "size": {"delta": 1},
        }
        result = _factor_reason(changes)
        assert "가치 팩터 강화" in result
        assert "성장 팩터 완화" in result

    def test_unknown_factor_key_uses_raw_key(self):
        changes = {"unknown_factor": {"delta": 15}}
        result = _factor_reason(changes)
        assert "unknown_factor 팩터 강화" in result


class TestBuildTradeRecommendations:
    def _make_item(self, ticker: str, market: str, name: str, weight: float):
        return SimpleNamespace(ticker=ticker, market=market, name=name, weight=weight)

    def test_new_ticker_gets_new_action(self):
        items = [self._make_item("035420", "KOSPI", "NAVER", 30.0)]
        recs = _build_trade_recommendations({}, items, {}, [], [])
        assert len(recs) == 1
        assert recs[0]["action"] == "신규 편입"
        assert recs[0]["ticker"] == "035420"

    def test_below_threshold_skipped(self):
        current = {"005930-KOSPI": {"ticker": "005930", "market": "KOSPI", "name": "삼성전자", "value_krw": 1000000.0}}
        items = [self._make_item("005930", "KOSPI", "삼성전자", 11.5)]  # 10% current, 11.5% target → delta 1.5 < 2
        recs = _build_trade_recommendations(current, items, {}, [], [])
        assert all(r["ticker"] != "005930" or r["action"] != "비중 확대" for r in recs)

    def test_increase_weight(self):
        # 005930 holds 30% of current portfolio, target is 70% → delta +40 → increase
        current = {
            "005930-KOSPI": {"ticker": "005930", "market": "KOSPI", "name": "삼성전자", "value_krw": 3000000.0},
            "035420-KOSPI": {"ticker": "035420", "market": "KOSPI", "name": "NAVER", "value_krw": 7000000.0},
        }
        items = [
            self._make_item("005930", "KOSPI", "삼성전자", 70.0),
            self._make_item("035420", "KOSPI", "NAVER", 30.0),
        ]
        recs = _build_trade_recommendations(current, items, {}, [], [])
        assert any(r["action"] == "비중 확대" for r in recs)

    def test_decrease_weight(self):
        current = {
            "005930-KOSPI": {"ticker": "005930", "market": "KOSPI", "name": "삼성전자", "value_krw": 7000000.0},
            "035420-KOSPI": {"ticker": "035420", "market": "KOSPI", "name": "NAVER", "value_krw": 3000000.0},
        }
        items = [
            self._make_item("005930", "KOSPI", "삼성전자", 40.0),
            self._make_item("035420", "KOSPI", "NAVER", 30.0),
        ]
        recs = _build_trade_recommendations(current, items, {}, [], [])
        assert any(r["action"] == "비중 축소" for r in recs)

    def test_sell_action_for_missing_from_target(self):
        current = {"999999-KOSPI": {"ticker": "999999", "market": "KOSPI", "name": "구종목", "value_krw": 5000000.0}}
        items = []
        recs = _build_trade_recommendations(current, items, {}, [], [])
        assert any(r["action"] == "전량 매도" and r["ticker"] == "999999" for r in recs)

    def test_empty_inputs(self):
        assert _build_trade_recommendations({}, [], {}, [], []) == []

    def test_results_limited_to_10(self):
        items = [self._make_item(f"00{i:04d}", "KOSPI", f"종목{i}", 5.0) for i in range(15)]
        recs = _build_trade_recommendations({}, items, {}, [], [])
        assert len(recs) <= 10


class TestDriftThreshold:
    def test_small_target_weight_uses_floor(self):
        assert _drift_threshold(5.0) == 2.0  # max(2.0, 5.0*0.1=0.5) → 바닥값(2.0)

    def test_large_target_weight_uses_ratio(self):
        assert _drift_threshold(30.0) == 3.0  # max(2.0, 30.0*0.1=3.0) → 비율값(3.0)

    def test_zero_target_weight_uses_floor(self):
        assert _drift_threshold(0.0) == 2.0


class TestPerTickerFactorReason:
    def _holding(self, ticker: str, **scores) -> dict:
        base = {"value_score": 50.0, "growth_score": 50.0, "size_score": 50.0, "momentum_score": 50.0}
        base.update(scores)
        return {"ticker": ticker, **base}

    def test_missing_current_holding_uses_fallback(self):
        target = {"005930": self._holding("005930")}
        result = _per_ticker_factor_reason("005930", {}, target, "폴백")
        assert result == "폴백"

    def test_missing_target_holding_uses_fallback(self):
        current = {"005930": self._holding("005930")}
        result = _per_ticker_factor_reason("005930", current, {}, "폴백")
        assert result == "폴백"

    def test_no_significant_delta_uses_fallback(self):
        current = {"005930": self._holding("005930", value_score=50.0)}
        target = {"005930": self._holding("005930", value_score=52.0)}  # delta=2 <= 5, 무의미
        result = _per_ticker_factor_reason("005930", current, target, "폴백")
        assert result == "폴백"

    def test_largest_delta_used_over_smaller_one(self):
        current = {"005930": self._holding("005930", value_score=50.0, momentum_score=50.0)}
        target = {"005930": self._holding("005930", value_score=60.0, momentum_score=90.0)}
        result = _per_ticker_factor_reason("005930", current, target, "폴백")
        assert "모멘텀 팩터 강화" in result
        assert "가치 팩터 강화" in result
        # 모멘텀(delta=40)이 가치(delta=10)보다 먼저 나와야 한다(내림차순 정렬)
        assert result.index("모멘텀") < result.index("가치")

    def test_negative_delta_is_weakening(self):
        current = {"005930": self._holding("005930", growth_score=70.0)}
        target = {"005930": self._holding("005930", growth_score=40.0)}
        result = _per_ticker_factor_reason("005930", current, target, "폴백")
        assert "성장 팩터 완화" in result

    def test_at_most_two_factors_shown(self):
        current = {"005930": self._holding("005930")}
        target = {
            "005930": {
                "ticker": "005930",
                "value_score": 90.0,
                "growth_score": 90.0,
                "size_score": 90.0,
                "momentum_score": 90.0,
            }
        }
        result = _per_ticker_factor_reason("005930", current, target, "폴백")
        assert result.count("팩터") == 2


class TestBuildTradeRecommendationsPerTickerReason:
    def _make_item(self, ticker: str, market: str, name: str, weight: float):
        return SimpleNamespace(ticker=ticker, market=market, name=name, weight=weight)

    def _holding(self, ticker: str, **scores) -> dict:
        base = {"value_score": 50.0, "growth_score": 50.0, "size_score": 50.0, "momentum_score": 50.0}
        base.update(scores)
        return {"ticker": ticker, **base}

    def test_increase_uses_per_ticker_reason_when_holdings_available(self):
        current_pos = {
            "005930-KOSPI": {"ticker": "005930", "market": "KOSPI", "name": "삼성전자", "value_krw": 3000000.0},
            "035420-KOSPI": {"ticker": "035420", "market": "KOSPI", "name": "NAVER", "value_krw": 7000000.0},
        }
        items = [
            self._make_item("005930", "KOSPI", "삼성전자", 70.0),
            self._make_item("035420", "KOSPI", "NAVER", 30.0),
        ]
        current_holdings = [self._holding("005930", momentum_score=30.0)]
        target_holdings = [self._holding("005930", momentum_score=80.0)]

        recs = _build_trade_recommendations(current_pos, items, {}, current_holdings, target_holdings)

        increase_rec = next(r for r in recs if r["action"] == "비중 확대")
        assert "모멘텀 팩터 강화" in increase_rec["reason"]

    def test_increase_falls_back_to_portfolio_summary_without_holdings(self):
        current_pos = {
            "005930-KOSPI": {"ticker": "005930", "market": "KOSPI", "name": "삼성전자", "value_krw": 3000000.0},
            "035420-KOSPI": {"ticker": "035420", "market": "KOSPI", "name": "NAVER", "value_krw": 7000000.0},
        }
        items = [
            self._make_item("005930", "KOSPI", "삼성전자", 70.0),
            self._make_item("035420", "KOSPI", "NAVER", 30.0),
        ]
        factor_changes = {"value": {"delta": 10}}

        recs = _build_trade_recommendations(current_pos, items, factor_changes, [], [])

        increase_rec = next(r for r in recs if r["action"] == "비중 확대")
        assert "가치 팩터 강화" in increase_rec["reason"]

    def test_decrease_falls_back_to_fixed_text_without_holdings(self):
        current_pos = {
            "005930-KOSPI": {"ticker": "005930", "market": "KOSPI", "name": "삼성전자", "value_krw": 7000000.0},
            "035420-KOSPI": {"ticker": "035420", "market": "KOSPI", "name": "NAVER", "value_krw": 3000000.0},
        }
        items = [
            self._make_item("005930", "KOSPI", "삼성전자", 40.0),
            self._make_item("035420", "KOSPI", "NAVER", 30.0),
        ]

        recs = _build_trade_recommendations(current_pos, items, {}, [], [])

        decrease_rec = next(r for r in recs if r["action"] == "비중 축소")
        assert decrease_rec["reason"] == "리스크 감소 또는 비중 조정"

    def test_relative_threshold_skips_small_delta_on_large_target_weight(self):
        """목표비중 30%에 델타 2.5%p는 기존 고정 임계값(2.0)으로는 포함됐겠지만, 상대 임계값
        max(2.0, 30*0.1=3.0)=3.0보다 작아 이제는 스킵돼야 한다."""
        current_pos = {
            "005930-KOSPI": {"ticker": "005930", "market": "KOSPI", "name": "삼성전자", "value_krw": 2750000.0},
            "035420-KOSPI": {"ticker": "035420", "market": "KOSPI", "name": "NAVER", "value_krw": 7250000.0},
        }
        items = [
            self._make_item("005930", "KOSPI", "삼성전자", 30.0),  # 27.5% → 30.0%, delta=2.5
            self._make_item("035420", "KOSPI", "NAVER", 70.0),
        ]

        recs = _build_trade_recommendations(current_pos, items, {}, [], [])

        assert all(r["ticker"] != "005930" for r in recs)


class TestOverallDirection:
    def test_risk_decrease_sharpe_improve(self):
        result = _overall_direction(risk_change=-3.0, return_change=1.0, sharpe_improvement=True)
        assert result == "리스크 감소형"

    def test_return_increase_no_sharpe(self):
        result = _overall_direction(risk_change=0.5, return_change=3.0, sharpe_improvement=False)
        assert result == "수익 추구형"

    def test_sharpe_improvement(self):
        result = _overall_direction(risk_change=-1.0, return_change=1.0, sharpe_improvement=True)
        assert result == "효율성 개선형"

    def test_balanced_adjustment(self):
        result = _overall_direction(risk_change=0.0, return_change=0.0, sharpe_improvement=False)
        assert result == "균형 조정형"


class TestBuildSummary:
    def test_basic_summary_structure(self):
        changes = {"value": {"delta": 8}}
        result = _build_summary(
            portfolio_name="성장형",
            factor_changes=changes,
            risk_change=1.2,
            return_change=0.5,
            sharpe_improvement=False,
            overall_direction="수익 추구형",
        )
        assert isinstance(result, str)
        assert result.endswith(".")
        assert "'성장형'으로 전환 시" in result
        assert "전환 방향: 수익 추구형" in result

    def test_risk_change_shown_above_threshold(self):
        result = _build_summary(
            portfolio_name="테스트",
            factor_changes={},
            risk_change=-2.5,
            return_change=0.0,
            sharpe_improvement=False,
            overall_direction="리스크 감소형",
        )
        assert "변동성이 2.5%p 감소하고" in result

    def test_risk_change_below_threshold_omitted(self):
        result = _build_summary(
            portfolio_name="테스트",
            factor_changes={},
            risk_change=0.3,
            return_change=0.0,
            sharpe_improvement=False,
            overall_direction="균형 조정형",
        )
        assert "변동성" not in result

    def test_sharpe_improvement_mentioned(self):
        result = _build_summary(
            portfolio_name="테스트",
            factor_changes={},
            risk_change=0.0,
            return_change=0.0,
            sharpe_improvement=True,
            overall_direction="효율성 개선형",
        )
        assert "위험 대비 수익률(Sharpe)이 개선됩니다" in result

    def test_sharpe_not_mentioned_when_no_improvement(self):
        result = _build_summary(
            portfolio_name="테스트",
            factor_changes={},
            risk_change=0.0,
            return_change=0.0,
            sharpe_improvement=False,
            overall_direction="균형 조정형",
        )
        assert "Sharpe" not in result

    def test_improving_factors_mentioned(self):
        changes = {"growth": {"delta": 12}}
        result = _build_summary(
            portfolio_name="테스트",
            factor_changes=changes,
            risk_change=0.0,
            return_change=0.0,
            sharpe_improvement=False,
            overall_direction="균형 조정형",
        )
        assert "성장 팩터 노출도가 강화됩니다" in result

    def test_small_factor_delta_not_mentioned(self):
        changes = {"growth": {"delta": 4}}
        result = _build_summary(
            portfolio_name="테스트",
            factor_changes=changes,
            risk_change=0.0,
            return_change=0.0,
            sharpe_improvement=False,
            overall_direction="균형 조정형",
        )
        assert "팩터 노출도가 강화됩니다" not in result
