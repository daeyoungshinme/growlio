"""알림 Job 단위 테스트 — 스케줄 작업 진입점 검증."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_mock_db():
    mock_db = MagicMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=False)
    return mock_db


@pytest.mark.asyncio
async def test_run_exchange_rate_alert_check_calls_service():
    """run_exchange_rate_alert_check가 check_and_trigger_alerts를 cache와 함께 호출한다.

    needs_cache=True여야 usd_krw_rate 캐시가 갱신됨 — 회귀 방지용 assertion.
    """
    mock_db = _make_mock_db()
    mock_cache = MagicMock()

    with (
        patch("app.jobs._job_helpers.get_cache_store", new=AsyncMock(return_value=mock_cache)),
        patch("app.jobs._job_helpers.AsyncSessionLocal", return_value=mock_db),
        patch("app.jobs.exchange_rate_alert.check_and_trigger_alerts", new=AsyncMock()) as mock_check,
    ):
        from app.jobs.exchange_rate_alert import run_exchange_rate_alert_check

        await run_exchange_rate_alert_check()

    mock_check.assert_called_once_with(mock_db, mock_cache)


@pytest.mark.asyncio
async def test_run_exchange_rate_alert_check_handles_exception():
    """check_and_trigger_alerts 예외 발생 시 Job이 크래시하지 않는다."""
    mock_db = _make_mock_db()
    mock_cache = MagicMock()

    with (
        patch("app.jobs._job_helpers.get_cache_store", new=AsyncMock(return_value=mock_cache)),
        patch("app.jobs._job_helpers.AsyncSessionLocal", return_value=mock_db),
        patch(
            "app.jobs.exchange_rate_alert.check_and_trigger_alerts",
            new=AsyncMock(side_effect=RuntimeError("DB error")),
        ),
    ):
        from app.jobs.exchange_rate_alert import run_exchange_rate_alert_check

        await run_exchange_rate_alert_check()  # 예외 전파 없어야 함


@pytest.mark.asyncio
async def test_run_rebalancing_alert_check_calls_service():
    """run_rebalancing_alert_check가 check_rebalancing_alerts를 호출한다."""
    mock_db = _make_mock_db()

    with (
        patch("app.jobs._job_helpers.AsyncSessionLocal", return_value=mock_db),
        patch("app.jobs.rebalancing_alert.check_rebalancing_alerts", new=AsyncMock()) as mock_check,
    ):
        from app.jobs.rebalancing_alert import run_rebalancing_alert_check

        await run_rebalancing_alert_check()

    mock_check.assert_called_once_with(mock_db)


@pytest.mark.asyncio
async def test_run_rebalancing_alert_check_handles_exception():
    """check_rebalancing_alerts 예외 발생 시 Job이 크래시하지 않는다."""
    mock_db = _make_mock_db()

    with (
        patch("app.jobs._job_helpers.AsyncSessionLocal", return_value=mock_db),
        patch(
            "app.jobs.rebalancing_alert.check_rebalancing_alerts",
            new=AsyncMock(side_effect=ValueError("분석 실패")),
        ),
    ):
        from app.jobs.rebalancing_alert import run_rebalancing_alert_check

        await run_rebalancing_alert_check()  # 예외 전파 없어야 함


@pytest.mark.asyncio
async def test_run_stock_price_alert_check_calls_service():
    """run_stock_price_alert_check가 check_and_trigger_stock_price_alerts를 호출한다."""
    mock_db = _make_mock_db()
    mock_cache = MagicMock()

    with (
        patch("app.jobs._job_helpers.get_cache_store", new=AsyncMock(return_value=mock_cache)),
        patch("app.jobs._job_helpers.AsyncSessionLocal", return_value=mock_db),
        patch("app.jobs.stock_price_alert.check_and_trigger_stock_price_alerts", new=AsyncMock()) as mock_check,
    ):
        from app.jobs.stock_price_alert import run_stock_price_alert_check

        await run_stock_price_alert_check()

    mock_check.assert_called_once_with(mock_db, mock_cache)


@pytest.mark.asyncio
async def test_run_market_signal_daily_digest_calls_service():
    """run_market_signal_daily_digest가 send_market_signal_daily_digest를 cache와 함께 호출한다."""
    mock_db = _make_mock_db()
    mock_cache = MagicMock()

    with (
        patch("app.jobs._job_helpers.get_cache_store", new=AsyncMock(return_value=mock_cache)),
        patch("app.jobs._job_helpers.AsyncSessionLocal", return_value=mock_db),
        patch("app.jobs.market_signal_daily_digest.send_market_signal_daily_digest", new=AsyncMock()) as mock_send,
    ):
        from app.jobs.market_signal_daily_digest import run_market_signal_daily_digest

        await run_market_signal_daily_digest()

    mock_send.assert_called_once_with(mock_db, mock_cache)


@pytest.mark.asyncio
async def test_run_market_signal_daily_digest_handles_exception():
    """send_market_signal_daily_digest 예외 발생 시 Job이 크래시하지 않는다."""
    mock_db = _make_mock_db()
    mock_cache = MagicMock()

    with (
        patch("app.jobs._job_helpers.get_cache_store", new=AsyncMock(return_value=mock_cache)),
        patch("app.jobs._job_helpers.AsyncSessionLocal", return_value=mock_db),
        patch(
            "app.jobs.market_signal_daily_digest.send_market_signal_daily_digest",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ),
    ):
        from app.jobs.market_signal_daily_digest import run_market_signal_daily_digest

        await run_market_signal_daily_digest()  # 예외 전파 없어야 함
