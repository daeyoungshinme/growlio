"""app/providers/_overseas_cache.py 단위 테스트."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from app.providers._overseas_cache import fetch_overseas_cached


class _TokenExpired(Exception):
    pass


def _cache(cached_value=None):
    c = AsyncMock()
    c.get = AsyncMock(return_value=cached_value)
    c.setex = AsyncMock()
    return c


@pytest.mark.asyncio
async def test_positions_present_caches_has_overseas_true():
    cache = _cache()
    result = await fetch_overseas_cached(
        AsyncMock(return_value={"positions": [{"ticker": "QQQ"}], "total_value_usd": 1.0, "deposit_usd": 0.0}),
        uuid.uuid4(),
        cache,
        token_expired_exc=_TokenExpired,
        broker_name="키움",
    )
    assert result["positions"]
    cache.setex.assert_awaited_once()
    assert cache.setex.await_args.args[2] == "1"


@pytest.mark.asyncio
async def test_deposit_only_account_still_marked_has_overseas():
    """보유 종목은 없어도 USD 예수금만 있으면 '해외 있음'으로 캐싱해야 한다."""
    cache = _cache()
    await fetch_overseas_cached(
        AsyncMock(return_value={"positions": [], "total_value_usd": 0.0, "deposit_usd": 500.0}),
        uuid.uuid4(),
        cache,
        token_expired_exc=_TokenExpired,
        broker_name="키움",
    )
    assert cache.setex.await_args.args[2] == "1"


@pytest.mark.asyncio
async def test_fetch_failure_returns_not_ok_and_is_not_cached():
    cache = _cache()
    result = await fetch_overseas_cached(
        AsyncMock(side_effect=RuntimeError("boom")),
        uuid.uuid4(),
        cache,
        token_expired_exc=_TokenExpired,
        broker_name="키움",
    )
    assert result["ok"] is False
    assert result["deposit_usd"] == 0.0
    cache.setex.assert_not_awaited()


@pytest.mark.asyncio
async def test_token_expired_propagates():
    cache = _cache()
    with pytest.raises(_TokenExpired):
        await fetch_overseas_cached(
            AsyncMock(side_effect=_TokenExpired()),
            uuid.uuid4(),
            cache,
            token_expired_exc=_TokenExpired,
            broker_name="키움",
        )


@pytest.mark.asyncio
async def test_cached_zero_skips_fetch():
    cache = _cache(cached_value="0")
    fetch_fn = AsyncMock()
    result = await fetch_overseas_cached(
        fetch_fn, uuid.uuid4(), cache, token_expired_exc=_TokenExpired, broker_name="키움"
    )
    fetch_fn.assert_not_awaited()
    assert result == {"positions": [], "total_value_usd": 0.0, "deposit_usd": 0.0}
