"""tax_service.py 추가 단위 테스트 (해외 포지션 상세 + 미실현 손익)."""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


def _make_position(
    ticker="AAPL",
    market="NASDAQ",
    qty=10,
    avg_price=150_000.0,
    current_price=185_000.0,
    avg_price_usd=None,
    name=None,
    currency="USD",
):
    return SimpleNamespace(
        ticker=ticker,
        name=name or ticker,
        market=market,
        qty=qty,
        avg_price=avg_price,
        current_price=current_price,
        avg_price_usd=avg_price_usd,
        currency=currency,
    )


def _make_snap_acc(positions):
    snap = SimpleNamespace(id=uuid.uuid4(), position_items=positions)
    acc = SimpleNamespace(id=uuid.uuid4(), name="테스트 계좌")
    return snap, acc


class TestGetOverseasPositionsDetail:
    @pytest.mark.asyncio
    async def test_empty_rows_returns_empty_list(self, mock_db, override_settings):
        from app.services.tax_service import get_overseas_positions_detail

        mock_db.execute = AsyncMock(
            return_value=MagicMock(all=MagicMock(return_value=[]))
        )
        result = await get_overseas_positions_detail(uuid.uuid4(), mock_db)
        assert result == []

    @pytest.mark.asyncio
    async def test_domestic_market_positions_excluded(self, mock_db, override_settings):
        from app.services.tax_service import get_overseas_positions_detail

        pos = _make_position(ticker="005930", market="KOSPI")
        snap, acc = _make_snap_acc([pos])

        mock_db.execute = AsyncMock(
            return_value=MagicMock(all=MagicMock(return_value=[(snap, acc)]))
        )
        result = await get_overseas_positions_detail(uuid.uuid4(), mock_db)
        assert result == []

    @pytest.mark.asyncio
    async def test_overseas_position_returns_pnl(self, mock_db, override_settings):
        from app.services.tax_service import get_overseas_positions_detail

        pos = _make_position(avg_price=100_000.0, current_price=150_000.0, qty=10)
        snap, acc = _make_snap_acc([pos])

        mock_db.execute = AsyncMock(
            return_value=MagicMock(all=MagicMock(return_value=[(snap, acc)]))
        )
        result = await get_overseas_positions_detail(uuid.uuid4(), mock_db)

        assert len(result) == 1
        p = result[0]
        assert p["ticker"] == "AAPL"
        assert p["unrealized_pnl_krw"] == pytest.approx(500_000.0)
        assert p["unrealized_pnl_pct"] == pytest.approx(50.0)

    @pytest.mark.asyncio
    async def test_position_with_loss_has_negative_pnl(self, mock_db, override_settings):
        from app.services.tax_service import get_overseas_positions_detail

        pos = _make_position(avg_price=200_000.0, current_price=150_000.0, qty=5)
        snap, acc = _make_snap_acc([pos])

        mock_db.execute = AsyncMock(
            return_value=MagicMock(all=MagicMock(return_value=[(snap, acc)]))
        )
        result = await get_overseas_positions_detail(uuid.uuid4(), mock_db)

        assert len(result) == 1
        assert result[0]["unrealized_pnl_krw"] < 0

    @pytest.mark.asyncio
    async def test_avg_price_usd_included_when_present(self, mock_db, override_settings):
        from app.services.tax_service import get_overseas_positions_detail

        pos = _make_position(avg_price_usd=100.0)
        snap, acc = _make_snap_acc([pos])

        mock_db.execute = AsyncMock(
            return_value=MagicMock(all=MagicMock(return_value=[(snap, acc)]))
        )
        result = await get_overseas_positions_detail(uuid.uuid4(), mock_db)

        assert result[0]["avg_price_usd"] == 100.0


class TestCalcStockUnrealized:
    @pytest.mark.asyncio
    async def test_empty_rows_returns_zero_tuple(self, mock_db, override_settings):
        from app.services.tax_service import _calc_stock_unrealized

        mock_db.execute = AsyncMock(
            return_value=MagicMock(all=MagicMock(return_value=[]))
        )
        overseas, domestic = await _calc_stock_unrealized(uuid.uuid4(), mock_db)
        assert overseas == 0.0
        assert domestic == 0.0

    @pytest.mark.asyncio
    async def test_overseas_position_unrealized_gain(self, mock_db, override_settings):
        from app.services.tax_service import _calc_stock_unrealized

        pos = _make_position(
            market="NASDAQ", avg_price=100_000.0, current_price=150_000.0, qty=10
        )
        snap = SimpleNamespace(id=uuid.uuid4(), position_items=[pos])
        acc = SimpleNamespace(id=uuid.uuid4())

        mock_db.execute = AsyncMock(
            return_value=MagicMock(all=MagicMock(return_value=[(snap, acc)]))
        )
        overseas, domestic = await _calc_stock_unrealized(uuid.uuid4(), mock_db)

        # overseas = 150_000 * 10 - 100_000 * 10 = 500_000
        assert overseas == pytest.approx(500_000.0)
        assert domestic == 0.0

    @pytest.mark.asyncio
    async def test_domestic_position_value(self, mock_db, override_settings):
        from app.services.tax_service import _calc_stock_unrealized

        pos = _make_position(
            ticker="005930", market="KOSPI", avg_price=60_000.0, current_price=70_000.0, qty=100
        )
        snap = SimpleNamespace(id=uuid.uuid4(), position_items=[pos])
        acc = SimpleNamespace(id=uuid.uuid4())

        mock_db.execute = AsyncMock(
            return_value=MagicMock(all=MagicMock(return_value=[(snap, acc)]))
        )
        overseas, domestic = await _calc_stock_unrealized(uuid.uuid4(), mock_db)

        assert overseas == 0.0
        assert domestic == pytest.approx(7_000_000.0)  # 70_000 * 100

    @pytest.mark.asyncio
    async def test_mixed_positions(self, mock_db, override_settings):
        from app.services.tax_service import _calc_stock_unrealized

        pos_overseas = _make_position(
            market="NASDAQ", avg_price=100_000.0, current_price=120_000.0, qty=5
        )
        pos_domestic = _make_position(
            ticker="005930", market="KOSPI",
            avg_price=60_000.0, current_price=70_000.0, qty=10
        )
        snap = SimpleNamespace(id=uuid.uuid4(), position_items=[pos_overseas, pos_domestic])
        acc = SimpleNamespace(id=uuid.uuid4())

        mock_db.execute = AsyncMock(
            return_value=MagicMock(all=MagicMock(return_value=[(snap, acc)]))
        )
        overseas, domestic = await _calc_stock_unrealized(uuid.uuid4(), mock_db)

        assert overseas == pytest.approx(100_000.0)  # (120k-100k)*5
        assert domestic == pytest.approx(700_000.0)  # 70k*10
