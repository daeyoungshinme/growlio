"""브로커 API 공통 재시도 헬퍼 — 토큰 만료 시 강제 갱신 후 1회 재시도."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


async def with_token_refresh(
    fetch: Callable[[str], Awaitable[T]],
    get_token: Callable[[bool], Awaitable[str]],
    expired_exc_type: type[Exception],
    on_expired: Callable[[], None] | None = None,
) -> T:
    """토큰 발급 → fetch 실행 → 토큰 만료 예외 시 강제 갱신 후 1회 재시도.

    KIS/Kiwoom 모두 "발급된 토큰으로 시도 → 만료 예외 시 강제 갱신 후 재시도" 패턴을
    독립적으로 구현하고 있었던 것을 공용화한 것. 브로커마다 만료 예외 타입이 다르므로
    `expired_exc_type`으로 받는다.
    """
    token = await get_token(False)
    try:
        return await fetch(token)
    except expired_exc_type:
        if on_expired:
            on_expired()
        token = await get_token(True)
        return await fetch(token)
