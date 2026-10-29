"""시장 위험 신호 등급 전환·매일 요약 이메일 템플릿."""

from __future__ import annotations

from app.services.notifications.email_templates._shared import (
    _SIGNAL_LEVEL_COLOR,
    _SIGNAL_LEVEL_LABEL,
    _email_div,
    _kv_table,
)


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


def tactical_regime_change_template(
    portfolio_name: str,
    old_label: str,
    new_label: str,
    weights_text: str,
    reasons: list[str],
    app_link: str,
) -> tuple[str, str]:
    """QQQ/SPY 전술 배분 국면이 바뀌었을 때 발송 — 자동 주문 없이 제안 비중만 안내한다."""
    subject = f"[Growlio] 전술 배분 국면 변경 — {old_label} → {new_label}"
    body = _kv_table(
        [
            ("포트폴리오", portfolio_name),
            ("이전 국면", old_label),
            ("현재 국면", f"<span style='font-weight:bold;'>{new_label}</span>"),
            ("제안 비중", weights_text),
        ]
    )
    if reasons:
        items = "".join(f"<li>{r}</li>" for r in reasons)
        body += f"<ul style='color:#64748b;font-size:13px;margin-top:12px;'>{items}</ul>"
    link = f"<a href='{app_link}' style='color:#2563eb;'>앱에서 제안 비중 확인·적용하기</a>"
    body += f"<p style='margin-top:16px;'>{link}</p>"
    html = _email_div(
        "전술 배분 국면 변경",
        "#2563eb",
        body,
        "자동 주문은 실행되지 않았습니다. 제안 비중을 적용한 뒤 리밸런싱 화면에서 직접 확인·실행하세요.<br>"
        "이 신호는 과거 데이터 기반 참고용이며 수익을 보장하지 않습니다.",
    )
    return subject, html


def tactical_dip_template(
    portfolio_name: str,
    stage_label: str,
    deploy_pct: float,
    weights_text: str,
    reasons: list[str],
    app_link: str,
) -> tuple[str, str]:
    """전술 배분 공격 국면에서 QQQ 웅덩이(눌림목) 단계가 깊어졌을 때 발송 — 현금 일부를 주식으로 옮기는 제안."""
    subject = f"[Growlio] 웅덩이 매수 제안 — {stage_label}"
    body = _kv_table(
        [
            ("포트폴리오", portfolio_name),
            ("웅덩이 단계", f"<span style='font-weight:bold;'>{stage_label}</span>"),
            ("현금 → 주식", f"{deploy_pct:g}%p"),
            ("제안 비중", weights_text),
        ]
    )
    if reasons:
        items = "".join(f"<li>{r}</li>" for r in reasons)
        body += f"<ul style='color:#64748b;font-size:13px;margin-top:12px;'>{items}</ul>"
    link = f"<a href='{app_link}' style='color:#2563eb;'>앱에서 제안 비중 확인·적용하기</a>"
    body += f"<p style='margin-top:16px;'>{link}</p>"
    html = _email_div(
        "웅덩이 매수 제안",
        "#2563eb",
        body,
        "자동 주문은 실행되지 않았습니다. 가격이 회복되면 투입분을 다시 현금으로 돌리는 제안이 이어집니다.<br>"
        "이 신호는 과거 데이터 기반 참고용이며 수익을 보장하지 않습니다.",
    )
    return subject, html
