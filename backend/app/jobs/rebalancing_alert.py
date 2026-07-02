"""리밸런싱 알림 체크 — 10분 간격 실행, 각 알림의 notify_time(HH:MM) 기준."""

from app.jobs._job_helpers import run_alert_job
from app.services.alert_service import check_rebalancing_alerts


async def run_rebalancing_alert_check() -> None:
    """활성 리밸런싱 알림을 조회하고 드리프트 초과 시 이메일 발송."""
    await run_alert_job(check_rebalancing_alerts, "rebalancing_alert_job")
