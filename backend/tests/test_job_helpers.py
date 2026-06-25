"""_job_helpers 단위 테스트 — run_alert_job 공통 실행 패턴 검증."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_mock_db():
    mock_db = MagicMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=False)
    return mock_db


@pytest.mark.asyncio
async def test_run_alert_job_without_redis_calls_service_with_db_only():
    mock_db = _make_mock_db()
    mock_func = AsyncMock()

    with patch("app.jobs._job_helpers.AsyncSessionLocal", return_value=mock_db):
        from app.jobs._job_helpers import run_alert_job

        await run_alert_job(mock_func, "test_job", needs_redis=False)

    mock_func.assert_called_once_with(mock_db)


@pytest.mark.asyncio
async def test_run_alert_job_with_redis_calls_service_with_db_and_redis():
    mock_db = _make_mock_db()
    mock_redis = MagicMock()
    mock_func = AsyncMock()

    with (
        patch("app.jobs._job_helpers.get_redis", new=AsyncMock(return_value=mock_redis)),
        patch("app.jobs._job_helpers.AsyncSessionLocal", return_value=mock_db),
    ):
        from app.jobs._job_helpers import run_alert_job

        await run_alert_job(mock_func, "test_job", needs_redis=True)

    mock_func.assert_called_once_with(mock_db, mock_redis)


@pytest.mark.asyncio
async def test_run_alert_job_logs_exception_without_propagating():
    mock_db = _make_mock_db()
    mock_func = AsyncMock(side_effect=RuntimeError("service failure"))

    with patch("app.jobs._job_helpers.AsyncSessionLocal", return_value=mock_db):
        from app.jobs._job_helpers import run_alert_job

        # 예외가 전파되지 않아야 함
        await run_alert_job(mock_func, "test_job")
