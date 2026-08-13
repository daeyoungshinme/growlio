"""이메일 HTML 템플릿 빌더 — 순수 함수, I/O 없음.

원래 단일 파일(847줄)이었던 것을 2026-08-13 기술부채 정리에서 알림 종류별로 분리했다 —
`_shared.py`(공용 헬퍼/상수), `alerts.py`(환율/주가 단순 알림), `rebalancing.py`(드리프트·자동실행·
AUTO 플랜 게이트, 가장 큰 그룹), `market_signal.py`(시장신호 등급전환·매일요약), `reports.py`(월간
리포트·목표달성·연말절세·추천비중변화·회원탈퇴). 이 `__init__.py`가 전체를 재노출하므로
`from app.services.email_templates import X` 호출부(email_service.py 등)는 변경 없이 그대로 동작한다.
"""

from __future__ import annotations

from app.services.email_templates.alerts import (
    exchange_rate_alert_template,
    stock_price_alert_template,
    test_email_template,
)
from app.services.email_templates.market_signal import (
    market_signal_change_template,
    market_signal_daily_digest_template,
)
from app.services.email_templates.rebalancing import (
    daily_value_cap_gate_blocked_template,
    market_signal_gate_blocked_template,
    rebalancing_alert_template,
    rebalancing_execution_template,
    rebalancing_plan_execution_failed_template,
    rebalancing_plan_pending_template,
    tax_impact_gate_blocked_template,
)
from app.services.email_templates.reports import (
    account_deletion_template,
    goal_achievement_template,
    monthly_report_template,
    recommendation_drift_alert_template,
    year_end_tax_reminder_template,
)

__all__ = [
    "account_deletion_template",
    "daily_value_cap_gate_blocked_template",
    "exchange_rate_alert_template",
    "goal_achievement_template",
    "market_signal_change_template",
    "market_signal_daily_digest_template",
    "market_signal_gate_blocked_template",
    "monthly_report_template",
    "rebalancing_alert_template",
    "rebalancing_execution_template",
    "rebalancing_plan_execution_failed_template",
    "rebalancing_plan_pending_template",
    "recommendation_drift_alert_template",
    "stock_price_alert_template",
    "tax_impact_gate_blocked_template",
    "test_email_template",
    "year_end_tax_reminder_template",
]
