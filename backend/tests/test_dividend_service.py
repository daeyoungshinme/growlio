"""dividend_service 단위 테스트 — 배당금 계산 로직 검증."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest


class TestGetDividendSummary:
    """get_dividend_summary: 연간 수령 + 예상 배당금 집계."""

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_transactions(self, mock_db, override_settings):
        """배당 내역 없으면 연간 수령액 0, 예상 배당금 0."""
        from app.services.dividend.aggregator import get_dividend_summary

        user_id = uuid.uuid4()

        with (
            patch(
                "app.services.dividend.aggregator._fetch_dividend_aggregates",
                new_callable=AsyncMock,
                return_value=(0.0, [], []),
            ),
            patch(
                "app.services.dividend.aggregator.get_ticker_dividend_summary",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            summary = await get_dividend_summary(user_id, mock_db)

        assert summary["annual_received"] == 0.0
        assert summary["estimated_annual"] == 0.0
        assert summary["monthly_breakdown"] == []

    @pytest.mark.asyncio
    async def test_sums_annual_received_correctly(self, mock_db, override_settings):
        """_fetch_dividend_aggregates 결과가 annual_received에 반영된다."""
        from app.services.dividend.aggregator import get_dividend_summary

        user_id = uuid.uuid4()

        with (
            patch(
                "app.services.dividend.aggregator._fetch_dividend_aggregates",
                new_callable=AsyncMock,
                return_value=(80_000.0, [], []),
            ),
            patch(
                "app.services.dividend.aggregator.get_ticker_dividend_summary",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            summary = await get_dividend_summary(user_id, mock_db)

        assert summary["annual_received"] == 80_000.0

    @pytest.mark.asyncio
    async def test_estimated_annual_from_ticker_summaries(self, mock_db, override_settings):
        """ticker_summaries의 estimated_annual_krw 합계가 estimated_annual에 반영된다."""
        from app.services.dividend.aggregator import get_dividend_summary

        user_id = uuid.uuid4()
        ticker_data = [
            {"ticker": "005930", "estimated_annual_krw": 120_000.0},
            {"ticker": "AAPL", "estimated_annual_krw": 50_000.0},
        ]

        with (
            patch(
                "app.services.dividend.aggregator._fetch_dividend_aggregates",
                new_callable=AsyncMock,
                return_value=(0.0, [], []),
            ),
            patch(
                "app.services.dividend.aggregator.get_ticker_dividend_summary",
                new_callable=AsyncMock,
                return_value=ticker_data,
            ),
        ):
            summary = await get_dividend_summary(user_id, mock_db)

        assert summary["estimated_annual"] == 170_000.0


# ── 배당월 예측 로직 테스트 ─────────────────────────────────


class TestDividendMonthPrediction:
    """알려진 배당 일정 vs. 실제 내역 우선순위 검증."""

    def test_known_schedule_produces_months(self):
        """하드코딩된 종목 배당월 목록이 정수 리스트인지 확인."""
        from app.services.dividend.constants import KNOWN_DIVIDEND_SCHEDULES

        for key, months in KNOWN_DIVIDEND_SCHEDULES.items():
            assert isinstance(months, list)
            for m in months:
                assert 1 <= m <= 12, f"{key}: 잘못된 배당월 {m}"
