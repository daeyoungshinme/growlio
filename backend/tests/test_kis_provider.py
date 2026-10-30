"""providers/kis_provider.py 단위 테스트 — 토큰 만료-재시도 경로 characterization."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.exceptions import ProviderCredentialError
from app.kis.client import KisTokenExpiredError
from app.providers.kis_provider import KISProvider


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
                "name": "애플",
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


class TestKISProviderSync:
    @pytest.mark.asyncio
    async def test_sync_timeout_raises_network_error(self, override_settings, make_account, mock_cache):
        """KIS도 키움/토스처럼 전체 동기화에 상한 시간을 둔다."""
        import asyncio

        from app.exceptions import ProviderNetworkError

        account = make_account(data_source="KIS_API", kis_app_key=b"enc_key", kis_app_secret=b"enc_secret")

        async def _hang(*args, **kwargs):
            await asyncio.sleep(10)

        with (
            patch("app.providers.kis_provider.decrypt", side_effect=["key", "secret"]),
            patch("app.providers.kis_provider.SYNC_TIMEOUT_SECONDS", 0.01),
            patch("app.providers.kis_provider.get_access_token", new=AsyncMock(return_value="token-1")),
            patch("app.providers.kis_provider.get_domestic_balance", new=_hang),
            patch("app.providers.kis_provider.get_overseas_balance", new=AsyncMock(return_value=_empty_overseas())),
            pytest.raises(ProviderNetworkError),
        ):
            await KISProvider().sync(account, db=AsyncMock(), cache=mock_cache)

    @pytest.mark.asyncio
    async def test_sync_pagination_error_maps_to_provider_502(self, override_settings, make_account, mock_cache):
        """잔고 연속조회 상한/반복 키는 전역 500이 아니라 키움과 같은 502 ProviderApiError로 (계획 57 B3)."""
        from app.exceptions import BalancePaginationError, ProviderApiError

        account = make_account(data_source="KIS_API", kis_app_key=b"enc_key", kis_app_secret=b"enc_secret")
        with (
            patch("app.providers.kis_provider.decrypt", side_effect=["key", "secret"]),
            patch("app.providers.kis_provider.get_access_token", new=AsyncMock(return_value="token-1")),
            patch(
                "app.providers.kis_provider.get_domestic_balance",
                new=AsyncMock(side_effect=BalancePaginationError("KIS 잔고 연속조회가 20페이지를 넘었습니다")),
            ),
            patch("app.providers.kis_provider.get_overseas_balance", new=AsyncMock(return_value=_empty_overseas())),
            pytest.raises(ProviderApiError) as exc_info,
        ):
            await KISProvider().sync(account, db=AsyncMock(), cache=mock_cache)
        assert exc_info.value.http_status == 502
        assert "연속조회" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_sync_happy_path_no_token_expiry(self, override_settings, make_account, mock_cache):
        account = make_account(data_source="KIS_API", kis_app_key=b"enc_key", kis_app_secret=b"enc_secret")
        provider = KISProvider()

        with (
            patch("app.providers.kis_provider.decrypt", side_effect=["key", "secret"]),
            patch("app.providers.kis_provider.get_access_token", new=AsyncMock(return_value="token-1")),
            patch(
                "app.providers.kis_provider.get_domestic_balance",
                new=AsyncMock(return_value=_domestic_balance()),
            ),
            patch(
                "app.providers.kis_provider.get_overseas_balance",
                new=AsyncMock(return_value=_empty_overseas()),
            ),
            patch("app.providers.kis_provider.get_usd_krw_rate", new=AsyncMock(return_value=1300.0)),
        ):
            result = await provider.sync(account, db=AsyncMock(), cache=mock_cache)

        assert result.total_value_krw == 1_100_000.0  # domestic total 1,000,000 + deposit 100,000
        assert result.deposit_krw == 100_000.0
        assert len(result.positions) == 1
        assert result.positions[0].ticker == "005930"

    @pytest.mark.asyncio
    async def test_sync_overseas_converts_with_shared_rate_not_quote(self, override_settings, make_account, mock_cache):
        """해외 환산은 공용 환율을 쓴다 — 시세 TR의 output.rate(등락률 %)를 환율로 쓰던 버그 회귀 (plans/99 A1)."""
        account = make_account(data_source="KIS_API", kis_app_key=b"enc_key", kis_app_secret=b"enc_secret")
        provider = KISProvider()

        with (
            patch("app.providers.kis_provider.decrypt", side_effect=["key", "secret"]),
            patch("app.providers.kis_provider.get_access_token", new=AsyncMock(return_value="token-1")),
            patch(
                "app.providers.kis_provider.get_domestic_balance",
                new=AsyncMock(return_value=_domestic_balance()),
            ),
            patch(
                "app.providers.kis_provider.get_overseas_balance",
                new=AsyncMock(return_value=_overseas_balance()),
            ),
            patch("app.providers.kis_provider.get_usd_krw_rate", new=AsyncMock(return_value=1300.0)),
            patch(
                "app.kis.overseas_quote.kis_request",
                new=AsyncMock(return_value={"output": {"last": "200", "rate": "1.25"}}),
            ) as quote_request,
            patch(
                "app.providers._overseas_name_enrichment.resolve_ticker_meta",
                new=AsyncMock(return_value=("Apple Inc.", "NASDAQ")),
            ),
        ):
            result = await provider.sync(account, db=AsyncMock(), cache=mock_cache)

        quote_request.assert_not_called()
        aapl = next(p for p in result.positions if p.ticker == "AAPL")
        assert aapl.avg_price == 150.0 * 1300.0
        assert result.total_value_krw == 1_100_000.0 + (1_000.0 + 100.0) * 1300.0

    @pytest.mark.asyncio
    async def test_sync_overseas_failure_marks_overseas_unknown(self, override_settings, make_account, mock_cache):
        """해외 잔고 조회 실패 → deposit_foreign=None, overseas_known=False (asset_service가 해외 포지션 보존)."""
        account = make_account(data_source="KIS_API", kis_app_key=b"enc_key", kis_app_secret=b"enc_secret")
        provider = KISProvider()

        with (
            patch("app.providers.kis_provider.decrypt", side_effect=["key", "secret"]),
            patch("app.providers.kis_provider.get_access_token", new=AsyncMock(return_value="token-1")),
            patch(
                "app.providers.kis_provider.get_domestic_balance",
                new=AsyncMock(return_value=_domestic_balance()),
            ),
            patch(
                "app.providers.kis_provider.get_overseas_balance",
                new=AsyncMock(side_effect=RuntimeError("KIS 해외잔고 조회 실패 거래소: AMEX")),
            ),
            patch("app.providers.kis_provider.get_usd_krw_rate", new=AsyncMock(return_value=1300.0)),
        ):
            result = await provider.sync(account, db=AsyncMock(), cache=mock_cache)

        assert result.overseas_known is False
        assert result.deposit_foreign is None
        mock_cache.setex.assert_not_called()  # "해외 없음"을 캐싱하지 않음

    @pytest.mark.asyncio
    async def test_sync_retries_after_token_expired(self, override_settings, make_account, mock_cache):
        """첫 조회에서 토큰 만료 → 강제 갱신 후 재시도해 성공해야 한다."""
        account = make_account(data_source="KIS_API", kis_app_key=b"enc_key", kis_app_secret=b"enc_secret")
        provider = KISProvider()

        token_calls: list[bool] = []

        async def _fake_get_access_token(*args, **kwargs):
            force_refresh = kwargs.get("force_refresh", False)
            token_calls.append(force_refresh)
            return "token-2" if force_refresh else "token-1"

        domestic_calls = {"count": 0}

        async def _fake_get_domestic_balance(*args, **kwargs):
            domestic_calls["count"] += 1
            if domestic_calls["count"] == 1:
                raise KisTokenExpiredError("expired")
            return _domestic_balance()

        with (
            patch("app.providers.kis_provider.decrypt", side_effect=["key", "secret"]),
            patch("app.providers.kis_provider.get_access_token", side_effect=_fake_get_access_token),
            patch(
                "app.providers.kis_provider.get_domestic_balance",
                side_effect=_fake_get_domestic_balance,
            ),
            patch(
                "app.providers.kis_provider.get_overseas_balance",
                new=AsyncMock(return_value=_empty_overseas()),
            ),
            patch("app.providers.kis_provider.get_usd_krw_rate", new=AsyncMock(return_value=1300.0)),
        ):
            result = await provider.sync(account, db=AsyncMock(), cache=mock_cache)

        assert result.total_value_krw == 1_100_000.0  # domestic total 1,000,000 + deposit 100,000
        assert token_calls == [False, True]
        assert domestic_calls["count"] == 2

    @pytest.mark.asyncio
    async def test_sync_missing_credentials_raises(self, override_settings, make_account, mock_cache):
        account = make_account(data_source="KIS_API", kis_app_key=None, kis_app_secret=None)
        provider = KISProvider()

        with pytest.raises(ProviderCredentialError):
            await provider.sync(account, db=AsyncMock(), cache=mock_cache)

    @pytest.mark.asyncio
    async def test_sync_overseas_position_name_replaced_with_english_canonical(
        self, override_settings, make_account, mock_cache
    ):
        """해외 포지션의 브로커 원본(한글) 종목명이 영문 캐노니컬 이름으로 교체되어야 한다."""
        account = make_account(data_source="KIS_API", kis_app_key=b"enc_key", kis_app_secret=b"enc_secret")
        provider = KISProvider()

        with (
            patch("app.providers.kis_provider.decrypt", side_effect=["key", "secret"]),
            patch("app.providers.kis_provider.get_access_token", new=AsyncMock(return_value="token-1")),
            patch(
                "app.providers.kis_provider.get_domestic_balance",
                new=AsyncMock(return_value=_domestic_balance()),
            ),
            patch(
                "app.providers.kis_provider.get_overseas_balance",
                new=AsyncMock(return_value=_overseas_balance()),
            ),
            patch("app.providers.kis_provider.get_usd_krw_rate", new=AsyncMock(return_value=1300.0)),
            patch(
                "app.providers._overseas_name_enrichment.resolve_ticker_meta",
                new=AsyncMock(return_value=("Apple Inc.", "NASDAQ")),
            ),
        ):
            result = await provider.sync(account, db=AsyncMock(), cache=mock_cache)

        aapl = next(p for p in result.positions if p.ticker == "AAPL")
        assert aapl.name == "Apple Inc."
        assert aapl.market == "NASDAQ"  # KIS가 확정한 시장은 그대로 유지
