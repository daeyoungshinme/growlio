"""QQQ/SPY 전술 배분 규칙 백테스트(비중표에 DIA가 있으면 DIA도 보유·비교).

실시간 판정(`tactical_allocation_service.classify_regime`)과 같은 규칙을 과거 일봉에 적용한다. 단 매크로
입력은 단순화한다 — 실시간 복합신호 8종 중 ICE 하이일드 스프레드 등은 FRED에 과거 이력이 짧아(약 3년)
장기 재현이 불가능하므로 VIX만으로 등급을 근사한다(GREEN <20, YELLOW 20~30, RED ≥30). 결과 화면에 이
차이를 명시한다. (VIX 경계에 히스테리시스를 두는 방식도 실측했으나 위험 신호 반영이 늦어져 성과가 나빠 채택하지 않음.)

룩어헤드 방지: t일 종가까지의 데이터로 판정한 국면은 t+1일 수익률부터 적용. 국면 판정·확정은 실시간과 같은
`classify_regime`(직전 확정 국면 전달)과 `step_confirmation`을 거래일 날짜로 돌린다. 국면이 바뀔 때만 목표
비중으로 리밸런싱하고 그 사이에는 비중이 시세대로 흘러가게 둔다. 현금은 미국 3개월 국채 금리(FRED DTB3)로 이자를
받고(이력이 없으면 0), 리밸런싱마다 거래한 주식 금액의 `_COST_RATE`를 비용으로 뺀다. 세금·환율은 미반영.

공정 비교용 "평균 비중 고정": 전술 배분이 기간 동안 평균적으로 들고 있던 목표 비중(시간가중)을 처음부터 그대로 두고
매월 리밸런싱한 결과. 전술 배분이 이보다 나아야 국면 판단(타이밍)이 가치를 더한 것이다 — 단순 보유보다 MDD가
작은 이유가 "평소 주식이 적어서"인지 "위험할 때 줄여서"인지 구분한다.

(2026-10-21·25 docstring의 실측 수치는 현금 0·비용 0 기준이다. 현금 이자·비용 반영 기준은 docs/plans/69.)

나스닥/S&P 틸트(`tactical_tilt`)는 매월 첫 거래일(입력이 모두 있는 첫날)에 그날 종가까지의 실질금리 변화·
QQQ/SPY 상대강도로 판정하고, 바뀌면 그 시점에 리밸런싱한다(실시간의 "그 달 첫 점검일" 갱신과 같은 취지).

눌림목(웅덩이) 투입(`tactical_dip`)은 매 거래일 그날 종가까지의 QQQ 웅덩이 단계로 실시간과 같은
`advance_dip_level`을 돌리고, 투입 단계가 바뀌면 리밸런싱한다.

QLD·SSO(2배 레버리지)는 실제 시세가 있는 날은 실제 수익률, 상장 전(2006년 이전)·결측일은 기초지수 일수익률
×2 − (보수+차입비용)/252로 합성한다.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import timedelta
from typing import TYPE_CHECKING, Any

import pandas as pd
import structlog

from app.services.backtest.backtest_metrics import compute_metrics
from app.services.market_signal.technical_indicators import pullback_series, trend_series
from app.services.market_signal.technical_signal_service import fetch_close_history
from app.services.tactical_allocation_service import (
    LEVERAGED_ASSETS,
    TACTICAL_ASSETS,
    ConfirmState,
    classify_regime,
    step_confirmation,
)
from app.services.tactical_dip import DIP_EXIT_STAGES, advance_dip_level, apply_dip
from app.services.tactical_tilt import REAL_YIELD_LOOKBACK, RS_SMA, apply_tilt, classify_tilt
from app.utils.cache_keys import TTL_TACTICAL_BACKTEST, get_cached_json, set_cached_json, tactical_backtest_key

if TYPE_CHECKING:
    from app.core.cache_store import CacheStore

logger = structlog.get_logger()

_WARMUP_DAYS = 420  # 200일선 워밍업(달력일)
_MAX_SERIES_POINTS = 260  # 차트용 다운샘플 상한
# 레버리지 ETF → (기초 종목, 연 보수+차입비용 근사). 차입비용은 장기 단기금리 평균 근사 2%(1배분 차입).
_LEVERAGE_BASE: dict[str, tuple[str, float]] = {"QLD": ("QQQ", 0.0095 + 0.02), "SSO": ("SPY", 0.0089 + 0.02)}
_LEVERAGE = 2.0
_COST_RATE = 0.001  # 편도 거래비용(해외 ETF 수수료+스프레드 근사) — 매수·매도 금액 각각에 부과


def vix_to_macro_level(vix: float | None) -> str:
    if vix is None or pd.isna(vix):
        return "YELLOW"
    if vix >= 30:
        return "RED"
    if vix < 20:
        return "GREEN"
    return "YELLOW"


def leveraged_returns(base_rets: pd.DataFrame, actual: pd.DataFrame | None) -> pd.DataFrame:
    """QLD·SSO 일수익률 — 실제 시세 수익률이 있으면 그것, 없으면 기초 수익률로 합성."""
    out = pd.DataFrame(index=base_rets.index)
    for lev, (base, annual_cost) in _LEVERAGE_BASE.items():
        synthetic = base_rets[base] * _LEVERAGE - annual_cost / 252
        if actual is not None and lev in actual.columns:
            real = actual[lev].reindex(base_rets.index).pct_change(fill_method=None)
            out[lev] = real.where(real.notna(), synthetic)
        else:
            out[lev] = synthetic
    return out


def _rebalance(holdings: dict[str, float], equity: float, weights: dict[str, float]) -> tuple[dict[str, float], float]:
    """목표 비중으로 재배분하고 거래비용을 뺀다. (새 보유, 회전율 = Σ|Δ비중|/2 — 현금 포함, 0~1).

    보유가 비어 있으면(최초 진입) 전액 현금에서 사는 것으로 보고 비용은 물리되, 회전율은 0으로 돌려준다 —
    회전율은 "진입 이후 얼마나 자주 갈아탔나"를 보여주는 값이다.
    """
    entering = not (equity > 0 and holdings)
    if entering:
        old = {a: (100.0 if a == "CASH" else 0.0) for a in TACTICAL_ASSETS}
    else:
        old = {a: holdings.get(a, 0.0) / equity * 100.0 for a in TACTICAL_ASSETS}
    deltas = {a: abs(weights.get(a, 0.0) - old[a]) for a in TACTICAL_ASSETS}
    traded = sum(v for a, v in deltas.items() if a != "CASH") / 100.0
    net = equity * (1 - traded * _COST_RATE)
    turnover = 0.0 if entering else sum(deltas.values()) / 200.0
    return {a: net * weights.get(a, 0.0) / 100.0 for a in TACTICAL_ASSETS}, turnover


def _grow(holdings: dict[str, float], row: pd.Series, cash_rate: float) -> None:
    """하루치 수익률 적용 — 현금은 국채 이자, 시세 없는 0% 자산은 그대로."""
    for asset in holdings:
        if asset == "CASH":
            holdings[asset] *= 1 + cash_rate
        elif asset in row.index:
            holdings[asset] *= 1 + float(row[asset])


def simulate_static(rets: pd.DataFrame, cash_daily: pd.Series, weights: dict[str, float], first: int) -> list[float]:
    """고정 비중을 매월 첫 거래일에 리밸런싱하며 보유한 가치(100 시작) — "평균 비중 고정" 비교선."""
    holdings, _ = _rebalance({}, 100.0, weights)
    values = [sum(holdings.values())]
    month = (rets.index[first].year, rets.index[first].month)
    for i in range(first + 1, len(rets)):
        _grow(holdings, rets.iloc[i], float(cash_daily.iloc[i]))
        ts = rets.index[i]
        if (ts.year, ts.month) != month:
            month = (ts.year, ts.month)
            holdings, _ = _rebalance(holdings, sum(holdings.values()), weights)
        values.append(sum(holdings.values()))
    return values


def simulate(
    closes: pd.DataFrame,
    vix: pd.Series,
    weights_table: dict[str, dict[str, float]],
    start: pd.Timestamp,
    real_yield: pd.Series | None = None,
    tilt_shift_pct: float = 0.0,
    dip_shift_pct: float = 0.0,
    dip_exit_stages: frozenset[str] = DIP_EXIT_STAGES,
    cash_yield: pd.Series | None = None,
    use_macro: bool = True,
) -> dict[str, Any]:
    """closes: QQQ/SPY(+선택 DIA·QLD·SSO) 종가(워밍업 포함), vix·real_yield·cash_yield(연율 %): 일별 시계열.

    start 이후 구간을 평가한다.
    """
    has_dia = "DIA" in closes.columns
    if not has_dia and any(w.get("DIA", 0.0) > 0 for w in weights_table.values()):
        raise ValueError("DIA 과거 시세를 불러오지 못했습니다. 잠시 후 다시 시도해주세요.")
    bench_tickers = ["SPY", "QQQ"] + (["DIA"] if has_dia else [])
    lev_actual = closes[[c for c in closes.columns if c in LEVERAGED_ASSETS]]
    closes = closes[["QQQ", "SPY"] + (["DIA"] if has_dia else [])].dropna()
    trends = {t: trend_series(closes[t]) for t in ("QQQ", "SPY")}
    vix_aligned = vix.reindex(closes.index).ffill()
    ratio = closes["QQQ"] / closes["SPY"]
    rel_strength = (ratio / ratio.rolling(RS_SMA).mean() - 1) * 100
    ry = (real_yield if real_yield is not None else pd.Series(dtype=float)).reindex(closes.index).ffill()
    ry_change = ry - ry.shift(REAL_YIELD_LOOKBACK)
    tilt_on = tilt_shift_pct > 0
    qqq_stages = pullback_series(closes["QQQ"]) if dip_shift_pct > 0 else None

    eval_idx = [i for i, ts in enumerate(closes.index) if ts >= start]
    if len(eval_idx) < 2:
        raise ValueError("백테스트 기간의 시세 데이터가 부족합니다.")

    rets = closes.pct_change().fillna(0.0)
    rets = rets.join(leveraged_returns(rets, lev_actual if not lev_actual.empty else None))
    cy = (cash_yield if cash_yield is not None else pd.Series(dtype=float)).reindex(closes.index).ffill()
    cash_daily = (cy.fillna(0.0) / 100.0 / 252).clip(lower=0.0)
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
    dip_level = 0
    dip_entries = 0
    dip_days = 0
    timeline: list[dict[str, str]] = []
    target: dict[str, float] = {}
    target_sum: dict[str, float] = dict.fromkeys(TACTICAL_ASSETS, 0.0)
    target_days = 0
    turnover = 0.0

    first = eval_idx[0]
    for i in range(first, len(closes)):
        if i > first:
            # t-1 종가 기준 보유분에 t일 수익률(현금은 국채 이자) 적용
            _grow(holdings, rets.iloc[i], float(cash_daily.iloc[i]))
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
            use_macro=use_macro,
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

        dip_changed = False
        if qqq_stages is not None:
            new_level = advance_dip_level(dip_level, qqq_stages.iloc[i], state.current, dip_exit_stages)
            dip_changed = new_level != dip_level
            dip_entries += int(dip_level == 0 < new_level)
            dip_level = new_level
        dip_days += int(dip_level > 0)

        if (changed or tilt_changed or dip_changed) and state.current is not None:
            tilted = apply_tilt(weights_table[state.current], tilt, tilt_shift_pct)
            target = apply_dip(tilted, dip_level, dip_shift_pct)
            holdings, traded = _rebalance(holdings, equity, target)
            turnover += traded
            equity = sum(holdings.values())
            strat_values[-1] = equity  # 거래비용은 그날 가치에 반영
        if state.current is not None:
            days_in[state.current] += 1
        if target:
            for a in TACTICAL_ASSETS:
                target_sum[a] += target.get(a, 0.0)
            target_days += 1
        tilt_days[tilt] += 1

    eval_closes = closes.iloc[first:]
    bench = {t: (eval_closes[t] / eval_closes[t].iloc[0] * 100.0).tolist() for t in bench_tickers}
    avg_weights = {a: round(v / (target_days or 1), 1) for a, v in target_sum.items()}
    avg_weights["CASH"] = round(100.0 - sum(v for a, v in avg_weights.items() if a != "CASH"), 1)
    static_values = simulate_static(rets, cash_daily, avg_weights, first)
    eval_years = max(len(strat_values) - 1, 1) / 252
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
            compute_metrics("평균 비중 고정", static_values).model_dump(),
            *(compute_metrics(f"{t} 보유", bench[t]).model_dump() for t in bench_tickers),
        ],
        "series": [
            {
                "date": dates[i],
                "strategy": round(strat_values[i], 2),
                "static": round(static_values[i], 2),
                "spy": round(bench["SPY"][i], 2),
                "qqq": round(bench["QQQ"][i], 2),
                **({"dia": round(bench["DIA"][i], 2)} if has_dia else {}),
            }
            for i in picks
        ],
        "regime_switches": switches,
        "avg_weights": avg_weights,
        "turnover_pct_per_year": round(turnover / eval_years * 100, 1),
        "dip_entries": dip_entries,
        "dip_time_pct": round(dip_days / (len(closes) - first or 1) * 100, 1),
        "tilt_switches": tilt_switches,
        "tilt_time_pct": {k: round(v / (sum(tilt_days.values()) or 1) * 100, 1) for k, v in tilt_days.items()},
        "regime_time_pct": {k: round(v / total_days * 100, 1) for k, v in days_in.items()},
        "regime_timeline": timeline[-20:],
    }


async def _fetch_fred_history(series_id: str, days: int) -> pd.Series:
    from app.services.market_signal.economic_indicator_service import fred_get_observations, parse_fred_obs
    from app.utils.circuit_breaker import fred_circuit
    from app.utils.kst import today_kst

    # 서킷이 열려 있으면 바로 빈 시리즈 — 호출부는 예외와 같게 매크로 없이 계산하고 안내 문구를 붙인다
    if not fred_circuit.is_available():
        logger.warning("fred_circuit_open", signal=f"tactical_backtest_{series_id}")
        return pd.Series(dtype=float)
    raw = await fred_circuit.call(
        fred_get_observations,
        series_id,
        limit=days + 30,  # 일별 시리즈 — 달력일 수 이상이면 기간 전체를 덮는다
        observation_start=today_kst() - timedelta(days=days),
    )
    points = parse_fred_obs(raw)
    if not points:
        return pd.Series(dtype=float)
    return pd.Series({pd.Timestamp(p["date"]): p["value"] for p in points}).sort_index()


async def _fetch_vix_history(days: int) -> pd.Series:
    return await _fetch_fred_history("VIXCLS", days)


async def _fetch_real_yield_history(days: int) -> pd.Series:
    return await _fetch_fred_history("DFII10", days)


async def _fetch_cash_yield_history(days: int) -> pd.Series:
    return await _fetch_fred_history("DTB3", days)  # 미국 3개월 국채(연율 %)


def _settings_hash(
    weights_table: dict[str, dict[str, float]], tilt_shift_pct: float, dip_shift_pct: float, use_macro: bool = True
) -> str:
    # 계산 방식이 바뀌면 cache_keys.tactical_backtest_key의 버전을 올린다
    payload = json.dumps(
        {"w": weights_table, "tilt": tilt_shift_pct, "dip": dip_shift_pct, "macro": use_macro}, sort_keys=True
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


async def run_tactical_backtest(
    weights_table: dict[str, dict[str, float]],
    years: int,
    cache: CacheStore | None,
    tilt_shift_pct: float = 0.0,
    dip_shift_pct: float = 0.0,
    use_macro: bool = True,
) -> dict[str, Any]:
    key = tactical_backtest_key(_settings_hash(weights_table, tilt_shift_pct, dip_shift_pct, use_macro), years)
    if (hit := await get_cached_json(cache, key)) is not None:
        return hit

    days = years * 366 + _WARMUP_DAYS
    # 레버리지 ETF는 비중표에 쓰일 때만 받는다(결측이면 합성 수익률로 대체)
    uses_leverage = [a for a in sorted(LEVERAGED_ASSETS) if any(w.get(a, 0.0) > 0 for w in weights_table.values())]
    tickers = ["QQQ", "SPY", "DIA", *uses_leverage]

    async def _no_real_yield() -> pd.Series | None:
        return None

    # 시세·VIX·국채·실질금리는 서로 독립이라 동시에 받는다(순차면 FRED 왕복이 콜드 캐시에서 그대로 누적됐다)
    closes_map, vix_res, cash_res, real_res = await asyncio.gather(
        fetch_close_history(tickers, days),
        _fetch_vix_history(days),
        _fetch_cash_yield_history(days),
        _fetch_real_yield_history(days) if tilt_shift_pct > 0 else _no_real_yield(),
        return_exceptions=True,
    )
    if isinstance(closes_map, BaseException):
        raise closes_map
    if "QQQ" not in closes_map or "SPY" not in closes_map:
        raise ValueError("QQQ/SPY 과거 시세를 불러오지 못했습니다. 잠시 후 다시 시도해주세요.")
    # DIA는 비교·선택 자산 — 결측이면 빼고 진행(비중표에 DIA가 있으면 simulate가 오류)
    closes = pd.DataFrame({t: closes_map[t] for t in tickers if t in closes_map})
    closes.index = pd.to_datetime(closes.index).tz_localize(None)

    if isinstance(vix_res, BaseException):
        logger.warning("tactical_backtest_vix_failed", error=str(vix_res))
        vix = pd.Series(dtype=float)
    else:
        vix = vix_res
    if not use_macro:
        macro_note = "매크로 미반영(차트 추세만) 설정으로 계산했습니다."
    elif not vix.empty:
        macro_note = "매크로 입력은 VIX만으로 근사했습니다(실시간 신호는 8개 지표 복합)."
    else:
        macro_note = "VIX 이력을 받지 못해 매크로 입력 없이(항상 '주의') 차트 추세만으로 계산했습니다."

    if isinstance(cash_res, BaseException):
        logger.warning("tactical_backtest_cash_yield_failed", error=str(cash_res))
        cash_yield = pd.Series(dtype=float)
    else:
        cash_yield = cash_res
    if cash_yield.empty:
        macro_note += " 국채 금리 이력을 받지 못해 현금 수익률은 0으로 계산했습니다."

    real_yield: pd.Series | None = None
    if tilt_shift_pct > 0:
        if isinstance(real_res, BaseException):
            logger.warning("tactical_backtest_real_yield_failed", error=str(real_res))
        else:
            real_yield = real_res
        if real_yield is None or real_yield.empty:
            macro_note += " 실질금리 이력을 받지 못해 나스닥/S&P 틸트는 반영하지 않았습니다."

    start = closes.index[-1] - timedelta(days=years * 365)
    # 일 단위 파이썬 루프(20년이면 약 5,000회 × pandas 접근)라 Render 저사양 CPU에서 수 초 걸린다 —
    # 이벤트 루프에서 돌리면 그동안 모든 사용자의 요청이 멈추므로 스레드로 넘긴다
    result = await asyncio.to_thread(
        simulate,
        closes,
        vix,
        weights_table,
        start,
        real_yield=real_yield,
        tilt_shift_pct=tilt_shift_pct,
        dip_shift_pct=dip_shift_pct,
        cash_yield=cash_yield,
        use_macro=use_macro,
    )
    result["years"] = years
    result["use_macro"] = use_macro
    result["tilt_shift_pct"] = tilt_shift_pct
    result["dip_shift_pct"] = dip_shift_pct
    result["macro_note"] = macro_note
    result["assumptions"] = (
        "국면 확정 2거래일 연속 · 공격 국면은 매크로 '주의'까지 유지 · 나스닥/S&P 틸트 월 1회 · "
        + ("웅덩이 투입은 공격 국면만·회복 시 회수 · " if dip_shift_pct > 0 else "")
        + "전환 시에만 리밸런싱 · "
        + ("QLD·SSO 상장 전 구간은 2배 합성(보수·차입비용 차감) · " if uses_leverage else "")
        + ("현금은 미국 3개월 국채 금리 · " if not cash_yield.empty else "현금 수익률 0 · ")
        + f"거래비용 매매금액의 {_COST_RATE * 100:g}% · 세금·환율 미반영"
    )
    await set_cached_json(cache, key, result, TTL_TACTICAL_BACKTEST)
    return result
