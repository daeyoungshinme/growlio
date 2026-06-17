"""목표환율 알림 체크 — 5분 간격 실행."""

import structlog

from app.database import AsyncSessionLocal
from app.services.alert_service import check_and_trigger_alerts

logger = structlog.get_logger()


async def run_exchange_rate_alert_check() -> None:
    """활성 목표환율 알림을 조회하고 조건 충족 시 이메일 발송."""
    async with AsyncSessionLocal() as db:
        try:
            await check_and_trigger_alerts(db)
        except Exception as e:
            logger.error("exchange_rate_alert_job_failed", error=str(e))
