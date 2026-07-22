"""email_templates.py 단위 테스트 — 순수 함수이므로 외부 의존 없음."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from app.services.email_templates import (
    exchange_rate_alert_template,
    market_signal_change_template,
    password_reset_template,
    rebalancing_alert_template,
    rebalancing_plan_pending_template,
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
        """복합신호는 특정 포트폴리오가 아닌 계정 전체 기준이므로 제목에 포트폴리오명을 넣지 않는다."""
        subject, html = rebalancing_alert_template(
            portfolio_name="복합신호포트폴리오",
            threshold_pct=5.0,
            items_to_show=[],
            drifting_count=0,
            is_composite_triggered=True,
            composite_reason="시장 위험 신호가 RED 단계입니다",
        )
        assert "점검 권장" in subject
        assert "복합신호포트폴리오" not in subject
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

    def test_composite_triggered_footer_mentions_daily_cap_and_settings(self):
        """복합신호 전용 분기는 포트폴리오 스케줄과 무관하므로 '하루 1회' + 설정 경로를 안내해야 한다."""
        _, html = rebalancing_alert_template(
            portfolio_name="P",
            threshold_pct=5.0,
            items_to_show=[],
            drifting_count=0,
            is_composite_triggered=True,
            composite_reason="시장 위험 신호가 RED 단계입니다",
        )
        assert "하루 1회" in html
        assert "시장 신호 알림" in html

    def test_scheduled_footer_unchanged_for_non_composite(self):
        _, html = rebalancing_alert_template(
            portfolio_name="P",
            threshold_pct=5.0,
            items_to_show=[],
            drifting_count=2,
            is_scheduled_report=True,
            schedule_type="WEEKLY",
        )
        assert "이 알림은 매주 발송됩니다" in html

    def test_no_app_link_renders_no_cta_button(self):
        _, html = rebalancing_alert_template("P", 5.0, [], 0)
        assert "앱에서 확인하기" not in html

    def test_app_link_renders_cta_button(self):
        _, html = rebalancing_alert_template(
            portfolio_name="P",
            threshold_pct=5.0,
            items_to_show=[],
            drifting_count=2,
            app_link="https://app.growlio.example/rebalancing?rtab=%EC%A7%84%EB%8B%A8",
        )
        assert "앱에서 확인하기" in html
        assert "https://app.growlio.example/rebalancing?rtab=%EC%A7%84%EB%8B%A8" in html


class TestMarketSignalChangeTemplate:
    def test_returns_subject_and_html_tuple(self):
        subject, html = market_signal_change_template("GREEN", "YELLOW", "시장 변동성이 확대되는 국면입니다")
        assert isinstance(subject, str)
        assert isinstance(html, str)
        assert "안정" in subject
        assert "주의" in subject

    def test_footer_explains_frequency_and_settings_path(self):
        _, html = market_signal_change_template("GREEN", "RED", "시장 위험 신호가 높은 국면입니다")
        assert "등급이 바뀔 때마다" in html
        assert "1시간 간격" in html
        assert "시장 신호 알림" in html


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


class TestRebalancingPlanPendingTemplate:
    """매수/매도 leg가 서로 독립적으로 존재할 수 있음(둘 중 하나만 있는 플랜도 유효) — 각 섹션은
    해당 leg가 있을 때만 렌더링되어야 한다. buy leg가 없을 때 buy_deadline_at=None으로 인한
    크래시가 없는지가 핵심 회귀 방지 포인트."""

    def _item(self, ticker="005930"):
        return SimpleNamespace(
            ticker=ticker, name="삼성전자", market="KOSPI", quantity=5, order_type="MARKET", limit_price=None
        )

    def _section(self, market="KR", ticker="005930", link="https://growlio.app/rebalancing/plan-confirm?token=t"):
        return {
            "market": market,
            "items": [self._item(ticker)],
            "deadline_at": datetime.now(UTC),
            "link": link,
        }

    def test_sell_only_plan_renders_without_buy_section(self):
        subject, html = rebalancing_plan_pending_template(
            portfolio_name="성장 포트폴리오",
            account_name="증권계좌",
            buy_sections=[],
            sell_sections=[self._section(link="https://growlio.app/rebalancing/plan-confirm?token=sell-token")],
        )

        assert "매도" in subject
        assert "매수" not in subject
        assert "매수 주문" not in html
        assert "매수 취소하기" not in html
        assert "매도 확인하러 가기" in html

    def test_buy_only_plan_renders_without_sell_section(self):
        subject, html = rebalancing_plan_pending_template(
            portfolio_name="성장 포트폴리오",
            account_name=None,
            buy_sections=[self._section(link="https://growlio.app/rebalancing/plan-confirm?token=buy-token")],
            sell_sections=[],
        )

        assert "매수" in subject
        assert "매도" not in subject
        assert "매수 취소하기" in html
        assert "매도 확인하러 가기" not in html

    def test_both_legs_present_renders_both_sections(self):
        subject, html = rebalancing_plan_pending_template(
            portfolio_name="성장 포트폴리오",
            account_name=None,
            buy_sections=[
                self._section("KR", "005930", "https://growlio.app/rebalancing/plan-confirm?token=buy-token")
            ],
            sell_sections=[
                self._section("KR", "000660", "https://growlio.app/rebalancing/plan-confirm?token=sell-token")
            ],
        )

        assert "매수/매도" in subject
        assert "매수 취소하기" in html
        assert "매도 확인하러 가기" in html

    def test_mixed_kr_us_legs_render_separate_sections_with_market_labels(self):
        subject, html = rebalancing_plan_pending_template(
            portfolio_name="성장 포트폴리오",
            account_name=None,
            buy_sections=[
                self._section("KR", "005930", "https://growlio.app/rebalancing/plan-confirm?token=buy-kr"),
                self._section("US", "AAPL", "https://growlio.app/rebalancing/plan-confirm?token=buy-us"),
            ],
            sell_sections=[],
        )

        assert "매수" in subject
        assert "매수 주문 (국내)" in html
        assert "매수 주문 (미국)" in html
        assert "token=buy-kr" in html
        assert "token=buy-us" in html
