"""KIS/Kiwoom 공용 해외 잔고 조회 캐시 헬퍼.

해외 보유가 없는 것으로 확인된 계좌는 캐시 TTL 동안 해외 API 호출을 건너뛰어
국내 전용 계좌의 불필요한 API 콜을 절감한다. 구 `kis_provider.py::_fetch_overseas_cached`/
`_safe_overseas`를 브로커 무관 형태로 추출한 것.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import structlog

from app.utils.cache_keys import TTL_HAS_OVERSEAS_FALSE, TTL_HAS_OVERSEAS_TRUE, has_overseas_key

if TYPE_CHECKING:
    from app.core.cache_store import CacheStore

logger = structlog.get_logger()

EMPTY_OVERSEAS: dict = {"positions": [], "total_value_usd": 0.0, "deposit_usd": 0.0}


async def fetch_overseas_cached(
    fetch_fn: Callable[[], Awaitable[dict]],
    account_id: uuid.UUID,
    cache: CacheStore,
    *,
    token_expired_exc: type[Exception],
    broker_name: str,
) -> dict:
    """해외 잔고 조회 — 캐시로 국내 전용 계좌의 해외 API 호출을 건너뛴다."""
    cached = await cache.get(has_overseas_key(account_id))
    if cached == "0":
        return dict(EMPTY_OVERSEAS)
    result = await _safe_overseas(fetch_fn, token_expired_exc, broker_name)
    # 보유 종목이 없어도 외화 예수금만 있는 계좌가 있으므로 예수금>0도 "해외 있음"으로 본다 —
    # 아니면 TTL 동안 해외 조회를 건너뛰어 deposit_usd가 0으로 취급됨.
    has_ov = bool(result["positions"]) or float(result.get("deposit_usd") or 0) > 0
    # 해외 조회가 실패(fail-soft)한 결과는 "해외 없음"으로 캐싱하지 않는다 — 일시 장애가
    # TTL 동안 굳어져 USD 예수금·포지션이 사라지는 것을 방지.
    if result.get("ok", True):
        await cache.setex(
            has_overseas_key(account_id),
            TTL_HAS_OVERSEAS_TRUE if has_ov else TTL_HAS_OVERSEAS_FALSE,
            "1" if has_ov else "0",
        )
    return result


async def _safe_overseas(
    fetch_fn: Callable[[], Awaitable[dict]],
    token_expired_exc: type[Exception],
    broker_name: str,
) -> dict:
    """해외 잔고 조회. token_expired_exc는 re-raise, 나머지 오류는 warn 후 빈 결과 반환."""
    try:
        return await fetch_fn()
    except token_expired_exc:
        raise
    except Exception as e:
        logger.warning("overseas_fetch_failed", broker=broker_name, error=str(e))
        # ok=False → 호출부가 "확정된 0"이 아닌 "미확인"으로 처리 (deposit_usd 덮어쓰기 금지)
        return {**EMPTY_OVERSEAS, "ok": False}
