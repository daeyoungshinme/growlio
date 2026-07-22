"""dividend_plan_service 단위 테스트."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.dividend.plan_service import _calc_monthly_projected, get_dividend_plan

# ---------------------------------------------------------------------------
# _calc_monthly_projected 순수 함수 테스트
# ---------------------------------------------------------------------------


class TestCalcMonthlyProjected:
    def test_empty_summaries_returns_zero_buckets(self):
        result = _calc_monthly_projected([])
        assert len(result) == 12
        assert all(r["amount_krw"] == 0 for r in result)
        assert [r["month"] for r in result] == list(range(1, 13))

    def test_single_ticker_distributes_evenly(self):
        summaries = [
            {"estimated_annual_krw": 1200, "dividend_months": [1, 4, 7, 10]},
        ]
        result = _calc_monthly_projected(summaries)
        by_month = {r["month"]: r["amount_krw"] for r in result}
        assert by_month[1] == 300
        assert by_month[4] == 300
        assert by_month[7] == 300
        assert by_month[10] == 300
        # 배당 없는 달은 0
        assert by_month[2] == 0

    def test_monthly_dividend_all_months(self):
        summaries = [
            {"estimated_annual_krw": 1200, "dividend_months": list(range(1, 13))},
        ]
        result = _calc_monthly_projected(summaries)
        assert all(r["amount_krw"] == 100 for r in result)

    def test_skips_ticker_with_zero_annual(self):
        summaries = [
            {"estimated_annual_krw": 0, "dividend_months": [1, 2, 3]},
        ]
        result = _calc_monthly_projected(summaries)
        assert all(r["amount_krw"] == 0 for r in result)

    def test_skips_ticker_with_no_months(self):
        summaries = [
            {"estimated_annual_krw": 1200, "dividend_months": []},
        ]
        result = _calc_monthly_projected(summaries)
        assert all(r["amount_krw"] == 0 for r in result)

    def test_multiple_tickers_accumulate(self):
        summaries = [
            {"estimated_annual_krw": 1200, "dividend_months": [3]},
            {"estimated_annual_krw": 2400, "dividend_months": [3]},
        ]
        result = _calc_monthly_projected(summaries)
        by_month = {r["month"]: r["amount_krw"] for r in result}
        assert by_month[3] == 3600  # 1200 + 2400

    def test_none_dividend_months_skipped(self):
        summaries = [
            {"estimated_annual_krw": 1200, "dividend_months": None},
        ]
        result = _calc_monthly_projected(summaries)
        assert all(r["amount_krw"] == 0 for r in result)


# ---------------------------------------------------------------------------
# get_dividend_plan 통합 테스트 (DB/캐시 mock)
# ---------------------------------------------------------------------------


@pytest.fixture
def user_id():
    return uuid.uuid4()


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.scalar = AsyncMock()
    db.execute = AsyncMock()
    return db


@pytest.fixture
def mock_cache():
    return MagicMock()


TICKER_SUMMARIES = [
    {
        "ticker": "005930",
        "estimated_annual_krw": 1_200_000,
        "estimated_monthly_krw": 100_000,
        "dividend_months": [4, 5, 8, 11],
    },
    {
        "ticker": "QQQ",
        "estimated_annual_krw": 600_000,
        "estimated_monthly_krw": 50_000,
        "dividend_months": [1, 4, 7, 10],
    },
]

DIVIDEND_SUMMARY = {
    "annual_received": 500_000,
    "monthly_breakdown": [{"month": "2026-04", "amount": 200_000}],
    "monthly_ticker_breakdown": [],
    "estimated_annual": 1_800_000,
}

YEARLY_ROWS = [
    SimpleNamespace(year=2024, amount_krw=300_000.0),
    SimpleNamespace(year=2025, amount_krw=450_000.0),
    SimpleNamespace(year=2026, amount_krw=500_000.0),
]


class TestGetDividendPlan:
    @pytest.mark.asyncio
    async def test_no_goal_returns_none_achievement(self, user_id, mock_db, mock_cache):
        mock_db.scalar.return_value = SimpleNamespace(annual_dividend_goal=None)
        execute_result = MagicMock()
        execute_result.fetchall.return_value = YEARLY_ROWS
        mock_db.execute = AsyncMock(return_value=execute_result)

        with (
            patch(
                "app.services.dividend.plan_service.get_ticker_dividend_summary",
                AsyncMock(return_value=TICKER_SUMMARIES),
            ),
            patch(
                "app.services.dividend.plan_service.get_dividend_summary",
                AsyncMock(return_value=DIVIDEND_SUMMARY),
            ),
        ):
            result = await get_dividend_plan(user_id, mock_db, mock_cache)

        assert result["annual_dividend_goal"] is None
        assert result["goal_achievement_pct"] is None
        assert result["estimated_annual_krw"] == 1_800_000
        assert result["estimated_monthly_krw"] == 150_000
        assert result["actual_annual_received_krw"] == 500_000
        assert len(result["monthly_projected"]) == 12
        assert len(result["yearly_received"]) == 3

    @pytest.mark.asyncio
    async def test_with_goal_calculates_achievement(self, user_id, mock_db, mock_cache):
        mock_db.scalar.return_value = SimpleNamespace(annual_dividend_goal=3_600_000)
        execute_result = MagicMock()
        execute_result.fetchall.return_value = []
        mock_db.execute = AsyncMock(return_value=execute_result)

        with (
            patch(
                "app.services.dividend.plan_service.get_ticker_dividend_summary",
                AsyncMock(return_value=TICKER_SUMMARIES),
            ),
            patch(
                "app.services.dividend.plan_service.get_dividend_summary",
                AsyncMock(return_value=DIVIDEND_SUMMARY),
            ),
        ):
            result = await get_dividend_plan(user_id, mock_db, mock_cache)

        assert result["annual_dividend_goal"] == 3_600_000
        assert result["goal_achievement_pct"] == 50.0  # 1_800_000 / 3_600_000 * 100

    @pytest.mark.asyncio
    async def test_no_settings_row_returns_none_goal(self, user_id, mock_db, mock_cache):
        mock_db.scalar.return_value = None
        execute_result = MagicMock()
        execute_result.fetchall.return_value = []
        mock_db.execute = AsyncMock(return_value=execute_result)

        with (
            patch(
                "app.services.dividend.plan_service.get_ticker_dividend_summary",
                AsyncMock(return_value=[]),
            ),
            patch(
                "app.services.dividend.plan_service.get_dividend_summary",
                AsyncMock(return_value={"annual_received": 0, "monthly_breakdown": []}),
            ),
        ):
            result = await get_dividend_plan(user_id, mock_db, mock_cache)

        assert result["annual_dividend_goal"] is None
        assert result["estimated_annual_krw"] == 0
        assert result["estimated_monthly_krw"] == 0

    @pytest.mark.asyncio
    async def test_monthly_projected_sums_correctly(self, user_id, mock_db, mock_cache):
        mock_db.scalar.return_value = SimpleNamespace(annual_dividend_goal=None)
        execute_result = MagicMock()
        execute_result.fetchall.return_value = []
        mock_db.execute = AsyncMock(return_value=execute_result)

        with (
            patch(
                "app.services.dividend.plan_service.get_ticker_dividend_summary",
                AsyncMock(return_value=TICKER_SUMMARIES),
            ),
            patch(
                "app.services.dividend.plan_service.get_dividend_summary",
                AsyncMock(return_value=DIVIDEND_SUMMARY),
            ),
        ):
            result = await get_dividend_plan(user_id, mock_db, mock_cache)

        projected = {p["month"]: p["amount_krw"] for p in result["monthly_projected"]}
        # 월 4: 005930(1_200_000/4=300_000) + QQQ(600_000/4=150_000) = 450_000
        assert projected[4] == 450_000
        # 월 1: QQQ만 (600_000/4=150_000)
        assert projected[1] == 150_000
        # 월 2: 아무것도 없음
        assert projected[2] == 0

    @pytest.mark.asyncio
    async def test_yearly_received_mapped_correctly(self, user_id, mock_db, mock_cache):
        mock_db.scalar.return_value = SimpleNamespace(annual_dividend_goal=None)
        execute_result = MagicMock()
        execute_result.fetchall.return_value = YEARLY_ROWS
        mock_db.execute = AsyncMock(return_value=execute_result)

        with (
            patch(
                "app.services.dividend.plan_service.get_ticker_dividend_summary",
                AsyncMock(return_value=[]),
            ),
            patch(
                "app.services.dividend.plan_service.get_dividend_summary",
                AsyncMock(return_value={"annual_received": 0, "monthly_breakdown": []}),
            ),
        ):
            result = await get_dividend_plan(user_id, mock_db, mock_cache)

        years = result["yearly_received"]
        assert len(years) == 3
        assert years[0] == {"year": 2024, "amount_krw": 300_000}
        assert years[2] == {"year": 2026, "amount_krw": 500_000}
