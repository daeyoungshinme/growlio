"""이메일 템플릿 전역 공용 헬퍼/상수 — I/O 없는 순수 함수.

`email_templates` 패키지의 모든 서브모듈이 공유한다. `_SIGNAL_LEVEL_LABEL`/`_SIGNAL_LEVEL_COLOR`는
`market_signal.py`(등급 전환·매일 요약)와 `rebalancing.py`(시장신호 게이트 보류 알림) 양쪽에서
동일한 라벨/색상을 써야 하므로 여기에 둔다.
"""

from __future__ import annotations


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


_SIGNAL_LEVEL_LABEL: dict[str, str] = {"GREEN": "안정", "YELLOW": "주의", "RED": "위험"}
_SIGNAL_LEVEL_COLOR: dict[str, str] = {"GREEN": "#16a34a", "YELLOW": "#d97706", "RED": "#dc2626"}


def _name_ticker_cell(td_style: str, name: str, ticker: str) -> str:
    """종목명 아래 회색 작은 글씨로 티커를 붙인 표 셀."""
    return f"<td style='{td_style}'>{name}<br><span style='color:#6b7280;font-size:11px;'>{ticker}</span></td>"


def _data_table(headers: list[tuple[str, str]], rows_html: str, *, margin_top: int) -> str:
    """회색 헤더 행 + 본문 행의 표. headers는 (제목, text-align) 목록."""
    ths = "".join(
        f"<th style='padding:8px;text-align:{align};font-size:13px;'>{label}</th>" for label, align in headers
    )
    return (
        f"<table style='width:100%;border-collapse:collapse;margin-top:{margin_top}px;'>"
        f"<thead><tr style='background:#f1f5f9;'>{ths}</tr></thead>"
        f"<tbody>{rows_html}</tbody></table>"
    )


def _notice_banner(text: str) -> str:
    """노란 안내 배너(테스트 발송·자동 실행 보류 안내 등)."""
    return (
        "<div style='background:#fef3c7;border:1px solid #f59e0b;border-radius:8px;"
        f"padding:10px 14px;margin-bottom:16px;font-size:13px;color:#92400e;'>{text}</div>"
    )
