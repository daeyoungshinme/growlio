"""주가 목표 알림 Job — 10분 간격 실행."""

from app.jobs._job_helpers import run_alert_job
from app.services.stock_price_alert_service import check_and_trigger_stock_price_alerts


async def run_stock_price_alert_check() -> None:
    """10분 간격 — 활성 주가 알림 조건 체크 후 이메일 발송."""
    await run_alert_job(check_and_trigger_stock_price_alerts, "stock_price_alert_job", needs_redis=True)
