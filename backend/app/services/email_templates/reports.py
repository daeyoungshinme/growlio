"""정기 리포트/목표 알림 + 계정 관리(회원 탈퇴) 이메일 템플릿."""

from __future__ import annotations

from collections.abc import Mapping
from html import escape
from typing import Any

from app.services.email_templates._shared import _email_div, _kv_table

_ASSET_TYPE_LABEL: dict[str, str] = {
    "BANK_ACCOUNT": "예금/적금",
    "DEPOSIT": "예치금",
    "STOCK_KIS": "주식(KIS)",
    "STOCK_KIWOOM": "주식(키움)",
    "STOCK_TOSS": "주식(토스)",
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


def year_end_tax_reminder_template(content: Mapping[str, Any]) -> tuple[str, str]:
    """11~12월 매주 월요일 발송되는 연말 절세 리마인더 이메일.

    content는 tax_reminder_service.build_reminder_content()의 반환값(TaxReminderContent) — 앱 세금 탭의
    절세 액션 플랜(tax_action_service)과 같은 액션 목록이다.
    """
    subject = "[Growlio] 연말 절세 리마인더 — 지금 활용할 수 있는 절세 방법"
    items_html = ""
    for action in content.get("actions") or []:
        meta: list[str] = []
        if action.get("benefit_krw"):
            meta.append(f"예상 절세 약 {action['benefit_krw']:,.0f}원")
        if action.get("deadline"):
            meta.append(f"마감 {action['deadline']}")
        meta_html = (
            f"<div style='font-size:12px;color:#7c3aed;margin-top:2px;'>{' · '.join(meta)}</div>" if meta else ""
        )
        items_html += (
            "<li style='margin-bottom:10px;'>"
            f"<div style='font-weight:bold;color:#1e293b;'>{escape(action['title'])}</div>"
            f"<div style='color:#475569;margin-top:2px;'>{escape(action['detail'])}</div>{meta_html}</li>"
        )
    total_benefit = content.get("total_benefit_krw") or 0
    total_html = (
        f"<p style='font-size:13px;color:#64748b;margin-top:4px;'>위 항목 예상 절세 합계 약 {total_benefit:,.0f}원 "
        "(참고용 추정치 — 이익실현 항목은 향후 매도 시 절감액)</p>"
        if total_benefit
        else ""
    )
    sections = (
        "<h3 style='margin:16px 0 4px;font-size:15px;color:#1e293b;'>올해 남은 절세 액션</h3>"
        f"<ul style='padding-left:20px;margin:0;font-size:13px;color:#374151;'>{items_html}</ul>{total_html}"
    )

    html = _email_div(
        "연말 절세 리마인더",
        "#7c3aed",
        sections,
        "이 알림은 11~12월 매주 월요일 09:00 KST에 발송됩니다.<br>"
        "Growlio 앱 자산 &gt; 투자현황 &gt; 세금 탭의 절세 액션 플랜에서 전체 목록을 확인하세요.<br>"
        "매매 관련 항목은 정보 제공 목적이며 투자 권유가 아닙니다.<br>"
        "알림 설정은 설정 &gt; 알림 설정에서 변경하세요.",
    )
    return subject, html


def recommendation_drift_alert_template(portfolio_names: list[str], app_link: str) -> tuple[str, str]:
    """매주 월요일 09:15 KST 발송되는 추천 비중 변화 알림 이메일 — 목표 역산 추천 비중이 타겟
    포트폴리오의 현재 목표 비중과 유의미하게(3%p 이상 또는 신규 후보 존재) 달라진 경우에만 발송."""
    subject = "[Growlio] 추천 비중이 달라졌어요"
    names_html = "".join(f"<li style='margin-bottom:4px;'>{name}</li>" for name in portfolio_names)
    body = (
        "<p style='font-size:13px;color:#374151;'>시장 상황이 바뀌어 아래 포트폴리오의 추천 비중이 "
        "현재 목표 비중과 달라졌습니다.</p>"
        f"<ul style='padding-left:20px;margin:8px 0;font-size:13px;color:#374151;'>{names_html}</ul>"
        f"<p style='margin-top:16px;'><a href='{app_link}' "
        "style='color:#0d9488;font-weight:bold;text-decoration:none;'>추천 비중 확인하러 가기 →</a></p>"
    )
    html = _email_div(
        "추천 비중이 달라졌어요",
        "#0d9488",
        body,
        "이 알림은 매주 월요일 09:15 KST에 발송됩니다.<br>"
        "추천은 참고용 제안이며 자동으로 반영되지 않습니다 — 확인 후 직접 적용해야 합니다.<br>"
        "알림 설정은 설정 &gt; 알림 설정에서 변경하세요.",
    )
    return subject, html


def challenge_reminder_template(
    title: str, month_label: str, this_month_net_krw: float, target_amount: float | None, current_streak: int
) -> tuple[str, str]:
    """매월 25일 발송되는 적립 챌린지 독려 이메일 — 이번 달 아직 목표를 채우지 못한 경우."""
    subject = f"[Growlio] 이번 달 적립, 아직이에요 — {title}"
    rows: list[tuple[str, str]] = [("챌린지", title), ("이번 달", month_label)]
    if target_amount:
        remaining = max(target_amount - this_month_net_krw, 0.0)
        rows.append(("이번 달 입금", f"{this_month_net_krw:,.0f}원 / {target_amount:,.0f}원"))
        rows.append(("남은 금액", f"<span style='font-weight:bold;color:#dc2626;'>{remaining:,.0f}원</span>"))
    else:
        rows.append(("이번 달 입금", f"{this_month_net_krw:,.0f}원"))
    if current_streak > 0:
        rows.append(("현재 연속 적립", f"{current_streak}개월 — 이번 달을 놓치면 끊깁니다"))
    body = (
        "<p style='color:#374151;margin-top:8px;'>이번 달이 지나기 전에 적립을 완료해 습관을 이어가세요.</p>"
        + _kv_table(rows)
    )
    html = _email_div(
        "이번 달 적립을 잊지 마세요",
        "#d97706",
        body,
        "이 알림은 매월 25일 09:00 KST에 발송됩니다.<br>"
        "Growlio 앱 계획 &gt; 챌린지 탭에서 진행 현황을 확인하세요.<br>"
        "알림 설정은 설정 &gt; 알림 설정에서 변경하세요.",
    )
    return subject, html


def challenge_wrap_template(
    title: str,
    month_label: str,
    prev_month_net_krw: float,
    target_met: bool,
    current_streak: int,
    longest_streak: int,
    milestone: int | None,
    completed: bool,
) -> tuple[str, str]:
    """매월 1일 발송되는 적립 챌린지 월간 결산 이메일."""
    if completed:
        subject = f"[Growlio] 챌린지 달성! 🎉 — {title}"
        heading = "챌린지를 달성했어요"
    elif milestone:
        subject = f"[Growlio] 연속 {milestone}개월 적립 달성! 🎉 — {title}"
        heading = f"연속 {milestone}개월 적립 달성"
    else:
        subject = f"[Growlio] {month_label} 적립 챌린지 결산 — {title}"
        heading = f"{month_label} 적립 결산"

    status_html = (
        "<span style='font-weight:bold;color:#16a34a;'>달성 ✅</span>"
        if target_met
        else "<span style='font-weight:bold;color:#dc2626;'>미달 ✕</span>"
    )
    rows: list[tuple[str, str]] = [
        ("챌린지", title),
        (f"{month_label} 결과", status_html),
        (f"{month_label} 순입금", f"{prev_month_net_krw:,.0f}원"),
        ("현재 연속 적립", f"{current_streak}개월"),
        ("최장 연속 기록", f"{longest_streak}개월"),
    ]
    body = "<p style='color:#374151;margin-top:8px;'>지난달 적립 현황을 정리했어요.</p>" + _kv_table(rows)
    html = _email_div(
        heading,
        "#16a34a" if (target_met or milestone or completed) else "#1d4ed8",
        body,
        "이 알림은 매월 1일 09:30 KST에 발송됩니다.<br>"
        "Growlio 앱 계획 &gt; 챌린지 탭에서 상세 내역을 확인하세요.<br>"
        "알림 설정은 설정 &gt; 알림 설정에서 변경하세요.",
    )
    return subject, html
