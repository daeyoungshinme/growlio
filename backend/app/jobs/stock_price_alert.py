"""주가 목표 알림 Job — 10분 간격 실행."""
from __future__ import annotations

from app.database import AsyncSessionLocal
from app.redis_client import get_redis
from app.services.alert_service import check_and_trigger_stock_price_alerts


async def run_stock_price_alert_check() -> None:
    """10분 간격 — 활성 주가 알림 조건 체크 후 이메일 발송."""
    redis = await get_redis()
    async with AsyncSessionLocal() as db:
        await check_and_trigger_stock_price_alerts(db, redis)
