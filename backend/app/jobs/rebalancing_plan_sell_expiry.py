"""리밸런싱 매도 승인 만료 Job — 1일 1회(장마감 직후), 당일 미응답 SELL leg를 만료 처리한다."""

from __future__ import annotations

import structlog

from app.database import AsyncSessionLocal
from app.services.rebalancing.plan_service import expire_due_sell_legs

logger = structlog.get_logger()


async def run_rebalancing_plan_sell_expiry() -> None:
    """1일 1회, 15:31 KST — 당일 장마감까지 미응답 매도 승인 요청을 만료 처리한다."""
    async with AsyncSessionLocal() as db:
        count = await expire_due_sell_legs(db)
        if count:
            logger.info("rebalancing_plan_sell_expiry_done", count=count)
