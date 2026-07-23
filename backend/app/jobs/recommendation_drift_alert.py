"""추천 비중 변화 알림 job — 매주 월요일 09:15 KST 실행."""

from app.jobs._job_helpers import run_alert_job
from app.services.alerts.recommendation_drift_alert_service import send_recommendation_drift_alerts


async def run_recommendation_drift_alert() -> None:
    """옵트인한 유저 중 목표 역산 추천 비중이 타겟 포트폴리오와 유의미하게 달라진 유저에게 안내 발송."""
    await run_alert_job(send_recommendation_drift_alerts, "recommendation_drift_alert_job")
