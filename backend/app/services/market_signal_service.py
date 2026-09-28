"""시장 위험 신호 서비스 — VIX, 미국 금리 커브(T10Y2Y+DGS2-FEDFUNDS 병합),
하이일드 스프레드, 달러 인덱스, 환율 방향성(DEXKOUS), 유가(WTI), 인플레이션(CPI+PCE 병합),
고용(실업률 Sahm Rule-lite) 통합.

2026-07 방법론 개선(docs/plans/21-market-signal-methodology.md): Fear & Greed Index(크립토 시장
기반 프록시라는 태생적 한계로 완전 제거) + 장단기금리차/금리인하기대(둘 다 "Fed 정책금리 경로 기대"라는
동일 정보를 반영하던 것을 단일 신호로 병합, 이중계상 방지).

2026-07-25 인플레이션·고용 지표 추가: CPI(CPIAUCSL)와 PCE(PCEPI)는 둘 다 "미국 인플레이션 추세"라는
동일 정보를 반영하므로 미국 금리 커브와 동일한 worst-case(max) 병합 패턴으로 단일 `inflation` 신호로
합쳤다. 실업률(UNRATE)은 Sahm Rule(3개월 평균 실업률이 과거 12개월 최저치 대비 0.5%p 이상 상승하면
경기침체 신호)의 단순화 버전으로 `employment` 신호를 구성한다.


개별 지표 조회는 `market_signal_indicators`, 복합 점수 계산은 `market_signal_scoring`으로 분리했다
(docs/plans/41). 이 모듈은 캐시·single-flight 진입점과 confirmed level(hysteresis)을 담당하고,
외부 호출부 호환을 위해 두 모듈의 공개 심볼을 재노출한다."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import structlog

from app.services.market_signal_indicators import (
    fetch_cpi_inflation_signal,
    fetch_dollar_index_signal,
    fetch_employment_signal,
    fetch_exchange_rate_signal,
    fetch_high_yield_spread_signal,
    fetch_inflation_signal,
    fetch_oil_price_signal,
    fetch_pce_inflation_signal,
    fetch_rate_cut_expectation_signal,
    fetch_us_rate_curve_signal,
    fetch_vix_signal,
    fetch_yield_curve_signal,
)
from app.services.market_signal_scoring import COMPOSITE_SCORE_MAX, compute_composite_signal
from app.utils.cache_keys import (
    TTL_MARKET_SIGNAL,
    TTL_MARKET_SIGNAL_DEGRADED,
    TTL_MARKET_SIGNAL_LAST_LEVEL,
    get_cached_json,
    market_signal_last_level_key,
    market_signal_latest_key,
    market_signal_pending_confirmation_key,
    set_cached_json,
)
from app.utils.durable_state import delete_durable, get_durable, set_durable
from app.utils.inproc_lock import single_flight_fetch

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.cache_store import CacheStore

__all__ = [
    "COMPOSITE_SCORE_MAX",
    "compute_composite_signal",
    "fetch_cpi_inflation_signal",
    "fetch_dollar_index_signal",
    "fetch_employment_signal",
    "fetch_exchange_rate_signal",
    "fetch_high_yield_spread_signal",
    "fetch_inflation_signal",
    "fetch_oil_price_signal",
    "fetch_pce_inflation_signal",
    "fetch_rate_cut_expectation_signal",
    "fetch_us_rate_curve_signal",
    "fetch_vix_signal",
    "fetch_yield_curve_signal",
    "get_confirmed_composite_level",
    "get_last_composite_level",
    "get_market_signal",
    "set_last_composite_level",
]

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# 캐시 포함 메인 진입점
# ---------------------------------------------------------------------------


async def get_market_signal(cache: CacheStore | None = None) -> dict[str, Any]:
    """복합 시장 위험 신호를 반환한다. 캐시(정상 시 1시간, 일부/전체 실패 시 1분)."""
    cache_key = market_signal_latest_key()

    async def _read_cache() -> dict[str, Any] | None:
        data = await get_cached_json(cache, cache_key)
        if isinstance(data, dict) and data.get("data_freshness") != "STALE":
            data["data_freshness"] = "CACHED"
        return data

    cached = await _read_cache()
    if cache is not None and cached is not None:
        return cached

    async def _fetch_and_cache() -> dict[str, Any]:
        (
            vix,
            us_rate_curve,
            high_yield_spread,
            dollar_index,
            exchange_rate,
            oil_price,
            inflation,
            employment,
        ) = await _fetch_all_signals(cache)
        result = compute_composite_signal(
            vix,
            us_rate_curve,
            high_yield_spread,
            dollar_index,
            exchange_rate,
            oil_price,
            inflation,
            employment,
        )
        ttl = TTL_MARKET_SIGNAL if result["data_freshness"] == "LIVE" else TTL_MARKET_SIGNAL_DEGRADED
        await set_cached_json(cache, cache_key, result, ttl)
        return result

    if cache is None:
        return await _fetch_and_cache()

    return await single_flight_fetch(cache, cache_key, _read_cache, _fetch_and_cache)


CONFIRM_STREAK_REQUIRED = 2
"""raw 레벨이 연속 몇 회 관측돼야 confirmed level로 승격되는지 — LIVE 캐시 주기(1시간) 기준
최소 CONFIRM_STREAK_REQUIRED시간 지속돼야 반영되어 경계값 근처 flapping을 억제한다."""


async def get_confirmed_composite_level(cache: CacheStore | None, db: AsyncSession) -> tuple[str, str]:
    """AUTO 게이트·등급전환 알림 전용 — 연속 확인된 confirmed level을 반환한다 (raw와 별개).

    표시용 raw level(`get_market_signal`)은 캐시가 갱신될 때마다 즉시 반영되지만, 이 함수는 raw
    레벨이 `CONFIRM_STREAK_REQUIRED`회 연속 관측된 뒤에만 confirmed를 갱신해 경계값 근처에서
    GREEN↔YELLOW↔RED가 잦게 뒤바뀌는 것을 막는다. STALE은 이미 게이트가 무조건 차단하는 신호라
    확인 절차 없이 즉시 반영한다. 조회 자체가 실패하면 "판단 불가"를 "GREEN(안전)"으로 오인해
    게이트를 통과시키는 사고를 막기 위해 (GREEN, STALE)로 안전하게 폴백한다.

    `market_signal_last_level_key()`는 원래 "마지막 관측 레벨"용이었으나, 이 값을 소비하는 곳이
    등급전환 알림(`check_market_signal_level_change`) 하나뿐이라 "마지막 confirmed 레벨"로 의미를
    재정의해도 안전하다(마이그레이션 불필요 — durable_state는 스키마리스 key-value).
    """
    try:
        return await _resolve_confirmed_level(cache, db)
    except Exception as exc:
        logger.warning("market_signal_confirmed_level_fetch_failed", error=str(exc))
        return "GREEN", "STALE"


async def _resolve_confirmed_level(cache: CacheStore | None, db: AsyncSession) -> tuple[str, str]:
    raw = await get_market_signal(cache)
    raw_level: str = raw.get("composite_level", "GREEN")
    freshness: str = raw.get("data_freshness", "LIVE")
    observed_at: str = raw.get("computed_at", "")

    if freshness == "STALE":
        return raw_level, freshness

    confirmed = await get_durable(db, market_signal_last_level_key())
    if confirmed is None:
        await set_last_composite_level(db, raw_level)
        return raw_level, freshness

    if raw_level == confirmed:
        await delete_durable(db, market_signal_pending_confirmation_key())
        return confirmed, freshness

    pending_raw = await get_durable(db, market_signal_pending_confirmation_key())
    pending: dict[str, Any] = json.loads(pending_raw) if pending_raw else {}

    if pending.get("last_observed_at") == observed_at and pending.get("candidate") == raw_level:
        streak = pending.get("streak", 1)  # 같은 raw-fetch 세대의 중복 호출 — 재증가 방지
    elif pending.get("candidate") == raw_level:
        streak = pending.get("streak", 0) + 1
    else:
        streak = 1

    if streak >= CONFIRM_STREAK_REQUIRED:
        await set_last_composite_level(db, raw_level)
        await delete_durable(db, market_signal_pending_confirmation_key())
        return raw_level, freshness

    await set_durable(
        db,
        market_signal_pending_confirmation_key(),
        json.dumps({"candidate": raw_level, "streak": streak, "last_observed_at": observed_at}),
        ttl=TTL_MARKET_SIGNAL_LAST_LEVEL,
    )
    return confirmed, freshness


async def get_last_composite_level(db: AsyncSession) -> str | None:
    """등급 변화 감지 job이 마지막으로 관측한 confirmed composite_level을 조회한다. 없으면 None.

    재시작에도 유지돼야 하는 상태라(콜드스타트 직후 오탐/누락 방지) Postgres 기반
    durable_state를 사용한다 — in-memory 캐시(Tier 1)와는 별개.
    """
    return await get_durable(db, market_signal_last_level_key())


async def set_last_composite_level(db: AsyncSession, level: str) -> None:
    """현재 confirmed composite_level을 다음 비교를 위해 저장한다."""
    await set_durable(db, market_signal_last_level_key(), level, ttl=TTL_MARKET_SIGNAL_LAST_LEVEL)


async def _fetch_all_signals(
    cache: CacheStore | None = None,
) -> tuple[
    dict[str, Any] | None,
    dict[str, Any] | None,
    dict[str, Any] | None,
    dict[str, Any] | None,
    dict[str, Any] | None,
    dict[str, Any] | None,
    dict[str, Any] | None,
    dict[str, Any] | None,
]:
    """여덟 신호를 병렬로 조회한다. 개별 실패가 전체를 막지 않는다."""
    import asyncio

    results = await asyncio.gather(
        fetch_vix_signal(),
        fetch_us_rate_curve_signal(),
        fetch_high_yield_spread_signal(),
        fetch_dollar_index_signal(),
        fetch_exchange_rate_signal(cache),
        fetch_oil_price_signal(),
        fetch_inflation_signal(),
        fetch_employment_signal(),
        return_exceptions=True,
    )

    def _safe(r: dict[str, Any] | BaseException | None) -> dict[str, Any] | None:
        if isinstance(r, BaseException):
            logger.warning("market_signal_fetch_error", error=str(r))
            return None
        return r

    return tuple(_safe(r) for r in results)  # type: ignore[return-value]
