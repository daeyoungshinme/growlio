"""services/rebalancing/broker_balance_service.py 단위 테스트."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.providers.base import BalanceResult, Position
from app.services.rebalancing.broker_balance_service import fetch_broker_balance


def _position(**overrides):
    defaults = dict(
        ticker="005930",
        name="삼성전자",
        market="KOSPI",
        qty=10,
        avg_price=70000.0,
        current_price=75000.0,
        currency="KRW",
        value_krw=750000.0,
    )
    defaults.update(overrides)
    return Position(**defaults)


def _patch_session(mock_db):
    """fetch_broker_balance가 여는 AsyncSessionLocal()을 mock_db로 대체."""
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=None)
    return patch("app.services.rebalancing.broker_balance_service.AsyncSessionLocal", return_value=mock_db)


class TestFetchBrokerBalance:
    @pytest.mark.asyncio
    async def test_unsupported_asset_type_raises(self, make_account, mock_cache):
        account = make_account(asset_type="BANK_ACCOUNT")

        with pytest.raises(ValueError, match="지원하지 않는 계좌 유형"):
            await fetch_broker_balance(account, mock_cache)

    @pytest.mark.asyncio
    async def test_kis_account_fetches_orderable_cash_when_credentials_present(self, make_account, mock_db, mock_cache):
        account = make_account(
            asset_type="STOCK_KIS",
            data_source="KIS_API",
            kis_app_key=b"enc_key",
            kis_app_secret=b"enc_secret",
            kis_account_no="12345678-01",
        )
        balance = BalanceResult(positions=[_position()], deposit_krw=100_000.0)

        with (
            _patch_session(mock_db),
            patch("app.services.rebalancing.broker_balance_service.KISProvider") as mock_provider_cls,
            patch(
                "app.services.rebalancing.broker_balance_service.decrypt_kis_credentials",
                return_value=("app_key", "app_secret"),
            ),
            patch(
                "app.services.rebalancing.broker_balance_service.get_access_token",
                new=AsyncMock(return_value="token"),
            ),
            patch(
                "app.services.rebalancing.broker_balance_service.get_orderable_cash",
                new=AsyncMock(return_value=250_000.0),
            ) as mock_orderable,
        ):
            mock_provider_cls.return_value.sync = AsyncMock(return_value=balance)

            result = await fetch_broker_balance(account, mock_cache)

        mock_orderable.assert_awaited_once()
        assert result.orderable_krw == 250_000.0
        assert result.deposit_krw == 100_000.0
        assert len(result.positions) == 1
        assert result.positions[0].ticker == "005930"

    @pytest.mark.asyncio
    async def test_kis_account_without_credentials_skips_orderable_cash(self, make_account, mock_db, mock_cache):
        account = make_account(
            asset_type="STOCK_KIS",
            data_source="KIS_API",
            kis_app_key=None,
            kis_app_secret=None,
        )
        balance = BalanceResult(positions=[], deposit_krw=0.0)

        with (
            _patch_session(mock_db),
            patch("app.services.rebalancing.broker_balance_service.KISProvider") as mock_provider_cls,
        ):
            mock_provider_cls.return_value.sync = AsyncMock(return_value=balance)
            result = await fetch_broker_balance(account, mock_cache)

        assert result.orderable_krw is None

    @pytest.mark.asyncio
    async def test_orderable_cash_fetch_failure_returns_none_without_raising(self, make_account, mock_db, mock_cache):
        account = make_account(
            asset_type="STOCK_KIS",
            data_source="KIS_API",
            kis_app_key=b"enc_key",
            kis_app_secret=b"enc_secret",
            kis_account_no="12345678-01",
        )
        balance = BalanceResult(positions=[], deposit_krw=0.0)

        with (
            _patch_session(mock_db),
            patch("app.services.rebalancing.broker_balance_service.KISProvider") as mock_provider_cls,
            patch(
                "app.services.rebalancing.broker_balance_service.decrypt_kis_credentials",
                return_value=("app_key", "app_secret"),
            ),
            patch(
                "app.services.rebalancing.broker_balance_service.get_access_token",
                new=AsyncMock(side_effect=RuntimeError("token refresh failed")),
            ),
        ):
            mock_provider_cls.return_value.sync = AsyncMock(return_value=balance)
            result = await fetch_broker_balance(account, mock_cache)

        assert result.orderable_krw is None

    @pytest.mark.asyncio
    async def test_toss_account_uses_deposit_krw_as_orderable_cash(self, make_account, mock_db, mock_cache):
        account = make_account(
            asset_type="STOCK_TOSS",
            data_source="TOSS_API",
            toss_client_id=b"enc_id",
            toss_client_secret=b"enc_secret",
        )
        balance = BalanceResult(
            positions=[_position(ticker="AAPL", name="Apple", market="NASDAQ", currency="USD")],
            deposit_krw=123_456.0,
        )

        with (
            _patch_session(mock_db),
            patch("app.services.rebalancing.broker_balance_service.TossProvider") as mock_provider_cls,
        ):
            mock_provider_cls.return_value.sync = AsyncMock(return_value=balance)
            result = await fetch_broker_balance(account, mock_cache)

        # 토스는 별도 orderable-cash API가 없어 sync의 deposit_krw(=cashBuyingPower)를 그대로 쓴다
        assert result.orderable_krw == 123_456.0
        assert result.deposit_krw == 123_456.0
        assert result.positions[0].ticker == "AAPL"

    @pytest.mark.asyncio
    async def test_kiwoom_account_never_fetches_orderable_cash(self, make_account, mock_db, mock_cache):
        account = make_account(
            asset_type="STOCK_KIWOOM",
            data_source="KIWOOM_API",
            kiwoom_app_key=b"enc_key",
            kiwoom_app_secret=b"enc_secret",
        )
        balance = BalanceResult(positions=[_position(ticker="000660", name="SK하이닉스")], deposit_krw=50_000.0)

        with (
            _patch_session(mock_db),
            patch("app.services.rebalancing.broker_balance_service.KiwoomProvider") as mock_provider_cls,
        ):
            mock_provider_cls.return_value.sync = AsyncMock(return_value=balance)
            result = await fetch_broker_balance(account, mock_cache)

        assert result.orderable_krw is None
        assert result.deposit_krw == 50_000.0
        assert result.positions[0].ticker == "000660"
