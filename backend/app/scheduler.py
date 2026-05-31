import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = structlog.get_logger()

scheduler = AsyncIOScheduler(timezone="Asia/Seoul", job_defaults={"coalesce": True, "max_instances": 1})


def init_scheduler() -> None:
    from app.jobs.asset_sync import run_daily_asset_sync
    from app.jobs.token_refresh import refresh_all_user_tokens
    from app.jobs.exchange_rate_alert import run_exchange_rate_alert_check
    from app.jobs.rebalancing_alert import run_rebalancing_alert_check
    from apscheduler.triggers.interval import IntervalTrigger

    scheduler.add_job(
        refresh_all_user_tokens,
        CronTrigger(hour=6, minute=0, timezone="Asia/Seoul"),
        id="kis_token_refresh_daily",
        replace_existing=True,
    )
    scheduler.add_job(
        run_daily_asset_sync,
        CronTrigger(hour=18, minute=0, timezone="Asia/Seoul"),
        id="asset_sync_daily",
        replace_existing=True,
    )
    scheduler.add_job(
        run_exchange_rate_alert_check,
        IntervalTrigger(minutes=5),
        id="exchange_rate_alert_check",
        replace_existing=True,
    )
    scheduler.add_job(
        run_rebalancing_alert_check,
        CronTrigger(hour=18, minute=30, timezone="Asia/Seoul"),
        id="rebalancing_alert_check_daily",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("scheduler_started", jobs=len(scheduler.get_jobs()))
