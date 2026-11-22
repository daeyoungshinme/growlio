"""plans/145 PR3 — 허용 범위 경계까지만 거래(`shrink_to_band`)·최소 거래액(`drop_orders_below_min_value`)."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.rebalancing.drift_rule import band_width_pct, shrink_to_band
from app.services.rebalancing.order_builder import drop_orders_below_min_value


def _row(**kwargs) -> SimpleNamespace:
    """기준 자산 1,000만원 포트폴리오의 한 종목(가격 1만원)."""
    defaults = {
        "target_weight_pct": 30.0,
        "current_weight_pct": 40.0,
        "weight_diff_pct": -10.0,
        "target_value_krw": 3_000_000.0,
        "current_value_krw": 4_000_000.0,
        "current_price_krw": 10_000.0,
        "current_qty": 400.0,
        "target_qty": 300.0,
        "shares_to_trade": -100.0,
        "diff_krw": -1_000_000.0,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class TestBandWidth:
    def test_absolute_only(self):
        assert band_width_pct(30.0, 5.0, None) == 5.0

    def test_relative_tighter_for_small_target(self):
        # 목표 10% × 25% = 2.5%p < 5%p
        assert band_width_pct(10.0, 5.0, 25.0) == 2.5

    def test_relative_ignored_for_zero_target(self):
        assert band_width_pct(0.0, 5.0, 25.0) == 5.0


class TestShrinkToBand:
    def test_overweight_sells_only_to_upper_edge(self):
        row = _row()
        shrink_to_band(row, 5.0)
        # 목표 30% + 5%p = 35% → 350만원까지만 매도
        assert row.target_value_krw == 3_500_000.0
        assert row.diff_krw == -500_000.0
        assert row.shares_to_trade == -50.0
        assert row.target_qty == 350.0

    def test_underweight_buys_only_to_lower_edge_with_relative_band(self):
        row = _row(
            target_weight_pct=10.0,
            current_weight_pct=6.0,
            weight_diff_pct=4.0,
            target_value_krw=1_000_000.0,
            current_value_krw=600_000.0,
            current_qty=60.0,
            target_qty=100.0,
            shares_to_trade=40.0,
            diff_krw=400_000.0,
        )
        shrink_to_band(row, 5.0, 25.0)
        # 목표 10% − 2.5%p = 7.5% → 75만원(75주)까지만 매수. 실시간가 재계산용 반 주 여유가 목표 금액에 붙는다
        assert row.target_value_krw == 755_000.0
        assert row.shares_to_trade == 15.0

    def test_underweight_buy_rounds_up_to_get_inside_band(self):
        """plans/146 A3 — 경계까지 내림하면 1주 미만 모자라 다음 실행에 또 이탈 — 경계 안쪽 정수 주까지 산다."""
        row = _row(
            target_weight_pct=30.0,
            current_weight_pct=20.0,
            weight_diff_pct=10.0,
            target_value_krw=3_000_000.0,
            current_value_krw=2_000_000.0,
            current_price_krw=300_000.0,
            current_qty=6.666,
            target_qty=10.0,
            shares_to_trade=3.0,
            diff_krw=1_000_000.0,
        )
        shrink_to_band(row, 5.0)
        # 하단 경계 25% = 250만원 → 8.33주. 내림(8주=240만)은 24%로 경계 밖, 9주(270만)는 안쪽이고 목표 300만 이하
        assert row.target_qty == 9.0
        assert row.target_value_krw <= 3_000_000.0
        assert 9 * 300_000 / 10_000_000 * 100 > 25.0

    def test_buy_never_exceeds_full_target_value(self):
        row = _row(
            target_weight_pct=30.0,
            current_weight_pct=20.0,
            weight_diff_pct=10.0,
            target_value_krw=3_000_000.0,
            current_value_krw=2_000_000.0,
            current_price_krw=2_900_000.0,
            current_qty=0.0,
            target_qty=1.0,
            shares_to_trade=1.0,
            diff_krw=1_000_000.0,
        )
        shrink_to_band(row, 5.0)
        assert row.target_value_krw == 3_000_000.0
        assert row.target_qty == 1.0

    def test_inside_band_is_untouched(self):
        row = _row(weight_diff_pct=-3.0)
        shrink_to_band(row, 5.0)
        assert row.target_value_krw == 3_000_000.0
        assert row.shares_to_trade == -100.0

    def test_group_row_changes_target_value_only(self):
        """지수 그룹 행은 수량이 없다 — 목표 금액만 줄이면 expand_group_items가 그 값으로 멤버에 배분한다."""
        row = _row(shares_to_trade=None, target_qty=None)
        shrink_to_band(row, 5.0)
        assert row.target_value_krw == 3_500_000.0
        assert row.shares_to_trade is None

    def test_untargeted_holding_is_fully_sold(self):
        """plans/146 A4 — 목표 0%는 경계에서 멈추지 않고 전량 정리한다(멈추면 그 뒤로는 이탈이 아니라 남는다)."""
        row = _row(
            target_weight_pct=0.0,
            current_weight_pct=8.0,
            weight_diff_pct=-8.0,
            target_value_krw=0.0,
            current_value_krw=800_000.0,
            current_qty=80.0,
            target_qty=0.0,
            shares_to_trade=-80.0,
            diff_krw=-800_000.0,
        )
        shrink_to_band(row, 5.0)
        assert row.target_value_krw == 0.0
        assert row.shares_to_trade == -80.0


def _order(qty: int, price: float | None, ticker: str = "A") -> SimpleNamespace:
    return SimpleNamespace(ticker=ticker, side="BUY", quantity=qty, reference_price=price)


class TestMinTradeFilter:
    def test_drops_small_orders(self):
        orders = [_order(1, 50_000.0, "SMALL"), _order(10, 50_000.0, "BIG")]
        kept = drop_orders_below_min_value(orders, 100_000.0)
        assert [o.ticker for o in kept] == ["BIG"]

    def test_none_keeps_all(self):
        orders = [_order(1, 1.0)]
        assert drop_orders_below_min_value(orders, None) == orders

    def test_unpriced_order_is_kept(self):
        orders = [_order(1, None)]
        assert drop_orders_below_min_value(orders, 100_000.0) == orders


class TestPlanGenerationWiring:
    """`_drifting_items_for_alert`가 알림의 trade_to_band를 따른다."""

    @pytest.mark.asyncio
    async def test_trade_to_band_shrinks_before_expansion(self):
        from app.services.rebalancing import plan_generation as gen

        row = _row(ticker="A", market="KOSPI", members=[], group_key=None)
        analysis = SimpleNamespace(items=[row], ticker_account_map={})
        alert = SimpleNamespace(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            trigger_condition="DRIFT_ONLY",
            threshold_pct=5.0,
            relative_threshold_pct=None,
            trade_to_band=True,
        )
        with (
            patch("app.services.rebalancing.alert_scope.load_alert_overview", new=AsyncMock(return_value={})),
            patch("app.services.rebalancing.alert_scope.analyze_alert_overview", return_value=analysis),
            patch.object(gen, "expand_group_items", side_effect=lambda items, _t: items) as expand,
            patch.object(gen, "refresh_live_prices", new=AsyncMock()),
        ):
            prepared = await gen._drifting_items_for_alert(alert, MagicMock(), MagicMock(), None, None)

        assert prepared is not None
        # 펼침 시점에 이미 경계까지 줄어 있어야 그룹 멤버 배분도 줄어든 금액을 쓴다
        assert expand.call_args.args[0][0].target_value_krw == 3_500_000.0

    @pytest.mark.asyncio
    async def test_off_by_default_trades_to_target(self):
        from app.services.rebalancing import plan_generation as gen

        row = _row(ticker="A", market="KOSPI", members=[], group_key=None)
        analysis = SimpleNamespace(items=[row], ticker_account_map={})
        alert = SimpleNamespace(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            trigger_condition="DRIFT_ONLY",
            threshold_pct=5.0,
            relative_threshold_pct=None,
            trade_to_band=False,
        )
        with (
            patch("app.services.rebalancing.alert_scope.load_alert_overview", new=AsyncMock(return_value={})),
            patch("app.services.rebalancing.alert_scope.analyze_alert_overview", return_value=analysis),
            patch.object(gen, "expand_group_items", side_effect=lambda items, _t: items),
            patch.object(gen, "refresh_live_prices", new=AsyncMock()),
        ):
            await gen._drifting_items_for_alert(alert, MagicMock(), MagicMock(), None, None)

        assert row.target_value_krw == 3_000_000.0


class TestAlertSchema:
    def test_defaults_keep_existing_behavior(self):
        from app.schemas.rebalancing import RebalancingAlertCreate

        body = RebalancingAlertCreate(portfolio_id=uuid.uuid4())
        assert (body.dca_allocation_mode, body.trade_to_band, body.min_trade_krw) == ("TARGET", False, None)

    def test_min_trade_must_be_positive(self):
        from pydantic import ValidationError

        from app.schemas.rebalancing import RebalancingAlertCreate

        with pytest.raises(ValidationError):
            RebalancingAlertCreate(portfolio_id=uuid.uuid4(), min_trade_krw=0)
        assert RebalancingAlertCreate(portfolio_id=uuid.uuid4(), min_trade_krw=50_000.4).min_trade_krw == 50_000


class TestMinTradeSkipsFixedDca:
    """plans/146 A5 — 최소 거래액은 정액 적립 매수를 지우지 않는다(일반 AUTO에는 그대로 적용)."""

    @staticmethod
    def _build(alert):
        from unittest.mock import patch

        from app.services.rebalancing import plan_generation as pg

        orders = [_order(1, 50_000.0, "SMALL"), _order(10, 50_000.0, "BIG")]
        with (
            patch.object(pg, "build_rebalancing_orders", return_value=orders),
            patch.object(pg, "clamp_orders_to_max_value", side_effect=lambda o, _cap: o),
            patch.object(pg, "_coerce_overseas_market_orders_to_limit", side_effect=lambda o, **_kw: o),
        ):
            return pg._build_plan_orders(alert, [], {}, "BUY_ONLY", "MARKET", None)

    @staticmethod
    def _alert(**kwargs):
        import uuid

        defaults = {
            "id": uuid.uuid4(),
            "strategy": "BUY_ONLY",
            "trigger_condition": "SCHEDULE_ONLY",
            "schedule_type": "MONTHLY",
            "mode": "AUTO",
            "dca_amount_krw": 300_000.0,
            "min_trade_krw": 100_000.0,
        }
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)

    def test_fixed_dca_keeps_small_orders(self):
        assert [o.ticker for o in self._build(self._alert())] == ["SMALL", "BIG"]

    def test_regular_auto_still_drops_small_orders(self):
        assert [o.ticker for o in self._build(self._alert(dca_amount_krw=None))] == ["BIG"]


class TestAlertOrderPreviewMatchesPlan:
    """plans/146 A8 — 알림 메일 수량 미리보기도 경계 거래·최소 거래액을 실제 플랜과 같게 반영한다."""

    @staticmethod
    def _alert(**kwargs):
        import uuid

        defaults = {
            "id": uuid.uuid4(),
            "account_id": None,
            "strategy": "FULL",
            "order_type": "MARKET",
            "trigger_condition": "DRIFT_ONLY",
            "schedule_type": "DAILY",
            "mode": "AUTO",
            "threshold_pct": 5.0,
            "relative_threshold_pct": None,
            "trade_to_band": True,
            "min_trade_krw": 100_000.0,
            "dca_amount_krw": None,
        }
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)

    def test_shrinks_copy_and_drops_small_orders(self):
        from unittest.mock import patch

        from app.services.rebalancing import order_builder as ob

        row = _row()
        captured: list = []

        def fake_build(drifting, *_args, **_kw):
            captured.extend(drifting)
            return [_order(1, 50_000.0, "SMALL"), _order(10, 50_000.0, "BIG")]

        with patch.object(ob, "build_rebalancing_orders", side_effect=fake_build):
            orders = ob.build_alert_order_preview(self._alert(), [row], {})
        assert [o.ticker for o in orders] == ["BIG"]
        assert captured[0].target_value_krw == 3_500_000.0  # 상단 경계까지만
        assert row.target_value_krw == 3_000_000.0  # 원본 분석 행은 그대로
