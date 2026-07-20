"""pension_contribution_service.py 단위 테스트 (구 test_tax_service.py에서 분리)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.pension_contribution_service import calc_pension_contribution_status


class TestCalcPensionContributionStatus:
    @pytest.mark.asyncio
    async def test_no_deposits_returns_zero(self, mock_db, override_settings):
        execute_result = MagicMock()
        execute_result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=execute_result)

        result = await calc_pension_contribution_status(uuid.uuid4(), 2026, mock_db)

        assert result["pension_savings_deposit_krw"] == 0
        assert result["irp_deposit_krw"] == 0
        assert result["total_deposit_krw"] == 0
        assert result["pension_savings_achievement_pct"] == 0.0
        assert result["total_achievement_pct"] == 0.0
        assert result["pension_savings_remaining_krw"] == 6_000_000
        assert result["total_remaining_krw"] == 9_000_000

    @pytest.mark.asyncio
    async def test_pension_savings_only(self, mock_db, override_settings):
        execute_result = MagicMock()
        execute_result.all.return_value = [("PENSION_SAVINGS", 3_000_000.0)]
        mock_db.execute = AsyncMock(return_value=execute_result)

        result = await calc_pension_contribution_status(uuid.uuid4(), 2026, mock_db)

        assert result["pension_savings_deposit_krw"] == 3_000_000
        assert result["irp_deposit_krw"] == 0
        assert result["total_deposit_krw"] == 3_000_000
        assert result["pension_savings_achievement_pct"] == 50.0

    @pytest.mark.asyncio
    async def test_irp_only(self, mock_db, override_settings):
        execute_result = MagicMock()
        execute_result.all.return_value = [("IRP", 1_500_000.0)]
        mock_db.execute = AsyncMock(return_value=execute_result)

        result = await calc_pension_contribution_status(uuid.uuid4(), 2026, mock_db)

        assert result["pension_savings_deposit_krw"] == 0
        assert result["irp_deposit_krw"] == 1_500_000
        assert result["total_deposit_krw"] == 1_500_000

    @pytest.mark.asyncio
    async def test_combined_over_limit_caps_pct_and_remaining_at_zero(self, mock_db, override_settings):
        execute_result = MagicMock()
        execute_result.all.return_value = [
            ("PENSION_SAVINGS", 6_000_000.0),
            ("IRP", 5_000_000.0),
        ]
        mock_db.execute = AsyncMock(return_value=execute_result)

        result = await calc_pension_contribution_status(uuid.uuid4(), 2026, mock_db)

        assert result["total_deposit_krw"] == 11_000_000
        assert result["total_remaining_krw"] == 0
        assert result["pension_savings_remaining_krw"] == 0
        assert result["total_achievement_pct"] == pytest.approx(122.2, abs=0.1)

    @pytest.mark.asyncio
    async def test_note_present(self, mock_db, override_settings):
        execute_result = MagicMock()
        execute_result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=execute_result)

        result = await calc_pension_contribution_status(uuid.uuid4(), 2026, mock_db)

        assert "수기 입력" in result["note"]
