"""리밸런싱 알림 체크 — 매일 08:30 KST 실행."""

from app.jobs._job_helpers import run_alert_job
from app.services.alert_service import check_rebalancing_alerts


async def run_rebalancing_alert_check() -> None:
    """활성 리밸런싱 알림을 조회하고 드리프트 초과 시 이메일 발송."""
    await run_alert_job(check_rebalancing_alerts, "rebalancing_alert_job")
