import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = structlog.get_logger()

scheduler = AsyncIOScheduler(timezone="Asia/Seoul", job_defaults={"coalesce": True, "max_instances": 1})


def init_scheduler() -> None:
    from apscheduler.triggers.interval import IntervalTrigger

    from app.jobs.asset_sync import run_daily_asset_sync, run_intraday_asset_sync
    from app.jobs.exchange_rate_alert import run_exchange_rate_alert_check
    from app.jobs.rebalancing_alert import run_rebalancing_alert_check
    from app.jobs.token_refresh import refresh_all_user_tokens

    scheduler.add_job(
        refresh_all_user_tokens,
        CronTrigger(hour=6, minute=0, timezone="Asia/Seoul"),
        id="kis_token_refresh_daily",
        replace_existing=True,
    )
    scheduler.add_job(
        run_intraday_asset_sync,
        CronTrigger(hour=15, minute=30, timezone="Asia/Seoul"),
        id="asset_sync_intraday",
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
        IntervalTrigger(minutes=10),
        id="rebalancing_alert_check_interval",
        replace_existing=True,
    )
    from app.jobs.market_signal_alert import run_market_signal_alert_check

    scheduler.add_job(
        run_market_signal_alert_check,
        IntervalTrigger(minutes=10),
        id="market_signal_alert_check_interval",
        replace_existing=True,
    )
    from app.jobs.dca_auto_buy import run_dca_auto_execution

    scheduler.add_job(
        run_dca_auto_execution,
        CronTrigger(hour=9, minute=0, timezone="Asia/Seoul"),
        id="dca_auto_execution_daily",
        replace_existing=True,
    )
    from app.jobs.rebalancing_auto_execution import run_rebalancing_auto_execution

    scheduler.add_job(
        run_rebalancing_auto_execution,
        CronTrigger(minute="*/5", hour="9-15", timezone="Asia/Seoul"),
        id="rebalancing_auto_execution_intraday",
        replace_existing=True,
    )
    from app.jobs.stock_price_alert import run_stock_price_alert_check

    scheduler.add_job(
        run_stock_price_alert_check,
        IntervalTrigger(minutes=10),
        id="stock_price_alert_check",
        replace_existing=True,
    )
    from app.jobs.price_publisher import run_price_broadcast

    scheduler.add_job(
        run_price_broadcast,
        IntervalTrigger(seconds=30),
        id="ws_price_broadcast",
        replace_existing=True,
    )
    from app.jobs.monthly_report import run_monthly_report

    scheduler.add_job(
        run_monthly_report,
        CronTrigger(day=1, hour=9, minute=0, timezone="Asia/Seoul"),
        id="monthly_report_job",
        replace_existing=True,
    )
    from app.jobs.goal_achievement import run_goal_achievement_check

    scheduler.add_job(
        run_goal_achievement_check,
        CronTrigger(hour=18, minute=45, timezone="Asia/Seoul"),
        id="goal_achievement_check_daily",
        replace_existing=True,
    )
    from app.jobs.economic_indicator_sync import (
        run_economic_indicator_alert_check,
        run_economic_indicator_sync,
    )

    scheduler.add_job(
        run_economic_indicator_sync,
        CronTrigger(hour=8, minute=0, timezone="Asia/Seoul"),
        id="economic_indicator_sync_daily",
        replace_existing=True,
    )
    scheduler.add_job(
        run_economic_indicator_alert_check,
        CronTrigger(hour=8, minute=5, timezone="Asia/Seoul"),
        id="economic_indicator_alert_check_daily",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("scheduler_started", jobs=len(scheduler.get_jobs()))
