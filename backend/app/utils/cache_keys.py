"""Redis 캐시 키 빌더 및 TTL 상수 — 키 형식을 한 곳에서 관리한다."""

from __future__ import annotations

import uuid

from redis.asyncio import Redis as AioRedis

RedisType = AioRedis | None

# ---------------------------------------------------------------------------
# TTL 상수 (초)
# ---------------------------------------------------------------------------
TTL_PRICE_CURRENT = 900          # 현재가 15분
TTL_MONTHLY_TREND = 300          # 월별 추이 5분
TTL_DASHBOARD_SUMMARY = 300      # 대시보드 전체 응답 5분
TTL_PRICE_RETURN = 86400         # 기간 수익률 1일
TTL_BACKTEST = 86400             # 백테스트 결과 1일
TTL_ALLOC_HISTORY = 86400        # 포트폴리오 배분 이력 1일
TTL_DIVIDEND_INFO = 86400        # 배당 정보 1일
TTL_DART = 3600                  # DART 공시 1시간
TTL_DIVIDEND_MONTHS = 604800     # 배당 월별 데이터 7일
TTL_OB_STATE = 600               # 오픈뱅킹 OAuth state 10분
TTL_HAS_OVERSEAS_TRUE = 21600    # 해외 보유 중 6시간
TTL_HAS_OVERSEAS_FALSE = 900     # 해외 없음 15분 (신규 매수 시 빠른 반영)
TTL_DIVIDEND_SUMMARY = 3600      # 배당 집계 1시간
TTL_PORTFOLIO_OVERVIEW = 900     # 포트폴리오 overview 15분
TTL_PORTFOLIO_LIST = 300         # 포트폴리오 목록 5분
TTL_ACCOUNT_DETAIL = 300         # 계좌 상세 5분
TTL_EXCHANGE_RATE_ALERTS = 300   # 환율 알림 목록 5분
TTL_INDICATOR_LATEST = 3600      # 경제지표 최신값 1시간
TTL_INDICATOR_HISTORY = 21600    # 경제지표 시계열 6시간
TTL_INDICATOR_CALENDAR = 86400   # 경제지표 발표 일정 24시간

# ---------------------------------------------------------------------------
# 단순 상수 키
# ---------------------------------------------------------------------------
USD_KRW_RATE = "usd_krw_rate"

# ---------------------------------------------------------------------------
# 동적 키 빌더
# ---------------------------------------------------------------------------


def current_price_key(ticker: str, market: str) -> str:
    return f"price:current:{ticker}:{market}"


def price_return_key(years: int, ticker: str, market: str) -> str:
    return f"return:{years}y:{ticker}:{market}"


def dashboard_summary_key(user_id: uuid.UUID) -> str:
    return f"dashboard_summary:{user_id}"


def monthly_trend_key(user_id: uuid.UUID) -> str:
    return f"monthly_trend:{user_id}"


def dividend_ticker_summary_key(user_id: uuid.UUID, year: int) -> str:
    return f"dividend:by-ticker:{user_id}:{year}"


def dividend_months_key(ticker: str, market: str) -> str:
    return f"dividend:months:{ticker}:{market}"


def dividend_info_key(ticker: str, market: str) -> str:
    return f"dividend:info:{ticker}:{market}"


def backtest_key(user_id: uuid.UUID, param_hash: str) -> str:
    return f"backtest:{user_id}:{param_hash}"


def correlation_key(user_id: uuid.UUID, param_hash: str) -> str:
    return f"correlation:{user_id}:{param_hash}"


def dart_disclosures_key(user_id: uuid.UUID, days: int) -> str:
    return f"dart:disclosures:{user_id}:{days}"


def alloc_history_key(user_id: uuid.UUID, months: int) -> str:
    return f"alloc_history_v2:{user_id}:{months}"


def ob_state_key(state: str) -> str:
    return f"ob_state:{state}"


def has_overseas_key(account_id: int) -> str:
    return f"has_overseas:{account_id}"


def dividend_summary_key(user_id: uuid.UUID) -> str:
    return f"dividend_summary:{user_id}"


def portfolio_overview_key(user_id: uuid.UUID) -> str:
    return f"portfolio_overview:{user_id}"


def portfolio_overview_lite_key(user_id: uuid.UUID) -> str:
    return f"portfolio_overview_lite:{user_id}"


def portfolio_list_key(user_id: uuid.UUID) -> str:
    return f"portfolio_list:{user_id}"


def account_detail_key(user_id: uuid.UUID, account_id: uuid.UUID) -> str:
    return f"account_detail:{user_id}:{account_id}"


def exchange_rate_alerts_key(user_id: uuid.UUID) -> str:
    return f"alerts:exchange_rate:{user_id}"


def economic_indicator_latest_key(code: str) -> str:
    return f"economic:latest:{code}"


def economic_indicator_history_key(code: str, months: int) -> str:
    return f"economic:history:{code}:{months}"


def economic_indicator_calendar_key() -> str:
    return "economic:calendar:upcoming"


async def invalidate_user_caches(redis: RedisType, *keys: str) -> None:
    """주어진 캐시 키들을 RedisError 무시하며 일괄 삭제한다."""
    if redis is None:
        return
    import contextlib

    from redis.exceptions import RedisError

    with contextlib.suppress(RedisError):
        await redis.delete(*keys)
