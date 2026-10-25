"""차트 기술적 지표 — 일봉 종가 Series 입력의 순수 함수 (I/O 없음).

전술 배분(tactical_allocation_service)의 추세 판정 입력. 모두 일봉 종가 기준이며, 데이터가 지표 계산에
필요한 길이보다 짧으면 None을 돌려 호출부가 "판정 불가"로 다루게 한다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, TypedDict

if TYPE_CHECKING:
    import pandas as pd  # 런타임 import는 trend_series 안에서만 — 앱 기동 시 pandas 로드 방지

TrendState = Literal["UP", "NEUTRAL", "DOWN", "UNKNOWN"]
# 눌림목(웅덩이) 단계 — 종가가 가장 깊이 내려간 이평선. 120일선 아래이면서 RSI 과매도면 가장 깊은 단계.
PullbackStage = Literal["NONE", "SMA20", "SMA60", "SMA120", "SMA120_RSI", "UNKNOWN"]

SMA_20, SMA_60, SMA_120 = 20, 60, 120
PULLBACK_RSI_OVERSOLD = 35.0
SMA_SHORT = 50
SMA_LONG = 200
RSI_PERIOD = 14
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
HIGH_LOOKBACK = 252  # 52주 거래일
# 추세 히스테리시스 — 이미 UP(DOWN)인 상태는 종가가 200일선 아래(위)로 이 비율 이상 벗어나야 이탈한다.
# 200일선 근처에서 종가가 위아래로 오가며 국면이 하루 단위로 뒤집히던 왕복을 줄인다. 1%→2%(plans/70): 20년 성과는
# 같고(CAGR·MDD·샤프 ±0.1) 국면 전환이 94→75회로 줄어 매매·세금 부담이 준다.
TREND_BAND_PCT = 2.0


class TechnicalSnapshot(TypedDict):
    close: float | None
    sma20: float | None
    sma60: float | None
    sma120: float | None
    sma50: float | None
    sma200: float | None
    rsi14: float | None
    macd_hist: float | None
    drawdown_pct: float | None  # 52주 고점 대비 하락률(%, 0 이하)
    trend: TrendState
    pullback_stage: PullbackStage


def sma(close: pd.Series, period: int) -> float | None:
    if len(close) < period:
        return None
    return float(close.iloc[-period:].mean())


def rsi(close: pd.Series, period: int = RSI_PERIOD) -> float | None:
    """Wilder 평활 RSI."""
    if len(close) < period + 1:
        return None
    value = rsi_series(close, period).iloc[-1]
    return None if value != value else float(value)  # NaN 체크(pandas import 없이)


def rsi_series(close: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
    """일자별 Wilder RSI(앞쪽 `period`일은 NaN). 상승만 있으면 100, 변동이 없으면 50."""
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    out = 100 - 100 / (1 + gain / loss)
    out = out.mask((loss == 0) & (gain > 0), 100.0).mask((loss == 0) & (gain == 0), 50.0)
    return out.where(gain.notna())


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


def classify_pullback(
    close: float | None,
    sma20: float | None,
    sma60: float | None,
    sma120: float | None,
    rsi14: float | None,
) -> PullbackStage:
    """종가가 20/60/120일선 이하로 내려온 가장 깊은 단계(웅덩이매매법의 분할매수 구간).

    120일선 이하이면서 RSI가 과매도(<35)면 `SMA120_RSI`. 이평선이 아직 없으면 UNKNOWN.
    """
    if close is None or sma20 is None or sma60 is None or sma120 is None:
        return "UNKNOWN"
    if close <= sma120:
        if rsi14 is not None and rsi14 < PULLBACK_RSI_OVERSOLD:
            return "SMA120_RSI"
        return "SMA120"
    if close <= sma60:
        return "SMA60"
    if close <= sma20:
        return "SMA20"
    return "NONE"


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
    s20, s60, s120 = sma(close, SMA_20), sma(close, SMA_60), sma(close, SMA_120)
    s50 = sma(close, SMA_SHORT)
    s200 = sma(close, SMA_LONG)
    rsi14 = rsi(close)
    # 추세는 완충 상태를 이어받아야 해서 단일 시점 계산이 아니라 이력 전체를 따라간 마지막 값을 쓴다
    trend: TrendState = trend_series(close).iloc[-1] if not close.empty else "UNKNOWN"
    return TechnicalSnapshot(
        close=last,
        sma20=s20,
        sma60=s60,
        sma120=s120,
        sma50=s50,
        sma200=s200,
        rsi14=rsi14,
        macd_hist=macd_histogram(close),
        drawdown_pct=drawdown_from_high_pct(close),
        trend=trend,
        pullback_stage=classify_pullback(last, s20, s60, s120, rsi14),
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


def pullback_series(close: pd.Series) -> pd.Series:
    """일자별 웅덩이 단계 Series — 각 시점에서 그날까지의 데이터만 사용(룩어헤드 없음)."""
    import pandas as pd

    close = close.dropna().astype(float)
    s20, s60, s120 = (close.rolling(p).mean() for p in (SMA_20, SMA_60, SMA_120))
    r = rsi_series(close)

    def _v(x: float) -> float | None:
        return None if pd.isna(x) else float(x)

    stages = [
        classify_pullback(c, _v(a), _v(b), _v(d), _v(e)) for c, a, b, d, e in zip(close, s20, s60, s120, r, strict=True)
    ]
    return pd.Series(stages, index=close.index)
