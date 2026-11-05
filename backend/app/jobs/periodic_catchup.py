"""놓친 월간 잡 보충 — Render 슬립·재시작으로 정해진 시각을 놓치면 다음 달까지 복구되지 않는다.

jobstore가 메모리라 `misfire_grace_time`은 프로세스 재시작을 넘지 못한다. 대상 잡은 모두 사용자·챌린지별 월 단위 dedup이
있어 다시 돌려도 받은 사람에게 또 보내지 않는다. 주간 잡은 당일 dedup뿐이라 넣지 않았다 — 주 단위 키가 먼저 필요하다.
"""

from __future__ import annotations

from datetime import datetime

from app.jobs.challenge_deposit_reminder import run_challenge_deposit_reminder
from app.jobs.challenge_monthly_wrap import run_challenge_monthly_wrap
from app.jobs.monthly_report import run_monthly_report
from app.utils.kst import now_kst

# 정시 잡(09:00·09:30)과 겹치지 않고, 밤에 알림이 가지 않는 시간대
_CATCHUP_HOURS = range(10, 22)
_MONTH_START_DAYS = range(1, 4)
_REMINDER_DAYS = range(25, 29)


def _due_jobs(now: datetime) -> list:
    if now.hour not in _CATCHUP_HOURS:
        return []
    if now.day in _MONTH_START_DAYS:
        return [run_monthly_report, run_challenge_monthly_wrap]
    if now.day in _REMINDER_DAYS:
        return [run_challenge_deposit_reminder]
    return []


async def run_periodic_catchup() -> None:
    """기동 직후와 낮 시간 매시간 실행 — 해당 기간이 아니면 아무것도 하지 않는다. 잡은 실패를 자체 처리한다."""
    for job in _due_jobs(now_kst()):
        await job()
