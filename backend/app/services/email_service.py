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
