"""리밸런싱 알림 체크 — 매일 18:30 KST 실행."""
from __future__ import annotations

import structlog

from app.database import AsyncSessionLocal
from app.services.alert_service import check_rebalancing_alerts

logger = structlog.get_logger()


async def run_rebalancing_alert_check() -> None:
    """활성 리밸런싱 알림을 조회하고 드리프트 초과 시 이메일 발송."""
    async with AsyncSessionLocal() as db:
        try:
            await check_rebalancing_alerts(db)
        except Exception as e:
            logger.error("rebalancing_alert_job_failed", error=str(e))
