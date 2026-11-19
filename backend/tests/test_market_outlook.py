"""시장 종합 판단(plans/137 B) — 표시 전용, 자동 실행 게이트·전술 국면과 무관."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.services.market_signal.market_outlook import build_market_outlook, classify_breadth
from tests.api_helpers import make_user


def _tech(qqq: str, spy: str, dia: str, dd: float | None = -3.0) -> dict:
    return {t: {"trend": tr, "drawdown_pct": dd} for t, tr in (("QQQ", qqq), ("SPY", spy), ("DIA", dia))}


def _signal(level: str, freshness: str = "LIVE") -> dict:
    return {"composite_level": level, "composite_score": 3, "composite_score_max": 27, "data_freshness": freshness}


class TestClassifyBreadth:
    def test_majority_up(self):
        assert classify_breadth({"QQQ": "UP", "SPY": "UP", "DIA": "NEUTRAL"}) == ("UP", 2, 3)

    def test_majority_down(self):
        assert classify_breadth({"QQQ": "DOWN", "SPY": "DOWN", "DIA": "UP"}) == ("DOWN", 1, 3)

    def test_mixed(self):
        assert classify_breadth({"QQQ": "UP", "SPY": "NEUTRAL", "DIA": "DOWN"}) == ("MIXED", 1, 3)

    def test_unknown_excluded_from_count(self):
        # 판정 가능한 2개 중 1개만 상승 — 과반이 아니므로 혼조
        assert classify_breadth({"QQQ": "UP", "SPY": "DOWN", "DIA": "UNKNOWN"}) == ("MIXED", 1, 2)

    def test_too_few_known(self):
        assert classify_breadth({"QQQ": "UP", "SPY": "UNKNOWN", "DIA": "UNKNOWN"}) == (None, 1, 1)


class TestBuildMarketOutlookMatrix:
    @pytest.mark.parametrize(
        ("level", "trends", "verdict"),
        [
            ("GREEN", ("UP", "UP", "UP"), "FAVORABLE"),
            ("GREEN", ("UP", "NEUTRAL", "DOWN"), "STEADY"),
            ("GREEN", ("DOWN", "DOWN", "UP"), "STEADY"),
            ("YELLOW", ("UP", "UP", "DOWN"), "STEADY"),
            ("YELLOW", ("UP", "NEUTRAL", "DOWN"), "CAUTION"),
            ("YELLOW", ("DOWN", "DOWN", "DOWN"), "CAUTION"),
            ("RED", ("UP", "UP", "UP"), "CAUTION"),
            ("RED", ("UP", "NEUTRAL", "DOWN"), "DEFENSIVE"),
            ("RED", ("DOWN", "DOWN", "NEUTRAL"), "DEFENSIVE"),
        ],
    )
    def test_matrix(self, level, trends, verdict):
        result = build_market_outlook(_signal(level), _tech(*trends))
        assert result["verdict"] == verdict
        assert result["macro_level"] == level
        assert result["action"]

    def test_trend_unknown_falls_back_to_macro_mixed(self):
        result = build_market_outlook(_signal("GREEN"), _tech("UNKNOWN", "UNKNOWN", "UP"))
        assert result["verdict"] == "STEADY"
        assert result["trend_breadth"] is None
        assert any("추세 확인 불가" in r for r in result["reasons"])

    def test_stale_macro_uses_trend_only(self):
        result = build_market_outlook(_signal("GREEN", freshness="STALE"), _tech("DOWN", "DOWN", "DOWN"))
        assert result["verdict"] == "CAUTION"
        assert result["macro_level"] is None
        assert "매크로 데이터를 받지 못했어요" in result["reasons"]

    def test_nothing_available(self):
        result = build_market_outlook({}, {})
        assert result["verdict"] == "UNKNOWN"
        assert result["label"] == "판단 보류"

    def test_drawdown_reasons(self):
        bear = build_market_outlook(_signal("GREEN"), _tech("UP", "UP", "UP", dd=-22.0))
        assert any("약세장" in r for r in bear["reasons"])
        assert bear["deepest_drawdown_pct"] == -22.0
        # 조정 깊이는 근거만 바꾸고 판정 칸은 그대로
        assert bear["verdict"] == "FAVORABLE"
        correction = build_market_outlook(_signal("GREEN"), _tech("UP", "UP", "UP", dd=-12.0))
        assert any("조정 구간" in r for r in correction["reasons"])

    def test_reason_names_all_three_indexes(self):
        result = build_market_outlook(_signal("YELLOW"), _tech("UP", "UP", "NEUTRAL"))
        trend_reason = result["reasons"][1]
        assert "나스닥100 상승" in trend_reason
        assert "다우 혼조" in trend_reason


class TestOutlookEndpoint:
    @pytest.fixture(autouse=True)
    def app(self, override_settings):
        from app.api.deps import get_current_user
        from app.main import app

        async def override_auth():
            return make_user()

        app.dependency_overrides[get_current_user] = override_auth
        yield app
        app.dependency_overrides.pop(get_current_user, None)

    def test_combines_cached_inputs(self, app):
        with (
            patch("app.api.v1.market_signals.get_market_signal", new=AsyncMock(return_value=_signal("RED"))),
            patch(
                "app.api.v1.market_signals.get_technical_signals",
                new=AsyncMock(return_value=_tech("DOWN", "DOWN", "DOWN")),
            ),
            TestClient(app) as client,
        ):
            resp = client.get("/api/v1/market-signals/outlook")
        assert resp.status_code == 200
        body = resp.json()
        assert body["verdict"] == "DEFENSIVE"
        assert body["trends"] == {"QQQ": "DOWN", "SPY": "DOWN", "DIA": "DOWN"}

    def test_partial_failure_still_answers(self, app):
        with (
            patch("app.api.v1.market_signals.get_market_signal", new=AsyncMock(side_effect=RuntimeError("fred"))),
            patch(
                "app.api.v1.market_signals.get_technical_signals",
                new=AsyncMock(return_value=_tech("UP", "UP", "UP")),
            ),
            TestClient(app) as client,
        ):
            resp = client.get("/api/v1/market-signals/outlook")
        assert resp.status_code == 200
        assert resp.json()["verdict"] == "STEADY"


class TestValueNBack:
    def test_skips_missing_and_counts_from_latest(self):
        from app.services.market_signal.market_signal_indicators import _value_n_back

        obs = [{"value": "20"}, {"value": "."}, {"value": "18"}, {"value": "15"}]
        assert _value_n_back(obs, 0) == 20.0
        assert _value_n_back(obs, 2) == 15.0
        assert _value_n_back(obs, 3) is None
