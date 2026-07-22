"""이메일 HTML 템플릿 빌더 — 순수 함수, I/O 없음."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any


def _kv_table(rows: list[tuple[str, str]]) -> str:
    """key-value 2열 테이블. 각 행: (label, value_html)."""
    td_label = "padding:8px;background:#f1f5f9;font-weight:bold;"
    td_value = "padding:8px;"
    trs = "".join(
        f"<tr><td style='{td_label}'>{label}</td><td style='{td_value}'>{value}</td></tr>" for label, value in rows
    )
    return f"<table style='width:100%;border-collapse:collapse;margin-top:16px;'>{trs}</table>"


def _email_div(heading: str, heading_color: str, body: str, footer: str = "") -> str:
    """표준 이메일 감싸기."""
    footer_html = f"<p style='margin-top:20px;color:#64748b;font-size:13px;'>{footer}</p>" if footer else ""
    return (
        f"<div style='font-family:sans-serif;max-width:520px;margin:0 auto;'>"
        f"<h2 style='color:{heading_color};'>{heading}</h2>"
        f"{body}"
        f"{footer_html}"
        f"</div>"
    )


# ---------------------------------------------------------------------------
# 공개 템플릿 함수 (subject, html) 반환
# ---------------------------------------------------------------------------


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


def _order_preview_table(items: list) -> str:
    """NOTIFY 리포트용 예상 매수/매도 수량 표 (참고용, 링크/버튼 없음). items: ExecutionOrderItem 목록."""
    td = "padding:8px;border-bottom:1px solid #e2e8f0;font-size:13px;"
    rows_html = ""
    for item in items:
        side = getattr(item, "side", None)
        side_label = "매수" if side == "BUY" else ("매도" if side == "SELL" else "—")
        side_color = "#ef4444" if side == "BUY" else "#3b82f6"
        ticker = getattr(item, "ticker", "") or ""
        name = getattr(item, "name", "") or ticker
        qty = getattr(item, "quantity", 0) or 0
        price = getattr(item, "limit_price", None) or getattr(item, "reference_price", None)
        price_str = f"{float(price):,.0f}" if price else "—"
        rows_html += (
            f"<tr>"
            f"<td style='{td}'>{name}<br><span style='color:#6b7280;font-size:11px;'>{ticker}</span></td>"
            f"<td style='{td}text-align:center;color:{side_color};font-weight:bold;'>{side_label}</td>"
            f"<td style='{td}text-align:right;'>{qty:,}주</td>"
            f"<td style='{td}text-align:right;'>{price_str}</td>"
            f"</tr>"
        )
    return (
        f"<p style='color:#374151;margin-top:16px;font-weight:bold;'>예상 매수/매도 수량 (참고용)</p>"
        f"<table style='width:100%;border-collapse:collapse;margin-top:4px;'>"
        f"<thead><tr style='background:#f1f5f9;'>"
        f"<th style='padding:8px;text-align:left;font-size:13px;'>종목</th>"
        f"<th style='padding:8px;text-align:center;font-size:13px;'>구분</th>"
        f"<th style='padding:8px;text-align:right;font-size:13px;'>수량</th>"
        f"<th style='padding:8px;text-align:right;font-size:13px;'>참고가</th>"
        f"</tr></thead><tbody>{rows_html}</tbody></table>"
    )


def _plan_items_table(items: list) -> str:
    """플랜 대기 이메일용 leg 내 종목 표 (side는 섹션 제목으로 이미 표시되므로 열에 포함 안 함)."""
    td = "padding:8px;border-bottom:1px solid #e2e8f0;font-size:13px;"
    rows_html = ""
    for item in items:
        ticker = getattr(item, "ticker", "") or ""
        name = getattr(item, "name", "") or ticker
        qty = getattr(item, "quantity", 0) or 0
        order_type = getattr(item, "order_type", "MARKET")
        type_label = "지정가" if order_type == "LIMIT" else "시장가"
        price = getattr(item, "limit_price", None) or getattr(item, "reference_price", None)
        price_str = f"{float(price):,.0f}" if price else "—"
        rows_html += (
            f"<tr>"
            f"<td style='{td}'>{name}<br><span style='color:#6b7280;font-size:11px;'>{ticker}</span></td>"
            f"<td style='{td}text-align:right;'>{qty:,}주</td>"
            f"<td style='{td}text-align:center;'>{type_label}</td>"
            f"<td style='{td}text-align:right;'>{price_str}</td>"
            f"</tr>"
        )
    return (
        f"<table style='width:100%;border-collapse:collapse;margin-top:8px;'>"
        f"<thead><tr style='background:#f1f5f9;'>"
        f"<th style='padding:8px;text-align:left;font-size:13px;'>종목</th>"
        f"<th style='padding:8px;text-align:right;font-size:13px;'>수량</th>"
        f"<th style='padding:8px;text-align:center;font-size:13px;'>주문유형</th>"
        f"<th style='padding:8px;text-align:right;font-size:13px;'>참고가</th>"
        f"</tr></thead><tbody>{rows_html}</tbody></table>"
    )


def rebalancing_alert_template(
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
    app_link: str | None = None,
    automation_note: str | None = None,
) -> tuple[str, str]:
    _SCHEDULE_LABEL: dict[str, str] = {
        "DAILY": "매일",
        "WEEKLY": "매주",
        "MONTHLY": "매월",
        "QUARTERLY": "매 3개월",
        "SEMIANNUAL": "매 6개월",
        "ANNUAL": "매년",
    }
    schedule_label = _SCHEDULE_LABEL.get(schedule_type, "주기")

    test_prefix = "[테스트] " if is_test else ""
    test_banner = (
        (
            "<div style='background:#fef3c7;border:1px solid #f59e0b;border-radius:8px;"
            "padding:10px 14px;margin-bottom:16px;font-size:13px;color:#92400e;'>"
            "⚠️ 이것은 테스트 알림입니다. 실제 리밸런싱 조건과 무관하게 발송되었습니다."
            "</div>"
        )
        if is_test
        else ""
    )
    automation_note_banner = (
        (
            "<div style='background:#fef3c7;border:1px solid #f59e0b;border-radius:8px;"
            "padding:10px 14px;margin-bottom:16px;font-size:13px;color:#92400e;'>"
            f"{automation_note}"
            "</div>"
        )
        if automation_note
        else ""
    )

    if is_composite_triggered and not drifting_count:
        # 복합신호는 특정 포트폴리오가 아닌 계정 전체 기준으로 평가되므로 포트폴리오명을 노출하지 않는다.
        subject = f"{test_prefix}[Growlio] 시장/리스크 신호 감지 — 포트폴리오 점검 권장"
        heading = "시장/리스크 신호 감지"
        subheading = f"현재 목표 비중 이탈은 없지만, {composite_reason}. 보유 포트폴리오 점검을 권장합니다."
    elif is_scheduled_report:
        subject = f"{test_prefix}[Growlio] {schedule_label} 리밸런싱 리포트 — {portfolio_name}"
        heading = "정기 리밸런싱 현황"
        subheading = f"포트폴리오 <strong>{portfolio_name}</strong>의 {schedule_label} 리밸런싱 현황입니다."
        if drifting_count:
            subheading += (
                f" 현재 <strong style='color:#f59e0b;'>{drifting_count}개 종목</strong>이 "
                f"목표 비중에서 ±{threshold_pct:.1f}% 이상 이탈했습니다."
            )
    else:
        subject = f"{test_prefix}[Growlio] 리밸런싱 알림 — {portfolio_name} (비중 이탈 감지)"
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
        td = "padding:8px;border-bottom:1px solid #e2e8f0;"
        rows_html += (
            f"<tr style='{row_bg}'>"
            f"<td style='{td}{bold}'>{item.name} ({item.ticker})</td>"
            f"<td style='{td}text-align:right;'>{float(item.target_weight_pct):.1f}%</td>"
            f"<td style='{td}text-align:right;'>{float(item.current_weight_pct):.1f}%</td>"
            f"<td style='{td}text-align:right;color:{action_color};{bold}'>{diff:+.1f}%</td>"
            f"<td style='{td}text-align:right;'>{diff_krw:+,.0f}원</td>"
            f"<td style='{td}text-align:right;color:{action_color};'>{direction}</td>"
            f"</tr>"
        )

    if is_composite_triggered and not drifting_count:
        footer = (
            "Growlio 앱에서 리밸런싱 분석을 실행하여 상세 내역을 확인하세요.<br>"
            "이 알림은 시장/리스크 신호가 감지될 때 최대 하루 1회 발송됩니다.<br>"
            "알림 설정은 설정 &gt; 알림 설정 &gt; 시장 신호 알림에서 변경하세요."
        )
    else:
        footer = (
            f"Growlio 앱에서 리밸런싱 분석을 실행하여 상세 내역을 확인하세요.<br>이 알림은 {schedule_label} 발송됩니다."
        )
    order_preview_html = _order_preview_table(order_preview_items) if order_preview_items else ""
    cta_html = (
        f"<a href='{app_link}' style='display:inline-block;padding:10px 20px;border-radius:8px;"
        f"font-weight:bold;font-size:14px;text-decoration:none;margin-top:16px;"
        f"background:#1d4ed8;color:#ffffff;'>앱에서 확인하기</a>"
        if app_link
        else ""
    )
    body = (
        f"{test_banner}"
        f"{automation_note_banner}"
        f"<p style='color:#374151;margin-top:8px;'>{subheading}</p>"
        f"<table style='width:100%;border-collapse:collapse;margin-top:16px;font-size:13px;'>"
        f"<thead><tr style='background:#f1f5f9;'>"
        f"<th style='padding:8px;text-align:left;'>종목</th>"
        f"<th style='padding:8px;text-align:right;'>목표 비중</th>"
        f"<th style='padding:8px;text-align:right;'>현재 비중</th>"
        f"<th style='padding:8px;text-align:right;'>차이</th>"
        f"<th style='padding:8px;text-align:right;'>금액</th>"
        f"<th style='padding:8px;text-align:right;'>조치</th>"
        f"</tr></thead>"
        f"<tbody>{rows_html}</tbody></table>"
        f"{order_preview_html}"
        f"{cta_html}"
    )
    html = _email_div(heading, "#1d4ed8", body, footer)
    return subject, html


def rebalancing_execution_template(
    portfolio_name: str,
    executed_at: datetime,
    result_items: list,
    total_success: int,
    total_fail: int,
    total_skipped: int,
) -> tuple[str, str]:
    """리밸런싱 자동 실행 완료 이메일 템플릿."""
    has_fail = total_fail > 0
    heading_color = "#ef4444" if has_fail else "#16a34a"
    heading = "리밸런싱 자동 실행 완료" if not has_fail else "리밸런싱 자동 실행 완료 (일부 실패)"
    subject = f"[Growlio] 리밸런싱 자동 실행 완료 — {portfolio_name}"

    _KST_OFFSET = 9 * 3600
    kst_time = datetime.fromtimestamp(executed_at.timestamp() + _KST_OFFSET)
    time_str = kst_time.strftime("%Y-%m-%d %H:%M KST")

    _ACTION_LABEL = {"BUY": "매수", "SELL": "매도", "SKIPPED": "건너뜀"}
    _STATUS_COLOR = {"SUCCESS": "#16a34a", "FAILED": "#ef4444", "SKIPPED": "#6b7280"}
    _STATUS_LABEL = {"SUCCESS": "성공", "FAILED": "실패", "SKIPPED": "건너뜀"}

    td = "padding:8px;border-bottom:1px solid #e2e8f0;font-size:13px;"
    rows_html = ""
    for item in result_items:
        action = getattr(item, "action", "")
        status = getattr(item, "status", "")
        ticker = getattr(item, "ticker", "") or ""
        name = getattr(item, "name", "") or ""
        quantity = getattr(item, "quantity", None)
        error_msg = getattr(item, "error_message", None)
        status_color = _STATUS_COLOR.get(status, "#6b7280")
        status_label = _STATUS_LABEL.get(status, status)
        action_label = _ACTION_LABEL.get(action, action)
        qty_str = f"{quantity:,}주" if quantity else "—"
        error_html = (
            f"<br><span style='font-size:11px;color:#ef4444;'>{error_msg}</span>"
            if error_msg and status == "FAILED"
            else ""
        )
        rows_html += (
            f"<tr>"
            f"<td style='{td}'>{name}<br><span style='color:#6b7280;font-size:11px;'>{ticker}</span></td>"
            f"<td style='{td}text-align:center;'>{action_label}</td>"
            f"<td style='{td}text-align:right;'>{qty_str}</td>"
            f"<td style='{td}text-align:center;color:{status_color};font-weight:bold;'>"
            f"{status_label}{error_html}</td>"
            f"</tr>"
        )

    summary_color = "#16a34a" if not has_fail else "#f59e0b"
    body = (
        f"<p style='color:#374151;margin-top:8px;'>"
        f"포트폴리오 <strong>{portfolio_name}</strong>의 리밸런싱이 자동으로 실행되었습니다.<br>"
        f"실행 시각: {time_str}</p>"
        f"<div style='background:#f8fafc;border-radius:8px;padding:12px 16px;margin:16px 0;"
        f"font-size:14px;border-left:4px solid {summary_color};'>"
        f"<strong style='color:{summary_color};'>성공 {total_success}건</strong>"
        + (f" &nbsp;·&nbsp; <strong style='color:#ef4444;'>실패 {total_fail}건</strong>" if has_fail else "")
        + (f" &nbsp;·&nbsp; 건너뜀 {total_skipped}건" if total_skipped else "")
        + "</div>"
        + (
            f"<table style='width:100%;border-collapse:collapse;margin-top:8px;'>"
            f"<thead><tr style='background:#f1f5f9;'>"
            f"<th style='padding:8px;text-align:left;font-size:13px;'>종목</th>"
            f"<th style='padding:8px;text-align:center;font-size:13px;'>구분</th>"
            f"<th style='padding:8px;text-align:right;font-size:13px;'>수량</th>"
            f"<th style='padding:8px;text-align:center;font-size:13px;'>결과</th>"
            f"</tr></thead>"
            f"<tbody>{rows_html}</tbody></table>"
            if rows_html
            else ""
        )
    )
    html = _email_div(
        heading,
        heading_color,
        body,
        "Growlio 앱 > 리밸런싱 > 실행 이력에서 상세 내역을 확인하세요.",
    )
    return subject, html


_PLAN_MARKET_LABEL = {"KR": "국내", "US": "미국"}
_KST_OFFSET_SECONDS = 9 * 3600


def _render_plan_buy_section(section: dict, account_note: str, btn_style: str) -> str:
    market_label = _PLAN_MARKET_LABEL.get(section["market"], section["market"])
    buy_time_str = datetime.fromtimestamp(section["deadline_at"].timestamp() + _KST_OFFSET_SECONDS).strftime("%H:%M")
    return (
        f"<div style='margin-top:20px;padding:16px;background:#eff6ff;border-radius:8px;'>"
        f"<h3 style='margin:0;color:#1d4ed8;font-size:15px;'>매수 주문 ({market_label}){account_note}</h3>"
        f"<p style='color:#374151;font-size:13px;margin:8px 0 0;'>"
        f"<strong>{buy_time_str} KST</strong>에 아래 수량대로 자동 실행됩니다. "
        f"그 전까지 취소할 수 있습니다.</p>"
        f"{_plan_items_table(section['items'])}"
        f"<a href='{section['link']}' style='{btn_style}background:#ffffff;color:#1d4ed8;"
        f"border:1px solid #1d4ed8;'>매수 취소하기</a>"
        f"</div>"
    )


def _render_plan_sell_section(section: dict, account_note: str, btn_style: str) -> str:
    market_label = _PLAN_MARKET_LABEL.get(section["market"], section["market"])
    sell_time_str = datetime.fromtimestamp(section["deadline_at"].timestamp() + _KST_OFFSET_SECONDS).strftime(
        "%Y-%m-%d %H:%M"
    )
    return (
        f"<div style='margin-top:16px;padding:16px;background:#fef2f2;border-radius:8px;'>"
        f"<h3 style='margin:0;color:#dc2626;font-size:15px;'>매도 주문 ({market_label}){account_note} — 승인 필요</h3>"
        f"<p style='color:#374151;font-size:13px;margin:8px 0 0;'>"
        f"매도는 실현손익·세금에 영향을 주므로 승인이 필요합니다. "
        f"<strong>{sell_time_str} KST(정규장 마감)</strong>까지 응답이 없으면 자동으로 취소됩니다.</p>"
        f"{_plan_items_table(section['items'])}"
        f"<a href='{section['link']}' style='{btn_style}background:#dc2626;color:#ffffff;'>"
        f"매도 확인하러 가기</a>"
        f"</div>"
    )


def rebalancing_plan_pending_template(
    portfolio_name: str,
    account_name: str | None,
    buy_sections: list[dict],
    sell_sections: list[dict],
) -> tuple[str, str]:
    """AUTO 모드 플랜 생성 직후 발송하는 실행 전 계획 안내 이메일.

    매수: 대기시간 후 자동 실행(취소 가능). 매도: 이메일 승인 필요(정규장 마감 미응답 시 자동 취소).
    국내(KR)/해외(US) 주문이 섞여 있으면 leg가 시장별로 나뉘어 있으므로 side당 섹션이 최대 2개
    (KR/US) 있을 수 있다 — 각 section dict는 {"market", "items", "deadline_at", "link"} 형태.
    """
    has_buy = bool(buy_sections)
    has_sell = bool(sell_sections)

    subject_action = (
        "/".join(label for label, present in (("매수", has_buy), ("매도", has_sell)) if present) or "리밸런싱"
    )
    subject = f"[Growlio] 리밸런싱 자동화 — {portfolio_name} {subject_action} 대기"

    account_note = f" (실행 계좌: {account_name})" if account_name else ""

    btn_style = (
        "display:inline-block;padding:10px 20px;border-radius:8px;font-weight:bold;"
        "font-size:14px;text-decoration:none;margin-top:12px;"
    )

    buy_section_html = "".join(_render_plan_buy_section(s, account_note, btn_style) for s in buy_sections)
    sell_section_html = "".join(_render_plan_sell_section(s, account_note, btn_style) for s in sell_sections)

    body = (
        f"<p style='color:#374151;'>포트폴리오 <strong>{portfolio_name}</strong>의 리밸런싱 자동화 조건이 "
        f"충족되어 아래 계획이 생성되었습니다.</p>"
        f"{buy_section_html}"
        f"{sell_section_html}"
    )
    html = _email_div(
        "리밸런싱 자동화 계획 생성",
        "#1d4ed8",
        body,
        "Growlio 앱 > 리밸런싱 > 실행 이력에서도 대기중인 계획을 확인·취소할 수 있습니다.",
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


_ASSET_TYPE_LABEL: dict[str, str] = {
    "BANK_ACCOUNT": "예금/적금",
    "DEPOSIT": "예치금",
    "STOCK_KIS": "주식(KIS)",
    "STOCK_KIWOOM": "주식(키움)",
    "STOCK_OTHER": "주식(기타)",
    "CASH_STOCK": "주식 현금",
    "CASH_OTHER": "현금(기타)",
    "REAL_ESTATE": "부동산",
    "OTHER": "기타",
}


def monthly_report_template(
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
) -> tuple[str, str]:
    subject = f"[Growlio] {report_month} 월간 포트폴리오 리포트"

    mom_row = ""
    if mom_change_krw is not None and mom_change_pct is not None:
        mom_color = "#16a34a" if mom_change_krw >= 0 else "#dc2626"
        sign = "+" if mom_change_krw >= 0 else ""
        mom_row = (
            f"<tr><td style='padding:8px;background:#f1f5f9;font-weight:bold;'>전월 대비</td>"
            f"<td style='padding:8px;color:{mom_color};font-weight:bold;'>"
            f"{sign}{mom_change_krw:,.0f}원 ({sign}{mom_change_pct:.1f}%)</td></tr>"
        )

    return_rows = ""
    if annual_return_pct is not None:
        c = "#16a34a" if annual_return_pct >= 0 else "#dc2626"
        s = "+" if annual_return_pct >= 0 else ""
        return_rows += (
            f"<tr><td style='padding:8px;background:#f1f5f9;font-weight:bold;'>연환산 수익률</td>"
            f"<td style='padding:8px;color:{c};'>{s}{annual_return_pct:.1f}%</td></tr>"
        )
    if xirr_pct is not None:
        c = "#16a34a" if xirr_pct >= 0 else "#dc2626"
        s = "+" if xirr_pct >= 0 else ""
        return_rows += (
            f"<tr><td style='padding:8px;background:#f1f5f9;font-weight:bold;'>XIRR (내부수익률)</td>"
            f"<td style='padding:8px;color:{c};'>{s}{xirr_pct:.1f}%</td></tr>"
        )

    tl = "style='padding:8px;background:#f1f5f9;font-weight:bold;'"
    goal_rows = ""
    if goal_amount and goal_achievement_pct is not None:
        gc = "#16a34a" if goal_achievement_pct >= 100 else "#1d4ed8"
        goal_rows += (
            f"<tr><td {tl}>총 자산 목표</td>"
            f"<td style='padding:8px;'>{goal_amount:,.0f}원 → "
            f"<span style='color:{gc};font-weight:bold;'>{goal_achievement_pct:.1f}% 달성</span></td></tr>"
        )
    if annual_deposit_goal and deposit_achievement_pct is not None:
        dc = "#16a34a" if deposit_achievement_pct >= 100 else "#1d4ed8"
        goal_rows += (
            f"<tr><td {tl}>연간 입금 목표</td>"
            f"<td style='padding:8px;'>{annual_deposit_goal:,.0f}원 → "
            f"<span style='color:{dc};font-weight:bold;'>{deposit_achievement_pct:.1f}% 달성</span></td></tr>"
        )
    goal_section = (
        f"<h3 style='color:#374151;margin-top:24px;margin-bottom:8px;'>목표 달성</h3>"
        f"<table style='width:100%;border-collapse:collapse;'>{goal_rows}</table>"
        if goal_rows
        else ""
    )

    sorted_alloc = sorted(asset_allocation, key=lambda x: x.get("amount_krw", 0), reverse=True)[:5]
    _td = "padding:6px 8px;border-bottom:1px solid #e2e8f0;"
    alloc_rows = "".join(
        f"<tr>"
        f"<td style='{_td}'>{_ASSET_TYPE_LABEL.get(item['type'], item['type'])}</td>"
        f"<td style='{_td}text-align:right;'>{item.get('amount_krw', 0):,.0f}원</td>"
        f"<td style='{_td}text-align:right;'>{item.get('pct', 0):.1f}%</td>"
        f"</tr>"
        for item in sorted_alloc
    )

    body = (
        f"<h3 style='color:#374151;margin-top:24px;margin-bottom:8px;'>자산 현황</h3>"
        f"<table style='width:100%;border-collapse:collapse;'>"
        f"<tr><td style='padding:8px;background:#f1f5f9;font-weight:bold;'>총 자산</td>"
        f"<td style='padding:8px;font-size:18px;font-weight:bold;color:#1d4ed8;'>"
        f"{total_assets_krw:,.0f}원</td></tr>"
        f"{mom_row}{return_rows}"
        f"<tr><td style='padding:8px;background:#f1f5f9;font-weight:bold;'>연간 배당금</td>"
        f"<td style='padding:8px;'>{annual_dividends_received:,.0f}원</td></tr>"
        f"</table>"
        f"{goal_section}"
        f"<h3 style='color:#374151;margin-top:24px;margin-bottom:8px;'>자산 배분 (상위 5개)</h3>"
        f"<table style='width:100%;border-collapse:collapse;font-size:13px;'>"
        f"<thead><tr style='background:#f1f5f9;'>"
        f"<th style='padding:8px;text-align:left;'>유형</th>"
        f"<th style='padding:8px;text-align:right;'>금액</th>"
        f"<th style='padding:8px;text-align:right;'>비중</th>"
        f"</tr></thead>"
        f"<tbody>{alloc_rows}</tbody></table>"
    )
    html = _email_div(
        f"{report_month} 월간 포트폴리오 리포트",
        "#1d4ed8",
        body,
        "Growlio 앱에서 상세 내역을 확인하세요.<br>이 리포트는 매월 1일 자동으로 발송됩니다.",
    )
    return subject, html


def goal_achievement_template(
    goal_type: str,
    goal_amount: float,
    current_amount: float,
    achievement_pct: float,
) -> tuple[str, str]:
    if goal_type == "ASSET":
        subject = f"[Growlio] 목표 자산 달성! — {achievement_pct:.1f}% 달성"
        heading = "총 자산 목표 달성"
        goal_label, current_label = "총 자산 목표", "현재 총 자산"
    elif goal_type == "DIVIDEND":
        subject = f"[Growlio] 연간 배당 목표 달성! — {achievement_pct:.1f}% 달성"
        heading = "연간 배당 목표 달성"
        goal_label, current_label = "연간 배당 목표", "예상 연간 배당금"
    else:
        subject = f"[Growlio] 연간 입금 목표 달성! — {achievement_pct:.1f}% 달성"
        heading = "연간 입금 목표 달성"
        goal_label, current_label = "연간 입금 목표", "올해 순 입금액"

    table = _kv_table(
        [
            (goal_label, f"{goal_amount:,.0f}원"),
            (current_label, f"<span style='font-weight:bold;color:#16a34a;'>{current_amount:,.0f}원</span>"),
            ("달성률", f"<span style='font-size:20px;font-weight:bold;color:#16a34a;'>{achievement_pct:.1f}%</span>"),
        ]
    )
    body = "<p style='color:#374151;margin-top:8px;'>설정하신 투자 목표를 달성했습니다!</p>" + table
    html = _email_div(
        heading,
        "#16a34a",
        body,
        "Growlio 앱에서 새 목표를 설정하거나 상세 내역을 확인하세요.",
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


def password_reset_template(reset_link: str) -> tuple[str, str]:
    subject = "[Growlio] 비밀번호 재설정 안내"
    body = (
        "<p style='color:#374151;margin-top:16px;'>"
        "비밀번호 재설정을 요청하셨습니다. 아래 버튼을 클릭하여 새 비밀번호를 설정해주세요.</p>"
        f"<div style='margin:24px 0;text-align:center;'>"
        f"<a href='{reset_link}' style='display:inline-block;background:#1d4ed8;color:#ffffff;"
        f"text-decoration:none;padding:12px 28px;border-radius:8px;font-weight:bold;font-size:15px;'>"
        f"비밀번호 재설정</a></div>"
        f"<p style='color:#64748b;font-size:13px;'>이 링크는 1시간 후에 만료됩니다.<br>"
        f"본인이 요청하지 않은 경우 이 이메일을 무시하시면 됩니다.</p>"
        f"<p style='color:#9ca3af;font-size:12px;margin-top:16px;'>"
        f"링크가 클릭되지 않으면 아래 URL을 브라우저에 직접 입력해주세요:<br>"
        f"<span style='color:#6b7280;'>{reset_link}</span></p>"
    )
    html = _email_div("비밀번호 재설정", "#1d4ed8", body)
    return subject, html


def account_deletion_template() -> tuple[str, str]:
    subject = "[Growlio] 회원 탈퇴가 완료되었습니다"
    body = (
        "<p style='color:#374151;margin-top:16px;'>"
        "요청하신 회원 탈퇴가 정상적으로 처리되었습니다.<br>"
        "계좌·거래내역·포트폴리오·리밸런싱 이력 등 모든 데이터가 삭제되었습니다.</p>"
        "<p style='color:#64748b;font-size:13px;margin-top:20px;'>"
        "본인이 요청하지 않은 경우 즉시 고객센터로 문의해주세요.</p>"
    )
    html = _email_div("회원 탈퇴 완료", "#dc2626", body)
    return subject, html


_SIGNAL_LEVEL_LABEL: dict[str, str] = {"GREEN": "안정", "YELLOW": "주의", "RED": "위험"}
_SIGNAL_LEVEL_COLOR: dict[str, str] = {"GREEN": "#16a34a", "YELLOW": "#d97706", "RED": "#dc2626"}


def rebalancing_plan_execution_failed_template(
    portfolio_name: str, side: str, error_message: str | None
) -> tuple[str, str]:
    """AUTO 매수/매도 leg 실행 자체가 예외로 실패했을 때(개별 종목 실패가 아닌 leg 전체 실패) 발송."""
    side_label = "매수" if side == "BUY" else "매도"
    subject = f"[Growlio] 리밸런싱 자동화 {side_label} 실행 실패 — {portfolio_name}"
    table = _kv_table(
        [
            ("포트폴리오", portfolio_name),
            ("실행 유형", f"자동 {side_label}"),
            ("실패 사유", error_message or "알 수 없는 오류"),
        ]
    )
    html = _email_div(
        "리밸런싱 자동화 실행 실패",
        "#dc2626",
        table,
        "이번 자동 실행 계획은 체결되지 않았습니다. Growlio 앱 리밸런싱 &gt; 이력 탭에서 상세 내용을 확인하고, "
        "필요 시 직접 리밸런싱을 실행해주세요.",
    )
    return subject, html


def tax_impact_gate_blocked_template(
    portfolio_name: str, estimated_tax_krw: float, max_tax_impact_krw: float
) -> tuple[str, str]:
    """세금영향 게이트로 이번 자동 실행 계획 생성이 보류됐을 때 발송."""
    subject = f"[Growlio] 리밸런싱 자동화 보류 — 세금영향 상한 초과 ({portfolio_name})"
    table = _kv_table(
        [
            ("포트폴리오", portfolio_name),
            ("추정 양도세", f"약 {estimated_tax_krw:,.0f} 원"),
            ("설정된 상한", f"{max_tax_impact_krw:,.0f} 원"),
        ]
    )
    html = _email_div(
        "리밸런싱 자동화 보류 — 세금영향 상한 초과",
        "#d97706",
        table,
        "매도로 인해 예상되는 양도세가 설정하신 상한을 초과해 이번 자동 실행 계획을 만들지 않았습니다. "
        "드리프트가 유지되면 다음 실행 시각에 다시 확인합니다. 상한은 리밸런싱 자동화 설정에서 조정할 수 있습니다. "
        "이 알림은 같은 알림에 대해 하루 1회만 발송됩니다.",
    )
    return subject, html


def market_signal_gate_blocked_template(
    portfolio_name: str, composite_level: str, market_condition_mode: str
) -> tuple[str, str]:
    """시장신호 게이트로 이번 자동 실행 계획 생성이 보류됐을 때 발송."""
    level_label = _SIGNAL_LEVEL_LABEL.get(composite_level, composite_level)
    level_color = _SIGNAL_LEVEL_COLOR.get(composite_level, "#374151")
    mode_label = {"CAUTIOUS": "신중(YELLOW/RED 차단)", "STRICT": "엄격(RED만 차단)"}.get(
        market_condition_mode, market_condition_mode
    )
    subject = f"[Growlio] 리밸런싱 자동화 보류 — 시장신호 게이트 ({portfolio_name})"
    table = _kv_table(
        [
            ("포트폴리오", portfolio_name),
            ("현재 시장 신호", f"<span style='color:{level_color};font-weight:bold;'>{level_label}</span>"),
            ("설정된 게이트", mode_label),
        ]
    )
    html = _email_div(
        "리밸런싱 자동화 보류 — 시장신호 게이트",
        level_color,
        table,
        "현재 시장 위험 신호가 설정하신 자동화 게이트 조건에 해당해 이번 자동 실행 계획을 만들지 않았습니다. "
        "신호가 완화되면 다음 실행 시각에 다시 확인합니다. 게이트 조건은 리밸런싱 자동화 설정에서 조정할 수 있습니다. "
        "이 알림은 같은 알림에 대해 하루 1회만 발송됩니다.",
    )
    return subject, html


def market_signal_change_template(old_level: str, new_level: str, reason: str | None) -> tuple[str, str]:
    """시장 위험 신호등 등급이 전환되었을 때 발송하는 알림 이메일."""
    old_label = _SIGNAL_LEVEL_LABEL.get(old_level, old_level)
    new_label = _SIGNAL_LEVEL_LABEL.get(new_level, new_level)
    new_color = _SIGNAL_LEVEL_COLOR.get(new_level, "#374151")
    subject = f"[Growlio] 시장 위험 신호 변경 — {old_label} → {new_label}"
    table = _kv_table(
        [
            ("이전 신호", old_label),
            ("현재 신호", f"<span style='color:{new_color};font-weight:bold;'>{new_label}</span>"),
        ]
    )
    body = table
    if reason:
        body += f"<p style='color:#64748b;font-size:13px;margin-top:12px;'>{reason}</p>"
    html = _email_div(
        "시장 위험 신호 변경 알림",
        new_color,
        body,
        "이 알림은 시장 위험 신호 등급이 바뀔 때마다(1시간 간격 점검) 발송됩니다.<br>"
        "Growlio 앱 리밸런싱 &gt; 진단 탭에서 상세 지표를 확인하세요.<br>"
        "알림 설정은 설정 &gt; 알림 설정 &gt; 시장 신호 알림에서 변경하세요.",
    )
    return subject, html


def year_end_tax_reminder_template(content: Mapping[str, Any]) -> tuple[str, str]:
    """11~12월 매주 월요일 발송되는 연말 절세 리마인더 이메일.

    content는 tax_reminder_service.build_reminder_content()의 반환값(TaxReminderContent).
    """
    subject = "[Growlio] 연말 절세 리마인더 — 지금 활용할 수 있는 절세 방법"
    sections = ""

    harvesting_top = content.get("harvesting_top") or []
    if harvesting_top:
        items_html = "".join(
            f"<li style='margin-bottom:4px;'>{item['ticker']} — 손실 {abs(item['unrealized_loss_krw']):,.0f}원 "
            f"매도 시 절세 약 {item['tax_saved_krw']:,.0f}원</li>"
            for item in harvesting_top
        )
        sections += (
            "<h3 style='margin:16px 0 4px;font-size:15px;color:#1e293b;'>해외주식 손실수확 후보</h3>"
            f"<ul style='padding-left:20px;margin:0;font-size:13px;color:#374151;'>{items_html}</ul>"
            f"<p style='font-size:13px;color:#64748b;margin-top:4px;'>합계 절세 가능 약 "
            f"{content.get('harvesting_total_tax_saved_krw', 0):,.0f}원 (250만원 공제 활용 기준, 참고용 추정치)</p>"
        )

    pension_remaining = content.get("pension_remaining_krw", 0)
    if pension_remaining > 0:
        sections += (
            "<h3 style='margin:16px 0 4px;font-size:15px;color:#1e293b;'>연금저축/IRP 세액공제 잔여한도</h3>"
            f"<p style='font-size:13px;color:#374151;margin:0;'>올해 아직 {pension_remaining:,.0f}원의 "
            "세액공제 여력이 남아 있습니다. 연말 전 추가 납입을 고려해보세요.</p>"
        )

    isa_near_maturity = content.get("isa_near_maturity") or []
    isa_over_limit_count = content.get("isa_over_limit_count", 0)
    if isa_near_maturity or isa_over_limit_count:
        isa_lines = "".join(
            f"<li style='margin-bottom:4px;'>{acc['account_name']} — 의무가입 만기까지 D-{acc['days_remaining']}</li>"
            for acc in isa_near_maturity
        )
        over_limit_line = (
            f"<li style='margin-bottom:4px;'>비과세 한도 초과 계좌 {isa_over_limit_count}건</li>"
            if isa_over_limit_count
            else ""
        )
        sections += (
            "<h3 style='margin:16px 0 4px;font-size:15px;color:#1e293b;'>ISA 계좌 확인</h3>"
            f"<ul style='padding-left:20px;margin:0;font-size:13px;color:#374151;'>{isa_lines}{over_limit_line}</ul>"
        )

    html = _email_div(
        "연말 절세 리마인더",
        "#7c3aed",
        sections,
        "이 알림은 11~12월 매주 월요일 09:00 KST에 발송됩니다.<br>"
        "Growlio 앱 자산 &gt; 투자현황 &gt; 세금 탭에서 상세 시뮬레이션을 확인하세요.<br>"
        "알림 설정은 설정 &gt; 알림 설정에서 변경하세요.",
    )
    return subject, html


def market_signal_daily_digest_template(level: str, reason: str | None) -> tuple[str, str]:
    """매일 08:30 KST 발송되는 시장 위험 신호 요약 이메일 — 등급 전환 여부와 무관하게 발송."""
    label = _SIGNAL_LEVEL_LABEL.get(level, level)
    color = _SIGNAL_LEVEL_COLOR.get(level, "#374151")
    subject = f"[Growlio] 오늘의 시장 신호 — {label}"
    table = _kv_table([("오늘의 시장 신호", f"<span style='color:{color};font-weight:bold;'>{label}</span>")])
    body = table
    body += f"<p style='color:#64748b;font-size:13px;margin-top:12px;'>{reason or '오늘도 안정적입니다.'}</p>"
    html = _email_div(
        "오늘의 시장 신호",
        color,
        body,
        "이 알림은 매일 08:30 KST에 등급 전환 여부와 무관하게 발송됩니다.<br>"
        "Growlio 앱 리밸런싱 &gt; 진단 탭에서 상세 지표를 확인하세요.<br>"
        "알림 설정은 설정 &gt; 알림 설정 &gt; 시장 신호 알림에서 변경하세요.",
    )
    return subject, html
