"""email_templates.py 단위 테스트 — 순수 함수이므로 외부 의존 없음."""

from __future__ import annotations

from app.services.email_templates import (
    exchange_rate_alert_template,
    password_reset_template,
    rebalancing_alert_template,
    stock_price_alert_template,
)


class TestExchangeRateAlertTemplate:
    def test_returns_subject_and_html_tuple(self):
        subject, html = exchange_rate_alert_template(target_rate=1300.0, direction="BELOW", current_rate=1295.5)
        assert isinstance(subject, str)
        assert isinstance(html, str)

    def test_subject_contains_target_rate(self):
        subject, _ = exchange_rate_alert_template(target_rate=1300.0, direction="BELOW", current_rate=1295.0)
        assert "1,300" in subject

    def test_below_direction_label(self):
        subject, html = exchange_rate_alert_template(target_rate=1300.0, direction="BELOW", current_rate=1295.0)
        assert "이하" in subject
        assert "이하" in html

    def test_above_direction_label(self):
        subject, html = exchange_rate_alert_template(target_rate=1400.0, direction="ABOVE", current_rate=1405.0)
        assert "이상" in subject
        assert "이상" in html

    def test_html_contains_current_rate(self):
        _, html = exchange_rate_alert_template(target_rate=1300.0, direction="BELOW", current_rate=1295.55)
        assert "1,295.55" in html

    def test_html_is_nonempty(self):
        _, html = exchange_rate_alert_template(1300.0, "BELOW", 1295.0)
        assert len(html) > 100


class TestRebalancingAlertTemplate:
    def test_drift_alert_subject_format(self):
        subject, _ = rebalancing_alert_template(
            portfolio_name="성장형",
            threshold_pct=5.0,
            items_to_show=[],
            drifting_count=2,
            is_scheduled_report=False,
        )
        assert "성장형" in subject
        assert "비중 이탈 감지" in subject

    def test_scheduled_report_subject(self):
        subject, _ = rebalancing_alert_template(
            portfolio_name="안정형",
            threshold_pct=5.0,
            items_to_show=[],
            drifting_count=0,
            is_scheduled_report=True,
            schedule_type="WEEKLY",
        )
        assert "안정형" in subject
        assert "매주" in subject

    def test_html_contains_portfolio_name(self):
        _, html = rebalancing_alert_template(
            portfolio_name="내포트폴리오",
            threshold_pct=3.0,
            items_to_show=[],
            drifting_count=1,
        )
        assert "내포트폴리오" in html

    def test_html_is_nonempty(self):
        _, html = rebalancing_alert_template("P", 5.0, [], 0)
        assert len(html) > 100

    def test_composite_triggered_without_drift_uses_dedicated_heading(self):
        subject, html = rebalancing_alert_template(
            portfolio_name="복합신호포트폴리오",
            threshold_pct=5.0,
            items_to_show=[],
            drifting_count=0,
            is_composite_triggered=True,
            composite_reason="시장 위험 신호가 RED 단계입니다",
        )
        assert "점검 권장" in subject
        assert "복합신호포트폴리오" in subject
        assert "시장 위험 신호가 RED 단계입니다" in html

    def test_composite_triggered_with_drift_uses_normal_drift_heading(self):
        """drift가 있으면 복합신호 여부와 무관하게 기존 '비중 이탈 감지' 문구를 사용한다."""
        subject, _ = rebalancing_alert_template(
            portfolio_name="P",
            threshold_pct=5.0,
            items_to_show=[],
            drifting_count=2,
            is_composite_triggered=True,
            composite_reason="시장 위험 신호가 RED 단계입니다",
        )
        assert "비중 이탈 감지" in subject

    def test_composite_triggered_false_uses_normal_heading(self):
        subject, _ = rebalancing_alert_template(
            portfolio_name="P",
            threshold_pct=5.0,
            items_to_show=[],
            drifting_count=0,
            is_scheduled_report=True,
        )
        assert "점검 권장" not in subject


class TestStockPriceAlertTemplate:
    def test_returns_tuple(self):
        subject, html = stock_price_alert_template(
            ticker="005930",
            name="삼성전자",
            target_price=80000.0,
            current_price=80500.0,
            direction="ABOVE",
        )
        assert isinstance(subject, str)
        assert isinstance(html, str)

    def test_subject_contains_ticker_and_name(self):
        subject, _ = stock_price_alert_template(
            ticker="AAPL",
            name="Apple",
            target_price=150.0,
            current_price=148.0,
            direction="BELOW",
        )
        assert "AAPL" in subject
        assert "Apple" in subject

    def test_direction_label_in_subject(self):
        subject, _ = stock_price_alert_template(
            ticker="005930",
            name="삼성전자",
            target_price=70000.0,
            current_price=68000.0,
            direction="BELOW",
        )
        assert "이하" in subject


class TestPasswordResetTemplate:
    def test_returns_subject_and_html(self):
        subject, html = password_reset_template("https://example.com/reset?token=abc")
        assert isinstance(subject, str)
        assert isinstance(html, str)

    def test_html_contains_reset_link(self):
        link = "https://example.com/reset?token=xyz123"
        _, html = password_reset_template(link)
        assert link in html

    def test_subject_nonempty(self):
        subject, _ = password_reset_template("https://example.com/reset")
        assert len(subject) > 0
