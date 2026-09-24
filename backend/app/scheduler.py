import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = structlog.get_logger()

# misfire_grace_time: APScheduler 기본값(1초)이면 이벤트 루프가 동기 연산(pandas/MVO 등)으로 잠깐만 밀려도
# 잡이 "missed"로 조용히 버려진다. coalesce=True라 늦게 실행돼도 1회로 합쳐지므로 넉넉히 잡는다.
# 주의: jobstore가 메모리라 프로세스 재시작(재배포/Render 무료 플랜 슬립) 사이에 놓친 잡은 이 값과 무관하게
# 복구되지 않는다 — 슬립은 .github/workflows/keep-alive.yml로 완화 (backend/CLAUDE.md "jobs" 참고).
MISFIRE_GRACE_SECONDS = 900

scheduler = AsyncIOScheduler(
    timezone="Asia/Seoul",
    job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": MISFIRE_GRACE_SECONDS},
)


def init_scheduler() -> None:
    from apscheduler.triggers.interval import IntervalTrigger

    from app.jobs.asset_sync import run_daily_asset_sync, run_intraday_asset_sync
    from app.jobs.cache_sweep import run_cache_sweep
    from app.jobs.challenge_deposit_reminder import run_challenge_deposit_reminder
    from app.jobs.challenge_monthly_wrap import run_challenge_monthly_wrap
    from app.jobs.exchange_rate_alert import run_exchange_rate_alert_check
    from app.jobs.goal_achievement import run_goal_achievement_check
    from app.jobs.market_signal_alert import run_market_signal_alert_check
    from app.jobs.market_signal_daily_digest import run_market_signal_daily_digest
    from app.jobs.monthly_report import run_monthly_report
    from app.jobs.rebalancing_alert import run_rebalancing_alert_check
    from app.jobs.rebalancing_auto_execution import run_rebalancing_auto_execution
    from app.jobs.rebalancing_plan_buy_execution import run_rebalancing_plan_buy_execution
    from app.jobs.rebalancing_plan_sell_expiry import run_rebalancing_plan_sell_expiry
    from app.jobs.recommendation_drift_alert import run_recommendation_drift_alert
    from app.jobs.stock_price_alert import run_stock_price_alert_check
    from app.jobs.token_refresh import refresh_all_user_tokens
    from app.jobs.year_end_tax_reminder import run_year_end_tax_reminder

    def kst(**kwargs: str | int) -> CronTrigger:
        return CronTrigger(timezone="Asia/Seoul", **kwargs)

    jobs = [
        (refresh_all_user_tokens, kst(hour=6, minute=0), "kis_token_refresh_daily"),
        (run_intraday_asset_sync, kst(hour=15, minute=30), "asset_sync_intraday"),
        (run_daily_asset_sync, kst(hour=18, minute=0), "asset_sync_daily"),
        (run_exchange_rate_alert_check, IntervalTrigger(minutes=5), "exchange_rate_alert_check"),
        (run_rebalancing_alert_check, IntervalTrigger(minutes=10), "rebalancing_alert_check_interval"),
        (run_market_signal_alert_check, IntervalTrigger(hours=1), "market_signal_alert_check_interval"),
        (run_rebalancing_auto_execution, kst(minute="*/5"), "rebalancing_auto_execution_intraday"),
        (run_rebalancing_plan_buy_execution, IntervalTrigger(minutes=1), "rebalancing_plan_buy_execution"),
        (run_rebalancing_plan_sell_expiry, IntervalTrigger(minutes=15), "rebalancing_plan_sell_expiry_daily"),
        (run_stock_price_alert_check, IntervalTrigger(minutes=10), "stock_price_alert_check"),
        (run_monthly_report, kst(day=1, hour=9, minute=0), "monthly_report_job"),
        (run_goal_achievement_check, kst(hour=18, minute=45), "goal_achievement_check_daily"),
        (run_market_signal_daily_digest, kst(hour=8, minute=30), "market_signal_daily_digest"),
        (
            run_year_end_tax_reminder,
            kst(month="11-12", day_of_week="mon", hour=9, minute=0),
            "year_end_tax_reminder",
        ),
        (run_recommendation_drift_alert, kst(day_of_week="mon", hour=9, minute=15), "recommendation_drift_alert"),
        (run_challenge_deposit_reminder, kst(day=25, hour=9, minute=0), "challenge_deposit_reminder"),
        (run_challenge_monthly_wrap, kst(day=1, hour=9, minute=30), "challenge_monthly_wrap"),
        (run_cache_sweep, IntervalTrigger(minutes=15), "cache_sweep"),
    ]
    for func, trigger, job_id in jobs:
        scheduler.add_job(func, trigger, id=job_id, replace_existing=True)

    scheduler.start()
    logger.info("scheduler_started", jobs=len(scheduler.get_jobs()))
