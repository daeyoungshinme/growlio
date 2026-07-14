"""rebalancing_strategy_service.py 순수 함수 단위 테스트."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.rebalancing.strategy_service import (
    _build_summary,
    _build_trade_recommendations,
    _factor_reason,
    _overall_direction,
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
        recs = _build_trade_recommendations({}, items, {})
        assert len(recs) == 1
        assert recs[0]["action"] == "신규 편입"
        assert recs[0]["ticker"] == "035420"

    def test_below_threshold_skipped(self):
        current = {"005930-KOSPI": {"ticker": "005930", "market": "KOSPI", "name": "삼성전자", "value_krw": 1000000.0}}
        items = [self._make_item("005930", "KOSPI", "삼성전자", 11.5)]  # 10% current, 11.5% target → delta 1.5 < 2
        recs = _build_trade_recommendations(current, items, {})
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
        recs = _build_trade_recommendations(current, items, {})
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
        recs = _build_trade_recommendations(current, items, {})
        assert any(r["action"] == "비중 축소" for r in recs)

    def test_sell_action_for_missing_from_target(self):
        current = {"999999-KOSPI": {"ticker": "999999", "market": "KOSPI", "name": "구종목", "value_krw": 5000000.0}}
        items = []
        recs = _build_trade_recommendations(current, items, {})
        assert any(r["action"] == "전량 매도" and r["ticker"] == "999999" for r in recs)

    def test_empty_inputs(self):
        assert _build_trade_recommendations({}, [], {}) == []

    def test_results_limited_to_10(self):
        items = [self._make_item(f"00{i:04d}", "KOSPI", f"종목{i}", 5.0) for i in range(15)]
        recs = _build_trade_recommendations({}, items, {})
        assert len(recs) <= 10


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
