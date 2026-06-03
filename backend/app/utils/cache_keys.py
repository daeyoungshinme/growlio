"""Redis 캐시 키 빌더 — 키 형식을 한 곳에서 관리한다."""

from __future__ import annotations

import uuid
from datetime import date

# 단순 상수 키
USD_KRW_RATE = "usd_krw_rate"


def dividend_ticker_summary_key(user_id: uuid.UUID, year: int) -> str:
    return f"dividend:by-ticker:{user_id}:{year}"


def benchmark_key(start: date, end: date) -> str:
    return f"benchmark:{start}:{end}"


def price_return_key(years: int, ticker: str, market: str) -> str:
    return f"return:{years}y:{ticker}:{market}"


def monthly_trend_key(user_id: uuid.UUID) -> str:
    return f"monthly_trend:{user_id}"


def current_price_key(ticker: str, market: str) -> str:
    return f"price:current:{ticker}:{market}"
