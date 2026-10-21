"""QQQ/SPY 전술 배분 규칙 백테스트(비중표에 DIA가 있으면 DIA도 보유·비교).

실시간 판정(`tactical_allocation_service.classify_regime`)과 같은 규칙을 과거 일봉에 적용한다. 단 매크로
입력은 단순화한다 — 실시간 복합신호 8종 중 ICE 하이일드 스프레드 등은 FRED에 과거 이력이 짧아(약 3년)
장기 재현이 불가능하므로 VIX만으로 등급을 근사한다(GREEN <20, YELLOW 20~30, RED ≥30). 결과 화면에 이
차이를 명시한다. (VIX 경계에 히스테리시스를 두는 방식도 실측했으나 위험 신호 반영이 늦어져 성과가 나빠 채택하지 않음.)

룩어헤드 방지: t일 종가까지의 데이터로 판정한 국면은 t+1일 수익률부터 적용. 국면 판정·확정은 실시간과 같은
`classify_regime`(직전 확정 국면 전달)과 `step_confirmation`을 거래일 날짜로 돌린다. 국면이 바뀔 때만 목표
비중으로 리밸런싱하고 그 사이에는 비중이 시세대로 흘러가게 둔다. 현금 수익률 0, 거래비용·세금·환율 미반영.

나스닥/S&P 틸트(`tactical_tilt`)는 매월 첫 거래일(입력이 모두 있는 첫날)에 그날 종가까지의 실질금리 변화·
QQQ/SPY 상대강도로 판정하고, 바뀌면 그 시점에 리밸런싱한다(실시간의 "그 달 첫 점검일" 갱신과 같은 취지).
"""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from typing import TYPE_CHECKING, Any

import pandas as pd
import structlog

from app.services.backtest_metrics import compute_metrics
from app.services.tactical_allocation_service import TACTICAL_ASSETS, ConfirmState, classify_regime, step_confirmation
from app.services.tactical_tilt import REAL_YIELD_LOOKBACK, RS_SMA, apply_tilt, classify_tilt
from app.services.technical_indicators import trend_series
from app.services.technical_signal_service import fetch_close_history
from app.utils.cache_keys import TTL_TACTICAL_BACKTEST, get_cached_json, set_cached_json, tactical_backtest_key

if TYPE_CHECKING:
    from app.core.cache_store import CacheStore

logger = structlog.get_logger()

_WARMUP_DAYS = 420  # 200일선 워밍업(달력일)
_MAX_SERIES_POINTS = 260  # 차트용 다운샘플 상한


def vix_to_macro_level(vix: float | None) -> str:
    if vix is None or pd.isna(vix):
        return "YELLOW"
    if vix >= 30:
        return "RED"
    if vix < 20:
        return "GREEN"
    return "YELLOW"


def simulate(
    closes: pd.DataFrame,
    vix: pd.Series,
    weights_table: dict[str, dict[str, float]],
    start: pd.Timestamp,
    real_yield: pd.Series | None = None,
    tilt_shift_pct: float = 0.0,
) -> dict[str, Any]:
    """closes: QQQ/SPY(+선택 DIA) 종가(워밍업 포함), vix·real_yield: 일별 시계열. start 이후 구간을 평가한다."""
    has_dia = "DIA" in closes.columns
    if not has_dia and any(w.get("DIA", 0.0) > 0 for w in weights_table.values()):
        raise ValueError("DIA 과거 시세를 불러오지 못했습니다. 잠시 후 다시 시도해주세요.")
    bench_tickers = ["SPY", "QQQ"] + (["DIA"] if has_dia else [])
    closes = closes[["QQQ", "SPY"] + (["DIA"] if has_dia else [])].dropna()
    trends = {t: trend_series(closes[t]) for t in ("QQQ", "SPY")}
    vix_aligned = vix.reindex(closes.index).ffill()
    ratio = closes["QQQ"] / closes["SPY"]
    rel_strength = (ratio / ratio.rolling(RS_SMA).mean() - 1) * 100
    ry = (real_yield if real_yield is not None else pd.Series(dtype=float)).reindex(closes.index).ffill()
    ry_change = ry - ry.shift(REAL_YIELD_LOOKBACK)
    tilt_on = tilt_shift_pct > 0

    eval_idx = [i for i, ts in enumerate(closes.index) if ts >= start]
    if len(eval_idx) < 2:
        raise ValueError("백테스트 기간의 시세 데이터가 부족합니다.")

    rets = closes.pct_change().fillna(0.0)
    state = ConfirmState(None, None, None)
    holdings: dict[str, float] = {}
    equity = 100.0
    strat_values: list[float] = []
    switches = 0
    days_in: dict[str, int] = {"RISK_ON": 0, "NEUTRAL": 0, "RISK_OFF": 0}
    tilt = "BALANCED"
    tilt_month: tuple[int, int] | None = None
    tilt_switches = 0
    tilt_days: dict[str, int] = {"FAVOR_QQQ": 0, "BALANCED": 0, "FAVOR_SPY": 0}
    timeline: list[dict[str, str]] = []

    first = eval_idx[0]
    for i in range(first, len(closes)):
        if i > first:
            # t-1 종가 기준 보유분에 t일 수익률 적용
            for asset in holdings:
                if asset in rets.columns:  # 현금(·시세 없는 0% 자산)은 그대로
                    holdings[asset] *= 1 + float(rets.iloc[i][asset])
            equity = sum(holdings.values())
        strat_values.append(equity)

        ts = closes.index[i]
        day = ts.date()
        prev_regime = state.current
        observed, _ = classify_regime(
            vix_to_macro_level(vix_aligned.get(ts)),
            "LIVE",
            {t: trends[t].iloc[i] for t in ("QQQ", "SPY")},
            prev=prev_regime,
        )
        state, changed = step_confirmation(state, observed, day)
        if changed and state.current is not None:
            if prev_regime is not None:
                switches += 1
            timeline.append({"date": day.isoformat(), "regime": state.current})

        tilt_changed = False
        rs, chg = rel_strength.iloc[i], ry_change.iloc[i]
        if tilt_on and tilt_month != (day.year, day.month) and not (pd.isna(rs) or pd.isna(chg)):
            tilt_month = (day.year, day.month)
            new_tilt = classify_tilt(float(chg), float(rs))
            if new_tilt != tilt:
                tilt, tilt_changed = new_tilt, True
                tilt_switches += 1

        if (changed or tilt_changed) and state.current is not None:
            weights = apply_tilt(weights_table[state.current], tilt, tilt_shift_pct)
            holdings = {a: equity * weights.get(a, 0.0) / 100.0 for a in TACTICAL_ASSETS}
        if state.current is not None:
            days_in[state.current] += 1
        tilt_days[tilt] += 1

    eval_closes = closes.iloc[first:]
    bench = {t: (eval_closes[t] / eval_closes[t].iloc[0] * 100.0).tolist() for t in bench_tickers}
    dates = [ts.date().isoformat() for ts in eval_closes.index]

    step = max(1, len(dates) // _MAX_SERIES_POINTS)
    picks = list(range(0, len(dates), step))
    if picks[-1] != len(dates) - 1:
        picks.append(len(dates) - 1)

    total_days = sum(days_in.values()) or 1
    return {
        "start_date": dates[0],
        "end_date": dates[-1],
        "metrics": [
            compute_metrics("전술 배분", strat_values).model_dump(),
            *(compute_metrics(f"{t} 보유", bench[t]).model_dump() for t in bench_tickers),
        ],
        "series": [
            {
                "date": dates[i],
                "strategy": round(strat_values[i], 2),
                "spy": round(bench["SPY"][i], 2),
                "qqq": round(bench["QQQ"][i], 2),
                **({"dia": round(bench["DIA"][i], 2)} if has_dia else {}),
            }
            for i in picks
        ],
        "regime_switches": switches,
        "tilt_switches": tilt_switches,
        "tilt_time_pct": {k: round(v / (sum(tilt_days.values()) or 1) * 100, 1) for k, v in tilt_days.items()},
        "regime_time_pct": {k: round(v / total_days * 100, 1) for k, v in days_in.items()},
        "regime_timeline": timeline[-20:],
    }


async def _fetch_fred_history(series_id: str, days: int) -> pd.Series:
    from app.services.economic_indicator_service import _fred_get_observations, _parse_fred_obs
    from app.utils.circuit_breaker import fred_circuit
    from app.utils.kst import today_kst

    raw = await fred_circuit.call(
        _fred_get_observations,
        series_id,
        limit=days + 30,  # 일별 시리즈 — 달력일 수 이상이면 기간 전체를 덮는다
        observation_start=today_kst() - timedelta(days=days),
    )
    points = _parse_fred_obs(raw)
    if not points:
        return pd.Series(dtype=float)
    return pd.Series({pd.Timestamp(p["date"]): p["value"] for p in points}).sort_index()


async def _fetch_vix_history(days: int) -> pd.Series:
    return await _fetch_fred_history("VIXCLS", days)


async def _fetch_real_yield_history(days: int) -> pd.Series:
    return await _fetch_fred_history("DFII10", days)


def _settings_hash(weights_table: dict[str, dict[str, float]], tilt_shift_pct: float) -> str:
    payload = json.dumps({"w": weights_table, "tilt": tilt_shift_pct}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


async def run_tactical_backtest(
    weights_table: dict[str, dict[str, float]],
    years: int,
    cache: CacheStore | None,
    tilt_shift_pct: float = 0.0,
) -> dict[str, Any]:
    key = tactical_backtest_key(_settings_hash(weights_table, tilt_shift_pct), years)
    if (hit := await get_cached_json(cache, key)) is not None:
        return hit

    days = years * 366 + _WARMUP_DAYS
    closes_map = await fetch_close_history(["QQQ", "SPY", "DIA"], days)
    if "QQQ" not in closes_map or "SPY" not in closes_map:
        raise ValueError("QQQ/SPY 과거 시세를 불러오지 못했습니다. 잠시 후 다시 시도해주세요.")
    # DIA는 비교·선택 자산 — 결측이면 빼고 진행(비중표에 DIA가 있으면 simulate가 오류)
    closes = pd.DataFrame({t: closes_map[t] for t in ("QQQ", "SPY", "DIA") if t in closes_map})
    closes.index = pd.to_datetime(closes.index).tz_localize(None)

    try:
        vix = await _fetch_vix_history(days)
    except Exception as exc:
        logger.warning("tactical_backtest_vix_failed", error=str(exc))
        vix = pd.Series(dtype=float)
    macro_note = (
        "매크로 입력은 VIX만으로 근사했습니다(실시간 신호는 8개 지표 복합)."
        if not vix.empty
        else "VIX 이력을 받지 못해 매크로 입력 없이(항상 '주의') 차트 추세만으로 계산했습니다."
    )

    real_yield: pd.Series | None = None
    if tilt_shift_pct > 0:
        try:
            real_yield = await _fetch_real_yield_history(days)
        except Exception as exc:
            logger.warning("tactical_backtest_real_yield_failed", error=str(exc))
        if real_yield is None or real_yield.empty:
            macro_note += " 실질금리 이력을 받지 못해 나스닥/S&P 틸트는 반영하지 않았습니다."

    start = closes.index[-1] - timedelta(days=years * 365)
    result = simulate(closes, vix, weights_table, start, real_yield=real_yield, tilt_shift_pct=tilt_shift_pct)
    result["years"] = years
    result["tilt_shift_pct"] = tilt_shift_pct
    result["macro_note"] = macro_note
    result["assumptions"] = (
        "국면 확정 2거래일 연속 · 공격 국면은 매크로 '주의'까지 유지 · 나스닥/S&P 틸트 월 1회 · "
        "전환 시에만 리밸런싱 · "
        "현금 수익률 0 · 거래비용·세금·환율 미반영"
    )
    await set_cached_json(cache, key, result, TTL_TACTICAL_BACKTEST)
    return result
