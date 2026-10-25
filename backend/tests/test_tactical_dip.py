"""전술 배분 확장 — 웅덩이(눌림목) 단계 지표·현금 투입, QLD/SSO 레버리지 자산, 분할 적용."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.models.tactical import TacticalStrategy
from app.services import tactical_allocation_service as tactical
from app.services import tactical_dip as dip
from app.services import technical_indicators as ti
from app.services.tactical_backtest import leveraged_returns, simulate


def _series(values) -> pd.Series:
    return pd.Series(values, index=pd.bdate_range("2020-01-01", periods=len(values)), dtype=float)


def _strategy(**kw) -> TacticalStrategy:
    s = TacticalStrategy(user_id=uuid.uuid4(), portfolio_id=uuid.uuid4())
    s.notify_enabled = True
    s.dip_level = 0
    s.notified_dip_level = 0
    for k, v in kw.items():
        setattr(s, k, v)
    return s


# ---------------------------------------------------------------------------
# 웅덩이 단계 지표
# ---------------------------------------------------------------------------


class TestPullbackIndicators:
    @pytest.mark.parametrize(
        ("close", "rsi", "expected"),
        [
            (110, 50, "NONE"),  # 모든 이평선 위
            (99, 50, "SMA20"),  # 20일선(100) 이하
            (95, 50, "SMA60"),  # 60일선(95) 터치(≤)
            (90, 40, "SMA120"),  # 120일선(90) 터치, RSI 정상
            (85, 30, "SMA120_RSI"),  # 120일선 아래 + RSI 과매도
        ],
    )
    def test_classify_pullback(self, close, rsi, expected):
        assert ti.classify_pullback(close, 100, 95, 90, rsi) == expected

    def test_classify_pullback_unknown_without_averages(self):
        assert ti.classify_pullback(100, None, 95, 90, 50) == "UNKNOWN"
        # RSI 결측이어도 120일선 단계까지는 판정
        assert ti.classify_pullback(80, 100, 95, 90, None) == "SMA120"

    def test_rsi_series_matches_scalar(self):
        rng = np.random.default_rng(0)
        s = _series(100 + np.cumsum(rng.normal(0, 1, 120)))
        assert ti.rsi_series(s).iloc[-1] == pytest.approx(ti.rsi(s))
        assert ti.rsi_series(s).iloc[:14].isna().all()

    def test_pullback_series_no_lookahead_and_snapshot_fields(self):
        values = list(np.linspace(100, 200, 200)) + list(np.linspace(200, 150, 40))
        stages = ti.pullback_series(_series(values))
        assert stages.iloc[:119].eq("UNKNOWN").all()  # 120일선이 생기기 전
        assert stages.iloc[199] == "NONE"  # 상승 끝
        assert stages.iloc[-1] in {"SMA60", "SMA120", "SMA120_RSI"}
        # 각 시점 판정은 그날까지의 데이터만 쓴다 — 잘라서 계산해도 같은 값
        assert ti.pullback_series(_series(values[:220])).iloc[-1] == stages.iloc[219]
        snap = ti.compute_snapshot(_series(values))
        assert snap["pullback_stage"] == stages.iloc[-1]
        assert snap["sma20"] == pytest.approx(float(np.mean(values[-20:])))


# ---------------------------------------------------------------------------
# 투입 단계 규칙 (순수)
# ---------------------------------------------------------------------------


class TestDipRules:
    def test_ratchet_only_deepens_until_recovery(self):
        level = dip.advance_dip_level(0, "SMA60", "RISK_ON")
        assert level == 1
        level = dip.advance_dip_level(level, "SMA120_RSI", "RISK_ON")
        assert level == 3
        # 반등해 60일선 위(20일선 아래)로 와도 단계 유지 — 매일 매매 반복 방지
        assert dip.advance_dip_level(level, "SMA20", "RISK_ON") == 3
        assert dip.advance_dip_level(level, "SMA60", "RISK_ON") == 3
        # 모든 이평선 위로 회복하면 종료
        assert dip.advance_dip_level(level, "NONE", "RISK_ON") == 0

    def test_only_risk_on_and_unknown_keeps(self):
        assert dip.advance_dip_level(2, "SMA120", "NEUTRAL") == 0
        assert dip.advance_dip_level(2, "SMA120", "RISK_OFF") == 0
        assert dip.advance_dip_level(2, "SMA120", None) == 0
        assert dip.advance_dip_level(2, "UNKNOWN", "RISK_ON") == 2
        assert dip.advance_dip_level(0, "SMA20", "RISK_ON") == 0  # 20일선 눌림은 표시만

    def test_apply_dip_moves_cash_proportionally(self):
        out = dip.apply_dip({"QQQ": 50, "SPY": 40, "DIA": 0, "CASH": 10}, 3, 9)
        assert out["CASH"] == pytest.approx(1.0)
        assert out["QQQ"] == pytest.approx(55.0)
        assert out["SPY"] == pytest.approx(44.0)
        assert out["DIA"] == 0
        assert sum(out.values()) == pytest.approx(100.0)

    def test_apply_dip_clamps_to_cash_and_noop_cases(self):
        out = dip.apply_dip({"QQQ": 45, "SPY": 45, "CASH": 10}, 3, 30)  # 30%p 요청, 현금 10%
        assert out["CASH"] == 0.0
        assert sum(out.values()) == pytest.approx(100.0)
        assert dip.apply_dip({"QQQ": 50, "CASH": 50}, 0, 20) == {"QQQ": 50, "CASH": 50}
        assert dip.apply_dip({"QQQ": 50, "CASH": 50}, 2, 0) == {"QQQ": 50, "CASH": 50}
        assert dip.apply_dip({"CASH": 100}, 3, 20) == {"CASH": 100}  # 주식 자산 없음

    def test_apply_dip_rounding_never_negative_cash(self):
        out = dip.apply_dip({"QQQ": 33.3, "SPY": 33.3, "DIA": 23.4, "CASH": 10}, 3, 10)
        assert out["CASH"] >= 0
        assert sum(out.values()) == pytest.approx(100.0)

    def test_reasons(self):
        assert len(dip.dip_reasons("SMA60", 1, 0, "RISK_ON")) == 1  # 투입 꺼짐 — 단계만
        assert "10%p" in dip.dip_reasons("SMA120_RSI", 3, 10, "RISK_ON")[1]
        assert "공격 국면에서만" in dip.dip_reasons("SMA120", 0, 10, "NEUTRAL")[1]


# ---------------------------------------------------------------------------
# 서비스 연동 · 레버리지 자산 · 분할 보간
# ---------------------------------------------------------------------------


class TestServiceIntegration:
    def test_proposed_weights_apply_dip_only_in_risk_on(self):
        s = _strategy(dip_shift_pct=15, dip_level=3, tilt_shift_pct=0)
        on = tactical.proposed_weights_for(s, "RISK_ON", {})
        assert on["CASH"] == 0.0  # 현금 10% 전부 투입(요청 15%p, 상한=현금)
        neutral = tactical.proposed_weights_for(s, "NEUTRAL", {})
        assert neutral == tactical.DEFAULT_REGIME_WEIGHTS["NEUTRAL"]

    def test_advance_dip_tracks_even_when_disabled(self):
        s = _strategy(last_regime="RISK_ON", dip_shift_pct=0)
        assert tactical.advance_dip(s, {"qqq_pullback_stage": "SMA120"}) is True
        assert s.dip_level == 2
        assert tactical.advance_dip(s, {"qqq_pullback_stage": "SMA120"}) is False
        s.last_regime = "RISK_OFF"
        assert tactical.advance_dip(s, {"qqq_pullback_stage": "SMA120"}) is True
        assert s.dip_level == 0

    def test_leveraged_assets_validate_and_format(self):
        table = tactical.validate_regime_weights(
            {
                "RISK_ON": {"QQQ": 30, "QLD": 20, "SSO": 10, "SPY": 30, "CASH": 10},
                "NEUTRAL": {"SPY": 70, "CASH": 30},
                "RISK_OFF": {"CASH": 100},
            }
        )
        assert table["RISK_ON"]["QLD"] == 20.0
        assert table["NEUTRAL"]["QLD"] == 0.0
        assert tactical.format_weights(table["RISK_ON"]) == "QQQ 30% · SPY 30% · QLD 20% · SSO 10% · 현금 10%"
        assert tactical.format_weights(table["NEUTRAL"]) == "QQQ 0% · SPY 70% · 현금 30%"

    def test_interpolate_weights_half(self):
        out = tactical.interpolate_weights(
            {"QQQ": 50, "SPY": 40, "CASH": 10}, {"QQQ": 10, "SPY": 30, "DIA": 0, "CASH": 60}, 0.5
        )
        assert out == {"QQQ": 30.0, "SPY": 35.0, "DIA": 0.0, "CASH": 35.0}

    @pytest.mark.asyncio
    async def test_build_status_exposes_dip(self):
        s = _strategy(last_regime="RISK_ON", dip_shift_pct=10, dip_level=1, tilt_shift_pct=0)
        market = {
            "macro_level": "GREEN",
            "macro_freshness": "LIVE",
            "technicals": {},
            "observed_regime": "RISK_ON",
            "reasons": [],
            "qqq_pullback_stage": "SMA60",
        }
        portfolio = SimpleNamespace(id=uuid.uuid4(), name="P", items=[])
        status = await tactical.build_status(portfolio, s, market)
        assert status["dip_level"] == 1
        assert status["pullback_stage"] == "SMA60"
        assert status["dip_shift_pct"] == 10.0
        assert status["proposed_weights"]["CASH"] == pytest.approx(10 - 10 / 3, abs=0.1)


# ---------------------------------------------------------------------------
# 백테스트
# ---------------------------------------------------------------------------


class TestBacktest:
    def test_leveraged_returns_synthesizes_before_listing(self):
        idx = pd.bdate_range("2020-01-01", periods=5)
        base = pd.DataFrame({"QQQ": [0.0, 0.01, -0.02, 0.01, 0.0], "SPY": [0.0] * 5}, index=idx)
        actual = pd.DataFrame({"QLD": [np.nan, np.nan, np.nan, 100.0, 110.0]}, index=idx)
        out = leveraged_returns(base, actual)
        cost = (0.0095 + 0.02) / 252
        assert out["QLD"].iloc[1] == pytest.approx(0.02 - cost)  # 상장 전 → 합성
        assert out["QLD"].iloc[4] == pytest.approx(0.10)  # 실제 시세
        assert out["SSO"].iloc[2] == pytest.approx(-(0.0089 + 0.02) / 252)  # 실제 시세 없음 → 합성

    def test_simulate_holds_leverage_without_prices(self):
        idx = pd.bdate_range("2015-01-01", periods=600)
        up = np.linspace(100, 300, 600)
        closes = pd.DataFrame({"QQQ": up, "SPY": up}, index=idx)
        table = {r: {"QLD": 100.0, "CASH": 0.0} for r in tactical.REGIMES}
        lev = simulate(closes, pd.Series(15.0, index=idx), table, idx[300])
        plain = simulate(closes, pd.Series(15.0, index=idx), tactical.DEFAULT_REGIME_WEIGHTS, idx[300])
        assert lev["metrics"][0]["total_return_pct"] > plain["metrics"][0]["total_return_pct"]
        assert len(lev["metrics"]) == 3  # 레버리지는 벤치마크에 추가하지 않음

    def test_simulate_dip_enters_and_exits(self):
        # 긴 상승 → 120일선까지 눌림 → 재상승. 공격 국면 유지 중 웅덩이 투입이 생겨야 한다(수익 우열은 경로 의존).
        up1 = list(np.linspace(100, 300, 400))
        dip_ = list(np.linspace(300, 255, 30))
        up2 = list(np.linspace(255, 380, 120))
        idx = pd.bdate_range("2015-01-01", periods=len(up1) + len(dip_) + len(up2))
        prices = up1 + dip_ + up2
        closes = pd.DataFrame({"QQQ": prices, "SPY": prices}, index=idx)
        vix = pd.Series(15.0, index=idx)
        off = simulate(closes, vix, tactical.DEFAULT_REGIME_WEIGHTS, idx[250])
        on = simulate(closes, vix, tactical.DEFAULT_REGIME_WEIGHTS, idx[250], dip_shift_pct=10)
        assert off["dip_entries"] == 0
        assert on["dip_entries"] >= 1
        assert 0 < on["dip_time_pct"] < 100  # 회복하면 웅덩이를 빠져나온다
        assert on["metrics"][0]["total_return_pct"] != off["metrics"][0]["total_return_pct"]


# ---------------------------------------------------------------------------
# API — 분할 적용 · 투입폭 설정
# ---------------------------------------------------------------------------

_MARKET = {
    "macro_level": "GREEN",
    "macro_freshness": "LIVE",
    "technicals": {},
    "observed_regime": "RISK_ON",
    "reasons": ["r"],
    "qqq_pullback_stage": "NONE",
}


def _setup(db):
    from app.api.deps import get_current_user
    from app.core.database import get_db
    from app.main import app

    user = SimpleNamespace(id=uuid.uuid4(), email="t@example.com", is_active=True, needs_password_reset=False)

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


def _items(**weights):
    return [SimpleNamespace(ticker=t, weight=w) for t, w in weights.items()]


class TestApi:
    def _client(self, api_db, portfolio, strategy):
        app = _setup(api_db)
        return (
            patch.object(tactical, "get_owned_portfolio", AsyncMock(return_value=portfolio)),
            patch.object(tactical, "get_strategy", AsyncMock(return_value=strategy)),
            patch.object(tactical, "evaluate_market", AsyncMock(return_value=_MARKET)),
            TestClient(app, raise_server_exceptions=False),
        )

    def test_apply_half_interpolates_and_keeps_unapplied(self, api_db):
        portfolio = SimpleNamespace(id=uuid.uuid4(), name="P", items=_items(QQQ=50, SPY=40, CASH=10))
        strategy = _strategy(last_regime="RISK_OFF", notified_regime="RISK_ON", tilt_shift_pct=0)
        p1, p2, p3, tc = self._client(api_db, portfolio, strategy)
        with p1, p2, p3, tc as client:
            resp = client.post(f"/api/v1/tactical/{portfolio.id}/apply", json={"fraction": 0.5})
        assert resp.status_code == 200
        added = {i.ticker: float(i.weight) for i in (c.args[0] for c in api_db.add.call_args_list)}
        assert added == {"QQQ": 30.0, "SPY": 35.0, "CASH": 35.0}
        assert strategy.applied_regime is None  # 남은 절반 — 적용 버튼 유지
        assert strategy.notified_regime == "RISK_OFF"

    def test_apply_half_rejected_with_foreign_items(self, api_db):
        portfolio = SimpleNamespace(id=uuid.uuid4(), name="P", items=_items(AAPL=100))
        strategy = _strategy(last_regime="RISK_OFF")
        p1, p2, p3, tc = self._client(api_db, portfolio, strategy)
        with p1, p2, p3, tc as client:
            resp = client.post(f"/api/v1/tactical/{portfolio.id}/apply", json={"fraction": 0.5})
            bad = client.post(f"/api/v1/tactical/{portfolio.id}/apply", json={"fraction": 0})
        assert resp.status_code == 400
        assert bad.status_code == 422

    def test_full_apply_records_dip_level(self, api_db):
        portfolio = SimpleNamespace(id=uuid.uuid4(), name="P", items=[])
        strategy = _strategy(last_regime="RISK_ON", dip_level=2, dip_shift_pct=10, tilt_shift_pct=0)
        p1, p2, p3, tc = self._client(api_db, portfolio, strategy)
        with p1, p2, p3, tc as client:
            assert client.post(f"/api/v1/tactical/{portfolio.id}/apply").status_code == 200
        assert strategy.applied_regime == "RISK_ON"
        assert strategy.notified_dip_level == 2

    def test_upsert_dip_shift_range(self, api_db):
        portfolio = SimpleNamespace(id=uuid.uuid4(), name="P", items=[])
        p1, p2, p3, tc = self._client(api_db, portfolio, None)
        with p1, p2, p3, tc as client:
            ok = client.put(f"/api/v1/tactical/{portfolio.id}", json={"dip_shift_pct": 20})
            bad = client.put(f"/api/v1/tactical/{portfolio.id}", json={"dip_shift_pct": 31})
        assert ok.status_code == 200
        assert ok.json()["dip_shift_pct"] == 20.0
        assert bad.status_code == 422


# ---------------------------------------------------------------------------
# 일일 점검 job — 웅덩이 알림
# ---------------------------------------------------------------------------


class TestDipAlertJob:
    async def _run(self, strategy, market):
        from app.jobs import tactical_regime_check as job

        db = AsyncMock()
        db.get = AsyncMock(return_value=strategy)
        result = MagicMock()
        user = SimpleNamespace(id=uuid.uuid4(), email="u@example.com")
        result.first.return_value = (
            user,
            SimpleNamespace(notification_email=None, fcm_token="tok"),
            SimpleNamespace(id=uuid.uuid4(), name="P"),
        )
        db.execute = AsyncMock(return_value=result)
        dispatch = AsyncMock(return_value=True)
        with patch.object(job, "dispatch_dual_channel_alert", dispatch):
            await job._check_one(db, strategy.id, market)
        return dispatch

    @pytest.mark.asyncio
    async def test_alerts_when_dip_deepens(self):
        strategy = _strategy(last_regime="RISK_ON", notified_regime="RISK_ON", dip_shift_pct=15, tilt_shift_pct=0)
        dispatch = await self._run(strategy, {**_MARKET, "qqq_pullback_stage": "SMA120"})
        dispatch.assert_awaited_once()
        kwargs = dispatch.await_args.kwargs
        assert kwargs["alert_type"] == "TACTICAL_DIP"
        assert "120일선" in kwargs["history_message"]
        await kwargs["after_sent"]()
        assert strategy.notified_dip_level == 2

    @pytest.mark.asyncio
    async def test_no_dip_alert_when_disabled_or_recovering(self):
        off = _strategy(last_regime="RISK_ON", notified_regime="RISK_ON", dip_shift_pct=0)
        assert not (await self._run(off, {**_MARKET, "qqq_pullback_stage": "SMA120"})).await_count
        assert off.notified_dip_level == 2  # 기록만 맞춘다

        recovering = _strategy(
            last_regime="RISK_ON", notified_regime="RISK_ON", dip_shift_pct=15, dip_level=2, notified_dip_level=2
        )
        assert not (await self._run(recovering, _MARKET)).await_count
        assert recovering.dip_level == 0
        assert recovering.notified_dip_level == 0

    @pytest.mark.asyncio
    async def test_regime_alert_supersedes_dip_alert(self):
        strategy = _strategy(last_regime="RISK_ON", notified_regime="NEUTRAL", dip_shift_pct=15, tilt_shift_pct=0)
        dispatch = await self._run(strategy, {**_MARKET, "qqq_pullback_stage": "SMA60"})
        dispatch.assert_awaited_once()
        assert dispatch.await_args.kwargs["alert_type"] == "TACTICAL_REGIME"
        assert strategy.notified_dip_level == 1
