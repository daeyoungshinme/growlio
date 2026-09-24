"""app/scheduler.py — 잡 등록 스펙과 misfire 설정 검증."""

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
    "rebalancing_plan_sell_expiry_daily",
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
