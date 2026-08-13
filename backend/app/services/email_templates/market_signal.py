"""시장 위험 신호 등급 전환·매일 요약 이메일 템플릿."""

from __future__ import annotations

from app.services.email_templates._shared import _SIGNAL_LEVEL_COLOR, _SIGNAL_LEVEL_LABEL, _email_div, _kv_table


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
