"""tax_service.py 단위 테스트."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.tax_service import (
    _build_harvesting_recommendations,
    _calc_dividend_income,
    _calc_total_fees,
    _get_rates,
    get_tax_summary,
)

_RATES_2025 = _get_rates(2025)


# ── _build_harvesting_recommendations ────────────────────────

class TestBuildHarvestingRecommendations:
    """Tax-Loss Harvesting 추천 순수 로직 검증."""

    def test_no_gain_returns_empty(self, override_settings):
        """과세 대상 이익이 없으면 빈 리스트."""
        positions = [{"ticker": "AAPL", "name": "Apple", "market": "NASDAQ",
                      "unrealized_pnl_krw": -500_000, "qty": 5}]
        assert _build_harvesting_recommendations(positions, 0.0, _RATES_2025) == []
        assert _build_harvesting_recommendations(positions, -100_000, _RATES_2025) == []

    def test_loss_positions_only_selected(self, override_settings):
        """손실 포지션만 추천 목록에 포함된다."""
        positions = [
            {"ticker": "AAPL", "name": "Apple", "market": "NASDAQ",
             "unrealized_pnl_krw": 200_000, "qty": 3},
            {"ticker": "TSLA", "name": "Tesla", "market": "NASDAQ",
             "unrealized_pnl_krw": -400_000, "qty": 2},
        ]
        result = _build_harvesting_recommendations(positions, 500_000, _RATES_2025)
        tickers = [r["ticker"] for r in result]
        assert "TSLA" in tickers
        assert "AAPL" not in tickers

    def test_tax_saved_calculation(self, override_settings):
        """tax_saved_krw = min(loss, remaining_gain) × 0.22"""
        positions = [
            {"ticker": "TSLA", "name": "Tesla", "market": "NASDAQ",
             "unrealized_pnl_krw": -1_000_000, "qty": 5},
        ]
        result = _build_harvesting_recommendations(positions, 500_000, _RATES_2025)
        assert len(result) == 1
        # offset = min(1_000_000, 500_000) = 500_000; tax_saved = 500_000 * 0.22 = 110_000
        assert result[0]["tax_saved_krw"] == 110_000.0

    def test_stops_when_gain_fully_offset(self, override_settings):
        """과세이익이 상쇄되면 더 이상 추천하지 않는다."""
        positions = [
            {"ticker": "A", "name": "A", "market": "NYSE",
             "unrealized_pnl_krw": -2_000_000, "qty": 10},
            {"ticker": "B", "name": "B", "market": "NYSE",
             "unrealized_pnl_krw": -1_000_000, "qty": 5},
        ]
        # gain=1_500_000 → A(-2M)로 완전 상쇄되므로 B 추천 불필요
        result = _build_harvesting_recommendations(positions, 1_500_000, _RATES_2025)
        assert len(result) == 1
        assert result[0]["ticker"] == "A"

    def test_sorted_by_largest_loss_first(self, override_settings):
        """손실이 큰 종목이 먼저 추천된다."""
        positions = [
            {"ticker": "X", "name": "X", "market": "NYSE",
             "unrealized_pnl_krw": -300_000, "qty": 3},
            {"ticker": "Y", "name": "Y", "market": "NYSE",
             "unrealized_pnl_krw": -800_000, "qty": 4},
        ]
        result = _build_harvesting_recommendations(positions, 2_000_000, _RATES_2025)
        assert result[0]["ticker"] == "Y"
        assert result[1]["ticker"] == "X"

    def test_result_includes_required_fields(self, override_settings):
        """추천 결과에 필수 필드 포함."""
        positions = [
            {"ticker": "TSLA", "name": "Tesla", "market": "NASDAQ",
             "unrealized_pnl_krw": -500_000, "qty": 2},
        ]
        result = _build_harvesting_recommendations(positions, 1_000_000, _RATES_2025)
        assert len(result) == 1
        rec = result[0]
        assert "ticker" in rec
        assert "name" in rec
        assert "market" in rec
        assert "unrealized_loss_krw" in rec
        assert "tax_saved_krw" in rec
        assert "qty" in rec


# ── get_tax_summary ──────────────────────────────────────────

class TestGetTaxSummary:
    """get_tax_summary: 연도별 세금 추정 요약."""

    @pytest.mark.asyncio
    async def test_returns_required_fields(self, mock_db, override_settings):
        """반환 dict에 필수 키가 포함된다."""
        user_id = uuid.uuid4()

        with (
            patch("app.services.tax_service._calc_dividend_income", new_callable=AsyncMock, return_value=0.0),
            patch("app.services.tax_service._calc_total_fees", new_callable=AsyncMock, return_value=0.0),
            patch(
                "app.services.tax_service._calc_stock_unrealized",
                new_callable=AsyncMock,
                return_value=(0.0, 0.0, 0.0),
            ),
            patch("app.services.tax_service.get_overseas_positions_detail", new_callable=AsyncMock, return_value=[]),
        ):
            result = await get_tax_summary(user_id, 2025, mock_db)

        required = [
            "year", "dividend_income_krw", "dividend_tax_krw",
            "overseas_unrealized_gain_krw", "overseas_gain_deduction_krw",
            "overseas_tax_estimated_krw", "domestic_stock_value_krw",
            "domestic_unrealized_gain_krw",
            "domestic_large_holder_warning", "comprehensive_tax_warning",
            "total_estimated_tax_krw", "total_fees_krw",
            "harvesting_recommendations", "financial_investment_tax_simulation",
            "note", "rates",
        ]
        for key in required:
            assert key in result, f"Missing key: {key}"

    @pytest.mark.asyncio
    async def test_dividend_tax_is_154_pct_of_income(self, mock_db, override_settings):
        """배당소득세 = 배당소득 × 15.4%."""
        user_id = uuid.uuid4()
        dividend_income = 1_000_000.0

        with (
            patch(
                "app.services.tax_service._calc_dividend_income",
                new_callable=AsyncMock,
                return_value=dividend_income,
            ),
            patch("app.services.tax_service._calc_total_fees", new_callable=AsyncMock, return_value=0.0),
            patch(
                "app.services.tax_service._calc_stock_unrealized",
                new_callable=AsyncMock,
                return_value=(0.0, 0.0, 0.0),
            ),
            patch("app.services.tax_service.get_overseas_positions_detail", new_callable=AsyncMock, return_value=[]),
        ):
            result = await get_tax_summary(user_id, 2025, mock_db)

        assert result["dividend_income_krw"] == 1_000_000
        assert result["dividend_tax_krw"] == round(1_000_000.0 * 0.154)

    @pytest.mark.asyncio
    async def test_overseas_tax_after_deduction(self, mock_db, override_settings):
        """해외 양도세 = max(0, 미실현이익 - 250만원) × 22%."""
        user_id = uuid.uuid4()
        overseas_unrealized = 5_000_000.0  # 500만원 미실현 이익

        with (
            patch("app.services.tax_service._calc_dividend_income", new_callable=AsyncMock, return_value=0.0),
            patch("app.services.tax_service._calc_total_fees", new_callable=AsyncMock, return_value=0.0),
            patch(
                "app.services.tax_service._calc_stock_unrealized",
                new_callable=AsyncMock,
                return_value=(overseas_unrealized, 0.0, 0.0),
            ),
            patch("app.services.tax_service.get_overseas_positions_detail", new_callable=AsyncMock, return_value=[]),
        ):
            result = await get_tax_summary(user_id, 2025, mock_db)

        expected_taxable = 5_000_000.0 - 2_500_000.0  # = 2_500_000
        expected_tax = round(expected_taxable * 0.22)
        assert result["overseas_tax_estimated_krw"] == expected_tax

    @pytest.mark.asyncio
    async def test_overseas_unrealized_below_deduction_yields_zero_tax(self, mock_db, override_settings):
        """미실현 이익이 공제액(250만원) 미만이면 해외 양도세 0."""
        user_id = uuid.uuid4()

        with (
            patch("app.services.tax_service._calc_dividend_income", new_callable=AsyncMock, return_value=0.0),
            patch("app.services.tax_service._calc_total_fees", new_callable=AsyncMock, return_value=0.0),
            patch(
                "app.services.tax_service._calc_stock_unrealized",
                new_callable=AsyncMock,
                return_value=(1_000_000.0, 0.0, 0.0),
            ),
            patch("app.services.tax_service.get_overseas_positions_detail", new_callable=AsyncMock, return_value=[]),
        ):
            result = await get_tax_summary(user_id, 2025, mock_db)

        assert result["overseas_tax_estimated_krw"] == 0

    @pytest.mark.asyncio
    async def test_domestic_large_holder_warning(self, mock_db, override_settings):
        """국내주식 보유액 10억 이상이면 대주주 경고."""
        user_id = uuid.uuid4()

        with (
            patch("app.services.tax_service._calc_dividend_income", new_callable=AsyncMock, return_value=0.0),
            patch("app.services.tax_service._calc_total_fees", new_callable=AsyncMock, return_value=0.0),
            patch(
                "app.services.tax_service._calc_stock_unrealized",
                new_callable=AsyncMock,
                return_value=(0.0, 1_000_000_000.0, 0.0),
            ),
            patch("app.services.tax_service.get_overseas_positions_detail", new_callable=AsyncMock, return_value=[]),
        ):
            result = await get_tax_summary(user_id, 2025, mock_db)

        assert result["domestic_large_holder_warning"] is True

    @pytest.mark.asyncio
    async def test_comprehensive_tax_warning_when_over_20m(self, mock_db, override_settings):
        """금융소득 2000만원 초과 시 종합과세 경고."""
        user_id = uuid.uuid4()

        with (
            patch(
                "app.services.tax_service._calc_dividend_income",
                new_callable=AsyncMock,
                return_value=20_000_001.0,
            ),
            patch("app.services.tax_service._calc_total_fees", new_callable=AsyncMock, return_value=0.0),
            patch(
                "app.services.tax_service._calc_stock_unrealized",
                new_callable=AsyncMock,
                return_value=(0.0, 0.0, 0.0),
            ),
            patch("app.services.tax_service.get_overseas_positions_detail", new_callable=AsyncMock, return_value=[]),
        ):
            result = await get_tax_summary(user_id, 2025, mock_db)

        assert result["comprehensive_tax_warning"] is True

    @pytest.mark.asyncio
    async def test_total_fees_included(self, mock_db, override_settings):
        """총 거래 수수료가 결과에 포함된다."""
        user_id = uuid.uuid4()

        with (
            patch("app.services.tax_service._calc_dividend_income", new_callable=AsyncMock, return_value=0.0),
            patch("app.services.tax_service._calc_total_fees", new_callable=AsyncMock, return_value=15_000.0),
            patch(
                "app.services.tax_service._calc_stock_unrealized",
                new_callable=AsyncMock,
                return_value=(0.0, 0.0, 0.0),
            ),
            patch("app.services.tax_service.get_overseas_positions_detail", new_callable=AsyncMock, return_value=[]),
        ):
            result = await get_tax_summary(user_id, 2025, mock_db)

        assert result["total_fees_krw"] == 15_000

    @pytest.mark.asyncio
    async def test_year_in_result(self, mock_db, override_settings):
        """요청 연도가 결과에 반영된다."""
        user_id = uuid.uuid4()

        with (
            patch("app.services.tax_service._calc_dividend_income", new_callable=AsyncMock, return_value=0.0),
            patch("app.services.tax_service._calc_total_fees", new_callable=AsyncMock, return_value=0.0),
            patch(
                "app.services.tax_service._calc_stock_unrealized",
                new_callable=AsyncMock,
                return_value=(0.0, 0.0, 0.0),
            ),
            patch("app.services.tax_service.get_overseas_positions_detail", new_callable=AsyncMock, return_value=[]),
        ):
            result = await get_tax_summary(user_id, 2024, mock_db)

        assert result["year"] == 2024


# ── _calc_total_fees / _calc_dividend_income DB 헬퍼 ────────

class TestCalcTotalFeesDb:
    @pytest.mark.asyncio
    async def test_returns_sum_when_fees_exist(self, mock_db, override_settings):
        execute_result = MagicMock()
        execute_result.scalar.return_value = 50_000.0
        mock_db.execute = AsyncMock(return_value=execute_result)

        result = await _calc_total_fees(uuid.uuid4(), 2024, mock_db)

        assert result == pytest.approx(50_000.0)

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_fees(self, mock_db, override_settings):
        execute_result = MagicMock()
        execute_result.scalar.return_value = None
        mock_db.execute = AsyncMock(return_value=execute_result)

        result = await _calc_total_fees(uuid.uuid4(), 2024, mock_db)

        assert result == 0.0

    @pytest.mark.asyncio
    async def test_returns_zero_when_scalar_zero(self, mock_db, override_settings):
        execute_result = MagicMock()
        execute_result.scalar.return_value = 0
        mock_db.execute = AsyncMock(return_value=execute_result)

        result = await _calc_total_fees(uuid.uuid4(), 2024, mock_db)

        assert result == 0.0


class TestCalcDividendIncomeDb:
    @pytest.mark.asyncio
    async def test_returns_sum_when_dividends_exist(self, mock_db, override_settings):
        execute_result = MagicMock()
        execute_result.scalar.return_value = 1_500_000.0
        mock_db.execute = AsyncMock(return_value=execute_result)

        result = await _calc_dividend_income(uuid.uuid4(), 2024, mock_db)

        assert result == pytest.approx(1_500_000.0)

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_dividends(self, mock_db, override_settings):
        execute_result = MagicMock()
        execute_result.scalar.return_value = None
        mock_db.execute = AsyncMock(return_value=execute_result)

        result = await _calc_dividend_income(uuid.uuid4(), 2024, mock_db)

        assert result == 0.0
