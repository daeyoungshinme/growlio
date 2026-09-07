"""providers/toss_provider.py 단위 테스트 — 토큰 만료-재시도 · 통화 환산 · IP 차단 매핑."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.exceptions import ProviderApiError, ProviderCredentialError
from app.providers.toss_provider import TossProvider


def _balance(
    positions=None,
    invested=None,
    market_value=None,
    deposit_krw=100_000.0,
    deposit_usd=0.0,
):
    return {
        "positions": positions
        if positions is not None
        else [
            {
                "ticker": "005930",
                "name": "삼성전자",
                "market": "KOSPI",
                "qty": 10,
                "avg_price": 70_000.0,
                "current_price": 75_000.0,
                "currency": "KRW",
            }
        ],
        "invested": invested or {"krw": 700_000.0, "usd": 0.0},
        "market_value": market_value or {"krw": 750_000.0, "usd": 0.0},
        "deposit_krw": deposit_krw,
        "deposit_usd": deposit_usd,
    }


def _toss_account(make_account, **over):
    kwargs = {
        "data_source": "TOSS_API",
        "asset_type": "STOCK_TOSS",
        "toss_account_no": "12345678901",
        "toss_client_id": b"enc_id",
        "toss_client_secret": b"enc_secret",
    }
    kwargs.update(over)
    return make_account(**kwargs)


class TestTossProviderSync:
    @pytest.mark.asyncio
    async def test_sync_happy_path(self, override_settings, make_account, mock_cache):
        account = _toss_account(make_account)
        provider = TossProvider()

        with (
            patch("app.providers.toss_provider.decrypt", side_effect=["id", "secret"]),
            patch("app.toss.auth.get_access_token", new=AsyncMock(return_value="tok-1")),
            patch("app.toss.balance.get_balance", new=AsyncMock(return_value=_balance())),
            patch("app.providers.toss_provider.get_usd_krw_rate", new=AsyncMock(return_value=1300.0)),
        ):
            result = await provider.sync(account, db=AsyncMock(), cache=mock_cache)

        assert result.total_value_krw == 750_000.0 + 100_000.0
        assert result.deposit_krw == 100_000.0
        assert result.invested_krw == 700_000.0
        assert result.pnl_krw == 50_000.0
        assert len(result.positions) == 1
        assert result.positions[0].ticker == "005930"
        assert result.extra["source"] == "TOSS_API"

    @pytest.mark.asyncio
    async def test_sync_retries_after_token_expired(self, override_settings, make_account, mock_cache):
        from app.toss.client import TossTokenExpiredError

        account = _toss_account(make_account)
        provider = TossProvider()

        token_calls: list[bool] = []

        async def _fake_get_token(*args, **kwargs):
            force = kwargs.get("force_refresh", False)
            token_calls.append(force)
            return "tok-2" if force else "tok-1"

        calls = {"n": 0}

        async def _fake_get_balance(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise TossTokenExpiredError("expired")
            return _balance()

        with (
            patch("app.providers.toss_provider.decrypt", side_effect=["id", "secret"]),
            patch("app.toss.auth.get_access_token", side_effect=_fake_get_token),
            patch("app.toss.balance.get_balance", side_effect=_fake_get_balance),
            patch("app.providers.toss_provider.get_usd_krw_rate", new=AsyncMock(return_value=1300.0)),
        ):
            result = await provider.sync(account, db=AsyncMock(), cache=mock_cache)

        assert token_calls == [False, True]
        assert calls["n"] == 2
        assert result.total_value_krw == 850_000.0

    @pytest.mark.asyncio
    async def test_sync_missing_credentials_raises(self, override_settings, make_account, mock_cache):
        account = _toss_account(make_account, toss_client_id=None, toss_client_secret=None)
        provider = TossProvider()

        with pytest.raises(ProviderCredentialError):
            await provider.sync(account, db=AsyncMock(), cache=mock_cache)

    @pytest.mark.asyncio
    async def test_sync_usd_position_converted_to_krw(self, override_settings, make_account, mock_cache):
        account = _toss_account(make_account)
        provider = TossProvider()
        bal = _balance(
            positions=[
                {
                    "ticker": "AAPL",
                    "name": "애플",
                    "market": "US",  # 토스 holdings는 미국 하위 거래소를 구분하지 않음 → 센티널
                    "qty": 5,
                    "avg_price": 150.0,
                    "current_price": 200.0,
                    "currency": "USD",
                }
            ],
            invested={"krw": 0.0, "usd": 750.0},
            market_value={"krw": 0.0, "usd": 1_000.0},
            deposit_krw=0.0,
            deposit_usd=100.0,
        )

        with (
            patch("app.providers.toss_provider.decrypt", side_effect=["id", "secret"]),
            patch("app.toss.auth.get_access_token", new=AsyncMock(return_value="tok-1")),
            patch("app.toss.balance.get_balance", new=AsyncMock(return_value=bal)),
            patch("app.providers.toss_provider.get_usd_krw_rate", new=AsyncMock(return_value=1300.0)),
            patch(
                "app.providers._overseas_name_enrichment.resolve_ticker_meta",
                new=AsyncMock(return_value=("Apple Inc.", "NASDAQ")),
            ),
        ):
            result = await provider.sync(account, db=AsyncMock(), cache=mock_cache)

        assert result.invested_krw == 750.0 * 1300.0
        assert result.total_value_krw == 1_000.0 * 1300.0 + 100.0 * 1300.0
        assert result.deposit_foreign == 100.0
        aapl = result.positions[0]
        assert aapl.name == "Apple Inc."
        assert aapl.market == "NASDAQ"  # "US" 센티널 → enrich_overseas_positions()가 확정
        assert aapl.currency == "USD"
        assert aapl.avg_price_usd == 150.0
        assert aapl.avg_price == 150.0 * 1300.0

    @pytest.mark.asyncio
    async def test_sync_ip_blocked_maps_to_provider_api_error(self, override_settings, make_account, mock_cache):
        from app.toss.client import TossApiError

        account = _toss_account(make_account)
        provider = TossProvider()

        with (
            patch("app.providers.toss_provider.decrypt", side_effect=["id", "secret"]),
            patch("app.toss.auth.get_access_token", new=AsyncMock(return_value="tok-1")),
            patch(
                "app.toss.balance.get_balance",
                new=AsyncMock(side_effect=TossApiError("edge-blocked", "blocked", status_code=403)),
            ),
            patch("app.providers.toss_provider.get_usd_krw_rate", new=AsyncMock(return_value=1300.0)),
            pytest.raises(ProviderApiError) as exc,
        ):
            await provider.sync(account, db=AsyncMock(), cache=mock_cache)

        assert exc.value.http_status == 403
        assert "IP 관리" in exc.value.detail
