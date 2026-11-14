"""AUTO 리밸런싱이 주문을 내지 않을 때의 안내 메일.

게이트 차단(세금·시장신호·하루 한도·스냅샷)과 정기 적립 자금 부족(원화·달러).

드리프트 알림·실행 결과·플랜 승인 메일은 `rebalancing.py`.
"""

from __future__ import annotations

from html import escape

from app.services.notifications.email_templates._shared import (
    _SIGNAL_LEVEL_COLOR,
    _SIGNAL_LEVEL_LABEL,
    _email_div,
    _kv_table,
)


def dca_fx_required_template(
    portfolio_name: str,
    required_usd: float,
    available_usd: float,
    retry_until_label: str,
    *,
    krw_order: bool = False,
) -> tuple[str, str]:
    """정액 적립 해외 매수 직전 달러 예수금이 모자라 환전을 기다릴 때 발송(plans/120).

    `krw_order`(키움 원화주문 계좌)면 보유 달러가 아니라 원화 환산 포함 매수여력이 모자란 것이라
    원화 입금을 안내한다."""
    shortfall = max(required_usd - available_usd, 0.0)
    if krw_order:
        subject = f"[Growlio] 적립 해외 매수 대기 — 원화 예수금이 부족합니다 ({portfolio_name})"
        table = _kv_table(
            [
                ("포트폴리오", escape(portfolio_name)),
                ("필요 금액", f"${required_usd:,.2f}"),
                ("매수여력(원화 환산 포함)", f"${available_usd:,.2f}"),
                ("부족분", f"약 ${shortfall:,.2f}"),
                ("자동 재확인", f"{retry_until_label}까지"),
            ]
        )
        html = _email_div(
            "적립 해외 매수 — 원화 예수금 부족",
            "#d97706",
            table,
            "원화주문 계좌라 해외 매수가 원화로 결제되는데, 원화 매수여력이 모자라 매수를 잠시 멈췄습니다. "
            "계좌에 원화를 입금한 뒤 Growlio 앱 리밸런싱 &gt; 이력 탭에서 <b>다시 매수</b>를 눌러주세요. 누르지 않아도 "
            "기한까지 미국장 중에 매수여력을 다시 확인해 충분하면 자동으로 매수합니다.",
        )
        return subject, html
    subject = f"[Growlio] 적립 해외 매수 대기 — 달러 환전이 필요합니다 ({portfolio_name})"
    table = _kv_table(
        [
            ("포트폴리오", escape(portfolio_name)),
            ("필요 달러", f"${required_usd:,.2f}"),
            ("보유 달러", f"${available_usd:,.2f}"),
            ("부족분", f"약 ${shortfall:,.2f}"),
            ("자동 재확인", f"{retry_until_label}까지"),
        ]
    )
    html = _email_div(
        "적립 해외 매수 — 달러 환전 필요",
        "#d97706",
        table,
        "해외 종목 적립 매수에 필요한 달러가 부족해 매수를 잠시 멈췄습니다. 증권사 앱에서 환전한 뒤 "
        "Growlio 앱 리밸런싱 &gt; 이력 탭에서 <b>다시 매수</b>를 눌러주세요. 누르지 않아도 기한까지 "
        "미국장 중에 달러 잔고를 다시 확인해 충분하면 자동으로 매수합니다. 국내 종목 몫은 그대로 진행됩니다.",
    )
    return subject, html


def tax_impact_gate_blocked_template(
    portfolio_name: str, estimated_tax_krw: float, max_tax_impact_krw: float
) -> tuple[str, str]:
    """세금영향 게이트로 이번 자동 실행 계획 생성이 보류됐을 때 발송."""
    subject = f"[Growlio] 리밸런싱 자동화 보류 — 세금영향 상한 초과 ({portfolio_name})"
    table = _kv_table(
        [
            ("포트폴리오", escape(portfolio_name)),
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


def stale_snapshot_blocked_template(portfolio_name: str, account_name: str, days_since_sync: int) -> tuple[str, str]:
    """계좌 동기화가 오래 끊겨 이번 자동 실행 계획 생성이 보류됐을 때 발송."""
    subject = f"[Growlio] 리밸런싱 자동화 보류 — 계좌 동기화 끊김 ({portfolio_name})"
    table = _kv_table(
        [
            ("포트폴리오", escape(portfolio_name)),
            ("계좌", escape(account_name)),
            ("마지막 동기화", f"{days_since_sync}일 전"),
        ]
    )
    html = _email_div(
        "리밸런싱 자동화 보류 — 계좌 동기화 끊김",
        "#D97706",
        table,
        "보유 수량을 믿을 수 없어 이번 자동 실행 계획을 만들지 않았습니다. 앱에서 계좌를 동기화하면 다음 실행 때 다시 "
        "확인합니다. 동기화가 계속 실패하면 증권사 API 키를 확인해주세요. "
        "이 알림은 같은 알림에 대해 하루 1회만 발송됩니다.",
    )
    return subject, html


def market_signal_gate_blocked_template(
    portfolio_name: str, composite_level: str, market_condition_mode: str
) -> tuple[str, str]:
    """시장신호 게이트로 이번 자동 실행 계획 생성이 보류됐을 때 발송. TACTICAL은 전술 방어 국면 매수 보류 문구."""
    if market_condition_mode == "TACTICAL":
        return _tactical_gate_blocked_template(portfolio_name)
    level_label = _SIGNAL_LEVEL_LABEL.get(composite_level, composite_level)
    level_color = _SIGNAL_LEVEL_COLOR.get(composite_level, "#374151")
    # 판정은 order_builder.is_market_signal_blocking_auto_mode — CAUTIOUS=RED만, STRICT=YELLOW·RED
    mode_label = {"CAUTIOUS": "신중(RED만 차단)", "STRICT": "엄격(YELLOW·RED 차단)"}.get(
        market_condition_mode, market_condition_mode
    )
    subject = f"[Growlio] 리밸런싱 자동화 보류 — 시장신호 게이트 ({portfolio_name})"
    table = _kv_table(
        [
            ("포트폴리오", escape(portfolio_name)),
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


def _tactical_gate_blocked_template(portfolio_name: str) -> tuple[str, str]:
    color = "#2563eb"
    subject = f"[Growlio] 적립 매수 보류 — 전술 방어 국면 ({portfolio_name})"
    table = _kv_table(
        [
            ("포트폴리오", escape(portfolio_name)),
            ("전술 배분 국면", f"<span style='color:{color};font-weight:bold;'>방어</span>"),
            ("설정된 게이트", "전술 연동(방어 국면이면 보류)"),
        ]
    )
    html = _email_div(
        "적립 매수 보류 — 전술 방어 국면",
        color,
        table,
        "전술 배분이 방어 국면이라 이번 적립 매수를 보류했습니다. 입금액은 예수금으로 남아 있고, 방어 국면이 끝난 뒤 "
        "정기 매수일에 함께 매수됩니다. 매도는 하지 않습니다. 이 알림은 같은 알림에 대해 하루 1회만 발송됩니다.",
    )
    return subject, html


def daily_value_cap_gate_blocked_template(
    portfolio_name: str, today_total_krw: float, attempted_value_krw: float, cap_krw: float
) -> tuple[str, str]:
    """하루 합산 거래한도 게이트로 이번 자동 실행 계획 생성이 보류됐을 때 발송."""
    subject = "[Growlio] 리밸런싱 자동화 보류 — 하루 합산 거래한도 초과"
    table = _kv_table(
        [
            ("포트폴리오", escape(portfolio_name)),
            ("오늘 이미 실행된 금액", f"약 {today_total_krw:,.0f} 원"),
            ("이번 계획 예상 금액", f"약 {attempted_value_krw:,.0f} 원"),
            ("설정된 하루 상한", f"{cap_krw:,.0f} 원"),
        ]
    )
    html = _email_div(
        "리밸런싱 자동화 보류 — 하루 합산 거래한도 초과",
        "#d97706",
        table,
        "오늘 자동 실행된 금액에 이번 계획 예상 금액을 더하면 설정하신 하루 합산 상한을 초과해 이번 "
        "자동 실행 계획을 만들지 않았습니다. 상한은 리밸런싱 자동화 설정에서 조정할 수 있습니다. "
        "이 알림은 하루 1회만 발송됩니다.",
    )
    return subject, html


def dca_cash_shortfall_template(
    portfolio_name: str,
    account_name: str,
    run_date_label: str,
    cash_krw: float,
    expected_krw: float | None,
    synced_label: str | None,
) -> tuple[str, str]:
    """정기 적립식 자동매수(AUTO·SCHEDULE_ONLY·BUY_ONLY) 실행 1~3일 전, 실행 계좌 예수금이 부족할 때 발송."""
    subject = f"[Growlio] {run_date_label} 자동매수 전에 예수금을 채워주세요"
    rows: list[tuple[str, str]] = [
        ("포트폴리오", escape(portfolio_name)),
        ("실행 계좌", escape(account_name)),
        ("자동매수 예정일", run_date_label),
        ("현재 예수금", f"{cash_krw:,.0f} 원" + (f" ({synced_label} 동기화 기준)" if synced_label else "")),
    ]
    if expected_krw:
        shortfall = max(expected_krw - cash_krw, 0.0)
        rows.append(("월 적립액", f"{expected_krw:,.0f} 원"))
        rows.append(("부족 금액", f"<span style='font-weight:bold;color:#dc2626;'>{shortfall:,.0f} 원</span>"))
    html = _email_div(
        "자동매수 예정일 전에 예수금을 확인하세요",
        "#d97706",
        _kv_table(rows),
        "정기 적립식 자동매수는 실행 계좌에 있는 예수금으로만 매수합니다 — 예정일 전에 증권 계좌로 "
        "입금하지 않으면 이번 달 매수가 적거나 실행되지 않습니다. 월 적립액은 계획 &gt; 적립 계획에서 바꿀 수 "
        "있습니다. 이 알림은 예정일마다 1회만 발송됩니다.",
    )
    return subject, html
