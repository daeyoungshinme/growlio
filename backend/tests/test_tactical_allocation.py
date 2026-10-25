"""QQQ/SPY 전술 배분 — 기술적 지표, 국면 판정·확정, 나스닥/S&P 틸트, 비중표 검증, 규칙 백테스트, API, 일일 점검 job."""

from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.models.tactical import TacticalStrategy
from app.services import tactical_allocation_service as tactical
from app.services import tactical_tilt as tilt
from app.services import technical_indicators as ti
from app.services.tactical_backtest import simulate, vix_to_macro_level

# ---------------------------------------------------------------------------
# 기술적 지표
# ---------------------------------------------------------------------------


def _series(values) -> pd.Series:
    return pd.Series(values, index=pd.bdate_range("2020-01-01", periods=len(values)), dtype=float)


class TestIndicators:
    def test_sma_and_short_history(self):
        s = _series(range(1, 11))
        assert ti.sma(s, 5) == pytest.approx(8.0)
        assert ti.sma(s, 50) is None

    def test_rsi_extremes(self):
        assert ti.rsi(_series(range(1, 40))) == 100.0
        assert ti.rsi(_series(range(40, 1, -1))) == pytest.approx(0.0)
        assert ti.rsi(_series([1, 2])) is None

    def test_macd_sign_follows_trend(self):
        up = _series(np.linspace(100, 200, 80))
        assert ti.macd_histogram(_series(list(up) + [150] * 5)) < 0
        assert ti.macd_histogram(_series([1.0] * 10)) is None

    def test_drawdown(self):
        assert ti.drawdown_from_high_pct(_series([100, 120, 90])) == pytest.approx(-25.0)

    @pytest.mark.parametrize(
        ("close", "s50", "s200", "expected"),
        [
            (110, 105, 100, "UP"),
            (90, 95, 100, "DOWN"),
            (110, 95, 100, "NEUTRAL"),  # 200일선 위지만 데드크로스 상태
            (None, 1, 1, "UNKNOWN"),
        ],
    )
    def test_classify_trend(self, close, s50, s200, expected):
        assert ti.classify_trend(close, s50, s200) == expected

    def test_trend_band_keeps_state_near_sma200(self):
        # 200일선을 0.5% 밑돈 종가: 직전이 UP이면 밴드(1%) 안이라 UP 유지, 직전 상태가 없으면 NEUTRAL
        assert ti.classify_trend(99.5, 105, 100, prev="UP") == "UP"
        assert ti.classify_trend(99.5, 105, 100) == "NEUTRAL"
        assert ti.classify_trend(98.9, 105, 100, prev="UP") == "NEUTRAL"  # 밴드 밖으로 이탈
        assert ti.classify_trend(100.5, 95, 100, prev="DOWN") == "DOWN"
        assert ti.classify_trend(99.5, 95, 100, prev="UP") == "DOWN"  # 데드크로스면 밴드와 무관

    def test_snapshot_uptrend(self):
        snap = ti.compute_snapshot(_series(np.linspace(100, 300, 260)))
        assert snap["trend"] == "UP"
        assert snap["drawdown_pct"] == pytest.approx(0.0)

    def test_trend_series_has_no_lookahead(self):
        values = list(np.linspace(100, 300, 250)) + list(np.linspace(300, 50, 150))
        states = ti.trend_series(_series(values))
        assert states.iloc[:199].eq("UNKNOWN").all()  # 200일선이 생기기 전
        assert states.iloc[249] == "UP"
        assert states.iloc[-1] == "DOWN"


# ---------------------------------------------------------------------------
# 국면 판정 / 확정
# ---------------------------------------------------------------------------


class TestClassifyRegime:
    @pytest.mark.parametrize(
        ("macro", "fresh", "spy", "qqq", "expected"),
        [
            ("GREEN", "LIVE", "UP", "UP", "RISK_ON"),
            ("GREEN", "LIVE", "UP", "NEUTRAL", "NEUTRAL"),
            ("YELLOW", "LIVE", "UP", "UP", "NEUTRAL"),
            ("RED", "LIVE", "UP", "UP", "RISK_OFF"),
            ("GREEN", "LIVE", "DOWN", "UP", "RISK_OFF"),
            ("GREEN", "STALE", "UP", "UP", "NEUTRAL"),  # 매크로 지연이면 공격 국면 금지
            ("RED", "STALE", "UP", "UP", "NEUTRAL"),  # 지연된 RED만으로 방어 전환하지 않음
            ("GREEN", "LIVE", "UNKNOWN", "UNKNOWN", None),
        ],
    )
    def test_rules(self, macro, fresh, spy, qqq, expected):
        regime, reasons = tactical.classify_regime(macro, fresh, {"SPY": spy, "QQQ": qqq})
        assert regime == expected
        assert reasons

    @pytest.mark.parametrize(
        ("macro", "fresh", "spy", "qqq", "expected"),
        [
            ("YELLOW", "LIVE", "UP", "UP", "RISK_ON"),  # 이미 공격 국면이면 '주의'에서 유지
            ("GREEN", "STALE", "UP", "UP", "RISK_ON"),  # 지연 데이터로 신규 진입은 막지만 유지는 허용
            ("RED", "LIVE", "UP", "UP", "RISK_OFF"),
            ("YELLOW", "LIVE", "UP", "NEUTRAL", "NEUTRAL"),  # 추세가 깨지면 이탈
        ],
    )
    def test_risk_on_hysteresis(self, macro, fresh, spy, qqq, expected):
        regime, _ = tactical.classify_regime(macro, fresh, {"SPY": spy, "QQQ": qqq}, prev="RISK_ON")
        assert regime == expected

    def test_observed_for_uses_prev(self):
        market = {
            "observed_regime": "NEUTRAL",
            "reasons": ["a"],
            "observed_if_risk_on": "RISK_ON",
            "reasons_if_risk_on": ["b"],
        }
        assert tactical.observed_for(market, "RISK_ON") == ("RISK_ON", ["b"])
        assert tactical.observed_for(market, "NEUTRAL") == ("NEUTRAL", ["a"])
        assert tactical.observed_for({"observed_regime": "NEUTRAL", "reasons": []}, "RISK_ON")[0] == "NEUTRAL"


def _strategy(**kw) -> TacticalStrategy:
    s = TacticalStrategy(user_id=uuid.uuid4(), portfolio_id=uuid.uuid4())
    s.notify_enabled = True
    for k, v in kw.items():
        setattr(s, k, v)
    return s


def _m(observed):
    return {"observed_regime": observed, "reasons": []}


class TestAdvanceRegime:
    def test_first_observation_confirms_immediately(self):
        s = _strategy(last_regime=None)
        assert tactical.advance_regime(s, _m("NEUTRAL"), date(2026, 10, 1)) is True
        assert s.last_regime == "NEUTRAL"

    def test_needs_two_distinct_days(self):
        s = _strategy(last_regime="RISK_ON")
        d1, d2 = date(2026, 10, 1), date(2026, 10, 2)
        assert tactical.advance_regime(s, _m("RISK_OFF"), d1) is False
        assert tactical.advance_regime(s, _m("RISK_OFF"), d1) is False  # 같은 날 반복 조회는 확정 안 됨
        assert s.last_regime == "RISK_ON"
        assert tactical.advance_regime(s, _m("RISK_OFF"), d2) is True
        assert s.last_regime == "RISK_OFF"
        assert s.pending_regime is None

    def test_reverting_clears_pending(self):
        s = _strategy(last_regime="RISK_ON")
        tactical.advance_regime(s, _m("NEUTRAL"), date(2026, 10, 1))
        tactical.advance_regime(s, _m("RISK_ON"), date(2026, 10, 2))
        assert s.pending_regime is None
        assert tactical.advance_regime(s, _m("NEUTRAL"), date(2026, 10, 3)) is False

    def test_unknown_observation_keeps_state(self):
        s = _strategy(last_regime="RISK_ON")
        assert tactical.advance_regime(s, _m(None), date(2026, 10, 1)) is False
        assert s.last_regime == "RISK_ON"


class TestTilt:
    @pytest.mark.parametrize(
        ("chg", "rs", "expected"),
        [
            (0.30, -0.5, "FAVOR_SPY"),  # 실질금리 급등 + 나스닥 열위
            (0.30, 2.0, "BALANCED"),  # 금리는 올랐지만 나스닥이 여전히 앞섬
            (-0.10, 1.5, "FAVOR_QQQ"),
            (0.05, 1.5, "BALANCED"),  # 실질금리 상승 중엔 나스닥 우위 주지 않음
            (-0.10, 0.5, "BALANCED"),
            (None, 2.0, "BALANCED"),
            (-0.1, None, "BALANCED"),
        ],
    )
    def test_classify(self, chg, rs, expected):
        assert tilt.classify_tilt(chg, rs) == expected

    def test_apply_moves_within_equity_and_clamps(self):
        w = {"QQQ": 10.0, "SPY": 30.0, "CASH": 60.0}
        assert tilt.apply_tilt(w, "FAVOR_QQQ", 10) == {"QQQ": 20.0, "SPY": 20.0, "CASH": 60.0}
        assert tilt.apply_tilt(w, "FAVOR_SPY", 15) == {"QQQ": 0.0, "SPY": 40.0, "CASH": 60.0}  # QQQ 10만 이동
        assert tilt.apply_tilt(w, "FAVOR_QQQ", 0) == w
        assert tilt.apply_tilt(w, "BALANCED", 10) == w
        assert tilt.apply_tilt(w, None, 10) == w

    def test_inputs_math(self):
        qqq = _series([100.0] * 49 + [110.0])
        spy = _series([100.0] * 50)
        assert tilt.relative_strength_pct(qqq, spy) == pytest.approx((1.1 / (49 + 1.1) * 50 - 1) * 100)
        assert tilt.relative_strength_pct(qqq.iloc[:10], spy.iloc[:10]) is None
        assert tilt.real_yield_change([1.0] * 20 + [1.3]) == pytest.approx(0.3)
        assert tilt.real_yield_change([1.0] * 20) is None

    def test_is_new_month(self):
        assert tilt.is_new_month(None, date(2026, 10, 1))
        assert tilt.is_new_month(date(2026, 9, 30), date(2026, 10, 1))
        assert not tilt.is_new_month(date(2026, 10, 1), date(2026, 10, 31))

    def test_advance_tilt_monthly(self):
        s = _strategy(last_tilt=None, tilt_evaluated_on=None)
        market = {"tilt_inputs_complete": True, "observed_tilt": "FAVOR_SPY"}
        assert tactical.advance_tilt(s, market, date(2026, 10, 3)) is True
        assert s.last_tilt == "FAVOR_SPY"
        # 같은 달 안에서는 판정이 바뀌어도 유지
        assert tactical.advance_tilt(s, {**market, "observed_tilt": "FAVOR_QQQ"}, date(2026, 10, 20)) is False
        assert s.last_tilt == "FAVOR_SPY"
        # 입력 결측이면 이번 달 판정을 미루고 다음 점검에서 재시도
        assert tactical.advance_tilt(s, {"tilt_inputs_complete": False}, date(2026, 11, 1)) is False
        assert tactical.advance_tilt(s, {**market, "observed_tilt": "BALANCED"}, date(2026, 11, 2)) is True
        assert s.last_tilt == "BALANCED"
        assert s.tilt_evaluated_on == date(2026, 11, 2)

    def test_proposed_weights_apply_confirmed_tilt(self):
        s = _strategy(last_tilt="FAVOR_QQQ", tilt_shift_pct=10)
        expected = {"QQQ": 40.0, "SPY": 30.0, "DIA": 0.0, "QLD": 0.0, "SSO": 0.0, "CASH": 30.0}
        assert tactical.proposed_weights_for(s, "NEUTRAL", {}) == expected
        # 전략이 없으면 오늘 판정으로 미리보기, 이동폭은 기본값
        preview = tactical.proposed_weights_for(None, "NEUTRAL", {"observed_tilt": "FAVOR_SPY"})
        assert preview == {"QQQ": 20.0, "SPY": 50.0, "DIA": 0.0, "QLD": 0.0, "SSO": 0.0, "CASH": 30.0}
        assert tactical.tilt_shift_of(_strategy(tilt_shift_pct=None)) == tilt.DEFAULT_TILT_SHIFT_PCT

    def test_reasons_mention_missing_data(self):
        inputs = tilt.TiltInputs(real_yield=None, real_yield_change_pp=None, relative_strength_pct=1.2)
        reasons = tilt.tilt_reasons(inputs, "BALANCED")
        assert "확인 불가" in reasons[0]
        assert "+1.2%" in reasons[1]

    @pytest.mark.asyncio
    async def test_get_inputs_caches_only_complete(self):
        from app.core.cache_store import CacheStore

        closes = _trend_closes(120)
        closes["QQQ"] = closes["QQQ"] * np.linspace(1.0, 1.2, 120)  # 나스닥 우위
        cache = CacheStore()
        fetch = AsyncMock(return_value=closes)
        with (
            patch("app.services.technical_signal_service.fetch_close_history", fetch),
            patch.object(tilt, "_fetch_real_yields", AsyncMock(side_effect=RuntimeError("fred"))),
        ):
            partial = await tilt.get_tilt_inputs(cache)
        assert partial["real_yield"] is None
        assert partial["relative_strength_pct"] > 0
        with (
            patch("app.services.technical_signal_service.fetch_close_history", fetch),
            patch.object(tilt, "_fetch_real_yields", AsyncMock(return_value=[2.0] * 20 + [1.8])),
        ):
            full = await tilt.get_tilt_inputs(cache)
            again = await tilt.get_tilt_inputs(cache)
        assert full["real_yield_change_pp"] == pytest.approx(-0.2)
        assert again == full
        assert fetch.await_count == 2  # 부분 실패 결과는 캐시하지 않아 재조회, 완전한 결과는 캐시

    @pytest.mark.asyncio
    async def test_get_inputs_survive_price_failure(self):
        with (
            patch(
                "app.services.technical_signal_service.fetch_close_history",
                AsyncMock(side_effect=RuntimeError("yahoo")),
            ),
            patch.object(tilt, "_fetch_real_yields", AsyncMock(return_value=[])),
        ):
            result = await tilt.get_tilt_inputs(None)
        assert result == {"real_yield": None, "real_yield_change_pp": None, "relative_strength_pct": None}


class TestWeights:
    def test_valid_table_fills_missing_assets(self):
        raw = {"RISK_ON": {"QQQ": 100}, "NEUTRAL": {"SPY": 50, "CASH": 50}, "RISK_OFF": {"CASH": 100}}
        out = tactical.validate_regime_weights(raw)
        assert out["RISK_ON"] == {"QQQ": 100.0, "SPY": 0.0, "DIA": 0.0, "QLD": 0.0, "SSO": 0.0, "CASH": 0.0}

    @pytest.mark.parametrize(
        "raw",
        [
            {"RISK_ON": {"QQQ": 100}},  # 국면 누락
            {"RISK_ON": {"TQQQ": 100}, "NEUTRAL": {"SPY": 100}, "RISK_OFF": {"CASH": 100}},  # 허용 외 자산
            {"RISK_ON": {"QQQ": 90}, "NEUTRAL": {"SPY": 100}, "RISK_OFF": {"CASH": 100}},  # 합계 ≠ 100
            {"RISK_ON": {"QQQ": 110, "CASH": -10}, "NEUTRAL": {"SPY": 100}, "RISK_OFF": {"CASH": 100}},
        ],
    )
    def test_invalid_tables(self, raw):
        with pytest.raises(ValueError, match="비중|국면"):
            tactical.validate_regime_weights(raw)

    def test_invalid_stored_table_falls_back_to_default(self):
        assert tactical.resolve_weights(_strategy(regime_weights={"bad": {}})) is tactical.DEFAULT_REGIME_WEIGHTS

    def test_format(self):
        assert tactical.format_weights({"QQQ": 50, "SPY": 40, "CASH": 10}) == "QQQ 50% · SPY 40% · 현금 10%"

    def test_format_shows_dia_only_when_held(self):
        assert tactical.format_weights({"QQQ": 0, "SPY": 40, "DIA": 0, "CASH": 60}) == "QQQ 0% · SPY 40% · 현금 60%"
        assert (
            tactical.format_weights({"QQQ": 40, "SPY": 30, "DIA": 20, "CASH": 10})
            == "QQQ 40% · SPY 30% · DIA 20% · 현금 10%"
        )

    def test_dia_table_accepted_and_legacy_table_fills_zero(self):
        table = tactical.validate_regime_weights(
            {
                "RISK_ON": {"QQQ": 40, "SPY": 30, "DIA": 20, "CASH": 10},
                "NEUTRAL": {"QQQ": 30, "SPY": 40, "CASH": 30},  # DIA 없는 기존 저장값
                "RISK_OFF": {"CASH": 100},
            }
        )
        assert table["RISK_ON"]["DIA"] == 20.0
        assert table["NEUTRAL"]["DIA"] == 0.0

    def test_tilt_keeps_dia_share(self):
        out = tilt.apply_tilt({"QQQ": 40, "SPY": 30, "DIA": 20, "CASH": 10}, "FAVOR_QQQ", 10)
        assert out == {"QQQ": 50, "SPY": 20, "DIA": 20, "CASH": 10}


# ---------------------------------------------------------------------------
# 백테스트 시뮬레이션
# ---------------------------------------------------------------------------


class TestSimulate:
    def test_vix_levels(self):
        assert vix_to_macro_level(15) == "GREEN"
        assert vix_to_macro_level(25) == "YELLOW"
        assert vix_to_macro_level(35) == "RED"
        assert vix_to_macro_level(None) == "YELLOW"

    def test_crash_moves_to_defense_and_cuts_drawdown(self):
        up = list(np.linspace(100, 300, 400))
        crash = list(np.linspace(300, 120, 150))
        idx = pd.bdate_range("2015-01-01", periods=len(up) + len(crash))
        closes = pd.DataFrame({"QQQ": up + crash, "SPY": up + crash}, index=idx)
        vix = pd.Series(15.0, index=idx)

        result = simulate(closes, vix, tactical.DEFAULT_REGIME_WEIGHTS, idx[250])

        by_name = {m["name"]: m for m in result["metrics"]}
        strat, spy = by_name["전술 배분"], by_name["SPY 보유"]
        assert result["regime_time_pct"]["RISK_OFF"] > 0
        assert strat["mdd_pct"] < spy["mdd_pct"]
        assert result["regime_switches"] >= 1
        assert result["series"][-1]["date"] == idx[-1].date().isoformat()

    def test_tilt_shifts_toward_leader_monthly(self):
        idx = pd.bdate_range("2015-01-01", periods=700)
        base = np.linspace(100, 300, 700)
        closes = pd.DataFrame({"QQQ": base * np.linspace(1.0, 1.5, 700), "SPY": base}, index=idx)
        vix = pd.Series(15.0, index=idx)
        falling_yield = pd.Series(np.linspace(2.0, 0.5, 700), index=idx)

        off = simulate(closes, vix, tactical.DEFAULT_REGIME_WEIGHTS, idx[300])
        on = simulate(
            closes, vix, tactical.DEFAULT_REGIME_WEIGHTS, idx[300], real_yield=falling_yield, tilt_shift_pct=10
        )
        assert off["tilt_switches"] == 0
        assert off["tilt_time_pct"]["BALANCED"] == 100.0
        assert on["tilt_time_pct"]["FAVOR_QQQ"] > 90
        assert on["metrics"][0]["total_return_pct"] > off["metrics"][0]["total_return_pct"]

    def test_dia_benchmark_and_holding(self):
        idx = pd.bdate_range("2015-01-01", periods=600)
        up = np.linspace(100, 300, 600)
        closes = pd.DataFrame({"QQQ": up, "SPY": up, "DIA": up * 2}, index=idx)
        vix = pd.Series(15.0, index=idx)
        table = {r: {"QQQ": 0.0, "SPY": 0.0, "DIA": 100.0, "CASH": 0.0} for r in tactical.REGIMES}

        result = simulate(closes, vix, table, idx[300])

        assert [m["name"] for m in result["metrics"]][1:] == ["평균 비중 고정", "SPY 보유", "QQQ 보유", "DIA 보유"]
        assert "dia" in result["series"][0]
        # DIA 100% 보유 — 첫 국면 확정(2거래일) 이후 DIA 수익률을 따라간다
        assert result["metrics"][0]["total_return_pct"] > 0

    def test_dia_weight_without_dia_prices_raises(self):
        idx = pd.bdate_range("2015-01-01", periods=600)
        closes = pd.DataFrame({"QQQ": np.linspace(100, 300, 600), "SPY": np.linspace(100, 300, 600)}, index=idx)
        table = {r: {"QQQ": 50.0, "SPY": 30.0, "DIA": 20.0, "CASH": 0.0} for r in tactical.REGIMES}
        with pytest.raises(ValueError, match="DIA"):
            simulate(closes, pd.Series(15.0, index=idx), table, idx[300])
        # DIA 0%면 DIA 시세 없이도 계산되고 DIA 비교는 빠진다
        default = simulate(closes, pd.Series(15.0, index=idx), tactical.DEFAULT_REGIME_WEIGHTS, idx[300])
        assert len(default["metrics"]) == 4  # 전술·평균 비중 고정·SPY·QQQ
        assert "dia" not in default["series"][0]

    def test_too_short_period_raises(self):
        idx = pd.bdate_range("2020-01-01", periods=10)
        closes = pd.DataFrame({"QQQ": range(10), "SPY": range(10)}, index=idx, dtype=float)
        with pytest.raises(ValueError, match="부족"):
            simulate(closes, pd.Series(dtype=float), tactical.DEFAULT_REGIME_WEIGHTS, idx[-1])


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

_MARKET = {
    "macro_level": "GREEN",
    "macro_freshness": "LIVE",
    "technicals": {},
    "observed_regime": "RISK_ON",
    "reasons": ["r"],
}


def _user():
    return SimpleNamespace(id=uuid.uuid4(), email="t@example.com", is_active=True, needs_password_reset=False)


def _portfolio(items=()):
    return SimpleNamespace(id=uuid.uuid4(), name="미국 전술", items=list(items))


def _setup(user, db):
    from app.api.deps import get_current_user
    from app.core.database import get_db
    from app.main import app

    async def _auth():
        return user

    async def _db():
        yield db

    app.dependency_overrides[get_current_user] = _auth
    app.dependency_overrides[get_db] = _db
    return app


@pytest.fixture
def api_db():
    from sqlalchemy.ext.asyncio import AsyncSession

    db = AsyncMock(spec=AsyncSession)
    db.add = MagicMock()
    db.expire = MagicMock()
    return db


class TestTacticalApi:
    def test_status_404_for_foreign_portfolio(self, api_db):
        app = _setup(_user(), api_db)
        with (
            patch.object(tactical, "get_owned_portfolio", AsyncMock(return_value=None)),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            assert client.get(f"/api/v1/tactical/{uuid.uuid4()}").status_code == 404

    def test_status_without_strategy_proposes_observed_regime(self, api_db):
        app = _setup(_user(), api_db)
        portfolio = _portfolio([SimpleNamespace(ticker="AAPL", weight=100)])
        with (
            patch.object(tactical, "get_owned_portfolio", AsyncMock(return_value=portfolio)),
            patch.object(tactical, "get_strategy", AsyncMock(return_value=None)),
            patch.object(tactical, "evaluate_market", AsyncMock(return_value=_MARKET)),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            body = client.get(f"/api/v1/tactical/{portfolio.id}").json()
        assert body["enabled"] is False
        assert body["proposed_weights"] == tactical.DEFAULT_REGIME_WEIGHTS["RISK_ON"]
        assert body["confirmed_tilt"] == "BALANCED"
        assert body["tilt_shift_pct"] == tilt.DEFAULT_TILT_SHIFT_PCT
        assert body["portfolio_compatible"] is False
        api_db.commit.assert_not_awaited()

    def test_upsert_creates_strategy_without_initial_alert(self, api_db):
        app = _setup(_user(), api_db)
        portfolio = _portfolio()
        with (
            patch.object(tactical, "get_owned_portfolio", AsyncMock(return_value=portfolio)),
            patch.object(tactical, "get_strategy", AsyncMock(return_value=None)),
            patch.object(tactical, "evaluate_market", AsyncMock(return_value=_MARKET)),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.put(f"/api/v1/tactical/{portfolio.id}", json={"notify_enabled": True})
        assert resp.status_code == 200
        created: TacticalStrategy = api_db.add.call_args.args[0]
        assert created.last_regime == "RISK_ON"
        assert created.notified_regime == "RISK_ON"
        assert resp.json()["confirmed_regime"] == "RISK_ON"

    def test_upsert_saves_tilt_shift_and_rejects_out_of_range(self, api_db):
        app = _setup(_user(), api_db)
        portfolio = _portfolio()
        with (
            patch.object(tactical, "get_owned_portfolio", AsyncMock(return_value=portfolio)),
            patch.object(tactical, "get_strategy", AsyncMock(return_value=None)),
            patch.object(tactical, "evaluate_market", AsyncMock(return_value=_MARKET)),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            ok = client.put(f"/api/v1/tactical/{portfolio.id}", json={"notify_enabled": True, "tilt_shift_pct": 15})
            bad = client.put(f"/api/v1/tactical/{portfolio.id}", json={"tilt_shift_pct": 25})
        assert ok.status_code == 200
        assert ok.json()["tilt_shift_pct"] == 15.0
        assert float(api_db.add.call_args_list[0].args[0].tilt_shift_pct) == 15.0
        assert bad.status_code == 422

    def test_upsert_rejects_bad_weights(self, api_db):
        app = _setup(_user(), api_db)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.put(
                f"/api/v1/tactical/{uuid.uuid4()}",
                json={"regime_weights": {"RISK_ON": {"QQQ": 50}}},
            )
        assert resp.status_code == 422

    def test_apply_requires_strategy(self, api_db):
        app = _setup(_user(), api_db)
        with (
            patch.object(tactical, "get_owned_portfolio", AsyncMock(return_value=_portfolio())),
            patch.object(tactical, "get_strategy", AsyncMock(return_value=None)),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            assert client.post(f"/api/v1/tactical/{uuid.uuid4()}/apply").status_code == 400

    def test_apply_replaces_items_and_marks_regime(self, api_db):
        app = _setup(_user(), api_db)
        portfolio = _portfolio()
        strategy = _strategy(last_regime="RISK_OFF", notified_regime="RISK_ON")
        with (
            patch.object(tactical, "get_owned_portfolio", AsyncMock(return_value=portfolio)),
            patch.object(tactical, "get_strategy", AsyncMock(return_value=strategy)),
            patch.object(tactical, "evaluate_market", AsyncMock(return_value=_MARKET)),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            resp = client.post(f"/api/v1/tactical/{portfolio.id}/apply")
        assert resp.status_code == 200
        added = [c.args[0] for c in api_db.add.call_args_list]
        assert {(i.ticker, float(i.weight), i.market) for i in added} == {
            ("QQQ", 10.0, "NASDAQ"),
            ("SPY", 30.0, "NYSE"),
            ("CASH", 60.0, "KRW"),
        }
        assert strategy.applied_regime == "RISK_OFF"
        assert strategy.notified_regime == "RISK_OFF"
        api_db.commit.assert_awaited()


# ---------------------------------------------------------------------------
# 일일 점검 job
# ---------------------------------------------------------------------------


class TestRegimeCheckJob:
    async def _run(self, strategy, observed="RISK_OFF"):
        from app.jobs import tactical_regime_check as job

        db = AsyncMock()
        db.get = AsyncMock(return_value=strategy)
        result = MagicMock()
        user = SimpleNamespace(id=uuid.uuid4(), email="u@example.com")
        settings_row = SimpleNamespace(notification_email=None, fcm_token="tok")
        result.first.return_value = (user, settings_row, SimpleNamespace(name="P"))
        db.execute = AsyncMock(return_value=result)
        dispatch = AsyncMock(return_value=True)
        with patch.object(job, "dispatch_dual_channel_alert", dispatch):
            await job._check_one(db, strategy.id, {**_MARKET, "observed_regime": observed})
        return dispatch, db

    @pytest.mark.asyncio
    async def test_notifies_when_confirmed_differs_from_notified(self):
        # 앱 조회가 이미 확정한 경우(last_regime=RISK_OFF)에도 notified_regime과 달라 알림이 나간다
        strategy = _strategy(last_regime="RISK_OFF", notified_regime="RISK_ON")
        dispatch, _ = await self._run(strategy)
        dispatch.assert_awaited_once()
        assert dispatch.await_args.kwargs["alert_type"] == "TACTICAL_REGIME"
        assert len(dispatch.await_args.kwargs["alert_type"]) <= 20

    @pytest.mark.asyncio
    async def test_skips_when_already_applied(self):
        strategy = _strategy(last_regime="RISK_OFF", notified_regime="RISK_ON", applied_regime="RISK_OFF")
        dispatch, db = await self._run(strategy)
        dispatch.assert_not_awaited()
        assert strategy.notified_regime == "RISK_OFF"
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_tilt_only_change_updates_without_alert(self):
        from app.jobs import tactical_regime_check as job

        strategy = _strategy(last_regime="RISK_ON", notified_regime="RISK_ON", last_tilt="BALANCED")
        db = AsyncMock()
        db.get = AsyncMock(return_value=strategy)
        dispatch = AsyncMock(return_value=True)
        market = {**_MARKET, "tilt_inputs_complete": True, "observed_tilt": "FAVOR_SPY"}
        with patch.object(job, "dispatch_dual_channel_alert", dispatch):
            await job._check_one(db, strategy.id, market)
        dispatch.assert_not_awaited()
        assert strategy.last_tilt == "FAVOR_SPY"
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_alert_weights_include_tilt(self):
        strategy = _strategy(
            last_regime="RISK_OFF", notified_regime="RISK_ON", last_tilt="FAVOR_SPY", tilt_shift_pct=10
        )
        dispatch, _ = await self._run(strategy)
        assert "QQQ 0% · SPY 40% · 현금 60%" in dispatch.await_args.kwargs["history_message"]

    @pytest.mark.asyncio
    async def test_no_alert_while_pending(self):
        strategy = _strategy(last_regime="RISK_ON", notified_regime="RISK_ON")
        dispatch, _ = await self._run(strategy, observed="RISK_OFF")
        dispatch.assert_not_awaited()
        assert strategy.pending_regime == "RISK_OFF"


# ---------------------------------------------------------------------------
# 조회 래퍼 (캐시·실패 폴백)
# ---------------------------------------------------------------------------


def _trend_closes(n: int = 700) -> dict[str, pd.Series]:
    idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    up = pd.Series(np.linspace(100, 300, n), index=idx)
    return {"QQQ": up, "SPY": up * 1.1}


class TestFetchWrappers:
    @pytest.mark.asyncio
    async def test_technical_signals_cached_and_partial_failure(self):
        from app.core.cache_store import CacheStore
        from app.services import technical_signal_service as svc

        closes = _trend_closes()
        fetch = AsyncMock(return_value={"QQQ": closes["QQQ"]})  # SPY 실패
        cache = CacheStore()
        with patch.object(svc, "fetch_close_history", fetch):
            first = await svc.get_technical_signals(cache)
            second = await svc.get_technical_signals(cache)
        assert first["QQQ"]["trend"] == "UP"
        assert first["SPY"]["trend"] == "UNKNOWN"
        assert second == first
        fetch.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_technical_signals_dia_failure_keeps_normal_ttl(self):
        from app.services import technical_signal_service as svc

        closes = _trend_closes()
        cache = MagicMock()
        set_cached = AsyncMock()
        with (
            patch.object(svc, "fetch_close_history", AsyncMock(return_value=closes)),  # DIA 없음
            patch.object(svc, "get_cached_json", AsyncMock(return_value=None)),
            patch.object(svc, "set_cached_json", set_cached),
        ):
            result = await svc.get_technical_signals(cache)
        assert result["DIA"]["trend"] == "UNKNOWN"
        assert set_cached.await_args.args[3] == svc.TTL_TECHNICAL_SIGNAL

    @pytest.mark.asyncio
    async def test_technical_signals_fetch_exception(self):
        from app.services import technical_signal_service as svc

        with patch.object(svc, "fetch_close_history", AsyncMock(side_effect=RuntimeError("yahoo down"))):
            result = await svc.get_technical_signals(None)
        assert {s["trend"] for s in result.values()} == {"UNKNOWN"}

    @pytest.mark.asyncio
    async def test_backtest_without_vix_notes_fallback(self):
        from app.core.cache_store import CacheStore
        from app.services import tactical_backtest as bt

        cache = CacheStore()
        with (
            patch.object(bt, "fetch_close_history", AsyncMock(return_value=_trend_closes())),
            patch.object(bt, "_fetch_vix_history", AsyncMock(side_effect=RuntimeError("fred"))),
            patch.object(bt, "_fetch_cash_yield_history", AsyncMock(side_effect=RuntimeError("fred"))),
        ):
            result = await bt.run_tactical_backtest(tactical.DEFAULT_REGIME_WEIGHTS, 1, cache)
            cached = await bt.run_tactical_backtest(tactical.DEFAULT_REGIME_WEIGHTS, 1, cache)
        assert "VIX 이력을 받지 못해" in result["macro_note"]
        assert "현금 수익률은 0" in result["macro_note"]
        assert "현금 수익률 0" in result["assumptions"]
        assert result["years"] == 1
        assert cached == result

    @pytest.mark.asyncio
    async def test_backtest_missing_prices_raises(self):
        from app.services import tactical_backtest as bt

        with (
            patch.object(bt, "fetch_close_history", AsyncMock(return_value={})),
            pytest.raises(ValueError, match="불러오지 못했"),
        ):
            await bt.run_tactical_backtest(tactical.DEFAULT_REGIME_WEIGHTS, 3, None)

    @pytest.mark.asyncio
    async def test_vix_history_parsing(self):
        from app.services import tactical_backtest as bt

        obs = [{"date": "2026-10-02", "value": "18.5"}, {"date": "2026-10-01", "value": "."}]
        with patch("app.services.economic_indicator_service._fred_get_observations", AsyncMock(return_value=obs)):
            series = await bt._fetch_vix_history(30)
        assert series.to_dict() == {pd.Timestamp("2026-10-02"): 18.5}

    @pytest.mark.asyncio
    async def test_evaluate_market_macro_failure_is_stale(self):
        with (
            patch(
                "app.services.market_signal_service.get_confirmed_composite_level",
                AsyncMock(side_effect=RuntimeError("fred")),
            ),
            patch.object(
                tactical,
                "get_technical_signals",
                AsyncMock(return_value={"QQQ": {"trend": "UP"}, "SPY": {"trend": "UP"}}),
            ),
            patch.object(
                tactical,
                "get_tilt_inputs",
                AsyncMock(return_value={"real_yield": 2.0, "real_yield_change_pp": 0.4, "relative_strength_pct": -2.0}),
            ),
        ):
            market = await tactical.evaluate_market(None, AsyncMock())
        assert market["macro_freshness"] == "STALE"
        assert market["observed_regime"] == "NEUTRAL"
        assert market["observed_if_risk_on"] == "RISK_ON"
        assert market["observed_tilt"] == "FAVOR_SPY"
        assert market["tilt_inputs_complete"] is True
