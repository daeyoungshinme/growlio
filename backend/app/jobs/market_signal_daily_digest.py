"""시장 위험 신호 매일 요약 다이제스트 job — 매일 08:30 KST 실행, 등급 전환 여부와 무관하게 발송."""

from app.jobs._job_helpers import run_alert_job
from app.services.alerts.market_signal_alert_service import send_market_signal_daily_digest


async def run_market_signal_daily_digest() -> None:
    """옵트인한 유저에게 현재 시장 위험 신호(GREEN/YELLOW/RED)를 매일 08:30 KST에 요약 발송."""
    await run_alert_job(send_market_signal_daily_digest, "market_signal_daily_digest_job", needs_cache=True)
