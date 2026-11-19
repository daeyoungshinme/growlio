"""포트폴리오 위험 분석 서비스 (plans/137 A).

원화 기준 1년 일별 수익률로 하락 위험(VaR·최대 낙폭)·시장 대비 변동성·베타를 계산하고,
지수 기준 쏠림(`etf/index_exposure_service`)을 함께 돌려준다. 결과는 1시간 캐시.

함정:
- 종목별 종가는 **날짜로 맞춘다** — 한국·미국 휴장일이 달라 순번으로 짝지으면 다른 날 수익률이 섞인다.
- 미국 상장 종목·S&P500은 `USDKRW=X`를 곱해 원화로 본다(원화 투자자가 실제로 겪는 변동).
- 증권 계좌 예수금은 수익률 0 자산으로 넣는다 — 빼면 VaR·변동성이 과대.
- 베타는 주간 수익률 — 한국·미국 장 시간차 때문에 같은 날 일간 상관은 과소 추정된다.
"""

from __future__ import annotations

import asyncio
import math
import uuid
from datetime import timedelta
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import is_non_tradable
from app.core.database import release_read_connection
from app.services.accounts._snapshot_queries import latest_snapshot_rows
from app.services.etf.index_exposure_service import get_index_exposure
from app.services.market_data.market_data_fetcher import fetch_yf_close_series
from app.services.market_data.yahoo_price import run_yf_bounded
from app.services.market_data.yahoo_price import to_yf_symbol as _to_yf_symbol
from app.services.portfolio.portfolio_service import STOCK_TYPES
from app.utils.cache_keys import TTL_RISK_ANALYSIS, CacheStoreType, get_cached_json, risk_key, set_cached_json
from app.utils.inproc_lock import single_flight_fetch
from app.utils.kst import today_kst

if TYPE_CHECKING:
    import pandas as pd

logger = structlog.get_logger()

SP500_SYMBOL = "^GSPC"
USDKRW_SYMBOL = "USDKRW=X"
# 달러로 거래되는 시장 — 원화 환산 대상(토스 해외 포지션 market은 "US")
_USD_MARKETS = frozenset({"NYSE", "NASDAQ", "AMEX", "US"})

_LOOKBACK_ROWS = 252  # 최근 1년 거래일
_FFILL_LIMIT = 3  # 휴장일 메우기 상한(연휴 포함)
_MIN_SYMBOL_COVERAGE = 0.6  # 이보다 짧은 이력의 종목은 계산에서 뺀다
_MIN_RETURN_POINTS = 20  # 이보다 적으면 data_available=False
_MIN_WEEKLY_POINTS = 20  # 주간 베타 최소 표본
_TOP_INDEX_COUNT = 3
_SP500_DROP_SCENARIO = 0.10


# ── 순수 계산 ──────────────────────────────────────────────────


def _calc_var(returns: list[float], confidence: float) -> float:
    """역사적 VaR(%) — 손실 쪽 분위수의 절댓값."""
    if not returns:
        return 0.0
    sorted_r = sorted(returns)
    idx = max(0, int((1 - confidence) * len(sorted_r)) - 1)
    return abs(min(sorted_r[idx], 0.0)) * 100


def _calc_max_drawdown(returns: list[float]) -> float:
    """누적 수익 곡선의 고점 대비 최대 하락(%) — 양수로 돌려준다."""
    peak = 1.0
    level = 1.0
    worst = 0.0
    for r in returns:
        level *= 1 + r
        peak = max(peak, level)
        worst = min(worst, level / peak - 1)
    return abs(worst) * 100


def _calc_beta(portfolio_rets: list[float], bench_rets: list[float]) -> float | None:
    """같은 길이로 맞춘 두 수익률 시계열의 베타. 표본이 부족하거나 벤치마크 분산이 0이면 None."""
    n = min(len(portfolio_rets), len(bench_rets))
    if n < _MIN_WEEKLY_POINTS:
        return None
    p = portfolio_rets[-n:]
    b = bench_rets[-n:]
    mean_p = sum(p) / n
    mean_b = sum(b) / n
    cov = sum((p[i] - mean_p) * (b[i] - mean_b) for i in range(n)) / (n - 1)
    var_b = sum((x - mean_b) ** 2 for x in b) / (n - 1)
    return cov / var_b if var_b > 0 else None


def _annualized_vol_pct(returns: list[float]) -> float:
    n = len(returns)
    if n < 2:
        return 0.0
    mean = sum(returns) / n
    std = math.sqrt(sum((r - mean) ** 2 for r in returns) / (n - 1))
    return std * math.sqrt(252) * 100


def _normalize_index(series: pd.Series) -> pd.Series:
    """Yahoo(시간대 포함)·pykrx(날짜) 인덱스를 시간대 없는 자정 날짜로 맞춘다."""
    import pandas as pd

    idx = pd.DatetimeIndex(pd.to_datetime(series.index))
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    out = series.copy()
    out.index = idx.normalize()
    return out[~out.index.duplicated(keep="last")]


def _to_krw(series: pd.Series, fx: pd.Series | None) -> pd.Series | None:
    """달러 종가 × 같은 날(없으면 직전) 환율. 환율이 없으면 None — 원화 기준을 지킬 수 없다."""
    if fx is None or fx.empty:
        return None
    rate = fx.reindex(fx.index.union(series.index)).ffill().reindex(series.index)
    return (series * rate).dropna()


def build_krw_close_frame(
    closes: dict[str, pd.Series], usd_symbols: set[str], symbols: list[str]
) -> tuple[pd.DataFrame, list[str]]:
    """종목별 종가 → 원화 종가 DataFrame(날짜 정렬·휴장일 메움·최근 1년).

    Returns: (frame, 환율이 없어 원화로 못 바꾼 달러 종목)
    """
    import pandas as pd

    fx_raw = closes.get(USDKRW_SYMBOL)
    fx = _normalize_index(fx_raw) if fx_raw is not None else None
    columns: dict[str, pd.Series] = {}
    no_fx: list[str] = []
    for sym in symbols:
        raw = closes.get(sym)
        if raw is None or raw.empty:
            continue
        s = _normalize_index(raw)
        if sym in usd_symbols:
            converted = _to_krw(s, fx)
            if converted is None:
                no_fx.append(sym)
                continue
            s = converted
        columns[sym] = s
    if not columns:
        return pd.DataFrame(), no_fx
    frame = pd.concat(columns, axis=1).sort_index()
    frame = frame.ffill(limit=_FFILL_LIMIT)
    return frame.tail(_LOOKBACK_ROWS + 1), no_fx


def _weekly_returns(daily: pd.Series) -> list[float]:
    level = (1 + daily).cumprod()
    # resample은 pandas 내부 numpy 경고를 내서(테스트 경고 게이트) 주 단위 groupby로 같은 값을 만든다
    weekly = level.groupby(level.index.to_period("W-FRI")).last().pct_change(fill_method=None).dropna()
    return [float(x) for x in weekly if math.isfinite(x)]


def compute_risk_result(
    holdings: list[dict[str, Any]],
    cash_krw: float,
    closes: dict[str, pd.Series],
) -> dict[str, Any]:
    """원화 기준 위험 지표(순수 CPU 계산, 스레드에서 실행).

    holdings: [{"symbol": yf 심볼, "value_krw": 평가액, "usd": 달러 거래 여부}]
    """
    stock_value = sum(h["value_krw"] for h in holdings)
    usd_symbols = {h["symbol"] for h in holdings if h["usd"]} | {SP500_SYMBOL}
    symbols = [h["symbol"] for h in holdings]
    frame, no_fx = build_krw_close_frame(closes, usd_symbols, [*symbols, SP500_SYMBOL])
    if no_fx:
        logger.warning("risk_fx_missing", symbols=no_fx[:5])

    # 상한(_FFILL_LIMIT)보다 긴 휴장(추석 등)도 마지막 종가 기준 수익률로 — pct_change 기본 pad(폐기 예정)와 같은 값을
    # 명시적으로 만든다. pandas 3에서 기본 fill이 사라져도 연휴 뒤 첫 수익률이 NaN→0으로 빠지지 않는다
    returns = frame.ffill().pct_change(fill_method=None).iloc[1:] if not frame.empty else frame
    covered = {c for c in returns.columns if returns[c].notna().mean() >= _MIN_SYMBOL_COVERAGE}
    included = [h for h in holdings if h["symbol"] in covered]
    included_value = sum(h["value_krw"] for h in included)
    # 같은 심볼이 여러 시장 키로 들어와도 가중치는 합산
    weight_by_symbol: dict[str, float] = {}
    total_for_weights = included_value + max(cash_krw, 0.0)
    for h in included:
        weight_by_symbol[h["symbol"]] = weight_by_symbol.get(h["symbol"], 0.0) + h["value_krw"] / total_for_weights

    port: list[float] = []
    daily_port = None
    if weight_by_symbol and len(returns) >= _MIN_RETURN_POINTS:
        cols = list(weight_by_symbol)
        # 상장 전 구간 등 남은 결측은 그 종목을 현금처럼(수익률 0) 본다 — 커버리지 60% 이상만 들어온다
        daily_port = returns[cols].fillna(0.0).mul([weight_by_symbol[c] for c in cols], axis=1).sum(axis=1)
        port = [float(x) for x in daily_port if math.isfinite(x)]

    data_available = len(port) >= _MIN_RETURN_POINTS
    total_value = stock_value + max(cash_krw, 0.0)
    vol = _annualized_vol_pct(port)
    var_95 = _calc_var(port, 0.95)

    beta: float | None = None
    vol_ratio: float | None = None
    if daily_port is not None and SP500_SYMBOL in returns.columns:
        bench = returns[SP500_SYMBOL].dropna()
        joined_idx = daily_port.index.intersection(bench.index)
        if len(joined_idx) >= _MIN_RETURN_POINTS:
            beta = _calc_beta(_weekly_returns(daily_port.loc[joined_idx]), _weekly_returns(bench.loc[joined_idx]))
            bench_vol = _annualized_vol_pct([float(x) for x in bench.loc[joined_idx]])
            vol_ratio = round(vol / bench_vol, 2) if bench_vol > 0 else None

    coverage_pct = included_value / stock_value * 100 if stock_value > 0 else 0.0
    return {
        "data_available": data_available,
        "total_value_krw": round(total_value, 0),
        "cash_weight_pct": round(max(cash_krw, 0.0) / total_value * 100, 2) if total_value > 0 else 0.0,
        "coverage_pct": round(coverage_pct, 1),
        "var_95_pct": round(var_95, 2),
        "var_95_krw": round(var_95 / 100 * total_for_weights, 0),
        "annualized_volatility_pct": round(vol, 2),
        "max_drawdown_pct": round(_calc_max_drawdown(port), 2),
        "beta_sp500": round(beta, 3) if beta is not None else None,
        "vol_ratio_vs_sp500": vol_ratio if data_available else None,
        "sp500_10pct_drop_krw": (
            round(beta * _SP500_DROP_SCENARIO * total_for_weights, 0) if beta is not None and data_available else None
        ),
        "note": "최근 1년 원화 기준 추정값(예수금 포함)" if data_available else "가격 데이터가 부족해요",
    }


def _concentration(pos_map: dict[str, dict], exposure: Any) -> dict[str, Any]:
    """종목(티커) 최대 비중과 지수 기준 상위 노출 — 주식 평가액 대비 %."""
    stock_value = sum(p["value_krw"] for p in pos_map.values())
    # 같은 종목이 증권사마다 다른 시장 코드(토스 US·KIS NASDAQ)로 들어와도 한 종목으로 합친다
    by_symbol: dict[str, dict] = {}
    for p in pos_map.values():
        sym = _to_yf_symbol(p["ticker"], p["market"])
        entry = by_symbol.setdefault(sym, {"ticker": p["ticker"], "name": p.get("name"), "value_krw": 0.0})
        entry["value_krw"] += p["value_krw"]
    top = max(by_symbol.values(), key=lambda p: p["value_krw"], default=None)
    top_indexes: list[dict[str, Any]] = []
    if exposure is not None:
        top_indexes = [
            {"key": g.key, "label": g.label, "pct_of_stock": g.pct_of_stock}
            for g in sorted((g for g in exposure.groups if g.kind == "INDEX"), key=lambda g: -g.value_krw)[
                :_TOP_INDEX_COUNT
            ]
        ]
    return {
        "top_holding_weight_pct": round(top["value_krw"] / stock_value * 100, 2) if top and stock_value > 0 else 0.0,
        "top_holding_name": (top.get("name") or top["ticker"]) if top else None,
        "top_index_exposures": top_indexes,
    }


# ── 조회 ──────────────────────────────────────────────────────


async def _load_positions_and_cash(user_id: uuid.UUID, db: AsyncSession) -> tuple[dict[str, dict], float]:
    """최신 스냅샷의 종목별 평가액과 증권 계좌 예수금(평가액 − 종목 합)."""
    rows = await latest_snapshot_rows(db, user_id, with_positions=True)
    pos_map: dict[str, dict] = {}
    cash = 0.0
    for snap, acc in rows:
        positions_value = 0.0
        for pos in snap.position_items or []:
            value = float(pos.value_krw or 0)
            positions_value += value
            if value <= 0 or is_non_tradable(pos.ticker, pos.market):
                continue
            key = f"{pos.ticker}-{pos.market}"
            entry = pos_map.setdefault(
                key, {"ticker": pos.ticker, "market": pos.market, "name": pos.name or pos.ticker, "value_krw": 0.0}
            )
            entry["value_krw"] += value
        if acc.asset_type in STOCK_TYPES:
            cash += max(float(snap.amount_krw or 0) - positions_value, 0.0)
    return pos_map, cash


def _sync_fetch_closes(symbols: list[str]) -> dict[str, pd.Series]:
    end = today_kst()
    # 252거래일 + 연휴·주간 리샘플 여유
    return fetch_yf_close_series(symbols, end - timedelta(days=400), end)


async def get_portfolio_risk_metrics(
    user_id: uuid.UUID,
    db: AsyncSession,
    cache: CacheStoreType = None,
) -> dict:
    cache_key = risk_key(user_id)

    async def _read_cache() -> dict | None:
        return await get_cached_json(cache, cache_key)

    cached = await _read_cache()
    if cached is not None:
        return cached

    pos_map, cash_krw = await _load_positions_and_cash(user_id, db)
    if not pos_map:
        return _empty_risk_result()

    async def _fetch_and_cache() -> dict:
        try:
            # 지수 분류는 대시보드 overview(DB)를 읽은 뒤 커넥션을 반납한다
            exposure = await get_index_exposure(cache, db, user_id)
        except Exception as e:
            logger.warning("risk_index_exposure_failed", error=str(e))
            exposure = None
        # 1년 일봉 다운로드 동안 커넥션을 쥐지 않게(plans/125 A4)
        await release_read_connection(db)

        holdings = [
            {
                "symbol": _to_yf_symbol(p["ticker"], p["market"]),
                "value_krw": p["value_krw"],
                "usd": (p["market"] or "").upper() in _USD_MARKETS,
            }
            for p in pos_map.values()
        ]
        symbols = sorted({h["symbol"] for h in holdings} | {SP500_SYMBOL, USDKRW_SYMBOL})
        closes = await run_yf_bounded(_sync_fetch_closes, symbols)
        result = await asyncio.to_thread(compute_risk_result, holdings, cash_krw, closes)
        result.update(_concentration(pos_map, exposure))
        result["position_count"] = len(pos_map)

        await set_cached_json(cache, cache_key, result, TTL_RISK_ANALYSIS)
        return result

    if cache is None:
        return await _fetch_and_cache()

    return await single_flight_fetch(cache, cache_key, _read_cache, _fetch_and_cache)


def _empty_risk_result() -> dict:
    return {
        "data_available": False,
        "total_value_krw": 0.0,
        "cash_weight_pct": 0.0,
        "coverage_pct": 0.0,
        "var_95_pct": 0.0,
        "var_95_krw": 0.0,
        "annualized_volatility_pct": 0.0,
        "max_drawdown_pct": 0.0,
        "beta_sp500": None,
        "vol_ratio_vs_sp500": None,
        "sp500_10pct_drop_krw": None,
        "top_holding_weight_pct": 0.0,
        "top_holding_name": None,
        "top_index_exposures": [],
        "position_count": 0,
        "note": "보유 종목이 없어요",
    }
