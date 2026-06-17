"""서비스 레이어 내부 TypedDict — DB·API 모델과 분리된 순수 파이썬 타입 계약."""

from __future__ import annotations

from typing import TypedDict


class PositionMapEntry(TypedDict):
    """(ticker, market) 키로 인덱싱된 포지션 집계 항목."""

    value_krw: float
    current_price: float | None
    name: str


class TickerPositionEntry(TypedDict):
    """ticker 문자열로 인덱싱된 포지션 집계 항목 (factor/risk 서비스용)."""

    ticker: str
    market: str
    value_krw: float


class DividendMapEntry(TypedDict, total=False):
    """(ticker, market) 키로 인덱싱된 배당 정보 항목."""

    dividend_yield: float | None
    estimated_annual_krw: float


class ReturnsMapEntry(TypedDict, total=False):
    """(ticker, market) 키로 인덱싱된 수익률 항목."""

    cumulative_return_pct: float | None
    cagr_pct: float | None
    actual_years: float | None


class FactorData(TypedDict, total=False):
    """개별 종목의 팩터 데이터 (factor_service 내부 집계용)."""

    pe_ratio: float | None
    pb_ratio: float | None
    market_cap: float | None
    momentum_pct: float | None
