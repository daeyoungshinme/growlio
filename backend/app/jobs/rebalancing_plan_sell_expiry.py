"""리밸런싱 매도 승인 만료 Job — 15분 간격, 마감시각이 지난 미응답 SELL leg를 만료 처리한다."""

from __future__ import annotations

import structlog

from app.core.database import AsyncSessionLocal
from app.services.rebalancing.plan_service import expire_due_sell_legs

logger = structlog.get_logger()


async def run_rebalancing_plan_sell_expiry() -> None:
    """15분 간격 — 정규장 마감(국내 15:30 KST / 해외 NYSE 마감, leg별 deadline_at 기준)까지
    미응답 매도 승인 요청을 만료 처리한다. deadline_at은 leg 생성 시점에 이미 시장별로 정확히
    계산돼 있으므로(plan_service.generate_pending_plan_for_alert) 이 job은 단순히 자주
    돌면서 지난 leg를 정리하기만 하면 된다 — 해외 leg는 다음날(KST 기준) 새벽에 마감되므로
    기존처럼 하루 1회 고정 시각으로는 제때 만료시킬 수 없다.
    """
    async with AsyncSessionLocal() as db:
        count = await expire_due_sell_legs(db)
        if count:
            logger.info("rebalancing_plan_sell_expiry_done", count=count)
