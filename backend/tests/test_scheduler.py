"""app/scheduler.py — 잡 등록 스펙과 misfire 설정 검증."""

from unittest.mock import patch

import pytest
from apscheduler.triggers.cron import CronTrigger

from app import scheduler as scheduler_module

EXPECTED_JOB_IDS = {
    "kis_token_refresh_daily",
    "asset_sync_intraday",
    "asset_sync_daily",
    "exchange_rate_alert_check",
    "rebalancing_alert_check_interval",
    "market_signal_alert_check_interval",
    "rebalancing_auto_execution_intraday",
    "rebalancing_plan_buy_execution",
    "rebalancing_plan_sell_expiry",
    "stock_price_alert_check",
    "monthly_report_job",
    "goal_achievement_check_daily",
    "market_signal_daily_digest",
    "year_end_tax_reminder",
    "recommendation_drift_alert",
    "challenge_deposit_reminder",
    "challenge_monthly_wrap",
    "cache_sweep",
}


@pytest.fixture
def registered_jobs(monkeypatch):
    sched = scheduler_module.scheduler
    monkeypatch.setattr(sched, "start", lambda *a, **kw: None)
    sched.remove_all_jobs()
    scheduler_module.init_scheduler()
    yield sched.get_jobs()
    sched.remove_all_jobs()


def test_all_jobs_registered_with_expected_ids(registered_jobs):
    assert {job.id for job in registered_jobs} == EXPECTED_JOB_IDS


def test_misfire_grace_time_in_job_defaults(registered_jobs):
    # 기본값(1초)이면 이벤트 루프가 잠깐만 밀려도 잡이 조용히 버려진다. job_defaults는 start() 시점에
    # 각 잡에 적용되므로(여기선 start를 막았으므로) 스케줄러 기본값을 직접 확인하고, 잡별 override가 없는지 본다.
    defaults = scheduler_module.scheduler._job_defaults
    assert defaults["misfire_grace_time"] == scheduler_module.MISFIRE_GRACE_SECONDS
    assert defaults["coalesce"] is True
    assert defaults["max_instances"] == 1
    for job in registered_jobs:
        assert not hasattr(job, "misfire_grace_time"), job.id


def test_cron_triggers_use_kst(registered_jobs):
    # "매일 18:00" 같은 시각 기반 잡만 대상 — IntervalTrigger("N분마다")는 timezone과 무관하며
    # 미지정 시 시스템 TZ를 따르므로(CI는 UTC) 검사하지 않는다.
    cron_jobs = [job for job in registered_jobs if isinstance(job.trigger, CronTrigger)]
    assert cron_jobs
    for job in cron_jobs:
        assert str(job.trigger.timezone) == "Asia/Seoul", job.id


def test_job_event_listener_logs_missed_and_error():
    from datetime import datetime

    from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MISSED, JobExecutionEvent

    with patch.object(scheduler_module, "logger") as mock_logger:
        scheduler_module._on_job_event(
            JobExecutionEvent(EVENT_JOB_MISSED, "job-a", "default", datetime(2026, 9, 25, 9, 0))
        )
        scheduler_module._on_job_event(
            JobExecutionEvent(
                EVENT_JOB_ERROR, "job-b", "default", datetime(2026, 9, 25, 9, 0), exception=ValueError("x")
            )
        )

    mock_logger.warning.assert_called_once()
    assert mock_logger.warning.call_args.args[0] == "scheduler_job_missed"
    mock_logger.error.assert_called_once()
    assert mock_logger.error.call_args.kwargs["job_id"] == "job-b"


def test_report_job_failure_logs_and_captures_to_sentry():
    from app.jobs import _job_helpers

    exc = RuntimeError("boom")
    with (
        patch.object(_job_helpers, "logger") as mock_logger,
        patch.object(_job_helpers.sentry_sdk, "capture_exception") as mock_capture,
    ):
        _job_helpers.report_job_failure("x_failed", exc, user_id="u1")

    mock_logger.error.assert_called_once_with("x_failed", error="boom", user_id="u1")
    mock_capture.assert_called_once_with(exc)
