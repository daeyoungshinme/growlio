"""asset_service.py 추가 단위 테스트 — sync_account, get_provider."""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_account(data_source="KIS_API", user_id=None):
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id or uuid.uuid4(),
        name="테스트",
        asset_type="STOCK_KIS",
        data_source=data_source,
        is_active=True,
        is_mock_mode=True,
        deposit_krw=None,
        deposit_usd=None,
        kis_app_key=None,
        kis_app_secret=None,
    )


class TestGetProvider:
    def test_kis_api_returns_kis_provider(self, override_settings):
        from app.services.asset_service import get_provider
        from app.providers.kis_provider import KISProvider

        account = _make_account("KIS_API")
        provider = get_provider(account)
        assert isinstance(provider, KISProvider)

    def test_kiwoom_api_returns_kiwoom_provider(self, override_settings):
        from app.services.asset_service import get_provider
        from app.providers.kiwoom_provider import KiwoomProvider

        account = _make_account("KIWOOM_API")
        provider = get_provider(account)
        assert isinstance(provider, KiwoomProvider)

    def test_manual_returns_manual_provider(self, override_settings):
        from app.services.asset_service import get_provider
        from app.providers.manual_provider import ManualProvider

        account = _make_account("MANUAL")
        provider = get_provider(account)
        assert isinstance(provider, ManualProvider)

    def test_open_banking_returns_ob_provider(self, override_settings):
        from app.services.asset_service import get_provider
        from app.providers.openbanking_provider import OpenBankingProvider

        account = _make_account("OPEN_BANKING")
        provider = get_provider(account)
        assert isinstance(provider, OpenBankingProvider)

    def test_unknown_raises_credential_error(self, override_settings):
        from app.services.asset_service import get_provider
        from app.exceptions import ProviderCredentialError

        account = _make_account("UNKNOWN_SOURCE")
        with pytest.raises(ProviderCredentialError):
            get_provider(account)


class TestSyncAccount:
    @pytest.mark.asyncio
    async def test_sync_account_calls_provider_and_returns_snapshot(
        self, mock_db, override_settings
    ):
        from app.services.asset_service import sync_account
        from app.providers.base import BalanceResult

        account = _make_account("MANUAL")

        balance = BalanceResult(
            total_value_krw=10_000_000.0,
            positions=[],
        )

        mock_provider = AsyncMock()
        mock_provider.sync = AsyncMock(return_value=balance)

        fake_snapshot = SimpleNamespace(id=uuid.uuid4())

        with (
            patch("app.services.asset_service.get_provider", return_value=mock_provider),
            patch("app.services.asset_service._upsert_snapshot", new=AsyncMock(return_value=fake_snapshot)),
            patch("app.services.asset_service.invalidate_account_caches", new=AsyncMock()),
            patch("app.services.asset_service.broker_sync_duration"),
        ):
            result = await sync_account(account, mock_db, redis=MagicMock())

        assert result is fake_snapshot
        mock_provider.sync.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_account_updates_deposit_krw(self, mock_db, override_settings):
        from app.services.asset_service import sync_account
        from app.providers.base import BalanceResult

        account = _make_account("MANUAL")

        balance = BalanceResult(
            total_value_krw=5_000_000.0,
            deposit_krw=1_000_000.0,
            positions=[],
        )

        mock_provider = AsyncMock()
        mock_provider.sync = AsyncMock(return_value=balance)
        fake_snapshot = SimpleNamespace(id=uuid.uuid4())

        with (
            patch("app.services.asset_service.get_provider", return_value=mock_provider),
            patch("app.services.asset_service._upsert_snapshot", new=AsyncMock(return_value=fake_snapshot)),
            patch("app.services.asset_service.invalidate_account_caches", new=AsyncMock()),
            patch("app.services.asset_service.broker_sync_duration"),
        ):
            await sync_account(account, mock_db, redis=MagicMock())

        assert account.deposit_krw == 1_000_000.0

    @pytest.mark.asyncio
    async def test_sync_account_updates_deposit_usd_from_foreign(self, mock_db, override_settings):
        """deposit_foreign 있으면 account.deposit_usd에 반영 (line 99)."""
        from app.services.asset_service import sync_account
        from app.providers.base import BalanceResult

        account = _make_account("MANUAL")

        balance = BalanceResult(
            total_value_krw=5_000_000.0,
            deposit_foreign=500.0,
            positions=[],
        )

        mock_provider = AsyncMock()
        mock_provider.sync = AsyncMock(return_value=balance)
        fake_snapshot = SimpleNamespace(id=uuid.uuid4())

        with (
            patch("app.services.asset_service.get_provider", return_value=mock_provider),
            patch("app.services.asset_service._upsert_snapshot", new=AsyncMock(return_value=fake_snapshot)),
            patch("app.services.asset_service.invalidate_account_caches", new=AsyncMock()),
            patch("app.services.asset_service.broker_sync_duration"),
        ):
            await sync_account(account, mock_db, redis=MagicMock())

        assert account.deposit_usd == 500.0

    @pytest.mark.asyncio
    async def test_sync_account_with_positions_deletes_old_positions(
        self, mock_db, override_settings
    ):
        from app.services.asset_service import sync_account
        from app.providers.base import BalanceResult, Position

        account = _make_account("MANUAL")

        pos = Position(
            ticker="AAPL",
            name="Apple",
            market="NASDAQ",
            qty=10,
            avg_price=150_000.0,
            current_price=185_000.0,
            currency="USD",
            value_krw=1_850_000.0,
        )
        balance = BalanceResult(
            total_value_krw=1_850_000.0,
            positions=[pos],
        )

        mock_provider = AsyncMock()
        mock_provider.sync = AsyncMock(return_value=balance)
        fake_snapshot = SimpleNamespace(id=uuid.uuid4())

        with (
            patch("app.services.asset_service.get_provider", return_value=mock_provider),
            patch("app.services.asset_service._upsert_snapshot", new=AsyncMock(return_value=fake_snapshot)),
            patch("app.services.asset_service.sync_snapshot_positions", new=AsyncMock()),
            patch("app.services.asset_service.invalidate_account_caches", new=AsyncMock()),
            patch("app.services.asset_service.broker_sync_duration"),
        ):
            await sync_account(account, mock_db, redis=MagicMock())

        # db.execute was called for delete operation
        mock_db.execute.assert_called()
