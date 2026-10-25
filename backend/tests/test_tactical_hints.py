"""전술 배분 국면 전환 조건까지의 거리 안내(tactical_hints)."""

from __future__ import annotations

import pytest

from app.services.tactical_hints import transition_hints


def _snap(close, sma50, sma200, trend):
    return {"close": close, "sma50": sma50, "sma200": sma200, "trend": trend}


class TestTransitionHints:
    def test_unknown_returns_empty(self):
        assert transition_hints(None, "GREEN", "LIVE", {}) == []
        assert transition_hints("RISK_ON", "GREEN", "LIVE", {"SPY": _snap(None, None, None, "UNKNOWN")}) == []

    def test_risk_on_shows_nearest_exit_and_macro(self):
        tech = {
            "SPY": _snap(110.0, 105.0, 100.0, "UP"),  # 이탈선 99 → -10.0%
            "QQQ": _snap(103.0, 101.0, 100.0, "UP"),  # 이탈선 99 → -3.9%
        }
        hints = transition_hints("RISK_ON", "YELLOW", "LIVE", tech)
        assert [h["kind"] for h in hints] == ["TO_NEUTRAL", "TO_RISK_OFF"]
        assert hints[0]["text"].startswith("QQQ")
        assert hints[0]["distance_pct"] == pytest.approx(-3.9)
        assert hints[1]["distance_pct"] is None

    def test_neutral_lists_missing_conditions(self):
        tech = {
            "SPY": _snap(110.0, 105.0, 100.0, "UP"),
            "QQQ": _snap(98.0, 95.0, 100.0, "DOWN"),  # 50일선이 200일선보다 아래
        }
        hints = transition_hints("NEUTRAL", "YELLOW", "LIVE", tech)
        on = next(h for h in hints if h["kind"] == "TO_RISK_ON")
        assert "QQQ 50일선" in on["text"]
        assert "안정" in on["text"]
        off = next(h for h in hints if h["kind"] == "TO_RISK_OFF" and h["text"].startswith("SPY"))
        assert "50일선" in off["text"]  # SPY는 아직 골든크로스 상태 — 교차 조건 안내

    def test_neutral_spy_death_cross_gives_price_distance(self):
        tech = {"SPY": _snap(102.0, 98.0, 100.0, "NEUTRAL"), "QQQ": _snap(110.0, 105.0, 100.0, "UP")}
        hints = transition_hints("NEUTRAL", "GREEN", "LIVE", tech)
        off = next(h for h in hints if h["kind"] == "TO_RISK_OFF" and h["distance_pct"] is not None)
        assert off["distance_pct"] == pytest.approx(-2.0)
        on = next(h for h in hints if h["kind"] == "TO_RISK_ON")
        assert "SPY 50일선" in on["text"]

    def test_stale_macro_noted(self):
        tech = {"SPY": _snap(110.0, 105.0, 100.0, "UP"), "QQQ": _snap(110.0, 105.0, 100.0, "UP")}
        hints = transition_hints("NEUTRAL", "GREEN", "STALE", tech)
        assert "지연" in hints[0]["text"]

    def test_risk_off_recovery_distance(self):
        tech = {"SPY": _snap(95.0, 97.0, 100.0, "DOWN"), "QQQ": _snap(95.0, 97.0, 100.0, "DOWN")}
        hints = transition_hints("RISK_OFF", "RED", "LIVE", tech)
        assert hints[0]["text"].startswith("매크로")
        assert hints[1]["distance_pct"] == pytest.approx(6.3)  # 101 / 95 - 1
        assert transition_hints("RISK_OFF", "YELLOW", "LIVE", tech)[0]["kind"] == "TO_NEUTRAL"
