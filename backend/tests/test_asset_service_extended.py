"""asset_service.py 추가 단위 테스트 — sync_account, get_provider."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestGetProvider:
    def test_kis_api_returns_kis_provider(self, override_settings, make_account):
        from app.providers.kis_provider import KISProvider
        from app.services.asset_service import get_provider

        account = make_account(data_source="KIS_API")
        provider = get_provider(account)
        assert isinstance(provider, KISProvider)

    def test_kiwoom_api_returns_kiwoom_provider(self, override_settings, make_account):
        from app.providers.kiwoom_provider import KiwoomProvider
        from app.services.asset_service import get_provider

        account = make_account(data_source="KIWOOM_API")
        provider = get_provider(account)
        assert isinstance(provider, KiwoomProvider)

    def test_manual_returns_manual_provider(self, override_settings, make_account):
        from app.providers.manual_provider import ManualProvider
        from app.services.asset_service import get_provider

        account = make_account(data_source="MANUAL")
        provider = get_provider(account)
        assert isinstance(provider, ManualProvider)

    def test_unknown_raises_credential_error(self, override_settings, make_account):
        from app.exceptions import ProviderCredentialError
        from app.services.asset_service import get_provider

        account = make_account(data_source="UNKNOWN_SOURCE")
        with pytest.raises(ProviderCredentialError):
            get_provider(account)


class TestSyncAccount:
    @pytest.mark.asyncio
    async def test_sync_account_calls_provider_and_returns_snapshot(self, mock_db, override_settings, make_account):
        from app.providers.base import BalanceResult
        from app.services.asset_service import sync_account

        account = make_account(data_source="MANUAL")

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
            result = await sync_account(account, mock_db, cache=MagicMock())

        assert result is fake_snapshot
        mock_provider.sync.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_account_updates_deposit_krw(self, mock_db, override_settings, make_account):
        from app.providers.base import BalanceResult
        from app.services.asset_service import sync_account

        account = make_account(data_source="MANUAL")

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
            await sync_account(account, mock_db, cache=MagicMock())

        assert account.deposit_krw == 1_000_000.0

    @pytest.mark.asyncio
    async def test_sync_account_updates_deposit_usd_from_foreign(self, mock_db, override_settings, make_account):
        """deposit_foreign 있으면 account.deposit_usd에 반영 (line 99)."""
        from app.providers.base import BalanceResult
        from app.services.asset_service import sync_account

        account = make_account(data_source="MANUAL")

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
            await sync_account(account, mock_db, cache=MagicMock())

        assert account.deposit_usd == 500.0

    @pytest.mark.asyncio
    async def test_sync_account_deposit_foreign_none_preserves_existing_usd(
        self, mock_db, override_settings, make_account
    ):
        """deposit_foreign=None(해외 조회 실패/미조회) → 기존 account.deposit_usd 유지."""
        from app.providers.base import BalanceResult
        from app.services.asset_service import sync_account

        account = make_account(data_source="KIWOOM_API")
        account.deposit_usd = 777.0

        balance = BalanceResult(total_value_krw=5_000_000.0, deposit_foreign=None, positions=[])
        mock_provider = AsyncMock()
        mock_provider.sync = AsyncMock(return_value=balance)

        with (
            patch("app.services.asset_service.get_provider", return_value=mock_provider),
            patch("app.services.asset_service._CIRCUITS", {}),
            patch(
                "app.services.asset_service._upsert_snapshot",
                new=AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4())),
            ),
            patch("app.services.asset_service.invalidate_account_caches", new=AsyncMock()),
            patch("app.services.asset_service.broker_sync_duration"),
        ):
            await sync_account(account, mock_db, cache=MagicMock())

        assert account.deposit_usd == 777.0

    @pytest.mark.asyncio
    async def test_sync_account_deposit_foreign_zero_clears_stale_usd(self, mock_db, override_settings, make_account):
        """deposit_foreign=0.0(확정값) → stale account.deposit_usd를 0으로 갱신."""
        from app.providers.base import BalanceResult
        from app.services.asset_service import sync_account

        account = make_account(data_source="KIWOOM_API")
        account.deposit_usd = 777.0

        balance = BalanceResult(total_value_krw=5_000_000.0, deposit_foreign=0.0, positions=[])
        mock_provider = AsyncMock()
        mock_provider.sync = AsyncMock(return_value=balance)

        with (
            patch("app.services.asset_service.get_provider", return_value=mock_provider),
            patch("app.services.asset_service._CIRCUITS", {}),
            patch(
                "app.services.asset_service._upsert_snapshot",
                new=AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4())),
            ),
            patch("app.services.asset_service.invalidate_account_caches", new=AsyncMock()),
            patch("app.services.asset_service.broker_sync_duration"),
        ):
            await sync_account(account, mock_db, cache=MagicMock())

        assert account.deposit_usd == 0.0

    @pytest.mark.asyncio
    async def test_sync_account_with_positions_deletes_old_positions(self, mock_db, override_settings, make_account):
        from app.providers.base import BalanceResult, Position
        from app.services.asset_service import sync_account

        account = make_account(data_source="MANUAL")

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
            await sync_account(account, mock_db, cache=MagicMock())

        # db.execute was called for delete operation
        mock_db.execute.assert_called()


class TestSyncAccountNow:
    @pytest.mark.asyncio
    async def test_uses_own_short_lived_session_and_merges_account(self, mock_db, override_settings, make_account):
        """요청 세션이 아닌 AsyncSessionLocal()로 연 별도 세션을 사용하고, account를 merge해야 한다
        (커넥션 풀 슬롯을 브로커 HTTP 호출 동안 오래 붙잡지 않기 위한 구조 — QueuePool 고갈 수정)."""
        from app.services.asset_service import sync_account_now

        account = make_account(data_source="MANUAL")
        fake_snapshot = SimpleNamespace(id=uuid.uuid4(), snapshot_date="2026-09-12", amount_krw=1_000_000.0)

        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=None)
        mock_db.merge = AsyncMock(return_value=account)

        cache = MagicMock()
        with (
            patch("app.services.asset_service.AsyncSessionLocal", return_value=mock_db),
            patch("app.services.asset_service.sync_account", new=AsyncMock(return_value=fake_snapshot)) as mock_sync,
            patch("app.services.asset_service.invalidate_asset_account_caches", new=AsyncMock()) as mock_invalidate,
        ):
            result = await sync_account_now(account, account.user_id, cache=cache)

        mock_db.merge.assert_awaited_once_with(account)
        mock_sync.assert_awaited_once_with(account, mock_db, cache)
        mock_invalidate.assert_awaited_once()
        assert result == {
            "detail": "동기화 완료",
            "snapshot_date": "2026-09-12",
            "amount_krw": 1_000_000.0,
        }
