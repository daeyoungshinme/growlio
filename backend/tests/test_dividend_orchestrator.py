"""dividend/orchestrator.py 추가 단위 테스트."""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestGetDartKey:
    @pytest.mark.asyncio
    async def test_returns_settings_dart_key_when_user_has_custom(self, mock_db, override_settings):
        from app.services.dividend._dividend_queries import fetch_dart_api_key

        settings_row = SimpleNamespace(dart_api_key=b"encrypted_key")
        mock_db.scalar = AsyncMock(return_value=settings_row)

        with patch("app.services.dividend._dividend_queries.decrypt", return_value="user-dart-key"):
            result = await fetch_dart_api_key(uuid.uuid4(), mock_db)

        assert result == "user-dart-key"

    @pytest.mark.asyncio
    async def test_falls_back_to_config_when_no_user_settings(self, mock_db, override_settings):
        from app.services.dividend._dividend_queries import fetch_dart_api_key

        mock_db.scalar = AsyncMock(return_value=None)

        with patch("app.services.dividend._dividend_queries.settings") as mock_settings:
            mock_settings.dart_api_key = "config-dart-key"
            result = await fetch_dart_api_key(uuid.uuid4(), mock_db)

        assert result == "config-dart-key"

    @pytest.mark.asyncio
    async def test_falls_back_to_config_when_no_dart_api_key(self, mock_db, override_settings):
        from app.services.dividend._dividend_queries import fetch_dart_api_key

        settings_row = SimpleNamespace(dart_api_key=None)
        mock_db.scalar = AsyncMock(return_value=settings_row)

        with patch("app.services.dividend._dividend_queries.settings") as mock_settings:
            mock_settings.dart_api_key = "config-dart-key"
            result = await fetch_dart_api_key(uuid.uuid4(), mock_db)

        assert result == "config-dart-key"


class TestCollectPositions:
    @pytest.mark.asyncio
    async def test_empty_rows_returns_empty_map(self, mock_db, override_settings):
        from app.services.dividend.orchestrator import _collect_positions

        exec_result = MagicMock()
        exec_result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=exec_result)

        result = await _collect_positions(uuid.uuid4(), mock_db)
        assert result == {}

    @pytest.mark.asyncio
    async def test_aggregates_positions_from_snapshots(self, mock_db, override_settings):
        from app.services.dividend.orchestrator import _collect_positions

        pos1 = SimpleNamespace(
            ticker="AAPL",
            market="NASDAQ",
            name="Apple",
            value_krw=1_000_000.0,
            qty=10.0,
            current_price=100_000.0,
            avg_price=95_000.0,
        )
        snap = SimpleNamespace(id=uuid.uuid4(), position_items=[pos1])
        acc = SimpleNamespace(id=uuid.uuid4())

        exec_result = MagicMock()
        exec_result.all.return_value = [(snap, acc)]
        mock_db.execute = AsyncMock(return_value=exec_result)

        result = await _collect_positions(uuid.uuid4(), mock_db)

        assert ("AAPL", "NASDAQ") in result
        assert result[("AAPL", "NASDAQ")]["value_krw"] == pytest.approx(1_000_000.0)

    @pytest.mark.asyncio
    async def test_skips_positions_with_zero_value(self, mock_db, override_settings):
        from app.services.dividend.orchestrator import _collect_positions

        pos_zero = SimpleNamespace(
            ticker="DEAD",
            market="NASDAQ",
            name="Dead Stock",
            value_krw=0.0,
            qty=0.0,
            current_price=0.0,
            avg_price=0.0,
        )
        snap = SimpleNamespace(id=uuid.uuid4(), position_items=[pos_zero])
        acc = SimpleNamespace(id=uuid.uuid4())

        exec_result = MagicMock()
        exec_result.all.return_value = [(snap, acc)]
        mock_db.execute = AsyncMock(return_value=exec_result)

        result = await _collect_positions(uuid.uuid4(), mock_db)
        assert result == {}


class TestLoadUserOverrides:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_settings(self, mock_db, override_settings):
        from app.services.dividend._dividend_queries import load_user_dividend_overrides

        exec_result = MagicMock()
        exec_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=exec_result)

        result = await load_user_dividend_overrides(uuid.uuid4(), mock_db)
        assert result == {}

    @pytest.mark.asyncio
    async def test_returns_dividend_months_map(self, mock_db, override_settings):
        from app.services.dividend._dividend_queries import load_user_dividend_overrides

        row = SimpleNamespace(ticker="AAPL", market="NASDAQ", dividend_months=[3, 6, 9, 12])
        exec_result = MagicMock()
        exec_result.scalars.return_value.all.return_value = [row]
        mock_db.execute = AsyncMock(return_value=exec_result)

        result = await load_user_dividend_overrides(uuid.uuid4(), mock_db)

        assert ("AAPL", "NASDAQ") in result
        assert result[("AAPL", "NASDAQ")] == [3, 6, 9, 12]


class TestBuildTickerOutputEntry:
    def test_with_empty_est_keys_returns_zero_values(self, override_settings):
        from app.services.dividend.orchestrator import _build_ticker_output_entry

        result = _build_ticker_output_entry(
            ticker_key="AAPL",
            est_keys=[],
            estimated_map={},
            received_map={"AAPL": 500_000.0},
            pos_name="Apple",
        )

        assert result["ticker"] == "AAPL"
        assert result["name"] == "Apple"
        assert result["estimated_annual_krw"] == 0
        assert result["estimated_monthly_krw"] == 0
        assert result["dividend_months"] == []
        assert result["received_krw"] == 500_000.0

    def test_with_est_keys_aggregates_estimates(self, override_settings):
        from app.services.dividend.orchestrator import _build_ticker_output_entry

        estimated_map = {
            ("AAPL", "NASDAQ"): {
                "estimated_annual_krw": 100_000.0,
                "estimated_monthly_krw": 8_333.0,
                "dividend_months": [3, 6, 9, 12],
                "market": "NASDAQ",
                "yield_decimal": 0.02,
                "dps": 100.0,
                "investment_yield": 0.018,
                "dividend_months_is_manual": False,
                "currency": "USD",
                "estimated_monthly_usd": 5.0,
            }
        }

        result = _build_ticker_output_entry(
            ticker_key="AAPL",
            est_keys=[("AAPL", "NASDAQ")],
            estimated_map=estimated_map,
            received_map={"AAPL": 300_000.0},
            pos_name="Apple",
        )

        assert result["estimated_annual_krw"] == 100_000.0
        assert result["dividend_months"] == [3, 6, 9, 12]
        assert result["currency"] == "USD"
        assert result["estimated_monthly_usd"] == 5.0


class TestGetTickerDividendSummary:
    @pytest.mark.asyncio
    async def test_redis_cache_hit_returns_cached(self, mock_db, override_settings):
        from app.services.dividend.orchestrator import get_ticker_dividend_summary

        cached = [{"ticker": "AAPL", "estimated_annual_krw": 100_000.0}]

        with patch(
            "app.services.dividend.orchestrator.get_redis",
            new=AsyncMock(
                return_value=AsyncMock(
                    get=AsyncMock(return_value=json.dumps(cached).encode()),
                )
            ),
        ):
            result = await get_ticker_dividend_summary(uuid.uuid4(), mock_db)

        assert result == cached
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_positions_returns_only_unclassified_received(self, mock_db, override_settings):
        from app.services.dividend.orchestrator import get_ticker_dividend_summary

        unclassified_row = SimpleNamespace(ticker_key="__unclassified__", total=50_000.0)

        exec_result = MagicMock()
        exec_result.all = MagicMock()

        call_count = 0

        async def mock_execute(query, params=None):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                # First execute: received dividends query
                result.__iter__ = MagicMock(return_value=iter([unclassified_row]))
                result.all = MagicMock(return_value=[unclassified_row])
            else:
                result.all.return_value = []
            return result

        mock_db.execute = mock_execute

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.setex = AsyncMock()

        with (
            patch("app.services.dividend.orchestrator.get_redis", new=AsyncMock(return_value=mock_redis)),
            patch("app.services.dividend.orchestrator._collect_positions", new=AsyncMock(return_value={})),
            patch("app.services.dividend.orchestrator.load_user_dividend_overrides", new=AsyncMock(return_value={})),
            patch("app.services.dividend.orchestrator.fetch_dart_api_key", new=AsyncMock(return_value="key")),
            patch("app.services.dividend.orchestrator.get_kis_user_credentials", new=AsyncMock(return_value=None)),
            patch("app.services.dividend.orchestrator.get_usd_krw_rate", new=AsyncMock(return_value=1350.0)),
        ):
            result = await get_ticker_dividend_summary(uuid.uuid4(), mock_db)

        # Should have __unclassified__ entry
        unclassified = next((r for r in result if r["ticker"] is None), None)
        assert unclassified is not None
