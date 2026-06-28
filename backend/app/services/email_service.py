"""이메일 발송 서비스 (aiosmtplib SMTP)."""

from __future__ import annotations

import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings
from app.services.email_templates import (
    deposit_trigger_alert_template,
    exchange_rate_alert_template,
    goal_achievement_template,
    indicator_alert_template,
    monthly_report_template,
    password_reset_template,
    rebalancing_alert_template,
    stock_price_alert_template,
    test_email_template,
)

logger = structlog.get_logger()


@retry(
    retry=retry_if_exception_type((aiosmtplib.SMTPConnectError, TimeoutError, OSError)),
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
async def _send_html_email(to_email: str, subject: str, html: str) -> None:
    """HTML 이메일을 SMTP로 발송한다. 실패 시 예외를 그대로 전파한다."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from
    msg["To"] = to_email
    msg.attach(MIMEText(html, "html", "utf-8"))

    ctx = ssl.create_default_context()
    await aiosmtplib.send(
        msg,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_user,
        password=settings.smtp_password,
        start_tls=True,
        tls_context=ctx,
        timeout=settings.smtp_timeout,
    )


def _smtp_configured() -> bool:
    return bool(settings.smtp_host and settings.smtp_user)


async def send_exchange_rate_alert(
    to_email: str,
    target_rate: float,
    direction: str,
    current_rate: float,
) -> None:
    """목표환율 도달 알림 이메일 발송."""
    if not _smtp_configured():
        logger.warning("smtp_not_configured_skip_email", to=to_email)
        return
    subject, html = exchange_rate_alert_template(target_rate, direction, current_rate)
    try:
        await _send_html_email(to_email, subject, html)
        logger.info("exchange_rate_alert_email_sent", to=to_email, target_rate=target_rate, current_rate=current_rate)
    except Exception as e:
        logger.error("exchange_rate_alert_email_failed", to=to_email, error=str(e))
        raise


async def send_rebalancing_alert(
    to_email: str,
    portfolio_name: str,
    threshold_pct: float,
    items_to_show: list,
    drifting_count: int,
    is_scheduled_report: bool = False,
    schedule_type: str = "DAILY",
) -> bool:
    """리밸런싱 알림 이메일 발송. 발송 성공 시 True, SMTP 미설정 시 False 반환."""
    if not _smtp_configured():
        logger.warning("smtp_not_configured_skip_email", to=to_email)
        return False
    subject, html = rebalancing_alert_template(
        portfolio_name, threshold_pct, items_to_show, drifting_count, is_scheduled_report, schedule_type
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
        raise


async def send_deposit_trigger_alert(
    to_email: str,
    portfolio_name: str,
    deposit_increment: float,
    items: list[dict],
) -> None:
    """예수금 입금 감지 알림 이메일 발송."""
    if not _smtp_configured():
        logger.warning("smtp_not_configured_skip_email", to=to_email)
        return
    subject, html = deposit_trigger_alert_template(portfolio_name, deposit_increment, items)
    try:
        await _send_html_email(to_email, subject, html)
        logger.info(
            "deposit_trigger_alert_email_sent",
            to=to_email,
            portfolio=portfolio_name,
            increment=deposit_increment,
        )
    except Exception as exc:
        logger.error("deposit_trigger_alert_email_failed", to=to_email, error=str(exc))
        raise


async def send_stock_price_alert(
    to_email: str,
    ticker: str,
    name: str,
    target_price: float,
    current_price: float,
    direction: str,
) -> None:
    """주가 목표가 도달 알림 이메일 발송."""
    if not _smtp_configured():
        logger.warning("smtp_not_configured_skip_email", to=to_email)
        return
    subject, html = stock_price_alert_template(ticker, name, target_price, current_price, direction)
    try:
        await _send_html_email(to_email, subject, html)
        logger.info("stock_price_alert_email_sent", to=to_email, ticker=ticker, current_price=current_price)
    except Exception as e:
        logger.error("stock_price_alert_email_failed", to=to_email, error=str(e))
        raise


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
) -> None:
    """월별 포트폴리오 요약 리포트 이메일 발송."""
    if not _smtp_configured():
        logger.warning("smtp_not_configured_skip_email", to=to_email)
        return
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
    except Exception as e:
        logger.error("monthly_report_email_failed", to=to_email, error=str(e))
        raise


async def send_goal_achievement_email(
    to_email: str,
    goal_type: str,
    goal_amount: float,
    current_amount: float,
    achievement_pct: float,
) -> None:
    """투자 목표 달성 알림 이메일 발송. goal_type: 'ASSET' | 'DEPOSIT'."""
    if not _smtp_configured():
        logger.warning("smtp_not_configured_skip_email", to=to_email)
        return
    subject, html = goal_achievement_template(goal_type, goal_amount, current_amount, achievement_pct)
    try:
        await _send_html_email(to_email, subject, html)
        logger.info("goal_achievement_email_sent", to=to_email, goal_type=goal_type, pct=achievement_pct)
    except Exception as e:
        logger.error("goal_achievement_email_failed", to=to_email, error=str(e))
        raise


async def send_test_email(to_email: str) -> None:
    """이메일 설정 확인용 테스트 이메일 발송."""
    if not _smtp_configured():
        raise RuntimeError("smtp_not_configured")
    subject, html = test_email_template()
    try:
        await _send_html_email(to_email, subject, html)
        logger.info("test_email_sent", to=to_email)
    except Exception as e:
        logger.error("test_email_failed", to=to_email, error=str(e))
        raise


async def send_password_reset_email(to_email: str, reset_link: str) -> None:
    """비밀번호 재설정 링크 이메일 발송."""
    if not _smtp_configured():
        logger.warning("smtp_not_configured_skip_password_reset_email", to=to_email, reset_link=reset_link)
        return
    subject, html = password_reset_template(reset_link)
    try:
        await _send_html_email(to_email, subject, html)
        logger.info("password_reset_email_sent", to=to_email)
    except Exception as e:
        logger.error("password_reset_email_failed", to=to_email, error=str(e))


async def send_indicator_alert_email(
    to_email: str,
    indicators: list[dict],
) -> None:
    """경제지표 발표 알림 이메일 발송."""
    if not _smtp_configured():
        logger.warning("smtp_not_configured_skip_email", to=to_email)
        return
    subject, html = indicator_alert_template(indicators)
    try:
        await _send_html_email(to_email, subject, html)
        logger.info("indicator_alert_email_sent", to=to_email, count=len(indicators))
    except Exception as e:
        logger.error("indicator_alert_email_failed", to=to_email, error=str(e))
        raise
