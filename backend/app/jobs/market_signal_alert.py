"""시장 위험 신호등 등급 변화 감지 job — 10분 간격 실행, 등급 전환 시 즉시 알림."""

from app.jobs._job_helpers import run_alert_job
from app.services.market_signal_alert_service import check_market_signal_level_change


async def run_market_signal_alert_check() -> None:
    """시장 위험 신호(GREEN/YELLOW/RED) 등급이 이전 관측값과 달라졌으면 구독 유저에게 즉시 알림 발송."""
    await run_alert_job(check_market_signal_level_change, "market_signal_alert_job", needs_redis=True)
