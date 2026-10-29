"""기동 예열 잡 — 항목별 실패 격리."""

from unittest.mock import AsyncMock, patch

import pytest

from app.jobs import startup_warmup


@pytest.mark.asyncio
async def test_warmup_isolates_failures():
    fx = AsyncMock(return_value=1400.0)
    signal = AsyncMock(side_effect=RuntimeError("fred down"))
    tech = AsyncMock(return_value={})
    with (
        patch("app.utils.currency.fetch_usd_krw", fx),
        patch("app.services.market_signal.market_signal_service.get_market_signal", signal),
        patch("app.services.market_signal.technical_signal_service.get_technical_signals", tech),
        patch.object(startup_warmup, "_warm_jwks", AsyncMock()),
        patch.object(startup_warmup, "logger") as log,
    ):
        await startup_warmup.run_startup_warmup()

    fx.assert_awaited_once()
    assert fx.await_args.kwargs == {"force_refresh": True}
    tech.assert_awaited_once()
    log.warning.assert_called_once()
    assert "market_signal" in log.warning.call_args.kwargs["failed"]


@pytest.mark.asyncio
async def test_warm_jwks_skips_without_project_url(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "supabase_project_url", "")
    with patch("app.services.auth_service._get_jwks_client") as get_client:
        await startup_warmup._warm_jwks()
    get_client.assert_not_called()
