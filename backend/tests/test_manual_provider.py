"""providers/manual_provider.py 단위 테스트."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.providers.manual_provider import ManualProvider, _db_to_provider_position


def _make_db_position(**kwargs):
    import uuid
    defaults = dict(
        id=uuid.uuid4(),
        account_id=uuid.uuid4(),
        snapshot_id=None,
        ticker="005930",
        name="삼성전자",
        market="KOSPI",
        qty=10.0,
        avg_price=70000.0,
        current_price=75000.0,
        value_krw=750000.0,
        currency="KRW",
        avg_price_usd=None,
        usd_rate=None,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _make_mock_db(positions=None):
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = positions or []
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    db.add = MagicMock()
    return db


class TestDbToProviderPosition:
    def test_converts_krw_position(self):
        p = _make_db_position()
        pos = _db_to_provider_position(p)
        assert pos.ticker == "005930"
        assert pos.qty == 10
        assert pos.avg_price == 70000.0
        assert pos.current_price == 75000.0
        assert pos.currency == "KRW"
        assert pos.avg_price_usd is None

    def test_converts_usd_position(self):
        p = _make_db_position(
            ticker="AAPL", market="NASDAQ",
            avg_price=150000.0, avg_price_usd=100.0, usd_rate=1350.0,
        )
        pos = _db_to_provider_position(p)
        assert pos.avg_price_usd == pytest.approx(100.0)
        assert pos.usd_rate == pytest.approx(1350.0)

    def test_falls_back_to_avg_price_when_no_current(self):
        p = _make_db_position(current_price=None, avg_price=70000.0)
        pos = _db_to_provider_position(p)
        assert pos.current_price == pytest.approx(70000.0)

    def test_none_name_becomes_empty_string(self):
        p = _make_db_position(name=None)
        pos = _db_to_provider_position(p)
        assert pos.name == ""


class TestManualProviderSync:
    @pytest.mark.asyncio
    async def test_sync_with_no_positions_uses_manual_amount(self, override_settings, make_account):
        account = make_account(manual_amount=5_000_000.0, asset_type="STOCK_OTHER")
        db = _make_mock_db(positions=[])
        redis = AsyncMock()

        provider = ManualProvider()
        with patch("app.providers.manual_provider.fetch_usd_krw", AsyncMock(return_value=1350.0)):
            result = await provider.sync(account, db, redis)

        assert result.total_value_krw == pytest.approx(5_000_000.0)
        assert result.positions == []

    @pytest.mark.asyncio
    async def test_sync_with_positions_calculates_value(self, override_settings, make_account):
        account = make_account(asset_type="STOCK_OTHER")
        pos = _make_db_position(qty=10.0, avg_price=70000.0, current_price=75000.0)
        db = _make_mock_db(positions=[pos])
        redis = AsyncMock()

        provider = ManualProvider()
        with (
            patch("app.providers.manual_provider.fetch_usd_krw", AsyncMock(return_value=1350.0)),
            patch("app.providers.manual_provider.ManualProvider.sync") as mock_sync,
        ):
            from app.providers.base import BalanceResult
            mock_sync.return_value = BalanceResult(
                positions=[],
                total_value_krw=750000.0,
                deposit_krw=0.0,
                invested_krw=700000.0,
                pnl_krw=50000.0,
            )
            result = await provider.sync(account, db, redis)
        assert result.total_value_krw == pytest.approx(750000.0)

    @pytest.mark.asyncio
    async def test_sync_raises_when_no_amount_and_no_positions(self, override_settings, make_account):
        from app.exceptions import BadRequestError
        account = make_account(manual_amount=0.0, asset_type="STOCK_OTHER")
        db = _make_mock_db(positions=[])
        redis = AsyncMock()

        provider = ManualProvider()
        with (
            patch("app.providers.manual_provider.fetch_usd_krw", AsyncMock(return_value=1350.0)),
            pytest.raises(BadRequestError),
        ):
            await provider.sync(account, db, redis)

    @pytest.mark.asyncio
    async def test_sync_real_estate_subtracts_mortgage(self, override_settings, make_account):
        account = make_account(
            asset_type="REAL_ESTATE",
            manual_amount=500_000_000.0,
            real_estate_details={"mortgage_balance_krw": 100_000_000},
        )
        db = _make_mock_db(positions=[])
        redis = AsyncMock()

        provider = ManualProvider()
        with patch("app.providers.manual_provider.fetch_usd_krw", AsyncMock(return_value=1350.0)):
            result = await provider.sync(account, db, redis)

        assert result.total_value_krw == pytest.approx(400_000_000.0)

    @pytest.mark.asyncio
    async def test_sync_fetches_prices_when_positions_and_redis(self, override_settings, make_account):
        """redis 비-None + 포지션 있을 때 가격 조회 경로 (lines 33-54)."""
        account = make_account(asset_type="STOCK_OTHER")
        pos = _make_db_position(
            ticker="005930", market="KOSPI", qty=10.0, avg_price=70000.0, current_price=70000.0
        )
        db = _make_mock_db(positions=[pos])
        redis = AsyncMock()

        provider = ManualProvider()
        with (
            patch("app.services.price_service.fetch_prices_batch",
                  AsyncMock(return_value={"005930": 75000.0})),
            patch("app.providers.manual_provider.fetch_usd_krw", AsyncMock(return_value=1350.0)),
        ):
            result = await provider.sync(account, db, redis)

        assert pos.current_price == pytest.approx(75000.0)
        assert result.total_value_krw == pytest.approx(750000.0)

    @pytest.mark.asyncio
    async def test_sync_overseas_position_applies_usd_rate(self, override_settings, make_account):
        """해외 종목 USD 환율 적용 경로 (lines 40-48 — has_overseas branch)."""
        account = make_account(asset_type="STOCK_OTHER")
        pos = _make_db_position(
            ticker="AAPL", market="NASDAQ", qty=5.0, avg_price=200000.0, current_price=200000.0
        )
        db = _make_mock_db(positions=[pos])
        redis = AsyncMock()

        provider = ManualProvider()
        with (
            patch("app.services.price_service.fetch_prices_batch",
                  AsyncMock(return_value={"AAPL": 210.0})),
            patch("app.providers.manual_provider.fetch_usd_krw", AsyncMock(return_value=1350.0)),
        ):
            await provider.sync(account, db, redis)

        assert pos.current_price == pytest.approx(210.0 * 1350.0)

    @pytest.mark.asyncio
    async def test_real_estate_raises_when_gross_is_zero(self, override_settings, make_account):
        """부동산 시세 0 설정 시 BadRequestError (line 71)."""
        from app.exceptions import BadRequestError
        account = make_account(
            asset_type="REAL_ESTATE",
            manual_amount=0.0,
            real_estate_details={},
        )
        db = _make_mock_db(positions=[])
        redis = AsyncMock()

        provider = ManualProvider()
        with (
            patch("app.providers.manual_provider.fetch_usd_krw", AsyncMock(return_value=1350.0)),
            pytest.raises(BadRequestError, match="부동산 시세"),
        ):
            await provider.sync(account, db, redis)

    @pytest.mark.asyncio
    async def test_sync_with_deposit_krw_only(self, override_settings, make_account):
        """포지션 없고 deposit_krw만 있을 때 경로 (lines 73-74)."""
        account = make_account(
            asset_type="STOCK_OTHER",
            deposit_krw=1_000_000.0,
        )
        db = _make_mock_db(positions=[])
        redis = AsyncMock()

        provider = ManualProvider()
        with patch("app.providers.manual_provider.fetch_usd_krw", AsyncMock(return_value=1350.0)):
            result = await provider.sync(account, db, redis)

        assert result.total_value_krw == pytest.approx(1_000_000.0)

    @pytest.mark.asyncio
    async def test_sync_price_not_in_map_uses_fallback(self, override_settings, make_account):
        """가격 맵에 없는 종목은 기존 current_price 유지 (line 50 — else branch)."""
        account = make_account(asset_type="STOCK_OTHER")
        pos = _make_db_position(
            ticker="UNKNOWN", market="KOSPI", qty=10.0, avg_price=50000.0, current_price=50000.0
        )
        db = _make_mock_db(positions=[pos])
        redis = AsyncMock()

        provider = ManualProvider()
        with (
            patch("app.services.price_service.fetch_prices_batch", AsyncMock(return_value={})),
            patch("app.providers.manual_provider.fetch_usd_krw", AsyncMock(return_value=1350.0)),
        ):
            result = await provider.sync(account, db, redis)

        assert pos.current_price == pytest.approx(50000.0)  # Unchanged — fallback used
        assert result.total_value_krw == pytest.approx(500000.0)
