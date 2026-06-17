"""insight_service.py 단위 테스트."""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── _check_concentration ──────────────────────────────────────

class TestCheckConcentration:
    @pytest.mark.asyncio
    async def test_empty_dashboard_returns_empty(self, override_settings):
        from app.services.insight_service import _check_concentration
        result = await _check_concentration({})
        assert result == []

    @pytest.mark.asyncio
    async def test_no_allocation_returns_empty(self, override_settings):
        from app.services.insight_service import _check_concentration
        result = await _check_concentration({"total_assets_krw": 1_000_000, "asset_allocation": []})
        assert result == []

    @pytest.mark.asyncio
    async def test_under_30_pct_returns_empty(self, override_settings):
        from app.services.insight_service import _check_concentration
        dashboard = {
            "total_assets_krw": 1_000_000,
            "asset_allocation": [{"type": "STOCK_KIS", "pct": 25.0}],
        }
        result = await _check_concentration(dashboard)
        assert result == []

    @pytest.mark.asyncio
    async def test_over_30_returns_warning(self, override_settings):
        from app.services.insight_service import _check_concentration
        dashboard = {
            "total_assets_krw": 1_000_000,
            "asset_allocation": [{"type": "STOCK_KIS", "pct": 35.0}],
        }
        result = await _check_concentration(dashboard)
        assert len(result) == 1
        assert result[0].severity == "WARNING"

    @pytest.mark.asyncio
    async def test_over_40_returns_alert(self, override_settings):
        from app.services.insight_service import _check_concentration
        dashboard = {
            "total_assets_krw": 1_000_000,
            "asset_allocation": [{"type": "STOCK_KIS", "pct": 50.0}],
        }
        result = await _check_concentration(dashboard)
        assert len(result) == 1
        assert result[0].severity == "ALERT"


# ── _check_rebalancing_opportunity ───────────────────────────

class TestCheckRebalancingOpportunity:
    @pytest.mark.asyncio
    async def test_no_portfolios_returns_empty(self, mock_db, override_settings):
        from app.services.insight_service import _check_rebalancing_opportunity

        exec_result = MagicMock()
        exec_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=exec_result)

        result = await _check_rebalancing_opportunity(uuid.uuid4(), mock_db)
        assert result == []

    @pytest.mark.asyncio
    async def test_portfolio_with_no_drift_returns_empty(self, mock_db, override_settings):
        from app.services.insight_service import _check_rebalancing_opportunity

        portfolio = SimpleNamespace(
            id=uuid.uuid4(),
            name="테스트",
            base_type="STOCK_ONLY",
            items=[SimpleNamespace(ticker="AAPL", market="NASDAQ", weight=100.0)],
            account_ids=None,
        )
        exec_result = MagicMock()
        exec_result.scalars.return_value.all.return_value = [portfolio]
        mock_db.execute = AsyncMock(return_value=exec_result)

        overview = {
            "total_stock_krw": 1_000_000,
            "all_positions": [
                {"ticker": "AAPL", "market": "NASDAQ", "value_krw": 1_000_000},
            ],
        }
        with patch("app.services.portfolio_service.build_portfolio_overview",
                   new=AsyncMock(return_value=overview)):
            result = await _check_rebalancing_opportunity(uuid.uuid4(), mock_db)

        assert result == []


# ── _check_tax_loss_harvest ───────────────────────────────────

class TestCheckTaxLossHarvest:
    @pytest.mark.asyncio
    async def test_no_positions_returns_empty(self, mock_db, override_settings):
        from app.services.insight_service import _check_tax_loss_harvest

        with patch("app.services.insight_service.get_overseas_positions_detail",
                   new=AsyncMock(return_value=[])):
            result = await _check_tax_loss_harvest(uuid.uuid4(), mock_db)

        assert result == []

    @pytest.mark.asyncio
    async def test_no_loss_positions_returns_empty(self, mock_db, override_settings):
        from app.services.insight_service import _check_tax_loss_harvest

        positions = [
            {"ticker": "AAPL", "unrealized_pnl_krw": 500_000, "qty": 5},
        ]
        with patch("app.services.insight_service.get_overseas_positions_detail",
                   new=AsyncMock(return_value=positions)):
            result = await _check_tax_loss_harvest(uuid.uuid4(), mock_db)

        assert result == []

    @pytest.mark.asyncio
    async def test_significant_harvest_opportunity_returns_insight(self, mock_db, override_settings):
        from app.services.insight_service import _check_tax_loss_harvest

        positions = [
            {"ticker": "AAPL", "unrealized_pnl_krw": 3_000_000, "qty": 5},
            {"ticker": "TSLA", "unrealized_pnl_krw": -1_500_000, "qty": 3},
        ]
        with patch("app.services.insight_service.get_overseas_positions_detail",
                   new=AsyncMock(return_value=positions)):
            result = await _check_tax_loss_harvest(uuid.uuid4(), mock_db)

        assert len(result) == 1
        assert result[0].type == "TAX_LOSS_HARVEST"


# ── generate_insights ─────────────────────────────────────────

class TestGenerateInsights:
    @pytest.mark.asyncio
    async def test_redis_cache_hit(self, mock_db, override_settings):
        import json

        from app.services.insight_service import generate_insights

        cached = [{"type": "CONCENTRATION", "severity": "WARNING", "title": "테스트", "detail": "d"}]
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=json.dumps(cached).encode())

        result = await generate_insights(uuid.uuid4(), mock_db, redis=redis)
        assert len(result) == 1
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_list_when_no_issues(self, mock_db, override_settings):
        from app.services.insight_service import generate_insights

        mock_db.scalar = AsyncMock(return_value=None)

        with (
            patch("app.services.insight_service.get_dashboard_summary",
                  new=AsyncMock(return_value={"total_assets_krw": 0, "asset_allocation": []})),
            patch("app.services.insight_service._check_rebalancing_opportunity",
                  new=AsyncMock(return_value=[])),
            patch("app.services.insight_service._check_tax_loss_harvest",
                  new=AsyncMock(return_value=[])),
        ):
            result = await generate_insights(uuid.uuid4(), mock_db)

        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_force_refresh_bypasses_cache(self, mock_db, override_settings):
        import json

        from app.services.insight_service import generate_insights

        cached = [{"type": "OLD", "severity": "INFO", "title": "old", "detail": "old"}]
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=json.dumps(cached).encode())
        redis.setex = AsyncMock()

        with (
            patch("app.services.insight_service.get_dashboard_summary",
                  new=AsyncMock(return_value={"total_assets_krw": 0, "asset_allocation": []})),
            patch("app.services.insight_service._check_rebalancing_opportunity",
                  new=AsyncMock(return_value=[])),
            patch("app.services.insight_service._check_tax_loss_harvest",
                  new=AsyncMock(return_value=[])),
        ):
            await generate_insights(uuid.uuid4(), mock_db, redis=redis, force_refresh=True)

        # Should not use cached value since force_refresh=True
        redis.get.assert_not_called()
