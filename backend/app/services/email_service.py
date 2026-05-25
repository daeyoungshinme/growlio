"""이메일 발송 서비스 (aiosmtplib SMTP)."""
from __future__ import annotations

import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib
import structlog

from app.config import settings

logger = structlog.get_logger()


async def send_exchange_rate_alert(
    to_email: str,
    target_rate: float,
    direction: str,
    current_rate: float,
) -> None:
    """목표환율 도달 알림 이메일 발송."""
    if not settings.smtp_host or not settings.smtp_user:
        logger.warning("smtp_not_configured_skip_email", to=to_email)
        return

    direction_label = "이하" if direction == "BELOW" else "이상"
    subject = f"[Growlio] 목표환율 도달 알림 — {target_rate:,.0f}원 {direction_label}"

    html = f"""
    <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto;">
      <h2 style="color: #1d4ed8;">목표환율 도달 알림</h2>
      <table style="width:100%; border-collapse: collapse; margin-top: 16px;">
        <tr>
          <td style="padding: 8px; background: #f1f5f9; font-weight: bold;">목표환율</td>
          <td style="padding: 8px;">{target_rate:,.0f} 원 ({direction_label})</td>
        </tr>
        <tr>
          <td style="padding: 8px; background: #f1f5f9; font-weight: bold;">현재환율</td>
          <td style="padding: 8px; color: #1d4ed8; font-weight: bold;">{current_rate:,.2f} 원</td>
        </tr>
      </table>
      <p style="margin-top: 20px; color: #64748b; font-size: 13px;">
        이 알림은 설정하신 목표환율 조건이 충족되어 발송되었습니다.<br>
        알림은 1회 발동 후 자동으로 비활성화됩니다.
      </p>
    </div>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from
    msg["To"] = to_email
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        ctx = ssl.create_default_context()
        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user,
            password=settings.smtp_password,
            start_tls=True,
            tls_context=ctx,
        )
        logger.info("exchange_rate_alert_email_sent", to=to_email, target_rate=target_rate, current_rate=current_rate)
    except Exception as e:
        logger.error("exchange_rate_alert_email_failed", to=to_email, error=str(e))
        raise


async def send_password_reset_email(to_email: str, reset_link: str) -> None:
    """비밀번호 재설정 링크 이메일 발송."""
    if not settings.smtp_host or not settings.smtp_user:
        logger.warning("smtp_not_configured_skip_password_reset_email", to=to_email, reset_link=reset_link)
        return

    subject = "[Growlio] 비밀번호 재설정 안내"

    html = f"""
    <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto;">
      <h2 style="color: #1d4ed8;">비밀번호 재설정</h2>
      <p style="color: #374151; margin-top: 16px;">
        비밀번호 재설정을 요청하셨습니다. 아래 버튼을 클릭하여 새 비밀번호를 설정해주세요.
      </p>
      <div style="margin: 24px 0; text-align: center;">
        <a href="{reset_link}"
           style="display: inline-block; background: #1d4ed8; color: #ffffff; text-decoration: none;
                  padding: 12px 28px; border-radius: 8px; font-weight: bold; font-size: 15px;">
          비밀번호 재설정
        </a>
      </div>
      <p style="color: #64748b; font-size: 13px;">
        이 링크는 1시간 후에 만료됩니다.<br>
        본인이 요청하지 않은 경우 이 이메일을 무시하시면 됩니다.
      </p>
      <p style="color: #9ca3af; font-size: 12px; margin-top: 16px;">
        링크가 클릭되지 않으면 아래 URL을 브라우저에 직접 입력해주세요:<br>
        <span style="color: #6b7280;">{reset_link}</span>
      </p>
    </div>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from
    msg["To"] = to_email
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        ctx = ssl.create_default_context()
        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user,
            password=settings.smtp_password,
            start_tls=True,
            tls_context=ctx,
        )
        logger.info("password_reset_email_sent", to=to_email)
    except Exception as e:
        logger.error("password_reset_email_failed", to=to_email, error=str(e))
        raise
