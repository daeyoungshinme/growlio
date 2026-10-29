"""기동 직후 1회 — 콜드 스타트 첫 요청들이 외부 API를 직접 기다리지 않도록 공용 캐시를 미리 채운다.

Render 무료 플랜은 15분 무요청 시 잠들어 인메모리 캐시가 비워진다. 깨어난 직후 홈 화면 요청이 한꺼번에
들어오면 환율·시장 신호(FRED 8종)·기술적 신호(yfinance)·Supabase JWKS를 각 요청이 동기 대기했다.
특히 환율 캐시가 비어 있으면 설정 fallback(1300원)으로 계산된 배당 요약·대시보드가 캐시에 남았다.
항목별로 실패를 격리한다 — 예열 실패는 기존처럼 요청 시점 조회로 폴백할 뿐이다.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from app.core.cache_store import get_cache_store

logger = structlog.get_logger()


async def _warm_jwks() -> None:
    from app.core.config import settings
    from app.services.auth_service import _get_jwks_client

    if not settings.supabase_project_url:
        return
    # PyJWKClient는 동기 urllib으로 받는다 — 첫 인증 요청이 이벤트 루프를 막지 않도록 스레드에서 미리 받아 캐시
    await asyncio.to_thread(_get_jwks_client().get_signing_keys)


async def run_startup_warmup() -> None:
    from app.services.market_signal.market_signal_service import get_market_signal
    from app.services.market_signal.technical_signal_service import get_technical_signals
    from app.utils.currency import fetch_usd_krw

    cache = await get_cache_store()
    tasks: dict[str, Callable[[], Awaitable[Any]]] = {
        "usd_krw": lambda: fetch_usd_krw(cache, force_refresh=True),
        "jwks": _warm_jwks,
        "market_signal": lambda: get_market_signal(cache),
        "technical_signals": lambda: get_technical_signals(cache),
    }
    results = await asyncio.gather(*(fn() for fn in tasks.values()), return_exceptions=True)
    failed = {name: str(r) for name, r in zip(tasks, results, strict=True) if isinstance(r, BaseException)}
    if failed:
        logger.warning("startup_warmup_partial", failed=failed)
    else:
        logger.info("startup_warmup_done")
