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


_SCHEDULE_LABEL: dict[str, str] = {
    "DAILY": "매일",
    "WEEKLY": "매주",
    "MONTHLY": "매월",
    "QUARTERLY": "매 3개월",
    "SEMIANNUAL": "매 6개월",
    "ANNUAL": "매년",
}


async def send_rebalancing_alert(
    to_email: str,
    portfolio_name: str,
    threshold_pct: float,
    items_to_show: list,
    drifting_count: int,
    is_scheduled_report: bool = False,
    schedule_type: str = "DAILY",
) -> None:
    """리밸런싱 알림 이메일 발송.

    is_scheduled_report=True: 전체 종목 주기 리포트 (이탈 종목 강조)
    is_scheduled_report=False: 이탈 종목만 포함한 드리프트 알림
    """
    if not settings.smtp_host or not settings.smtp_user:
        logger.warning("smtp_not_configured_skip_email", to=to_email)
        return

    schedule_label = _SCHEDULE_LABEL.get(schedule_type, "주기")
    if is_scheduled_report:
        subject = f"[Growlio] {schedule_label} 리밸런싱 리포트 — {portfolio_name}"
        heading = "정기 리밸런싱 현황"
        subheading = (
            f"포트폴리오 <strong>{portfolio_name}</strong>의 {schedule_label} 리밸런싱 현황입니다."
        )
        if drifting_count:
            subheading += f" 현재 <strong style='color:#f59e0b;'>{drifting_count}개 종목</strong>이 목표 비중에서 ±{threshold_pct:.1f}% 이상 이탈했습니다."
    else:
        subject = f"[Growlio] 리밸런싱 알림 — {portfolio_name} (비중 이탈 감지)"
        heading = "비중 이탈 감지"
        subheading = (
            f"포트폴리오 <strong>{portfolio_name}</strong>의 {len(items_to_show)}개 종목이 "
            f"목표 비중에서 ±{threshold_pct:.1f}% 이상 벗어났습니다."
        )

    rows_html = ""
    for item in items_to_show:
        diff = float(item.weight_diff_pct)
        is_drifting = abs(diff) > threshold_pct
        direction = "매수 필요" if diff > 0 else ("매도 필요" if diff < 0 else "—")
        action_color = "#ef4444" if diff > 0 else ("#3b82f6" if diff < 0 else "#6b7280")
        diff_krw = float(item.diff_krw) if item.diff_krw is not None else 0.0
        row_bg = "background:#fffbeb;" if is_drifting else ""
        bold = "font-weight:bold;" if is_drifting else ""
        rows_html += (
            f"<tr style='{row_bg}'>"
            f"<td style='padding:8px;border-bottom:1px solid #e2e8f0;{bold}'>{item.name} ({item.ticker})</td>"
            f"<td style='padding:8px;border-bottom:1px solid #e2e8f0;text-align:right;'>{float(item.target_weight_pct):.1f}%</td>"
            f"<td style='padding:8px;border-bottom:1px solid #e2e8f0;text-align:right;'>{float(item.current_weight_pct):.1f}%</td>"
            f"<td style='padding:8px;border-bottom:1px solid #e2e8f0;text-align:right;color:{action_color};{bold}'>{diff:+.1f}%</td>"
            f"<td style='padding:8px;border-bottom:1px solid #e2e8f0;text-align:right;'>{diff_krw:+,.0f}원</td>"
            f"<td style='padding:8px;border-bottom:1px solid #e2e8f0;text-align:right;color:{action_color};'>{direction}</td>"
            f"</tr>"
        )

    footer = (
        "Growlio 앱에서 리밸런싱 분석을 실행하여 상세 내역을 확인하세요."
        f"<br>이 알림은 {schedule_label} 발송됩니다."
    )

    html = f"""
    <div style="font-family:sans-serif;max-width:640px;margin:0 auto;">
      <h2 style="color:#1d4ed8;">{heading}</h2>
      <p style="color:#374151;margin-top:8px;">{subheading}</p>
      <table style="width:100%;border-collapse:collapse;margin-top:16px;font-size:13px;">
        <thead>
          <tr style="background:#f1f5f9;">
            <th style="padding:8px;text-align:left;">종목</th>
            <th style="padding:8px;text-align:right;">목표 비중</th>
            <th style="padding:8px;text-align:right;">현재 비중</th>
            <th style="padding:8px;text-align:right;">차이</th>
            <th style="padding:8px;text-align:right;">금액</th>
            <th style="padding:8px;text-align:right;">조치</th>
          </tr>
        </thead>
        <tbody>{rows_html}</tbody>
      </table>
      <p style="margin-top:20px;color:#64748b;font-size:13px;">{footer}</p>
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
        logger.info(
            "rebalancing_alert_email_sent",
            to=to_email,
            portfolio=portfolio_name,
            items=len(items_to_show),
            drifting=drifting_count,
            is_scheduled=is_scheduled_report,
        )
    except Exception as e:
        logger.error("rebalancing_alert_email_failed", to=to_email, error=str(e))
        raise


async def send_test_email(to_email: str) -> None:
    """이메일 설정 확인용 테스트 이메일 발송."""
    if not settings.smtp_host or not settings.smtp_user:
        raise RuntimeError("smtp_not_configured")

    subject = "[Growlio] 이메일 알림 설정 확인"
    html = """
    <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto;">
      <h2 style="color: #1d4ed8;">이메일 알림 연결 완료</h2>
      <p style="color: #374151; margin-top: 16px;">
        Growlio 목표환율 알림 이메일이 정상적으로 설정되었습니다.<br>
        목표환율 조건이 충족되면 이 주소로 알림이 발송됩니다.
      </p>
      <p style="color: #64748b; font-size: 13px; margin-top: 20px;">
        본인이 요청하지 않은 경우 이 이메일을 무시하세요.
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
        logger.info("test_email_sent", to=to_email)
    except Exception as e:
        logger.error("test_email_failed", to=to_email, error=str(e))
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
