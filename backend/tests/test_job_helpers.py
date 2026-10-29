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
async def test_run_alert_job_without_cache_calls_service_with_db_only():
    mock_db = _make_mock_db()
    mock_func = AsyncMock()

    with patch("app.jobs._job_helpers.AsyncSessionLocal", return_value=mock_db):
        from app.jobs._job_helpers import run_alert_job

        await run_alert_job(mock_func, "test_job", needs_cache=False)

    mock_func.assert_called_once_with(mock_db)


@pytest.mark.asyncio
async def test_run_alert_job_with_cache_calls_service_with_db_and_cache():
    mock_db = _make_mock_db()
    mock_cache = MagicMock()
    mock_func = AsyncMock()

    with (
        patch("app.jobs._job_helpers.get_cache_store", new=AsyncMock(return_value=mock_cache)),
        patch("app.jobs._job_helpers.AsyncSessionLocal", return_value=mock_db),
    ):
        from app.jobs._job_helpers import run_alert_job

        await run_alert_job(mock_func, "test_job", needs_cache=True)

    mock_func.assert_called_once_with(mock_db, mock_cache)


@pytest.mark.asyncio
async def test_run_alert_job_logs_exception_without_propagating():
    mock_db = _make_mock_db()
    mock_func = AsyncMock(side_effect=RuntimeError("service failure"))

    with (
        patch("app.jobs._job_helpers.AsyncSessionLocal", return_value=mock_db),
        patch("app.jobs._job_helpers.report_job_failure") as mock_report,
    ):
        from app.jobs._job_helpers import run_alert_job

        # 예외가 전파되지 않아야 함
        await run_alert_job(mock_func, "test_job")

    mock_report.assert_called_once()
    assert isinstance(mock_report.call_args.args[1], RuntimeError)


@pytest.mark.asyncio
async def test_run_per_user_isolates_failures_and_resolves_email():
    from types import SimpleNamespace

    from app.jobs._job_helpers import run_per_user

    ok_user = SimpleNamespace(id="u1", email="signup@example.com")
    bad_user = SimpleNamespace(id="u2", email="b@example.com")
    rows = [
        (bad_user, SimpleNamespace(notification_email=None)),
        (ok_user, SimpleNamespace(notification_email="alerts@example.com")),
    ]
    seen: list[tuple[str, str]] = []

    async def handle(user, settings_row, to_email):
        if user is bad_user:
            raise RuntimeError("boom")
        seen.append((user.id, to_email))

    with patch("app.jobs._job_helpers.report_job_failure") as report:
        await run_per_user(rows, handle, concurrency=2, failure_event="x_failed")

    assert seen == [("u1", "alerts@example.com")]
    report.assert_called_once()
    assert report.call_args.args[0] == "x_failed"
    assert report.call_args.kwargs == {"user_id": "u2"}
