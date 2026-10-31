"""캐시 무효화 — 키 빌더(`cache_keys`)가 만든 키를 지운다. SCAN 패턴은 빌더 포맷과 맞아야 한다
(`tests/test_currency_and_cache_keys.py::TestInvalidationPatternsMatchBuilders`가 어긋남을 잡는다)."""

from __future__ import annotations

import uuid

from app.utils.cache_keys import (
    _ALLOC_HISTORY_VERSION,
    TTL_GOAL_RECOMMENDATION_GEN,
    CacheStoreType,
    _env_prefix,
    challenge_progress_key,
    dashboard_summary_key,
    dca_analysis_key,
    exchange_rate_alerts_key,
    factor_analysis_portfolio_key,
    goal_recommendation_age_key,
    goal_recommendation_age_stale_key,
    goal_recommendation_gen_key,
    goal_recommendation_horizon_key,
    goal_recommendation_horizon_stale_key,
    goal_recommendation_key,
    goal_recommendation_stale_key,
    insights_key,
    monthly_trend_key,
    risk_key,
)
from app.utils.kst import today_kst


async def invalidate_user_caches(cache: CacheStoreType, *keys: str) -> None:
    """주어진 캐시 키들을 일괄 삭제한다."""
    if cache is None:
        return
    await cache.delete(*keys)


async def invalidate_exchange_rate_alert_caches(cache: CacheStoreType, user_id: uuid.UUID) -> None:
    """환율 알림 목록 캐시를 삭제한다."""
    await invalidate_user_caches(cache, exchange_rate_alerts_key(user_id))


async def _scan_unlink(cache: CacheStoreType, pattern: str) -> None:
    """주어진 패턴에 매칭되는 키를 SCAN+UNLINK로 일괄 삭제한다.

    고정된 키 목록 대신 실제 존재하는 키만 삭제해 불필요한 삭제 호출을 줄인다.
    """
    if cache is None:
        return
    cursor = 0
    keys_to_delete: list[str] = []
    while True:
        cursor, batch = await cache.scan(cursor, match=pattern, count=100)
        keys_to_delete.extend(batch)
        if cursor == 0:
            break
    if keys_to_delete:
        await cache.unlink(*keys_to_delete)


async def invalidate_all_user_caches(cache: CacheStoreType, user_id: uuid.UUID) -> None:
    """회원 탈퇴 시 해당 유저의 모든 캐시 키를 SCAN+UNLINK로 일괄 삭제한다."""
    await _scan_unlink(cache, f"{_env_prefix()}*{user_id}*")


async def _invalidate_alloc_history(cache: CacheStoreType, user_id: uuid.UUID) -> None:
    """alloc_history 캐시를 SCAN+UNLINK 패턴으로 일괄 삭제한다."""
    await _scan_unlink(cache, f"{_env_prefix()}alloc_history_{_ALLOC_HISTORY_VERSION}:{user_id}:*")


async def invalidate_dividend_caches(
    cache: CacheStoreType, user_id: uuid.UUID, year: int, *, positions_changed: bool = True
) -> None:
    """dividend_summary/dividend_ticker_summary/dividends_positions 캐시를 계좌 조합(acct_suffix)
    전체에 대해 SCAN+UNLINK로 삭제한다 — `_invalidate_alloc_history`와 동일한 이유(무효화 시점엔
    어떤 account_id 조합이 캐시됐는지 알 수 없음).

    `positions_changed=False`면 실수령 배당 집계(dividend_summary, DB 쿼리만이라 저렴)만 지우고
    종목별 배당 추정(dividend:by-ticker/dividends:positions, 보유 종목마다 외부 API 폴백 체인이
    필요해 비쌈)은 건드리지 않는다 — 보유 종목 구성이 그대로인 단순 동기화(가격/잔고 갱신)에서
    다음 대시보드 조회가 불필요하게 외부 API를 재호출하는 것을 막기 위함
    (호출부: asset_service.sync_account, 계좌 동기화마다 매번 지우던 기존 동작 때문에
    "동기화 후 대시보드 로딩이 느리다"는 체감 지연의 원인이었음)."""
    await _scan_unlink(cache, f"{_env_prefix()}dividend_summary:{user_id}:*")
    if not positions_changed:
        return
    await _scan_unlink(cache, f"{_env_prefix()}dividend:by-ticker:{user_id}:{year}:*")
    await _scan_unlink(cache, f"{_env_prefix()}dividends:positions:{user_id}:*")


async def invalidate_goal_recommendation_caches(cache: CacheStoreType, user_id: uuid.UUID) -> None:
    """목표 역산 추천(전체/stale/기간별/연령대) 캐시를 무효화한다 — 목표 설정, 후보 ETF, 계좌 포지션 변경 시 호출.

    현재 세대 키를 지우고 세대를 새로 바꾼다 — 진행 중인 옛 계산은 옛 세대 키에만 쓰게 된다
    (`get_goal_recommendation_generation` 참고). 결과 키를 직접 지우지 말고 이 함수를 쓸 것.
    """
    if cache is None:
        return
    gen_key = goal_recommendation_gen_key(user_id)
    old_gen = await cache.get(gen_key)
    if old_gen:
        await invalidate_user_caches(
            cache,
            goal_recommendation_key(user_id, old_gen),
            goal_recommendation_stale_key(user_id, old_gen),
            goal_recommendation_horizon_key(user_id, old_gen),
            goal_recommendation_horizon_stale_key(user_id, old_gen),
            goal_recommendation_age_key(user_id, old_gen),
            goal_recommendation_age_stale_key(user_id, old_gen),
        )
    await cache.set(gen_key, uuid.uuid4().hex, ex=TTL_GOAL_RECOMMENDATION_GEN)


async def invalidate_portfolio_overview_cache(cache: CacheStoreType, user_id: uuid.UUID) -> None:
    """`portfolio_overview`/`portfolio_overview_lite` 캐시를 계좌 조합(acct_suffix) 전체에 대해 삭제한다.

    account_ids 조합별로 키가 분기되어(무효화 시점엔 어떤 조합이 캐시됐는지 알 수 없음) SCAN+UNLINK
    와일드카드 패턴을 사용한다 — `invalidate_rebalancing_strategy_cache`와 동일한 패턴.
    """
    await _scan_unlink(cache, f"{_env_prefix()}portfolio_overview:{user_id}:*")
    await _scan_unlink(cache, f"{_env_prefix()}portfolio_overview_lite:{user_id}:*")


async def invalidate_rebalancing_strategy_cache(
    cache: CacheStoreType, user_id: uuid.UUID, portfolio_id: uuid.UUID | str
) -> None:
    """리밸런싱 전략 캐시(계좌 그룹별 acct_suffix 포함)를 SCAN+UNLINK로 일괄 삭제한다.

    쓰기 시점엔 acct_suffix(계좌 그룹 조합)를 알지만 무효화 시점엔 알 수 없으므로,
    와일드카드 패턴으로 해당 user+portfolio의 모든 acct_suffix 변형 키를 삭제한다.
    """
    await _scan_unlink(cache, f"{_env_prefix()}rebalancing_strategy:{user_id}:{portfolio_id}:*")


async def invalidate_rebalancing_analysis_cache(
    cache: CacheStoreType, user_id: uuid.UUID, portfolio_id: uuid.UUID | str
) -> None:
    """리밸런싱 진단(analyze) 캐시를 SCAN+UNLINK로 일괄 삭제한다 (계좌 조합·예수금 override 변형 전체).

    포트폴리오 수정, 리밸런싱 주문 실행 등 특정 포트폴리오가 특정된 이벤트에서 호출한다.
    같은 목표·보유로 계산하는 전략 비교 캐시도 함께 지운다 — 예전엔 주문 실행만 따로 지워서 포트폴리오 수정·
    전술 적용 뒤 1시간 동안 이전 목표 기준 거래 추천이 보였다(plans/77 B3).
    전략 캐시가 재계산 때 읽는 목표 팩터·프론티어 캐시도 지운다 — 남아 있으면 바깥 캐시만 지워도
    목표 위치가 옛 비중으로 다시 조립됐다(plans/95 A1).
    """
    await _scan_unlink(cache, f"{_env_prefix()}rebalancing_analysis:{user_id}:{portfolio_id}:*")
    await invalidate_rebalancing_strategy_cache(cache, user_id, portfolio_id)
    await invalidate_user_caches(cache, factor_analysis_portfolio_key(portfolio_id))
    await _scan_unlink(cache, f"{_env_prefix()}efficient_frontier:{user_id}:{portfolio_id}:*")


async def invalidate_rebalancing_analysis_cache_all(cache: CacheStoreType, user_id: uuid.UUID) -> None:
    """유저의 모든 포트폴리오에 대한 리밸런싱 진단(analyze) 캐시를 삭제한다.

    계좌 sync·CRUD처럼 어떤 포트폴리오가 영향받는지 특정할 수 없는 이벤트에서 호출한다.
    """
    await _scan_unlink(cache, f"{_env_prefix()}rebalancing_analysis:{user_id}:*")
    await _scan_unlink(cache, f"{_env_prefix()}rebalancing_strategy:{user_id}:*")


async def invalidate_asset_account_caches(
    cache: CacheStoreType,
    user_id: uuid.UUID,
    year: int | None = None,
    *,
    positions_changed: bool = True,
) -> None:
    """계좌 생성/수정/삭제/동기화·포지션 수정 후 관련 캐시 일괄 무효화.

    계좌 삭제(is_active=False)·포지션 수정도 월별 추이·배분 이력(둘 다 is_active 필터)에 반영돼야
    하므로 sync와 똑같이 두 캐시를 지운다 — 예전엔 sync 전용 함수에서만 지워 계좌 삭제 후 배분
    이력에 최대 하루 남았다.

    계좌 수정에는 investment_horizon/tax_type 태그 변경(목표 역산 추천의 조합 구성에 직접
    영향)도 포함되므로 goal_recommendation 캐시도 함께 무효화한다.

    `positions_changed`: 보유 종목 구성이 실제로 바뀌었는지 — `invalidate_dividend_caches`
    참고. 계좌 CRUD 등 변경 여부를 모르는 호출부는 기본값(True, 항상 전체 무효화)을 쓴다.
    목표 역산 추천 캐시도 이 값이 True일 때만 지운다 — 평가액만 바뀐 정기 sync마다 지우면 무거운
    MVO 재계산이 거의 매번 콜드로 돌았다(평가액 변동은 TTL 1시간까지 미반영 — 허용된 트레이드오프).
    """

    _year = year if year is not None else today_kst().year
    keys = [
        monthly_trend_key(user_id),
        dashboard_summary_key(user_id),
        dca_analysis_key(user_id),
        # 계좌 삭제·잔액 수정(입출금 거래 생성)·sync가 챌린지 진행률(순입금·평가액·수익률)과
        # 보유 포지션 기반 인사이트·리스크 지표를 바꾼다 — 빠지면 TTL 동안 삭제 계좌가 남는다
        challenge_progress_key(user_id),
        insights_key(user_id),
        risk_key(user_id),
    ]
    if positions_changed:
        await invalidate_goal_recommendation_caches(cache, user_id)
        # 보유 기반 팩터 분석·효율적 프론티어(현재 위치) — 무거운 yfinance 재계산이라 목표 추천처럼
        # 구성이 바뀐 경우에만 지운다(plans/95 A2). 포트폴리오 단위 팩터 키는 목표 비중만 써서 대상 아님
        await _scan_unlink(cache, f"{_env_prefix()}factor_analysis:{user_id}:*")
        await _scan_unlink(cache, f"{_env_prefix()}efficient_frontier:{user_id}:*")
    await invalidate_user_caches(cache, *keys)
    await _invalidate_alloc_history(cache, user_id)
    await invalidate_dividend_caches(cache, user_id, _year, positions_changed=positions_changed)
    await invalidate_tax_overseas_caches(cache, user_id)
    await invalidate_portfolio_overview_cache(cache, user_id)
    await invalidate_rebalancing_analysis_cache_all(cache, user_id)


async def invalidate_tax_overseas_caches(cache: CacheStoreType, user_id: uuid.UUID) -> None:
    """해외주식 양도세(보유 포지션·실현손익) 캐시 삭제 — 계좌 sync뿐 아니라 계좌 CRUD(삭제·tax_type
    변경·API 키 등록)도 과세 대상 계좌 집합을 바꾸므로 양쪽에서 호출한다."""
    await _scan_unlink(cache, f"{_env_prefix()}tax:overseas:{user_id}:*")
    await _scan_unlink(cache, f"{_env_prefix()}tax:overseas_realized:{user_id}:*")
