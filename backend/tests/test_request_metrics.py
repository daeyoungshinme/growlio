"""요청 단위 DB 계측·단계 타이머(plans/151 배치 0)."""

import asyncio
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from sqlalchemy.util import greenlet_spawn
from structlog.testing import capture_logs

from app.core.request_metrics import (
    current_db_queries,
    record_db_query,
    reset_request_metrics,
    start_request_metrics,
)
from app.core.timing import StepTimer


def test_record_outside_request_is_noop():
    record_db_query(5.0)
    assert current_db_queries() is None


def test_counts_queries_and_resets():
    metrics, token = start_request_metrics()
    try:
        record_db_query(2.0)
        record_db_query(3.5)
        assert current_db_queries() == 2
    finally:
        reset_request_metrics(token)
    assert metrics.db_queries == 2
    assert metrics.db_ms == 5.5
    assert current_db_queries() is None


async def test_counter_shared_with_gathered_tasks_and_greenlet():
    """cursor 이벤트는 SQLAlchemy 드라이버 greenlet 안에서 돈다 — 거기서도, gather로 갈라진 작업에서도 같은 카운터."""
    metrics, token = start_request_metrics()
    try:

        async def in_greenlet() -> None:
            await greenlet_spawn(record_db_query, 1.0)

        await asyncio.gather(in_greenlet(), in_greenlet())
    finally:
        reset_request_metrics(token)
    assert metrics.db_queries == 2


def test_step_timer_logs_steps_total_and_query_delta():
    metrics, token = start_request_metrics()
    try:
        record_db_query(1.0)  # 타이머 시작 전 쿼리는 세지 않는다
        with capture_logs() as logs:
            timer = StepTimer("demo_timing", lite=True)
            record_db_query(1.0)
            timer.mark("first")
            timer.mark("second")
            timer.log(accounts=3)
    finally:
        reset_request_metrics(token)
    (event,) = [e for e in logs if e["event"] == "demo_timing"]
    assert event["lite"] is True
    assert event["accounts"] == 3
    assert event["db_queries"] == 1
    assert {"first_ms", "second_ms", "total_ms"} <= event.keys()


def test_step_timer_outside_request_omits_db_queries():
    with capture_logs() as logs:
        StepTimer("demo_timing").log()
    (event,) = logs
    assert "db_queries" not in event


def test_http_request_log_carries_db_queries(override_settings):
    from app.main import app

    db = AsyncMock()

    async def _execute(*_args, **_kwargs):
        record_db_query(4.0)  # 실제 엔진이면 after_cursor_execute가 부른다

    db.execute.side_effect = _execute

    async def _get_db():
        yield db

    with (
        patch("app.main.get_db", _get_db),
        TestClient(app, raise_server_exceptions=False) as client,
        capture_logs() as logs,
    ):
        resp = client.get("/health", headers={"X-Request-ID": "req-151"})
    assert resp.status_code == 200
    (event,) = [e for e in logs if e["event"] == "http_request"]
    assert event["db_queries"] == 1
    assert event["db_ms"] == 4
    assert event["request_id"] == "req-151"
