"""리밸런싱 시점 판정(plans/136) — timing_verdict·drift_rule 순수 함수."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.rebalancing.drift_rule import alert_relative_threshold, drift_progress, is_drifting
from app.services.rebalancing.service import filter_drifting_items
from app.services.rebalancing.timing_verdict import decide_timing


def _item(target, diff):
    return SimpleNamespace(target_weight_pct=target, weight_diff_pct=diff)


class TestIsDrifting:
    def test_absolute_strictly_greater(self):
        assert is_drifting(5.0, 30.0, 5.0) is False
        assert is_drifting(-5.01, 30.0, 5.0) is True

    def test_small_target_needs_relative_rule(self):
        """목표 5% 종목이 0%가 돼도(전량 이탈) 절대 5%p는 못 넘는다 — 상대 기준을 켜야 잡힌다."""
        assert is_drifting(5.0, 5.0, 5.0) is False
        assert is_drifting(5.0, 5.0, 5.0, 25.0) is True

    def test_relative_strictly_greater(self):
        # 목표 10%의 25% = 2.5%p — 경계는 이탈 아님
        assert is_drifting(2.5, 10.0, 5.0, 25.0) is False
        assert is_drifting(2.6, 10.0, 5.0, 25.0) is True

    def test_zero_target_uses_absolute_only(self):
        assert is_drifting(-3.0, 0.0, 5.0, 10.0) is False

    def test_filter_drifting_items_passes_relative(self):
        items = [_item(10.0, 3.0), _item(40.0, 3.0)]
        assert filter_drifting_items(items, 5.0) == []
        assert filter_drifting_items(items, 5.0, 25.0) == [items[0]]


class TestDriftProgress:
    def test_takes_larger_of_absolute_and_relative(self):
        items = [_item(10.0, 2.0), _item(50.0, 1.0)]
        assert drift_progress(items, 5.0) == pytest.approx(0.4)
        # 상대: 2/10=20% → 20/25=0.8
        assert drift_progress(items, 5.0, 25.0) == pytest.approx(0.8)


class TestAlertRelativeThreshold:
    def test_reads_numeric(self):
        assert alert_relative_threshold(SimpleNamespace(relative_threshold_pct=Decimal("25"))) == 25.0

    def test_none_and_mock_are_off(self):
        assert alert_relative_threshold(SimpleNamespace(relative_threshold_pct=None)) is None
        # MagicMock 속성은 float()로 1.0이 된다 — 숫자로 보지 않는다
        assert alert_relative_threshold(MagicMock()) is None


def _decide(**overrides):
    kwargs = {
        "needs_rebalancing": True,
        "drift_progress": 1.4,
        "max_drift_pct": 7.0,
        "threshold_pct": 5.0,
        "relative_threshold_pct": None,
        "confirmed_level": "GREEN",
        "market_stale": False,
        "gate_blocked_mode": None,
        "estimated_overseas_tax_krw": 0.0,
    }
    kwargs.update(overrides)
    return decide_timing(**kwargs)


class TestDecideTiming:
    @pytest.mark.parametrize(
        ("overrides", "expected"),
        [
            ({}, "NOW"),
            ({"confirmed_level": "YELLOW"}, "SPLIT"),
            ({"confirmed_level": "RED"}, "HOLD"),
            ({"gate_blocked_mode": "STRICT", "confirmed_level": "YELLOW"}, "HOLD"),
            ({"gate_blocked_mode": "TACTICAL"}, "HOLD"),
            ({"needs_rebalancing": False, "drift_progress": 0.6}, "WATCH"),
            ({"needs_rebalancing": False, "drift_progress": 0.5}, "WATCH"),
            ({"needs_rebalancing": False, "drift_progress": 0.49}, "OK"),
            # 이탈이 아니면 시장 RED여도 할 일 없음
            ({"needs_rebalancing": False, "drift_progress": 0.1, "confirmed_level": "RED"}, "OK"),
        ],
    )
    def test_table(self, overrides, expected):
        assert _decide(**overrides).timing == expected

    def test_tax_is_appended_to_reason_without_changing_timing(self):
        verdict = _decide(estimated_overseas_tax_krw=123456)
        assert verdict.timing == "NOW"
        assert "123,456원" in verdict.reason

    def test_stale_gate_reason_mentions_signal_unavailable(self):
        verdict = _decide(gate_blocked_mode="CAUTIOUS", market_stale=True)
        assert verdict.timing == "HOLD"
        assert "확인할 수 없어" in verdict.reason

    def test_stale_without_gate_is_now_with_note(self):
        verdict = _decide(confirmed_level=None, market_stale=True)
        assert verdict.timing == "NOW"
        assert "확인하지 못했어요" in verdict.reason

    def test_reason_includes_relative_rule(self):
        assert "목표 대비 25%" in _decide(relative_threshold_pct=25.0).reason
