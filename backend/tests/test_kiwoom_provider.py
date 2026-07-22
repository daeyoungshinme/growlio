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
                "currency": "KRW",
            }
        ],
    }


def _empty_overseas():
    return {"positions": [], "total_value_usd": 0.0, "deposit_usd": 0.0}


def _overseas_balance(total_value_usd=1_000.0, deposit_usd=100.0):
    return {
        "positions": [
            {
                "ticker": "AAPL",
                "name": "Apple",
                "market": "NASDAQ",
                "qty": 5,
                "avg_price": 150.0,
                "current_price": 200.0,
                "value_usd": total_value_usd,
                "currency": "USD",
            }
        ],
        "total_value_usd": total_value_usd,
        "deposit_usd": deposit_usd,
    }


class TestKiwoomProviderSync:
    @pytest.mark.asyncio
    async def test_sync_happy_path_no_token_expiry(self, override_settings, make_account, mock_cache):
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
            patch("app.kiwoom.balance.get_overseas_balance", new=AsyncMock(return_value=_empty_overseas())),
            patch("app.providers.kiwoom_provider.get_usd_krw_rate", new=AsyncMock(return_value=1300.0)),
        ):
            result = await provider.sync(account, db=AsyncMock(), cache=mock_cache)

        assert result.total_value_krw == 1_100_000.0  # domestic total 1,000,000 + deposit 100,000
        assert result.deposit_krw == 100_000.0
        assert len(result.positions) == 1
        assert result.positions[0].ticker == "005930"

    @pytest.mark.asyncio
    async def test_sync_retries_after_token_expired(self, override_settings, make_account, mock_cache):
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
            patch("app.kiwoom.balance.get_overseas_balance", new=AsyncMock(return_value=_empty_overseas())),
            patch("app.providers.kiwoom_provider.get_usd_krw_rate", new=AsyncMock(return_value=1300.0)),
        ):
            result = await provider.sync(account, db=AsyncMock(), cache=mock_cache)

        assert result.total_value_krw == 1_100_000.0  # domestic total 1,000,000 + deposit 100,000
        assert token_calls == [False, True]
        assert domestic_calls["count"] == 2

    @pytest.mark.asyncio
    async def test_sync_missing_credentials_raises(self, override_settings, make_account, mock_cache):
        account = make_account(data_source="KIWOOM_API", kiwoom_app_key=None, kiwoom_app_secret=None)
        provider = KiwoomProvider()

        with pytest.raises(ProviderCredentialError):
            await provider.sync(account, db=AsyncMock(), cache=mock_cache)

    @pytest.mark.asyncio
    async def test_sync_with_domestic_and_overseas_positions(self, override_settings, make_account, mock_cache):
        """국내+해외 포지션이 모두 있을 때 합산 결과와 deposit_foreign이 올바르게 채워져야 한다."""
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
            patch(
                "app.kiwoom.balance.get_overseas_balance",
                new=AsyncMock(return_value=_overseas_balance(total_value_usd=1_000.0, deposit_usd=100.0)),
            ),
            patch("app.providers.kiwoom_provider.get_usd_krw_rate", new=AsyncMock(return_value=1300.0)),
            patch("app.providers._overseas_name_enrichment.resolve_english_name", new=AsyncMock(return_value=None)),
        ):
            result = await provider.sync(account, db=AsyncMock(), cache=mock_cache)

        # domestic(1,000,000 + 100,000) + overseas(1,000*1300=1,300,000 + 100*1300=130,000)
        assert result.total_value_krw == 1_100_000.0 + 1_300_000.0 + 130_000.0
        assert result.deposit_foreign == 100.0
        assert len(result.positions) == 2
        tickers = {p.ticker for p in result.positions}
        assert tickers == {"005930", "AAPL"}
        aapl = next(p for p in result.positions if p.ticker == "AAPL")
        assert aapl.currency == "USD"
        assert aapl.avg_price_usd == 150.0
        assert aapl.avg_price == 150.0 * 1300.0

    @pytest.mark.asyncio
    async def test_sync_overseas_fetch_failure_falls_back_to_domestic_only(
        self, override_settings, make_account, mock_cache
    ):
        """해외 API가 예외를 던져도 전체 sync는 실패하지 않고 국내 결과만으로 반환된다(fail-soft)."""
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
            patch(
                "app.kiwoom.balance.get_overseas_balance",
                new=AsyncMock(side_effect=RuntimeError("mock 모드 해외 미지원")),
            ),
            patch("app.providers.kiwoom_provider.get_usd_krw_rate", new=AsyncMock(return_value=1300.0)),
        ):
            result = await provider.sync(account, db=AsyncMock(), cache=mock_cache)

        assert result.total_value_krw == 1_100_000.0
        assert len(result.positions) == 1
        assert result.positions[0].ticker == "005930"

    @pytest.mark.asyncio
    async def test_sync_skips_overseas_when_cache_marks_no_overseas(self, override_settings, make_account, mock_cache):
        """Cache has_overseas 캐시가 '해외 없음'을 가리키면 해외 API를 호출하지 않아야 한다."""
        account = make_account(
            data_source="KIWOOM_API",
            kiwoom_app_key=b"enc_key",
            kiwoom_app_secret=b"enc_secret",
            kiwoom_account_no="1234567890",
        )
        provider = KiwoomProvider()
        mock_cache.get = AsyncMock(return_value="0")

        with (
            patch("app.providers.kiwoom_provider.decrypt", side_effect=["key", "secret"]),
            patch("app.kiwoom.auth.get_access_token", new=AsyncMock(return_value="token-1")),
            patch("app.kiwoom.balance.get_domestic_balance", new=AsyncMock(return_value=_domestic_balance())),
            patch("app.kiwoom.balance.get_overseas_balance", new=AsyncMock()) as overseas_fn,
            patch("app.providers.kiwoom_provider.get_usd_krw_rate", new=AsyncMock(return_value=1300.0)),
        ):
            result = await provider.sync(account, db=AsyncMock(), cache=mock_cache)

        overseas_fn.assert_not_called()
        assert result.total_value_krw == 1_100_000.0

    @pytest.mark.asyncio
    async def test_sync_overseas_position_name_replaced_with_english_canonical(
        self, override_settings, make_account, mock_cache
    ):
        """해외 포지션의 브로커 원본(한글) 종목명이 영문 캐노니컬 이름으로 교체되어야 한다."""
        account = make_account(
            data_source="KIWOOM_API",
            kiwoom_app_key=b"enc_key",
            kiwoom_app_secret=b"enc_secret",
            kiwoom_account_no="1234567890",
        )
        provider = KiwoomProvider()
        overseas = _overseas_balance()
        overseas["positions"][0]["name"] = "애플"

        with (
            patch("app.providers.kiwoom_provider.decrypt", side_effect=["key", "secret"]),
            patch("app.kiwoom.auth.get_access_token", new=AsyncMock(return_value="token-1")),
            patch("app.kiwoom.balance.get_domestic_balance", new=AsyncMock(return_value=_domestic_balance())),
            patch("app.kiwoom.balance.get_overseas_balance", new=AsyncMock(return_value=overseas)),
            patch("app.providers.kiwoom_provider.get_usd_krw_rate", new=AsyncMock(return_value=1300.0)),
            patch(
                "app.providers._overseas_name_enrichment.resolve_english_name",
                new=AsyncMock(return_value="Apple Inc."),
            ),
        ):
            result = await provider.sync(account, db=AsyncMock(), cache=mock_cache)

        aapl = next(p for p in result.positions if p.ticker == "AAPL")
        assert aapl.name == "Apple Inc."
        from app.utils.cache_keys import TTL_OVERSEAS_STOCK_NAME, overseas_stock_name_key

        mock_cache.setex.assert_any_call(overseas_stock_name_key("AAPL"), TTL_OVERSEAS_STOCK_NAME, "Apple Inc.")
