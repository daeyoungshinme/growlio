"""portfolio_optimizer.py 단위 테스트."""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.portfolio_optimizer import get_efficient_frontier

# ── get_efficient_frontier (DB mock) ──────────────────────


class TestGetEfficientFrontier:
    @pytest.mark.asyncio
    async def test_single_position_returns_not_enough(self, mock_db, override_settings):
        snap = SimpleNamespace(id=uuid.uuid4())
        acc = SimpleNamespace(id=uuid.uuid4(), is_active=True)
        pos = SimpleNamespace(ticker="005930", market="KOSPI", value_krw=1_000_000.0, snapshot_id=snap.id)

        snap_result = MagicMock()
        snap_result.all.return_value = [(snap, acc)]
        pos_result = MagicMock()
        pos_result.scalars.return_value.all.return_value = [pos]
        mock_db.execute = AsyncMock(side_effect=[snap_result, pos_result])

        result = await get_efficient_frontier(uuid.uuid4(), mock_db)

        assert result["frontier"] == []
        assert result["current"] is None

    @pytest.mark.asyncio
    async def test_no_positions_returns_empty(self, mock_db, override_settings):
        exec_result = MagicMock()
        exec_result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=exec_result)

        result = await get_efficient_frontier(uuid.uuid4(), mock_db)

        assert result["frontier"] == []
        assert "note" in result

    @pytest.mark.asyncio
    async def test_cache_cache_hit_skips_db(self, mock_db, override_settings):
        cached = {
            "frontier": [{"risk": 10.0, "return": 8.0}],
            "current": {"risk": 12.0, "return": 9.0},
            "assets": [],
            "note": "cached",
        }
        cache = AsyncMock()
        cache.get = AsyncMock(return_value=json.dumps(cached).encode())

        result = await get_efficient_frontier(uuid.uuid4(), mock_db, cache=cache)

        assert result["frontier"][0]["risk"] == 10.0
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_error_falls_back_to_db(self, mock_db, override_settings):
        cache = AsyncMock()
        cache.get = AsyncMock(side_effect=Exception("cache error"))

        exec_result = MagicMock()
        exec_result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=exec_result)

        result = await get_efficient_frontier(uuid.uuid4(), mock_db, cache=cache)
        assert result["frontier"] == []

    @pytest.mark.asyncio
    async def test_with_two_positions_calls_optimizer(self, mock_db, override_settings):
        snap = SimpleNamespace(id=uuid.uuid4())
        acc = SimpleNamespace(id=uuid.uuid4(), is_active=True)
        pos1 = SimpleNamespace(ticker="005930", market="KOSPI", value_krw=500_000.0, snapshot_id=snap.id)
        pos2 = SimpleNamespace(ticker="AAPL", market="NASDAQ", value_krw=500_000.0, snapshot_id=snap.id)

        snap_result = MagicMock()
        snap_result.all.return_value = [(snap, acc)]
        pos_result = MagicMock()
        pos_result.scalars.return_value.all.return_value = [pos1, pos2]
        mock_db.execute = AsyncMock(side_effect=[snap_result, pos_result])

        expected = {
            "frontier": [{"risk": 10.0, "return": 5.0}, {"risk": 15.0, "return": 10.0}],
            "current": {"risk": 12.0, "return": 7.0},
            "assets": [],
            "note": "1년 일별 수익률 기반 MVO (252일, 2종목)",
        }

        with patch("asyncio.get_running_loop") as mock_loop:
            # run_in_executor를 두 번 호출: returns_map 조회, _compute_frontier
            returns_map = {
                "005930.KS": [0.01] * 252,
                "AAPL": [0.008] * 252,
            }
            mock_loop.return_value.run_in_executor = AsyncMock(side_effect=[returns_map, expected])

            result = await get_efficient_frontier(uuid.uuid4(), mock_db)

        assert result["frontier"][0]["risk"] == 10.0
        assert result["current"] == {"risk": 12.0, "return": 7.0}

    @pytest.mark.asyncio
    async def test_cache_no_cache_write_when_no_positions(self, mock_db, override_settings):
        """포지션 없을 때 조기 반환되므로 Cache cache 쓰기 없음."""
        exec_result = MagicMock()
        exec_result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=exec_result)

        cache = AsyncMock()
        cache.get = AsyncMock(return_value=None)
        cache.setex = AsyncMock()

        await get_efficient_frontier(uuid.uuid4(), mock_db, cache=cache)
        cache.setex.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_cache_write_on_success(self, mock_db, override_settings):
        """2종목 이상 포지션 있을 때 결과를 Cache에 캐시 저장한다."""
        snap = SimpleNamespace(id=uuid.uuid4())
        acc = SimpleNamespace(id=uuid.uuid4(), is_active=True)
        pos1 = SimpleNamespace(ticker="005930", market="KOSPI", value_krw=500_000.0, snapshot_id=snap.id)
        pos2 = SimpleNamespace(ticker="AAPL", market="NASDAQ", value_krw=500_000.0, snapshot_id=snap.id)

        snap_result = MagicMock()
        snap_result.all.return_value = [(snap, acc)]
        pos_result = MagicMock()
        pos_result.scalars.return_value.all.return_value = [pos1, pos2]
        mock_db.execute = AsyncMock(side_effect=[snap_result, pos_result])

        cache = AsyncMock()
        cache.get = AsyncMock(return_value=None)
        cache.setex = AsyncMock()

        frontier_result = {"frontier": [{"risk": 10.0, "return": 5.0}], "current": None, "assets": [], "note": "ok"}
        returns_map: dict = {"005930.KS": [0.01] * 252, "AAPL": [0.008] * 252}
        with patch("asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(side_effect=[returns_map, frontier_result])
            await get_efficient_frontier(uuid.uuid4(), mock_db, cache=cache)

        cache.setex.assert_called_once()


# ── _compute_frontier 순수 로직 (numpy/scipy 직접 호출) ──


class TestComputeFrontierLogic:
    def test_insufficient_data_returns_note(self, override_settings):
        from app.services.portfolio_optimizer import _compute_frontier

        result = _compute_frontier(
            symbols=["A", "B"],
            weights=[0.5, 0.5],
            returns_map={"A": [0.01] * 10, "B": [0.01] * 10},  # 10일 < _MIN_RETURN_DAYS(30)
        )
        assert result["frontier"] == []
        assert result["current"] is None
        assert "note" in result

    def test_single_valid_symbol_not_enough(self, override_settings):
        from app.services.portfolio_optimizer import _compute_frontier

        result = _compute_frontier(
            symbols=["A", "B"],
            weights=[0.5, 0.5],
            returns_map={"A": [0.01] * 252},  # B 없음 → valid_pairs < 2
        )
        assert result["frontier"] == []

    def test_with_valid_data_produces_frontier(self, override_settings):
        """실제 scipy로 최소 2종목 효율적 프론티어 계산."""
        import random

        random.seed(42)
        from app.services.portfolio_optimizer import _compute_frontier

        r1 = [random.gauss(0.001, 0.01) for _ in range(252)]
        r2 = [random.gauss(0.0008, 0.015) for _ in range(252)]

        result = _compute_frontier(
            symbols=["A", "B"],
            weights=[0.6, 0.4],
            returns_map={"A": r1, "B": r2},
        )

        assert len(result["frontier"]) > 0
        assert result["current"] is not None
        assert result["current"]["risk"] > 0
        assert all(p["risk"] > 0 for p in result["frontier"])
        assert len(result["assets"]) == 2
