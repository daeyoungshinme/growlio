"""연말 절세 리마인더 job — 11~12월 매주 월요일 09:00 KST 실행."""

from app.jobs._job_helpers import run_alert_job
from app.services.alerts.tax_reminder_service import send_year_end_tax_reminder


async def run_year_end_tax_reminder() -> None:
    """옵트인한 유저에게 손실수확 후보·연금공제 잔여한도·ISA 만기 현황을 요약 발송."""
    await run_alert_job(send_year_end_tax_reminder, "year_end_tax_reminder_job")
