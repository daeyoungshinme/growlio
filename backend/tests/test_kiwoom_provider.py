"""providers/kiwoom_provider.py 단위 테스트 — 토큰 만료-재시도 경로 characterization."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.exceptions import ProviderCredentialError
from app.providers.kiwoom_provider import KiwoomProvider


def _domestic_balance(total_value_krw=1_000_000.0, deposit_krw=100_000.0, invested_krw=900_000.0):
    return {
        "total_value_krw": total_value_krw,
        "deposit_krw": deposit_krw,
        "invested_krw": invested_krw,
        "positions": [
            {
                "ticker": "005930",
                "name": "삼성전자",
                "market": "KOSPI",
                "qty": 10,
                "avg_price": 70000.0,
                "current_price": 75000.0,
                "value_krw": 750000.0,
            }
        ],
    }


class TestKiwoomProviderSync:
    @pytest.mark.asyncio
    async def test_sync_happy_path_no_token_expiry(self, override_settings, make_account, mock_redis):
        account = make_account(
            data_source="KIWOOM_API",
            kiwoom_app_key=b"enc_key",
            kiwoom_app_secret=b"enc_secret",
            kiwoom_account_no="1234567890",
        )
        provider = KiwoomProvider()

        with (
            patch("app.providers.kiwoom_provider.decrypt", side_effect=["key", "secret"]),
            patch("app.kiwoom.auth.get_access_token", new=AsyncMock(return_value="token-1")),
            patch("app.kiwoom.balance.get_domestic_balance", new=AsyncMock(return_value=_domestic_balance())),
            patch("app.providers.kiwoom_provider.get_usd_krw_rate", new=AsyncMock(return_value=1300.0)),
        ):
            result = await provider.sync(account, db=AsyncMock(), redis=mock_redis)

        assert result.total_value_krw == 1_100_000.0  # domestic total 1,000,000 + deposit 100,000
        assert result.deposit_krw == 100_000.0
        assert len(result.positions) == 1
        assert result.positions[0].ticker == "005930"

    @pytest.mark.asyncio
    async def test_sync_retries_after_token_expired(self, override_settings, make_account, mock_redis):
        """첫 조회에서 토큰 만료 → 강제 갱신 후 재시도해 성공해야 한다."""
        from app.kiwoom.client import KiwoomTokenExpiredError

        account = make_account(
            data_source="KIWOOM_API",
            kiwoom_app_key=b"enc_key",
            kiwoom_app_secret=b"enc_secret",
            kiwoom_account_no="1234567890",
        )
        provider = KiwoomProvider()

        token_calls: list[bool] = []

        async def _fake_get_access_token(*args, **kwargs):
            force_refresh = kwargs.get("force_refresh", False)
            token_calls.append(force_refresh)
            return "token-2" if force_refresh else "token-1"

        domestic_calls = {"count": 0}

        async def _fake_get_domestic_balance(*args, **kwargs):
            domestic_calls["count"] += 1
            if domestic_calls["count"] == 1:
                raise KiwoomTokenExpiredError("expired")
            return _domestic_balance()

        with (
            patch("app.providers.kiwoom_provider.decrypt", side_effect=["key", "secret"]),
            patch("app.kiwoom.auth.get_access_token", side_effect=_fake_get_access_token),
            patch("app.kiwoom.balance.get_domestic_balance", side_effect=_fake_get_domestic_balance),
            patch("app.providers.kiwoom_provider.get_usd_krw_rate", new=AsyncMock(return_value=1300.0)),
        ):
            result = await provider.sync(account, db=AsyncMock(), redis=mock_redis)

        assert result.total_value_krw == 1_100_000.0  # domestic total 1,000,000 + deposit 100,000
        assert token_calls == [False, True]
        assert domestic_calls["count"] == 2

    @pytest.mark.asyncio
    async def test_sync_missing_credentials_raises(self, override_settings, make_account, mock_redis):
        account = make_account(data_source="KIWOOM_API", kiwoom_app_key=None, kiwoom_app_secret=None)
        provider = KiwoomProvider()

        with pytest.raises(ProviderCredentialError):
            await provider.sync(account, db=AsyncMock(), redis=mock_redis)
