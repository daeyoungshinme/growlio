"""목표환율 알림 체크 — 5분 간격 실행."""

from app.jobs._job_helpers import run_alert_job
from app.services.exchange_rate_alert_service import check_and_trigger_alerts


async def run_exchange_rate_alert_check() -> None:
    """활성 목표환율 알림을 조회하고 조건 충족 시 이메일 발송."""
    await run_alert_job(check_and_trigger_alerts, "exchange_rate_alert_job", needs_redis=True)
