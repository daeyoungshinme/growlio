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
    "tactical_regime_check_daily",
    "year_end_tax_reminder",
    "recommendation_drift_alert",
    "challenge_deposit_reminder",
    "challenge_monthly_wrap",
    "dca_cash_shortfall_check",
    "cache_sweep",
    "app_state_sweep",
    "kosdaq_tickers_refresh",
    "startup_warmup",
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


def test_rebalancing_alert_check_ticks_on_every_notify_time(registered_jobs):
    """plans/62 A3 — notify_time(:00/:30, ±4분 창)마다 tick이 정확히 한 번 떨어져야 한다.

    기동 시각 기준 IntervalTrigger(10분)면 tick이 :x5에 놓일 때 모든 알림이 매일 누락됐다.
    """
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    from app.utils.market_hours import is_alert_execution_time

    job = next(j for j in registered_jobs if j.id == "rebalancing_alert_check_interval")
    assert isinstance(job.trigger, CronTrigger)

    kst = ZoneInfo("Asia/Seoul")
    # 기동 시각을 :05로 가정해도 하루치 tick이 각 notify_time 창에 정확히 1번 들어와야 한다
    start = datetime(2026, 10, 21, 0, 5, 30, tzinfo=kst)
    ticks = []
    prev = None
    now = start
    while now < start + timedelta(days=1):
        nxt = job.trigger.get_next_fire_time(prev, now)
        ticks.append(nxt)
        prev = nxt
        now = nxt + timedelta(seconds=1)

    for notify_time in ("06:00", "08:30", "13:30", "22:00"):
        hits = [t for t in ticks if is_alert_execution_time(notify_time, now=t)]
        assert len(hits) == 1, (notify_time, hits)
