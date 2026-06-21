"""Redis 캐시 키 빌더 및 TTL 상수 — 키 형식을 한 곳에서 관리한다."""

from __future__ import annotations

import uuid
from typing import Any, TypeAlias

from redis.asyncio import Redis as AioRedis

RedisType: TypeAlias = AioRedis | None


def _env_prefix() -> str:
    """app_env를 키 네임스페이스 prefix로 반환한다 (dev/staging/prod Redis 공유 시 충돌 방지)."""
    from app.config import settings  # lazy — 순환 임포트 방지

    return f"{settings.app_env}:"


# ---------------------------------------------------------------------------
# TTL 상수 (초)
# ---------------------------------------------------------------------------
TTL_PRICE_CURRENT = 900  # 현재가 15분
TTL_MONTHLY_TREND = 300  # 월별 추이 5분
TTL_DASHBOARD_SUMMARY = 900  # 대시보드 전체 응답 15분 (sync 후 수동 무효화가 primary)
TTL_PRICE_RETURN = 86400  # 기간 수익률 1일
TTL_BACKTEST = 86400  # 백테스트 결과 1일
TTL_ALLOC_HISTORY = 86400  # 포트폴리오 배분 이력 1일
TTL_DIVIDEND_INFO = 86400  # 배당 정보 1일
TTL_DART = 3600  # DART 공시 1시간
TTL_DIVIDEND_MONTHS = 604800  # 배당 월별 데이터 7일
TTL_OB_STATE = 600  # 오픈뱅킹 OAuth state 10분
TTL_HAS_OVERSEAS_TRUE = 21600  # 해외 보유 중 6시간
TTL_HAS_OVERSEAS_FALSE = 900  # 해외 없음 15분 (신규 매수 시 빠른 반영)
TTL_DIVIDEND_SUMMARY = 3600  # 배당 집계 1시간
TTL_PORTFOLIO_OVERVIEW = 1800  # 포트폴리오 overview 30분
TTL_PORTFOLIO_LIST = 300  # 포트폴리오 목록 5분
TTL_ACCOUNT_DETAIL = 300  # 계좌 상세 5분
TTL_EXCHANGE_RATE_ALERTS = 300  # 환율 알림 목록 5분
TTL_INDICATOR_LATEST = 3600  # 경제지표 최신값 1시간
TTL_INDICATOR_HISTORY = 21600  # 경제지표 시계열 6시간
TTL_INDICATOR_CALENDAR = 86400  # 경제지표 발표 일정 24시간
TTL_MARKET_SIGNAL = 3600  # 복합 시장 신호 1시간
TTL_FACTOR_ANALYSIS = 3600  # 팩터 분석 1시간
TTL_PORTFOLIO_OPTIMIZER = 3600  # 포트폴리오 최적화 1시간
TTL_RISK_ANALYSIS = 3600  # 위험 분석 1시간
TTL_REBALANCING_STRATEGY = 3600  # 리밸런싱 전략 1시간
TTL_JOB_LOCK_DCA = 3600  # DCA 자동매수 분산 락
TTL_JOB_LOCK_DEPOSIT = 600  # 입금 모니터 분산 락
TTL_OB_TOKEN = 90 * 24 * 3600  # 금융결제원 기본 토큰 유효기간 90일
TTL_PORTFOLIO_SUMMARY = 300  # KIS 실시간 포트폴리오 집계 5분
TTL_DIVIDENDS_POSITIONS = 3600  # 종목별 배당수익률 1시간
TTL_TAX_OVERSEAS = 86400  # 해외 미실현 손익 24시간

# ---------------------------------------------------------------------------
# 단순 상수 키
# ---------------------------------------------------------------------------
USD_KRW_RATE = "usd_krw_rate"

# ---------------------------------------------------------------------------
# 동적 키 빌더
# ---------------------------------------------------------------------------


def current_price_key(ticker: str, market: str) -> str:
    return f"{_env_prefix()}price:current:{ticker}:{market}"


def price_return_key(years: int, ticker: str, market: str) -> str:
    return f"{_env_prefix()}return:{years}y:{ticker}:{market}"


def dashboard_summary_key(user_id: uuid.UUID) -> str:
    return f"{_env_prefix()}dashboard_summary:{user_id}"


def monthly_trend_key(user_id: uuid.UUID) -> str:
    return f"{_env_prefix()}monthly_trend:{user_id}"


def dividend_ticker_summary_key(user_id: uuid.UUID, year: int) -> str:
    return f"{_env_prefix()}dividend:by-ticker:{user_id}:{year}"


def dividend_months_key(ticker: str, market: str) -> str:
    return f"{_env_prefix()}dividend:months:{ticker}:{market}"


def dividend_info_key(ticker: str, market: str) -> str:
    return f"{_env_prefix()}dividend:info:{ticker}:{market}"


def backtest_key(user_id: uuid.UUID, param_hash: str) -> str:
    return f"{_env_prefix()}backtest:{user_id}:{param_hash}"


def correlation_key(user_id: uuid.UUID, param_hash: str) -> str:
    return f"{_env_prefix()}correlation:{user_id}:{param_hash}"


def dart_disclosures_key(user_id: uuid.UUID, days: int) -> str:
    return f"{_env_prefix()}dart:disclosures:{user_id}:{days}"


def alloc_history_key(user_id: uuid.UUID, months: int) -> str:
    return f"{_env_prefix()}alloc_history_v2:{user_id}:{months}"


def ob_state_key(state: str) -> str:
    return f"{_env_prefix()}ob_state:{state}"


def has_overseas_key(account_id: uuid.UUID) -> str:
    return f"{_env_prefix()}has_overseas:{account_id}"


def dividend_summary_key(user_id: uuid.UUID) -> str:
    return f"{_env_prefix()}dividend_summary:{user_id}"


def portfolio_overview_key(user_id: uuid.UUID) -> str:
    return f"{_env_prefix()}portfolio_overview:{user_id}"


def portfolio_overview_lite_key(user_id: uuid.UUID) -> str:
    return f"{_env_prefix()}portfolio_overview_lite:{user_id}"


def portfolio_list_key(user_id: uuid.UUID) -> str:
    return f"{_env_prefix()}portfolio_list:{user_id}"


def account_detail_key(user_id: uuid.UUID, account_id: uuid.UUID) -> str:
    return f"{_env_prefix()}account_detail:{user_id}:{account_id}"


def exchange_rate_alerts_key(user_id: uuid.UUID) -> str:
    return f"{_env_prefix()}alerts:exchange_rate:{user_id}"


def portfolio_summary_key(user_id: uuid.UUID) -> str:
    return f"{_env_prefix()}portfolio_summary:{user_id}"


def dividends_positions_key(user_id: uuid.UUID) -> str:
    return f"{_env_prefix()}dividends:positions:{user_id}"


def tax_overseas_key(user_id: uuid.UUID) -> str:
    return f"{_env_prefix()}tax:overseas:{user_id}"


def economic_indicator_latest_key(code: str) -> str:
    return f"{_env_prefix()}economic:latest:{code}"


def economic_indicator_history_key(code: str, months: int) -> str:
    return f"{_env_prefix()}economic:history:{code}:{months}"


def economic_indicator_calendar_key() -> str:
    return f"{_env_prefix()}economic:calendar:upcoming"


def market_signal_latest_key() -> str:
    return f"{_env_prefix()}market:signal:latest"


async def get_cached_json(redis: RedisType, key: str) -> Any:
    """Redis에서 JSON을 조회한다. 캐시 미스나 오류 시 None 반환."""
    if redis is None:
        return None
    import contextlib
    import json

    from redis.exceptions import RedisError

    with contextlib.suppress(RedisError, json.JSONDecodeError, TypeError):
        cached = await redis.get(key)
        if cached:
            return json.loads(cached)
    return None


async def set_cached_json(redis: RedisType, key: str, value: object, ttl: int) -> None:
    """Redis에 JSON으로 직렬화해 저장한다. 오류 시 무시."""
    if redis is None:
        return
    import contextlib
    import json

    from redis.exceptions import RedisError

    with contextlib.suppress(RedisError):
        await redis.setex(key, ttl, json.dumps(value, ensure_ascii=False, allow_nan=False))


async def invalidate_user_caches(redis: RedisType, *keys: str) -> None:
    """주어진 캐시 키들을 RedisError 무시하며 일괄 삭제한다."""
    if redis is None:
        return
    import contextlib

    from redis.exceptions import RedisError

    with contextlib.suppress(RedisError):
        await redis.delete(*keys)


async def invalidate_exchange_rate_alert_caches(redis: RedisType, user_id: uuid.UUID) -> None:
    """환율 알림 목록 캐시를 삭제한다."""
    await invalidate_user_caches(redis, exchange_rate_alerts_key(user_id))


async def invalidate_account_caches(redis: RedisType, user_id: uuid.UUID, year: int | None = None) -> None:
    """계좌 싱크 완료 후 관련 캐시 일괄 무효화."""
    from datetime import date as _date

    _year = year if year is not None else _date.today().year
    await invalidate_user_caches(
        redis,
        monthly_trend_key(user_id),
        dashboard_summary_key(user_id),
        portfolio_overview_key(user_id),
        portfolio_overview_lite_key(user_id),
        alloc_history_key(user_id, 12),
        dividend_summary_key(user_id),
        dividend_ticker_summary_key(user_id, _year),
        portfolio_summary_key(user_id),
        dividends_positions_key(user_id),
        tax_overseas_key(user_id),
    )
