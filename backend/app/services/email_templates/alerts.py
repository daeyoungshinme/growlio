"""단순 임계값 도달 알림(환율/주가) + 연결 테스트 이메일 템플릿."""

from __future__ import annotations

from app.services.email_templates._shared import _email_div, _kv_table


def exchange_rate_alert_template(
    target_rate: float,
    direction: str,
    current_rate: float,
) -> tuple[str, str]:
    direction_label = "이하" if direction == "BELOW" else "이상"
    subject = f"[Growlio] 목표환율 도달 알림 — {target_rate:,.0f}원 {direction_label}"
    table = _kv_table(
        [
            ("목표환율", f"{target_rate:,.0f} 원 ({direction_label})"),
            ("현재환율", f"<span style='color:#1d4ed8;font-weight:bold;'>{current_rate:,.2f} 원</span>"),
        ]
    )
    html = _email_div(
        "목표환율 도달 알림",
        "#1d4ed8",
        table,
        "이 알림은 설정하신 목표환율 조건이 충족되어 발송되었습니다.<br>알림은 1회 발동 후 자동으로 비활성화됩니다.",
    )
    return subject, html


def stock_price_alert_template(
    ticker: str,
    name: str,
    target_price: float,
    current_price: float,
    direction: str,
) -> tuple[str, str]:
    direction_label = "이하" if direction == "BELOW" else "이상"
    subject = f"[Growlio] 주가 목표 도달 — {name}({ticker}) {target_price:,.0f}원 {direction_label}"
    table = _kv_table(
        [
            ("종목", f"{name} ({ticker})"),
            ("목표가", f"{target_price:,.0f}원 ({direction_label})"),
            ("현재가", f"<span style='color:#1d4ed8;font-weight:bold;'>{current_price:,.0f}원</span>"),
        ]
    )
    html = _email_div(
        "주가 목표 도달 알림",
        "#1d4ed8",
        table,
        "설정하신 주가 목표 조건이 충족되어 발송되었습니다.",
    )
    return subject, html


def test_email_template() -> tuple[str, str]:
    subject = "[Growlio] 이메일 알림 설정 확인"
    body = (
        "<p style='color:#374151;margin-top:16px;'>"
        "Growlio 목표환율 알림 이메일이 정상적으로 설정되었습니다.<br>"
        "목표환율 조건이 충족되면 이 주소로 알림이 발송됩니다.</p>"
        "<p style='color:#64748b;font-size:13px;margin-top:20px;'>"
        "본인이 요청하지 않은 경우 이 이메일을 무시하세요.</p>"
    )
    html = _email_div("이메일 알림 연결 완료", "#1d4ed8", body)
    return subject, html
