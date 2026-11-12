"""단순 임계값 도달 알림(환율/주가) + 연결 테스트 이메일 템플릿."""

from __future__ import annotations

from html import escape

from app.services.notifications.email_templates._shared import _email_div, _kv_table


def exchange_rate_alert_template(
    target_rate: float,
    direction: str,
    current_rate: float,
    planned_usd: float | None = None,
    plan_link: str | None = None,
    plan_label: str | None = None,
) -> tuple[str, str]:
    """`planned_usd`가 있으면 달러 환전 계획 구간 알림(plans/121) — 환전할 금액과 계획 화면 링크를 함께 싣는다.

    `plan_label`이 있으면 추가 환전 항목(여행 등, plans/123) 구간이다 — 제목에 항목 이름을 싣고,
    증권 계좌 동기화 대신 앱에서 이미 환전한 금액을 고치도록 안내한다.
    """
    direction_label = "이하" if direction == "BELOW" else "이상"
    rows = [
        ("목표환율", f"{target_rate:,.0f} 원 ({direction_label})"),
        ("현재환율", f"<span style='color:#1d4ed8;font-weight:bold;'>{current_rate:,.2f} 원</span>"),
    ]
    if planned_usd is not None:
        title = f"{plan_label} 환전 구간 도달" if plan_label else "환전 계획 구간 도달"
        title_html = f"{escape(plan_label)} 환전 구간 도달" if plan_label else title
        subject = f"[Growlio] {title} — {target_rate:,.0f}원 {direction_label}, ${planned_usd:,.0f} 환전"
        rows.append(
            (
                "이번 구간 환전",
                f"<b>${planned_usd:,.0f}</b> (약 {planned_usd * current_rate:,.0f}원)",
            )
        )
        link_html = (
            f"<p style='margin-top:16px;'><a href='{plan_link}' style='color:#2563eb;'>앱에서 환전 계획 보기</a></p>"
            if plan_link
            else ""
        )
        guide = (
            "이번 구간 금액을 환전하세요. 환전한 뒤 앱에서 이미 환전한 금액을 고치면 남은 계획이 다시 계산됩니다."
            if plan_label
            else "증권사 앱에서 이번 구간 금액을 환전하세요. 환전 후 계좌를 동기화하면 남은 계획이 다시 계산됩니다."
        )
        html = _email_div(
            title_html,
            "#1d4ed8",
            _kv_table(rows) + link_html,
            f"{guide}<br>이 알림은 1회 발동 후 자동으로 비활성화됩니다.",
        )
        return subject, html

    subject = f"[Growlio] 목표환율 도달 알림 — {target_rate:,.0f}원 {direction_label}"
    html = _email_div(
        "목표환율 도달 알림",
        "#1d4ed8",
        _kv_table(rows),
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
