"""이메일 발송 서비스 (Resend HTTP API).

계약: 모든 `send_*` 함수는 예외를 삼키고 bool을 반환한다(True=발송 성공,
False=이메일 미설정 또는 발송 실패). 예외는 설정 확인 진단이 필요한
`send_test_email`의 "미설정" 케이스에서만 RuntimeError로 표면화된다.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings
from app.services.email_templates import (
    account_deletion_template,
    exchange_rate_alert_template,
    goal_achievement_template,
    market_signal_change_template,
    market_signal_daily_digest_template,
    market_signal_gate_blocked_template,
    monthly_report_template,
    password_reset_template,
    rebalancing_alert_template,
    rebalancing_execution_template,
    rebalancing_plan_execution_failed_template,
    rebalancing_plan_pending_template,
    recommendation_drift_alert_template,
    stock_price_alert_template,
    tax_impact_gate_blocked_template,
    test_email_template,
    year_end_tax_reminder_template,
)

logger = structlog.get_logger()


@retry(
    retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError)),
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
async def _send_html_email(to_email: str, subject: str, html: str) -> None:
    """HTML 이메일을 Resend API로 발송한다. 실패 시 예외를 그대로 전파한다."""
    async with httpx.AsyncClient(timeout=settings.email_timeout) as client:
        resp = await client.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json={"from": settings.email_from, "to": [to_email], "subject": subject, "html": html},
        )
        resp.raise_for_status()


def _email_configured() -> bool:
    return bool(settings.resend_api_key)


async def send_exchange_rate_alert(
    to_email: str,
    target_rate: float,
    direction: str,
    current_rate: float,
) -> bool:
    """목표환율 도달 알림 이메일 발송. 발송 성공 시 True, 이메일 미설정/실패 시 False 반환."""
    if not _email_configured():
        logger.warning("email_not_configured_skip_email", to=to_email)
        return False
    subject, html = exchange_rate_alert_template(target_rate, direction, current_rate)
    try:
        await _send_html_email(to_email, subject, html)
        logger.info("exchange_rate_alert_email_sent", to=to_email, target_rate=target_rate, current_rate=current_rate)
        return True
    except Exception as e:
        logger.error("exchange_rate_alert_email_failed", to=to_email, error=str(e))
        return False


async def send_rebalancing_alert(
    to_email: str,
    portfolio_name: str,
    threshold_pct: float,
    items_to_show: list,
    drifting_count: int,
    is_scheduled_report: bool = False,
    schedule_type: str = "DAILY",
    is_test: bool = False,
    is_composite_triggered: bool = False,
    composite_reason: str | None = None,
    order_preview_items: list | None = None,
    automation_note: str | None = None,
) -> bool:
    """리밸런싱 알림 이메일 발송. 발송 성공 시 True, 이메일 미설정 시 False 반환."""
    if not _email_configured():
        logger.warning("email_not_configured_skip_email", to=to_email)
        return False
    app_link = f"{settings.frontend_url}/rebalancing?rtab={quote('진단')}"
    subject, html = rebalancing_alert_template(
        portfolio_name,
        threshold_pct,
        items_to_show,
        drifting_count,
        is_scheduled_report,
        schedule_type,
        is_test=is_test,
        is_composite_triggered=is_composite_triggered,
        composite_reason=composite_reason,
        order_preview_items=order_preview_items,
        app_link=app_link,
        automation_note=automation_note,
    )
    try:
        await _send_html_email(to_email, subject, html)
        logger.info(
            "rebalancing_alert_email_sent",
            to=to_email,
            portfolio=portfolio_name,
            items=len(items_to_show),
            drifting=drifting_count,
            is_scheduled=is_scheduled_report,
        )
        return True
    except Exception as e:
        logger.error("rebalancing_alert_email_failed", to=to_email, error=str(e))
        return False


async def send_rebalancing_execution_email(
    to_email: str,
    portfolio_name: str,
    executed_at,
    result_items: list,
    total_success: int,
    total_fail: int,
    total_skipped: int,
) -> bool:
    """리밸런싱 자동 실행 완료 이메일 발송. 발송 성공 시 True, 이메일 미설정 시 False 반환."""
    if not _email_configured():
        logger.warning("email_not_configured_skip_email", to=to_email)
        return False
    subject, html = rebalancing_execution_template(
        portfolio_name, executed_at, result_items, total_success, total_fail, total_skipped
    )
    try:
        await _send_html_email(to_email, subject, html)
        logger.info(
            "rebalancing_execution_email_sent",
            to=to_email,
            portfolio=portfolio_name,
            success=total_success,
            fail=total_fail,
        )
        return True
    except Exception as e:
        logger.error("rebalancing_execution_email_failed", to=to_email, error=str(e))
        return False


async def send_rebalancing_plan_execution_failed_email(
    to_email: str, portfolio_name: str, side: str, error_message: str | None
) -> bool:
    """AUTO 매수/매도 leg 실행 자체가 예외로 실패했을 때 발송. 발송 성공 시 True, 이메일 미설정 시 False 반환."""
    if not _email_configured():
        logger.warning("email_not_configured_skip_email", to=to_email)
        return False
    subject, html = rebalancing_plan_execution_failed_template(portfolio_name, side, error_message)
    try:
        await _send_html_email(to_email, subject, html)
        logger.info("rebalancing_plan_execution_failed_email_sent", to=to_email, portfolio=portfolio_name, side=side)
        return True
    except Exception as e:
        logger.error("rebalancing_plan_execution_failed_email_failed", to=to_email, error=str(e))
        return False


async def send_tax_impact_gate_blocked_email(
    to_email: str, portfolio_name: str, estimated_tax_krw: float, max_tax_impact_krw: float
) -> bool:
    """세금영향 게이트로 AUTO 계획 생성이 보류됐을 때 발송. 발송 성공 시 True, 이메일 미설정 시 False 반환."""
    if not _email_configured():
        logger.warning("email_not_configured_skip_email", to=to_email)
        return False
    subject, html = tax_impact_gate_blocked_template(portfolio_name, estimated_tax_krw, max_tax_impact_krw)
    try:
        await _send_html_email(to_email, subject, html)
        logger.info("tax_impact_gate_blocked_email_sent", to=to_email, portfolio=portfolio_name)
        return True
    except Exception as e:
        logger.error("tax_impact_gate_blocked_email_failed", to=to_email, error=str(e))
        return False


async def send_market_signal_gate_blocked_email(
    to_email: str, portfolio_name: str, composite_level: str, market_condition_mode: str
) -> bool:
    """시장신호 게이트로 AUTO 계획 생성이 보류됐을 때 발송. 발송 성공 시 True, 이메일 미설정 시 False 반환."""
    if not _email_configured():
        logger.warning("email_not_configured_skip_email", to=to_email)
        return False
    subject, html = market_signal_gate_blocked_template(portfolio_name, composite_level, market_condition_mode)
    try:
        await _send_html_email(to_email, subject, html)
        logger.info("market_signal_gate_blocked_email_sent", to=to_email, portfolio=portfolio_name)
        return True
    except Exception as e:
        logger.error("market_signal_gate_blocked_email_failed", to=to_email, error=str(e))
        return False


async def send_rebalancing_plan_pending_email(
    to_email: str,
    portfolio_name: str,
    account_name: str | None,
    buy_legs: list,
    sell_legs: list,
) -> bool:
    """AUTO 모드 플랜 생성 직후 발송하는 실행 전 계획 안내 이메일. 발송 성공 시 True.

    `buy_legs`/`sell_legs`는 `RebalancingPlanLeg` 객체 리스트(각각 `.market`/`.items`/
    `.deadline_at`/`.action_token_hash`에 대응하는 원문 토큰이 필요) — 국내(KR)/해외(US)
    주문이 섞여 있으면 side당 leg가 최대 2개(KR/US)일 수 있다. 각 leg는 `token` 속성으로
    원문 토큰을 함께 받는다(모델 자체엔 해시만 저장되므로 호출부가 별도로 실어 전달).
    """
    if not _email_configured():
        logger.warning("email_not_configured_skip_email", to=to_email)
        return False

    def _to_section(leg) -> dict:
        return {
            "market": leg.market,
            "items": leg.items,
            "deadline_at": leg.deadline_at,
            "link": f"{settings.frontend_url}/rebalancing/plan-confirm?token={leg.token}",
        }

    buy_sections = [_to_section(leg) for leg in buy_legs]
    sell_sections = [_to_section(leg) for leg in sell_legs]

    subject, html = rebalancing_plan_pending_template(
        portfolio_name,
        account_name,
        buy_sections,
        sell_sections,
    )
    try:
        await _send_html_email(to_email, subject, html)
        logger.info(
            "rebalancing_plan_pending_email_sent",
            to=to_email,
            portfolio=portfolio_name,
            buy_items=sum(len(leg.items) for leg in buy_legs),
            sell_items=sum(len(leg.items) for leg in sell_legs),
        )
        return True
    except Exception as e:
        logger.error("rebalancing_plan_pending_email_failed", to=to_email, error=str(e))
        return False


async def send_stock_price_alert(
    to_email: str,
    ticker: str,
    name: str,
    target_price: float,
    current_price: float,
    direction: str,
) -> bool:
    """주가 목표가 도달 알림 이메일 발송. 발송 성공 시 True, 이메일 미설정/실패 시 False 반환."""
    if not _email_configured():
        logger.warning("email_not_configured_skip_email", to=to_email)
        return False
    subject, html = stock_price_alert_template(ticker, name, target_price, current_price, direction)
    try:
        await _send_html_email(to_email, subject, html)
        logger.info("stock_price_alert_email_sent", to=to_email, ticker=ticker, current_price=current_price)
        return True
    except Exception as e:
        logger.error("stock_price_alert_email_failed", to=to_email, error=str(e))
        return False


async def send_monthly_report_email(
    to_email: str,
    report_month: str,
    total_assets_krw: float,
    mom_change_krw: float | None,
    mom_change_pct: float | None,
    annual_return_pct: float | None,
    xirr_pct: float | None,
    goal_amount: float | None,
    goal_achievement_pct: float | None,
    annual_deposit_goal: float | None,
    deposit_achievement_pct: float | None,
    annual_dividends_received: float,
    asset_allocation: list[dict],
) -> bool:
    """월별 포트폴리오 요약 리포트 이메일 발송. 발송 성공 시 True, 이메일 미설정/실패 시 False 반환."""
    if not _email_configured():
        logger.warning("email_not_configured_skip_email", to=to_email)
        return False
    subject, html = monthly_report_template(
        report_month,
        total_assets_krw,
        mom_change_krw,
        mom_change_pct,
        annual_return_pct,
        xirr_pct,
        goal_amount,
        goal_achievement_pct,
        annual_deposit_goal,
        deposit_achievement_pct,
        annual_dividends_received,
        asset_allocation,
    )
    try:
        await _send_html_email(to_email, subject, html)
        logger.info("monthly_report_email_sent", to=to_email, month=report_month)
        return True
    except Exception as e:
        logger.error("monthly_report_email_failed", to=to_email, error=str(e))
        return False


async def send_goal_achievement_email(
    to_email: str,
    goal_type: str,
    goal_amount: float,
    current_amount: float,
    achievement_pct: float,
) -> bool:
    """투자 목표 달성 알림 이메일 발송. goal_type: 'ASSET' | 'DEPOSIT' | 'DIVIDEND'.

    발송 성공 시 True, 이메일 미설정/실패 시 False 반환.
    """
    if not _email_configured():
        logger.warning("email_not_configured_skip_email", to=to_email)
        return False
    subject, html = goal_achievement_template(goal_type, goal_amount, current_amount, achievement_pct)
    try:
        await _send_html_email(to_email, subject, html)
        logger.info("goal_achievement_email_sent", to=to_email, goal_type=goal_type, pct=achievement_pct)
        return True
    except Exception as e:
        logger.error("goal_achievement_email_failed", to=to_email, error=str(e))
        return False


async def send_test_email(to_email: str) -> bool:
    """이메일 설정 확인용 테스트 이메일 발송.

    이메일 미설정 시에는 호출부(설정 진단 API)가 구분된 응답을 내려줄 수 있도록
    RuntimeError("email_not_configured")를 발생시킨다. 발송 자체가 실패하면
    다른 send_* 함수와 동일하게 예외를 삼키고 False를 반환한다.
    """
    if not _email_configured():
        raise RuntimeError("email_not_configured")
    subject, html = test_email_template()
    try:
        await _send_html_email(to_email, subject, html)
        logger.info("test_email_sent", to=to_email)
        return True
    except Exception as e:
        logger.error("test_email_failed", to=to_email, error=str(e))
        return False


async def send_password_reset_email(to_email: str, reset_link: str) -> bool:
    """비밀번호 재설정 링크 이메일 발송. 발송 성공 시 True, 이메일 미설정/실패 시 False 반환."""
    if not _email_configured():
        logger.warning("email_not_configured_skip_password_reset_email", to=to_email, reset_link=reset_link)
        return False
    subject, html = password_reset_template(reset_link)
    try:
        await _send_html_email(to_email, subject, html)
        logger.info("password_reset_email_sent", to=to_email)
        return True
    except Exception as e:
        logger.error("password_reset_email_failed", to=to_email, error=str(e))
        return False


async def send_account_deletion_email(to_email: str) -> bool:
    """회원 탈퇴 완료 안내 이메일 발송. 발송 성공 시 True, 이메일 미설정/실패 시 False 반환."""
    if not _email_configured():
        logger.warning("email_not_configured_skip_account_deletion_email", to=to_email)
        return False
    subject, html = account_deletion_template()
    try:
        await _send_html_email(to_email, subject, html)
        logger.info("account_deletion_email_sent", to=to_email)
        return True
    except Exception as e:
        logger.error("account_deletion_email_failed", to=to_email, error=str(e))
        return False


async def send_market_signal_change_alert(
    to_email: str,
    old_level: str,
    new_level: str,
    reason: str | None = None,
) -> bool:
    """시장 위험 신호등 등급 변경 알림 이메일 발송. 발송 성공 시 True, 이메일 미설정/실패 시 False 반환."""
    if not _email_configured():
        logger.warning("email_not_configured_skip_email", to=to_email)
        return False
    subject, html = market_signal_change_template(old_level, new_level, reason)
    try:
        await _send_html_email(to_email, subject, html)
        logger.info("market_signal_change_email_sent", to=to_email, old_level=old_level, new_level=new_level)
        return True
    except Exception as e:
        logger.error("market_signal_change_email_failed", to=to_email, error=str(e))
        return False


async def send_year_end_tax_reminder_email(to_email: str, content: Mapping[str, Any]) -> bool:
    """연말 절세 리마인더 이메일 발송. 발송 성공 시 True, 이메일 미설정/실패 시 False 반환."""
    if not _email_configured():
        logger.warning("email_not_configured_skip_email", to=to_email)
        return False
    subject, html = year_end_tax_reminder_template(content)
    try:
        await _send_html_email(to_email, subject, html)
        logger.info("year_end_tax_reminder_email_sent", to=to_email)
        return True
    except Exception as e:
        logger.error("year_end_tax_reminder_email_failed", to=to_email, error=str(e))
        return False


async def send_market_signal_daily_digest_alert(to_email: str, level: str, reason: str | None) -> bool:
    """매일 시장 신호 요약 이메일 발송. 발송 성공 시 True, 이메일 미설정/실패 시 False 반환."""
    if not _email_configured():
        logger.warning("email_not_configured_skip_email", to=to_email)
        return False
    subject, html = market_signal_daily_digest_template(level, reason)
    try:
        await _send_html_email(to_email, subject, html)
        logger.info("market_signal_daily_digest_email_sent", to=to_email, level=level)
        return True
    except Exception as e:
        logger.error("market_signal_daily_digest_email_failed", to=to_email, error=str(e))
        return False


async def send_recommendation_drift_alert_email(to_email: str, portfolio_names: list[str]) -> bool:
    """추천 비중 변화 알림 이메일 발송. 발송 성공 시 True, 이메일 미설정/실패 시 False 반환."""
    if not _email_configured():
        logger.warning("email_not_configured_skip_email", to=to_email)
        return False
    app_link = f"{settings.frontend_url}/rebalancing?rtab={quote('포트폴리오')}"
    subject, html = recommendation_drift_alert_template(portfolio_names, app_link)
    try:
        await _send_html_email(to_email, subject, html)
        logger.info("recommendation_drift_alert_email_sent", to=to_email, portfolio_count=len(portfolio_names))
        return True
    except Exception as e:
        logger.error("recommendation_drift_alert_email_failed", to=to_email, error=str(e))
        return False
