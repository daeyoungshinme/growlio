"""차트 기술적 지표 — 일봉 종가 Series 입력의 순수 함수 (I/O 없음).

전술 배분(tactical_allocation_service)의 추세 판정 입력. 모두 일봉 종가 기준이며, 데이터가 지표 계산에
필요한 길이보다 짧으면 None을 돌려 호출부가 "판정 불가"로 다루게 한다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, TypedDict

if TYPE_CHECKING:
    import pandas as pd  # 런타임 import는 trend_series 안에서만 — 앱 기동 시 pandas 로드 방지

TrendState = Literal["UP", "NEUTRAL", "DOWN", "UNKNOWN"]

SMA_SHORT = 50
SMA_LONG = 200
RSI_PERIOD = 14
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
HIGH_LOOKBACK = 252  # 52주 거래일
# 추세 히스테리시스 — 이미 UP(DOWN)인 상태는 종가가 200일선 아래(위)로 이 비율 이상 벗어나야 이탈한다.
# 200일선 근처에서 종가가 위아래로 오가며 국면이 하루 단위로 뒤집히던 왕복을 줄인다.
TREND_BAND_PCT = 1.0


class TechnicalSnapshot(TypedDict):
    close: float | None
    sma50: float | None
    sma200: float | None
    rsi14: float | None
    macd_hist: float | None
    drawdown_pct: float | None  # 52주 고점 대비 하락률(%, 0 이하)
    trend: TrendState


def sma(close: pd.Series, period: int) -> float | None:
    if len(close) < period:
        return None
    return float(close.iloc[-period:].mean())


def rsi(close: pd.Series, period: int = RSI_PERIOD) -> float | None:
    """Wilder 평활 RSI."""
    if len(close) < period + 1:
        return None
    delta = close.diff().dropna()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False, min_periods=period).mean().iloc[-1]
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False, min_periods=period).mean().iloc[-1]
    if loss == 0:
        return 100.0 if gain > 0 else 50.0
    return float(100 - 100 / (1 + gain / loss))


def macd_histogram(close: pd.Series) -> float | None:
    if len(close) < MACD_SLOW + MACD_SIGNAL:
        return None
    macd_line = close.ewm(span=MACD_FAST, adjust=False).mean() - close.ewm(span=MACD_SLOW, adjust=False).mean()
    signal_line = macd_line.ewm(span=MACD_SIGNAL, adjust=False).mean()
    return float(macd_line.iloc[-1] - signal_line.iloc[-1])


def drawdown_from_high_pct(close: pd.Series, lookback: int = HIGH_LOOKBACK) -> float | None:
    if close.empty:
        return None
    window = close.iloc[-lookback:]
    high = float(window.max())
    if high <= 0:
        return None
    return float((close.iloc[-1] / high - 1) * 100)


def classify_trend(
    close: float | None, sma50: float | None, sma200: float | None, prev: TrendState | None = None
) -> TrendState:
    """200일선 위 + 50>200(골든크로스 상태)이면 UP, 반대면 DOWN, 엇갈리면 NEUTRAL.

    `prev`(직전 거래일 상태)가 UP/DOWN이면 종가 조건에 `TREND_BAND_PCT` 완충을 둔다 — 50/200 교차 조건은
    그 자체로 느리게 움직여 완충 없이 그대로 쓴다.
    """
    if close is None or sma50 is None or sma200 is None:
        return "UNKNOWN"
    band = sma200 * TREND_BAND_PCT / 100
    if prev == "UP" and close >= sma200 - band and sma50 > sma200:
        return "UP"
    if prev == "DOWN" and close <= sma200 + band and sma50 < sma200:
        return "DOWN"
    if close > sma200 and sma50 > sma200:
        return "UP"
    if close < sma200 and sma50 < sma200:
        return "DOWN"
    return "NEUTRAL"


def compute_snapshot(close: pd.Series) -> TechnicalSnapshot:
    close = close.dropna().astype(float)
    last = float(close.iloc[-1]) if not close.empty else None
    s50 = sma(close, SMA_SHORT)
    s200 = sma(close, SMA_LONG)
    # 추세는 완충 상태를 이어받아야 해서 단일 시점 계산이 아니라 이력 전체를 따라간 마지막 값을 쓴다
    trend: TrendState = trend_series(close).iloc[-1] if not close.empty else "UNKNOWN"
    return TechnicalSnapshot(
        close=last,
        sma50=s50,
        sma200=s200,
        rsi14=rsi(close),
        macd_hist=macd_histogram(close),
        drawdown_pct=drawdown_from_high_pct(close),
        trend=trend,
    )


def trend_series(close: pd.Series) -> pd.Series:
    """일자별 추세 상태 Series — 각 시점에서 그날까지의 데이터와 직전 상태만 사용(룩어헤드 없음)."""
    import pandas as pd

    close = close.dropna().astype(float)
    s50 = close.rolling(SMA_SHORT).mean()
    s200 = close.rolling(SMA_LONG).mean()
    states: list[TrendState] = []
    prev: TrendState | None = None
    for c, a, b in zip(close, s50, s200, strict=True):
        prev = classify_trend(c, None if pd.isna(a) else a, None if pd.isna(b) else b, prev)
        states.append(prev)
    return pd.Series(states, index=close.index)
