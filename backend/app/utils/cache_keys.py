"""Redis 캐시 키 빌더 및 TTL 상수 — 키 형식을 한 곳에서 관리한다."""

from __future__ import annotations

import uuid
from typing import Any, TypeAlias

from redis.asyncio import Redis as AioRedis

RedisType: TypeAlias = AioRedis | None


def _env_prefix() -> str:
    """app_env를 키 네임스페이스 prefix로 반환한다 (dev/staging/prod Redis 공유 시 충돌 방지)."""
    from app.core.config import settings  # lazy — 순환 임포트 방지

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
TTL_HAS_OVERSEAS_TRUE = 21600  # 해외 보유 중 6시간
TTL_HAS_OVERSEAS_FALSE = 900  # 해외 없음 15분 (신규 매수 시 빠른 반영)
TTL_DIVIDEND_SUMMARY = 3600  # 배당 집계 1시간
TTL_PORTFOLIO_OVERVIEW = 1800  # 포트폴리오 overview 30분
TTL_PORTFOLIO_LIST = 300  # 포트폴리오 목록 5분
TTL_ACCOUNT_DETAIL = 300  # 계좌 상세 5분
TTL_EXCHANGE_RATE_ALERTS = 300  # 환율 알림 목록 5분
TTL_INDICATOR_HISTORY = 21600  # 경제지표 시계열 6시간
TTL_INDICATOR_CALENDAR = 86400  # 경제지표 발표 일정 24시간
TTL_MARKET_SIGNAL = 3600  # 복합 시장 신호 1시간 (전체 신호 정상 조회 시)
TTL_MARKET_SIGNAL_DEGRADED = 60  # 일부/전체 신호 조회 실패(PARTIAL·STALE) 시 1분 — 일시적 장애가
# 1시간짜리 캐시에 고착되어 사용자가 오래 빈 신호를 보는 것을 방지, 빠르게 재시도되도록 함
TTL_FACTOR_ANALYSIS = 3600  # 팩터 분석 1시간
TTL_PORTFOLIO_OPTIMIZER = 3600  # 포트폴리오 최적화 1시간
TTL_RISK_ANALYSIS = 3600  # 위험 분석 1시간
TTL_REBALANCING_STRATEGY = 3600  # 리밸런싱 전략 1시간
TTL_JOB_LOCK_REBALANCING_AUTO = 3600  # 리밸런싱 자동 실행 분산 락 (중복 실행 방지)
TTL_JOB_LOCK_REBALANCING_PLAN_BUY = 300  # 리밸런싱 매수 대기 플랜 실행 분산 락 (1분 간격 job, 중복 실행 방지)
TTL_DIVIDENDS_POSITIONS = 3600  # 종목별 배당수익률 1시간
TTL_TAX_OVERSEAS = 86400  # 해외 미실현 손익 24시간
TTL_MARKET_SIGNAL_LAST_LEVEL = 7 * 24 * 3600  # 시장 신호 등급 변화 감지 마지막 값 (job이 계속 갱신, 만료는 안전망)
TTL_COMPOSITE_ALERT_SENT = 86400  # 복합 리스크/시장 신호 알림 유저당 1일 1회 제한 플래그
TTL_SYNC_ALL_STATUS = 600  # "전체 갱신" 백그라운드 진행 상태 (폴링 종료 후에도 잠시 조회 가능하도록 여유)
TTL_ETF_INDEX_REGION = 7 * 24 * 3600  # ETF 추종지수 지역(국내/해외) 7일 — 사실상 불변 데이터
TTL_GOAL_RECOMMENDATION = 600  # 목표 역산 추천(전체/기간별) 10분 — 설정 변경 시 명시적으로 무효화됨

# ---------------------------------------------------------------------------
# 캐시 스키마 버전 상수
# ---------------------------------------------------------------------------
# 캐시 값의 필드 구성이나 산출 로직이 바뀌어 기존 캐시가 새 코드와 호환되지 않을 때,
# 아래처럼 `_XXX_VERSION` 상수를 올려 키를 분리한다(구버전 캐시가 TTL 만료 전까지
# 잘못된 값을 계속 서빙하는 것을 방지). **값 자체(문자열)는 여기서만 바꾸고,
# 키 빌더 함수의 f-string 포맷은 그대로 유지할 것 — 무단으로 포맷을 바꾸면 캐시 미스가 폭증한다.**
_ALLOC_HISTORY_VERSION = "v2"
_MARKET_SIGNAL_VERSION = "v4"
"""v4: exchange_rate.value 산출 소스를 FRED 지연값 → 실시간 캐시(get_usd_krw_rate)로 변경
(필드 구성은 동일하나 값 자체가 달라지므로, 기존 v3 캐시가 최대 1시간 TTL 동안
잘못된 값을 계속 서빙하지 않도록 키를 분리)"""

# ---------------------------------------------------------------------------
# 단순 상수 키
# ---------------------------------------------------------------------------
USD_KRW_RATE = "usd_krw_rate"

# ---------------------------------------------------------------------------
# 동적 키 빌더
# ---------------------------------------------------------------------------


def current_price_key(ticker: str, market: str) -> str:
    """price_service.py 내부 배치 조회(fetch_current_price/fetch_prices_batch) 전용 — plain float 문자열 캐시.
    JSON dict를 캐싱하는 `current_price_display_key`와 포맷이 다르므로 절대 공유하지 않는다."""
    return f"{_env_prefix()}price:current:{ticker}:{market}"


def current_price_display_key(ticker: str, market: str) -> str:
    """stocks.py의 /stocks/price, /stocks/prices-batch 응답 전용 — {price_krw, price_usd, usd_rate}
    JSON dict 캐시. plain float를 저장하는 `current_price_key`와 포맷이 다르므로 절대 공유하지 않는다."""
    return f"{_env_prefix()}price:display:{ticker}:{market}"


def price_return_key(years: int, ticker: str, market: str) -> str:
    return f"{_env_prefix()}return:{years}y:{ticker}:{market}"


def etf_index_region_key(ticker: str) -> str:
    return f"{_env_prefix()}etf:index_region:{ticker}"


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


def alloc_history_key(user_id: uuid.UUID, months: int) -> str:
    return f"{_env_prefix()}alloc_history_{_ALLOC_HISTORY_VERSION}:{user_id}:{months}"


def has_overseas_key(account_id: uuid.UUID) -> str:
    return f"{_env_prefix()}has_overseas:{account_id}"


def dividend_summary_key(user_id: uuid.UUID) -> str:
    return f"{_env_prefix()}dividend_summary:{user_id}"


def portfolio_overview_key(user_id: uuid.UUID, acct_suffix: str = "all") -> str:
    return f"{_env_prefix()}portfolio_overview:{user_id}:{acct_suffix}"


def portfolio_overview_lite_key(user_id: uuid.UUID, acct_suffix: str = "all") -> str:
    return f"{_env_prefix()}portfolio_overview_lite:{user_id}:{acct_suffix}"


def portfolio_overview_acct_suffix(account_ids: list[uuid.UUID] | None) -> str:
    """계좌 조합을 캐시 키 suffix로 정규화한다 (정렬해 조합 순서와 무관하게 동일 키를 사용)."""
    if not account_ids:
        return "all"
    return "-".join(sorted(str(a) for a in account_ids))


def portfolio_list_key(user_id: uuid.UUID) -> str:
    return f"{_env_prefix()}portfolio_list:{user_id}"


def account_detail_key(user_id: uuid.UUID, account_id: uuid.UUID) -> str:
    return f"{_env_prefix()}account_detail:{user_id}:{account_id}"


def sync_all_status_key(user_id: uuid.UUID) -> str:
    """ "전체 갱신" 백그라운드 진행 상태(JSON) 저장 키."""
    return f"{_env_prefix()}sync_all:status:{user_id}"


def exchange_rate_alerts_key(user_id: uuid.UUID) -> str:
    return f"{_env_prefix()}alerts:exchange_rate:{user_id}"


def dividends_positions_key(user_id: uuid.UUID) -> str:
    return f"{_env_prefix()}dividends:positions:{user_id}"


def rebalancing_strategy_key(user_id: uuid.UUID, portfolio_id: uuid.UUID | str, acct_suffix: str) -> str:
    return f"{_env_prefix()}rebalancing_strategy:{user_id}:{portfolio_id}:{acct_suffix}"


def tax_overseas_key(user_id: uuid.UUID) -> str:
    return f"{_env_prefix()}tax:overseas:{user_id}"


def goal_recommendation_key(user_id: uuid.UUID) -> str:
    return f"{_env_prefix()}goal_recommendation:{user_id}"


def goal_recommendation_horizon_key(user_id: uuid.UUID) -> str:
    return f"{_env_prefix()}goal_recommendation_horizon:{user_id}"


def economic_indicator_history_key(code: str, months: int) -> str:
    return f"{_env_prefix()}economic:history:{code}:{months}"


def economic_indicator_calendar_key() -> str:
    return f"{_env_prefix()}economic:calendar:upcoming"


def market_signal_latest_key() -> str:
    return f"{_env_prefix()}market:signal:latest:{_MARKET_SIGNAL_VERSION}"


def market_signal_last_level_key() -> str:
    """등급 변화 감지 job이 마지막으로 관측한 composite_level을 저장하는 키."""
    return f"{_env_prefix()}market:signal:last_level"


def composite_alert_sent_key(user_id: uuid.UUID, day: str) -> str:
    """복합 리스크/시장 신호만으로 리밸런싱 알림이 발송된 유저+일자를 기록하는 키(중복 발송 억제).

    이 신호는 포트폴리오와 무관하게 유저 단위로 동일하게 평가되므로, 유저가 여러
    포트폴리오 알림을 갖고 있어도 하루 1건만 발송하도록 제한한다.
    """
    return f"{_env_prefix()}rebalancing:composite_sent:{user_id}:{day}"


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


async def _scan_unlink(redis: RedisType, pattern: str) -> None:
    """주어진 패턴에 매칭되는 키를 SCAN+UNLINK로 일괄 삭제한다.

    고정된 키 목록 대신 실제 존재하는 키만 삭제해 불필요한 DEL 명령을 줄인다.
    """
    if redis is None:
        return
    import contextlib

    from redis.exceptions import RedisError

    with contextlib.suppress(RedisError):
        cursor = 0
        keys_to_delete: list[bytes | str] = []
        while True:
            cursor, batch = await redis.scan(cursor, match=pattern, count=100)
            keys_to_delete.extend(batch)
            if cursor == 0:
                break
        if keys_to_delete:
            await redis.unlink(*keys_to_delete)


async def invalidate_all_user_caches(redis: RedisType, user_id: uuid.UUID) -> None:
    """회원 탈퇴 시 해당 유저의 모든 캐시 키를 SCAN+UNLINK로 일괄 삭제한다."""
    await _scan_unlink(redis, f"{_env_prefix()}*{user_id}*")


async def _invalidate_alloc_history(redis: RedisType, user_id: uuid.UUID) -> None:
    """alloc_history 캐시를 SCAN+UNLINK 패턴으로 일괄 삭제한다."""
    await _scan_unlink(redis, f"{_env_prefix()}alloc_history_{_ALLOC_HISTORY_VERSION}:{user_id}:*")


async def invalidate_goal_recommendation_caches(redis: RedisType, user_id: uuid.UUID) -> None:
    """목표 역산 추천(전체/기간별) 캐시를 삭제한다 — 목표 설정, 후보 ETF, 계좌 포지션 변경 시 호출."""
    await invalidate_user_caches(
        redis,
        goal_recommendation_key(user_id),
        goal_recommendation_horizon_key(user_id),
    )


async def invalidate_portfolio_overview_cache(redis: RedisType, user_id: uuid.UUID) -> None:
    """`portfolio_overview`/`portfolio_overview_lite` 캐시를 계좌 조합(acct_suffix) 전체에 대해 삭제한다.

    account_ids 조합별로 키가 분기되어(무효화 시점엔 어떤 조합이 캐시됐는지 알 수 없음) SCAN+UNLINK
    와일드카드 패턴을 사용한다 — `invalidate_rebalancing_strategy_cache`와 동일한 패턴.
    """
    await _scan_unlink(redis, f"{_env_prefix()}portfolio_overview:{user_id}:*")
    await _scan_unlink(redis, f"{_env_prefix()}portfolio_overview_lite:{user_id}:*")


async def invalidate_rebalancing_strategy_cache(
    redis: RedisType, user_id: uuid.UUID, portfolio_id: uuid.UUID | str
) -> None:
    """리밸런싱 전략 캐시(계좌 그룹별 acct_suffix 포함)를 SCAN+UNLINK로 일괄 삭제한다.

    쓰기 시점엔 acct_suffix(계좌 그룹 조합)를 알지만 무효화 시점엔 알 수 없으므로,
    와일드카드 패턴으로 해당 user+portfolio의 모든 acct_suffix 변형 키를 삭제한다.
    """
    await _scan_unlink(redis, f"{_env_prefix()}rebalancing_strategy:{user_id}:{portfolio_id}:*")


async def invalidate_asset_account_caches(
    redis: RedisType,
    user_id: uuid.UUID,
    account_id: uuid.UUID | None = None,
    year: int | None = None,
) -> None:
    """계좌 생성/수정/삭제/동기화 후 관련 캐시 일괄 무효화.

    계좌 수정에는 investment_horizon/tax_type 태그 변경(목표 역산 추천의 조합 구성에 직접
    영향)도 포함되므로 goal_recommendation 캐시도 함께 무효화한다.
    """
    from datetime import date as _date

    _year = year if year is not None else _date.today().year
    keys = [
        dashboard_summary_key(user_id),
        dividend_summary_key(user_id),
        dividend_ticker_summary_key(user_id, _year),
        goal_recommendation_key(user_id),
        goal_recommendation_horizon_key(user_id),
    ]
    if account_id is not None:
        keys.append(account_detail_key(user_id, account_id))
    await invalidate_user_caches(redis, *keys)
    await invalidate_portfolio_overview_cache(redis, user_id)


async def invalidate_account_caches(redis: RedisType, user_id: uuid.UUID, year: int | None = None) -> None:
    """계좌 싱크 완료 후 관련 캐시 일괄 무효화."""
    from datetime import date as _date

    _year = year if year is not None else _date.today().year
    await _invalidate_alloc_history(redis, user_id)
    await invalidate_user_caches(
        redis,
        monthly_trend_key(user_id),
        dashboard_summary_key(user_id),
        dividend_summary_key(user_id),
        dividend_ticker_summary_key(user_id, _year),
        dividends_positions_key(user_id),
        tax_overseas_key(user_id),
        goal_recommendation_key(user_id),
        goal_recommendation_horizon_key(user_id),
    )
    await invalidate_portfolio_overview_cache(redis, user_id)
