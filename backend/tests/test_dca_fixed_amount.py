"""정기 적립 정액 매수 + 해외 달러 환전 대기(plans/120)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from app.exceptions import AppError
from app.schemas.rebalancing import RebalancingItem
from app.services.rebalancing import plan_execution as svc_exec
from app.services.rebalancing import plan_generation as gen
from app.services.rebalancing.dca_allocation import allocate_dca_amount, dca_buy_rows

_ET = ZoneInfo("America/New_York")


def _item(ticker, market, weight, price, **kwargs) -> RebalancingItem:
    defaults = {
        "ticker": ticker,
        "name": ticker,
        "market": market,
        "target_weight_pct": weight,
        "current_weight_pct": 0.0,
        "weight_diff_pct": 0.0,
        "current_value_krw": 0.0,
        "target_value_krw": 0.0,
        "diff_krw": 0.0,
        "shares_to_trade": None,
        "current_price_krw": price,
        "current_qty": 0.0,
    }
    defaults.update(kwargs)
    return RebalancingItem(**defaults)


def _dca_alert(**kwargs) -> SimpleNamespace:
    defaults = {
        "id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "account_id": uuid.uuid4(),
        "strategy": "BUY_ONLY",
        "order_type": "MARKET",
        "trigger_condition": "SCHEDULE_ONLY",
        "schedule_type": "MONTHLY",
        "mode": "AUTO",
        "buy_wait_minutes": 10,
        "dca_amount_krw": 500_000.0,
        "market_condition_mode": "DISABLED",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ── 정액 분할 ─────────────────────────────────────────────


class TestAllocateDcaAmount:
    def test_splits_by_weight_and_never_exceeds_amount(self):
        rows = dca_buy_rows(
            [_item("A", "KOSPI", 60, 10_000.0), _item("B", "KOSPI", 40, 30_000.0)],
            "GENERAL",
        )
        result = allocate_dca_amount(rows, 500_000.0)

        qty = {i.ticker: i.shares_to_trade for i in result.items}
        # A 30만원 → 30주, B 20만원 → 6주(18만원) 후 잔액 2만원으로 B 미달분이 더 커도 1주(3만원)는 못 사 A에 2주
        assert qty == {"A": 32.0, "B": 6.0}
        assert result.spent_krw <= 500_000.0
        assert result.spent_krw == 32 * 10_000 + 6 * 30_000

    def test_amount_capped_even_when_cash_is_huge(self):
        """예수금이 1,000만원이어도 정한 50만원까지만 산다 — 보유 비중·예수금은 분할에 쓰지 않는다."""
        rows = dca_buy_rows([_item("A", "KOSPI", 100, 7_000.0, current_value_krw=10_000_000.0)], "GENERAL")
        result = allocate_dca_amount(rows, 500_000.0)

        spent = sum(i.shares_to_trade * i.current_price_krw for i in result.items)
        assert spent <= 500_000.0
        assert result.items[0].shares_to_trade == 71.0  # floor(500,000 / 7,000)
        assert result.items[0].diff_krw > 0  # build_rebalancing_orders 방향 검사 통과

    def test_reports_unaffordable_items(self):
        rows = dca_buy_rows(
            [_item("CHEAP", "KOSPI", 90, 10_000.0), _item("PRICEY", "NASDAQ", 10, 900_000.0)], "GENERAL"
        )
        result = allocate_dca_amount(rows, 300_000.0)

        assert [i.ticker for i in result.items] == ["CHEAP"]
        assert result.unaffordable == ["PRICEY"]
        assert result.spent_krw <= 300_000.0

    def test_excludes_cash_and_zero_weight_and_renormalizes(self):
        rows = dca_buy_rows(
            [
                _item("CASH", "CASH", 20, None),
                _item("A", "KOSPI", 80, 10_000.0),
                _item("Z", "KOSPI", 0, 10_000.0),
            ],
            "GENERAL",
        )
        assert [r.ticker for r, _ in rows] == ["A"]
        result = allocate_dca_amount(rows, 100_000.0)
        assert result.items[0].shares_to_trade == 10.0

    def test_group_buys_primary_or_domestic_alt_for_tax_deferred(self):
        primary = _item("QQQ", "NASDAQ", 0, 700_000.0, group_role="PRIMARY")
        alt = _item("133690", "KOSPI", 0, 100_000.0, group_role="DOMESTIC_ALT")
        group = _item("QQQ", "NASDAQ", 100, None, group_key="nasdaq100", members=[primary, alt])

        general = dca_buy_rows([group], "GENERAL")
        isa = dca_buy_rows([group], "ISA")

        assert [(r.ticker, w) for r, w in general] == [("QQQ", 100.0)]
        assert [(r.ticker, w) for r, w in isa] == [("133690", 100.0)]
        assert general[0][0].group_key is None  # 펼친 행은 order_builder가 다시 그룹으로 펼치지 않는다
        assert group.members[0].shares_to_trade is None  # 원본 분석 행은 바꾸지 않는다

    def test_overseas_skipped_in_tax_deferred_account(self):
        rows = dca_buy_rows([_item("AAPL", "NASDAQ", 50, 300_000.0), _item("A", "KOSPI", 50, 10_000.0)], "ISA")
        assert [r.ticker for r, _ in rows] == ["A"]

    def test_no_price_is_unaffordable(self):
        result = allocate_dca_amount(dca_buy_rows([_item("A", "KOSPI", 100, None)], "GENERAL"), 100_000.0)
        assert result.items == []
        assert result.unaffordable == ["A"]


# ── 장 시간 유틸 ──────────────────────────────────────────


class TestMarketHourHelpers:
    def test_next_us_open_skips_weekend(self):
        from app.utils.market_hours import next_us_market_open

        friday_noon = datetime(2026, 11, 13, 12, 0, tzinfo=_ET)
        assert next_us_market_open(friday_noon) == datetime(2026, 11, 16, 9, 30, tzinfo=_ET)

    def test_next_us_open_same_day_before_open(self):
        from app.utils.market_hours import next_us_market_open

        tuesday_early = datetime(2026, 11, 10, 6, 0, tzinfo=_ET)
        assert next_us_market_open(tuesday_early) == datetime(2026, 11, 10, 9, 30, tzinfo=_ET)

    def test_close_after_weekdays(self):
        from app.utils.market_hours import us_market_close_after_weekdays

        thursday = datetime(2026, 11, 12, 10, 0, tzinfo=_ET)
        assert us_market_close_after_weekdays(5, thursday) == datetime(2026, 11, 19, 16, 0, tzinfo=_ET)


# ── 스키마 ────────────────────────────────────────────────


class TestAlertSchema:
    def _body(self, **kwargs):
        from app.schemas.rebalancing import RebalancingAlertCreate

        body = {
            "portfolio_id": str(uuid.uuid4()),
            "schedule_type": "MONTHLY",
            "schedule_day_of_month": 25,
            "trigger_condition": "SCHEDULE_ONLY",
            "mode": "AUTO",
            "strategy": "BUY_ONLY",
        }
        body.update(kwargs)
        return RebalancingAlertCreate(**body)

    def test_accepts_amount_on_dca_preset(self):
        assert self._body(dca_amount_krw=500_000).dca_amount_krw == 500_000

    def test_rejects_amount_outside_preset(self):
        with pytest.raises(ValidationError):
            self._body(dca_amount_krw=500_000, strategy="FULL")

    @pytest.mark.parametrize("amount", [0, 5_000, float("nan")])
    def test_rejects_invalid_amount(self, amount):
        with pytest.raises(ValidationError):
            self._body(dca_amount_krw=amount)


# ── 플랜 생성 ─────────────────────────────────────────────


class TestDcaPlanGeneration:
    def test_is_dca_amount_mode(self):
        assert gen.is_dca_amount_mode(_dca_alert())
        assert not gen.is_dca_amount_mode(_dca_alert(dca_amount_krw=None))
        assert not gen.is_dca_amount_mode(_dca_alert(strategy="FULL"))
        assert not gen.is_dca_amount_mode(_dca_alert(trigger_condition="DRIFT_ONLY"))

    @pytest.mark.asyncio
    async def test_us_buy_leg_waits_for_next_us_open_when_closed(self, mock_db):
        alert = _dca_alert()
        portfolio = SimpleNamespace(id=uuid.uuid4(), name="적립")
        drifting = [
            SimpleNamespace(
                ticker="005930", name="삼성", market="KOSPI", diff_krw=70000.0, shares_to_trade=1.0,
                current_price_krw=70000.0,
            ),
            SimpleNamespace(
                ticker="AAPL", name="애플", market="NASDAQ", diff_krw=300000.0, shares_to_trade=1.0,
                current_price_krw=300000.0,
            ),
        ]  # fmt: skip
        next_open = datetime(2026, 11, 10, 9, 30, tzinfo=_ET)
        with (
            patch("app.utils.market_hours.is_us_market_open", return_value=False),
            patch("app.utils.market_hours.next_us_market_open", return_value=next_open),
        ):
            plan, buy_tokens, _ = await gen.generate_pending_plan_for_alert(
                alert, portfolio, drifting, mock_db, {}, "GREEN"
            )

        assert len(buy_tokens) == 2
        legs = {leg.market: leg for leg in plan.legs}
        assert legs["US"].deadline_at == next_open.astimezone(UTC) + timedelta(minutes=10)
        assert legs["KR"].deadline_at < legs["US"].deadline_at

    @pytest.mark.asyncio
    async def test_non_dca_us_leg_keeps_wait_minutes(self, mock_db):
        alert = _dca_alert(dca_amount_krw=None)
        drifting = [
            SimpleNamespace(
                ticker="AAPL", name="애플", market="NASDAQ", diff_krw=300000.0, shares_to_trade=1.0,
                current_price_krw=300000.0,
            )
        ]  # fmt: skip
        before = datetime.now(tz=UTC)
        with patch("app.utils.market_hours.is_us_market_open", return_value=False):
            plan, _, _ = await gen.generate_pending_plan_for_alert(
                alert, SimpleNamespace(id=uuid.uuid4()), drifting, mock_db, {}, "GREEN"
            )
        assert plan.legs[0].deadline_at < before + timedelta(minutes=11)

    @pytest.mark.asyncio
    async def test_dca_items_for_alert_allocates_after_live_prices(self, mock_db):
        alert = _dca_alert(dca_amount_krw=100_000.0)
        analysis = SimpleNamespace(items=[_item("A", "KOSPI", 100, 1.0)], ticker_account_map={})

        async def _refresh(items, *_args):
            for item in items:
                item.current_price_krw = 20_000.0
                item.shares_to_trade = 999.0  # 목표금액 기준 재계산 — 분할이 덮어써야 한다

        with (
            patch("app.services.rebalancing.alert_scope.load_alert_overview", new=AsyncMock(return_value=None)),
            patch("app.services.rebalancing.alert_scope.analyze_alert_overview", return_value=analysis),
            patch.object(gen, "refresh_live_prices", new=AsyncMock(side_effect=_refresh)),
        ):
            prepared = await gen._dca_items_for_alert(alert, SimpleNamespace(), mock_db, alert.account_id, None)

        assert prepared is not None
        _, _, items = prepared
        assert [(i.ticker, i.shares_to_trade) for i in items] == [("A", 5.0)]
        assert analysis.items[0].shares_to_trade is None

    @pytest.mark.asyncio
    async def test_build_pending_plan_uses_dca_branch(self, mock_db):
        alert = _dca_alert()
        portfolio = SimpleNamespace(id=uuid.uuid4(), items=[])
        with (
            patch.object(gen, "_check_snapshot_freshness", new=AsyncMock(return_value=None)),
            patch.object(gen, "_dca_items_for_alert", new=AsyncMock(return_value=None)) as dca,
            patch.object(gen, "_drifting_items_for_alert", new=AsyncMock(return_value=None)) as drift,
        ):
            result = await gen.build_pending_plan_for_alert(alert, portfolio, mock_db, "GREEN", cache=MagicMock())
        assert result is None
        dca.assert_awaited_once()
        drift.assert_not_awaited()


# ── 달러 확인 ─────────────────────────────────────────────


class TestUsdBuyingPower:
    def test_required_usd_sums_us_limit_orders_with_buffer(self):
        from app.services.rebalancing.usd_buying_power import FX_FEE_BUFFER, required_usd_for_orders

        orders = [
            SimpleNamespace(market="NASDAQ", quantity=2, limit_price=100.0),
            SimpleNamespace(market="KOSPI", quantity=10, limit_price=70000.0),
        ]
        assert required_usd_for_orders(orders) == round(200.0 * FX_FEE_BUFFER, 2)
        assert required_usd_for_orders([SimpleNamespace(market="NYSE", quantity=1, limit_price=None)]) is None

    @pytest.mark.asyncio
    async def test_check_shortfall(self, mock_db):
        from app.services.rebalancing import usd_buying_power as ubp

        order = SimpleNamespace(market="NASDAQ", quantity=3, limit_price=100.0)
        with (
            patch.object(svc_exec, "_rebuild_orders_from_items", new=AsyncMock(return_value=[order])),
            patch.object(ubp, "fetch_usd_buying_power", new=AsyncMock(return_value=50.0)),
        ):
            short = await ubp.check_usd_shortfall([], uuid.uuid4(), uuid.uuid4(), mock_db, None)
        assert short is not None
        assert short.available_usd == 50.0
        assert short.required_usd > 300.0

        for available, expected in ((500.0, None), (None, ubp.USD_UNKNOWN)):
            with (
                patch.object(svc_exec, "_rebuild_orders_from_items", new=AsyncMock(return_value=[order])),
                patch.object(ubp, "fetch_usd_buying_power", new=AsyncMock(return_value=available)),
            ):
                assert await ubp.check_usd_shortfall([], uuid.uuid4(), uuid.uuid4(), mock_db, None) is expected

    @pytest.mark.asyncio
    async def test_check_unknown_when_price_or_limit_missing(self, mock_db):
        """시세 실패·지정가 없음은 "충분"이 아니라 미확인이다(plans/122 A2)."""
        from app.services.rebalancing import usd_buying_power as ubp

        with patch.object(svc_exec, "_rebuild_orders_from_items", new=AsyncMock(side_effect=ValueError("no price"))):
            assert await ubp.check_usd_shortfall([], uuid.uuid4(), uuid.uuid4(), mock_db, None) is ubp.USD_UNKNOWN
        no_limit = SimpleNamespace(market="NASDAQ", quantity=1, limit_price=None)
        with patch.object(svc_exec, "_rebuild_orders_from_items", new=AsyncMock(return_value=[no_limit])):
            assert await ubp.check_usd_shortfall([], uuid.uuid4(), uuid.uuid4(), mock_db, None) is ubp.USD_UNKNOWN

    @pytest.mark.asyncio
    async def test_fetch_returns_none_on_error(self, mock_db):
        from app.services.rebalancing import usd_buying_power as ubp

        with patch(
            "app.services.rebalancing.execution_service.load_executable_account",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ):
            assert await ubp.fetch_usd_buying_power(uuid.uuid4(), uuid.uuid4(), mock_db, None) is None

    @pytest.mark.asyncio
    async def test_fetch_kiwoom_deposit(self, mock_db):
        from app.services.rebalancing import usd_buying_power as ubp

        account = SimpleNamespace(is_mock_mode=False, asset_type="STOCK_KIWOOM", kiwoom_account_no="123")
        with (
            patch(
                "app.services.rebalancing.execution_service.load_executable_account",
                new=AsyncMock(return_value=account),
            ),
            patch("app.services.rebalancing.execution_service.load_kiwoom_credentials", return_value=("k", "s")),
            patch("app.kiwoom.auth.get_access_token", new=AsyncMock(return_value="tok")),
            patch("app.kiwoom.balance.get_overseas_balance", new=AsyncMock(return_value={"deposit_usd": 123.45})),
        ):
            assert await ubp.fetch_usd_buying_power(uuid.uuid4(), uuid.uuid4(), mock_db, None) == 123.45


# ── 실행 경로 ─────────────────────────────────────────────


def _us_leg(status="PENDING", **kwargs):
    defaults = {
        "id": uuid.uuid4(),
        "plan_id": uuid.uuid4(),
        "side": "BUY",
        "market": "US",
        "status": status,
        "deadline_at": datetime.now(tz=UTC) - timedelta(minutes=1),
        "decided_at": None,
        "decided_by": None,
        "execution_id": None,
        "error_message": None,
        "token_consumed_at": None,
        "items": [],
        "fx_retry_until": None,
        "required_usd": None,
        "available_usd": None,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _wire_db(mock_db, leg, plan, alert, due_ids=None):
    from app.models.alert import RebalancingAlert
    from app.models.rebalancing_plan import RebalancingPlan, RebalancingPlanLeg

    async def _get(model, _pk):
        if model is RebalancingPlan:
            return plan
        if model is RebalancingAlert:
            return alert
        if model is RebalancingPlanLeg:
            return leg
        return None

    due = MagicMock()
    due.all.return_value = [(leg.id,)] if due_ids is None else due_ids
    mock_db.execute = AsyncMock(return_value=due)
    mock_db.scalar = AsyncMock(return_value=leg)
    mock_db.get = AsyncMock(side_effect=_get)


def _plan(alert):
    return SimpleNamespace(
        id=uuid.uuid4(),
        alert_id=alert.id,
        user_id=alert.user_id,
        account_id=alert.account_id,
        portfolio_id=uuid.uuid4(),
        strategy="BUY_ONLY",
    )


class TestRunDueBuyLegFx:
    @pytest.mark.asyncio
    async def test_shortfall_moves_leg_to_waiting_fx_without_consuming_token(self, mock_db):
        from app.services.rebalancing.usd_buying_power import UsdShortfall

        alert = _dca_alert()
        leg = _us_leg()
        plan = _plan(alert)
        _wire_db(mock_db, leg, plan, alert)
        notify = AsyncMock()
        with (
            patch("app.utils.market_hours.is_us_market_open", return_value=True),
            patch.object(svc_exec, "_usd_shortfall_for_leg", new=AsyncMock(return_value=UsdShortfall(350.0, 12.0))),
            patch("app.services.rebalancing.plan_notifications.notify_dca_fx_required", new=notify),
            patch.object(svc_exec, "_execute_leg", new=AsyncMock()) as execute,
        ):
            count = await svc_exec.execute_due_buy_legs(mock_db, MagicMock())

        assert count == 1
        assert leg.status == "WAITING_FX"
        assert leg.token_consumed_at is None
        assert (leg.required_usd, leg.available_usd) == (350.0, 12.0)
        assert leg.fx_retry_until is not None
        assert leg.fx_retry_until > datetime.now(tz=UTC)
        execute.assert_not_awaited()
        notify.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_enough_usd_executes(self, mock_db):
        alert = _dca_alert()
        leg = _us_leg()
        _wire_db(mock_db, leg, _plan(alert), alert)
        with (
            patch("app.utils.market_hours.is_us_market_open", return_value=True),
            patch.object(svc_exec, "_usd_shortfall_for_leg", new=AsyncMock(return_value=None)),
            patch.object(svc_exec, "_execute_leg", new=AsyncMock(return_value=None)) as execute,
        ):
            await svc_exec.execute_due_buy_legs(mock_db, MagicMock())
        execute.assert_awaited_once()
        assert leg.token_consumed_at is not None

    @pytest.mark.asyncio
    async def test_reentering_wait_does_not_notify_again(self, mock_db):
        """재개 → 또 부족이면 상태만 대기로 — 환전 안내 메일·푸시를 반복하지 않는다(plans/122 B1)."""
        from app.services.rebalancing.usd_buying_power import UsdShortfall

        alert = _dca_alert()
        first_until = datetime.now(tz=UTC) + timedelta(days=2)
        leg = _us_leg(fx_retry_until=first_until)
        _wire_db(mock_db, leg, _plan(alert), alert)
        notify = AsyncMock()
        with (
            patch("app.utils.market_hours.is_us_market_open", return_value=True),
            patch.object(svc_exec, "_usd_shortfall_for_leg", new=AsyncMock(return_value=UsdShortfall(350.0, 12.0))),
            patch("app.services.rebalancing.plan_notifications.notify_dca_fx_required", new=notify),
        ):
            await svc_exec.execute_due_buy_legs(mock_db, MagicMock())
        assert leg.status == "WAITING_FX"
        assert leg.fx_retry_until == first_until
        notify.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_short_after_wait_deadline_expires_instead_of_waiting(self, mock_db):
        from app.services.rebalancing.usd_buying_power import UsdShortfall

        alert = _dca_alert()
        leg = _us_leg(fx_retry_until=datetime.now(tz=UTC) - timedelta(minutes=5))
        _wire_db(mock_db, leg, _plan(alert), alert)
        required = AsyncMock()
        with (
            patch("app.utils.market_hours.is_us_market_open", return_value=True),
            patch.object(svc_exec, "_usd_shortfall_for_leg", new=AsyncMock(return_value=UsdShortfall(350.0, 12.0))),
            patch("app.services.rebalancing.plan_notifications.notify_dca_fx_required", new=required),
            patch("app.services.rebalancing.plan_notifications.notify_dca_fx_wait_expired", new=AsyncMock()),
        ):
            await svc_exec.execute_due_buy_legs(mock_db, MagicMock())
        assert leg.status == "EXPIRED"
        required.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_resumed_leg_returns_to_waiting_when_market_closed(self, mock_db):
        """재개된 leg가 장 밖(서버 슬립·장마감 경계)에 돌면 만료가 아니라 대기로 돌아간다(plans/122 A3)."""
        alert = _dca_alert()
        leg = _us_leg(fx_retry_until=datetime.now(tz=UTC) + timedelta(days=2))
        _wire_db(mock_db, leg, _plan(alert), alert)
        expired = AsyncMock()
        with (
            patch("app.utils.market_hours.is_us_market_open", return_value=False),
            patch.object(svc_exec, "_notify_buy_leg_expired", new=expired),
            patch.object(svc_exec, "_execute_leg", new=AsyncMock()) as execute,
        ):
            await svc_exec.execute_due_buy_legs(mock_db, MagicMock())
        assert leg.status == "WAITING_FX"
        assert leg.decided_at is None
        execute.assert_not_awaited()
        expired.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_plain_leg_still_expires_when_market_closed(self, mock_db):
        alert = _dca_alert()
        leg = _us_leg()
        _wire_db(mock_db, leg, _plan(alert), alert)
        with (
            patch("app.utils.market_hours.is_us_market_open", return_value=False),
            patch.object(svc_exec, "_notify_buy_leg_expired", new=AsyncMock()),
        ):
            await svc_exec.execute_due_buy_legs(mock_db, MagicMock())
        assert leg.status == "EXPIRED"

    @pytest.mark.asyncio
    async def test_non_dca_alert_skips_usd_check(self, mock_db):
        alert = _dca_alert(dca_amount_krw=None)
        leg = _us_leg()
        _wire_db(mock_db, leg, _plan(alert), alert)
        with (
            patch("app.utils.market_hours.is_us_market_open", return_value=True),
            patch.object(svc_exec, "_usd_shortfall_for_leg", new=AsyncMock()) as check,
            patch.object(svc_exec, "_execute_leg", new=AsyncMock(return_value=None)),
        ):
            await svc_exec.execute_due_buy_legs(mock_db, MagicMock())
        check.assert_not_awaited()


class TestRetryFxWaitingLeg:
    def _setup(self, mock_db, **leg_kwargs):
        alert = _dca_alert()
        leg = _us_leg(status="WAITING_FX", fx_retry_until=datetime.now(tz=UTC) + timedelta(days=3), **leg_kwargs)
        plan = _plan(alert)
        _wire_db(mock_db, leg, plan, alert)
        return leg

    @pytest.mark.asyncio
    async def test_still_short_updates_amounts(self, mock_db):
        from app.services.rebalancing.usd_buying_power import UsdShortfall

        leg = self._setup(mock_db)
        with patch.object(svc_exec, "_usd_shortfall_for_leg", new=AsyncMock(return_value=UsdShortfall(300.0, 80.0))):
            outcome, execution_id, latest = await svc_exec.retry_fx_waiting_leg(leg, mock_db, None, "USER_APP")
        assert outcome == "STILL_SHORT"
        assert execution_id is None
        assert latest.status == "WAITING_FX"
        assert latest.available_usd == 80.0

    @pytest.mark.asyncio
    async def test_schedules_for_next_open_when_market_closed(self, mock_db):
        leg = self._setup(mock_db)
        next_open = datetime(2026, 11, 10, 9, 30, tzinfo=_ET)
        with (
            patch.object(svc_exec, "_usd_shortfall_for_leg", new=AsyncMock(return_value=None)),
            patch("app.utils.market_hours.is_us_market_open", return_value=False),
            patch("app.utils.market_hours.next_us_market_open", return_value=next_open),
        ):
            outcome, _, latest = await svc_exec.retry_fx_waiting_leg(leg, mock_db, None, "USER_APP")
        assert outcome == "SCHEDULED"
        assert latest.status == "PENDING"
        assert latest.deadline_at == next_open.astimezone(UTC)

    @pytest.mark.asyncio
    async def test_executes_immediately_when_market_open(self, mock_db):
        leg = self._setup(mock_db)
        execution_id = uuid.uuid4()

        async def _approve(locked, *_args, **_kwargs):
            # 재개와 선점 사이에 commit하면 락이 풀려 1분 잡이 끼어든다(plans/122 B3)
            assert mock_db.commit.await_count == 0
            locked.status = "EXECUTED"
            return execution_id

        with (
            patch.object(svc_exec, "_usd_shortfall_for_leg", new=AsyncMock(return_value=None)),
            patch("app.utils.market_hours.is_us_market_open", return_value=True),
            patch.object(svc_exec, "_approve_leg_now", new=AsyncMock(side_effect=_approve)),
        ):
            outcome, got_id, _ = await svc_exec.retry_fx_waiting_leg(leg, mock_db, None, "USER_APP")
        assert (outcome, got_id) == ("EXECUTED", execution_id)

    @pytest.mark.asyncio
    async def test_rejects_non_waiting_leg(self, mock_db):
        leg = _us_leg(status="PENDING")
        with pytest.raises(AppError):
            await svc_exec.retry_fx_waiting_leg(leg, mock_db, None, "USER_APP")

    @pytest.mark.asyncio
    async def test_expired_deadline_closes_leg(self, mock_db):
        leg = self._setup(mock_db)
        leg.fx_retry_until = datetime.now(tz=UTC) - timedelta(minutes=1)
        with (
            patch.object(svc_exec, "_usd_shortfall_for_leg", new=AsyncMock(return_value=None)),
            patch("app.services.rebalancing.plan_notifications.notify_dca_fx_wait_expired", new=AsyncMock()),
            pytest.raises(AppError),
        ):
            await svc_exec.retry_fx_waiting_leg(leg, mock_db, None, "USER_APP")
        assert leg.status == "EXPIRED"


class TestRecheckFxWaitingLegs:
    @pytest.mark.asyncio
    async def test_resumes_when_usd_arrives(self, mock_db):
        alert = _dca_alert()
        leg = _us_leg(status="WAITING_FX", fx_retry_until=datetime.now(tz=UTC) + timedelta(days=2))
        _wire_db(mock_db, leg, _plan(alert), alert)
        with (
            patch("app.utils.market_hours.is_us_market_open", return_value=True),
            patch.object(svc_exec, "_usd_shortfall_for_leg", new=AsyncMock(return_value=None)),
        ):
            assert await svc_exec.recheck_fx_waiting_legs(mock_db, None) == 1
        assert leg.status == "PENDING"

    @pytest.mark.asyncio
    async def test_skips_when_market_closed(self, mock_db):
        alert = _dca_alert()
        leg = _us_leg(status="WAITING_FX", fx_retry_until=datetime.now(tz=UTC) + timedelta(days=2))
        _wire_db(mock_db, leg, _plan(alert), alert)
        with (
            patch("app.utils.market_hours.is_us_market_open", return_value=False),
            patch.object(svc_exec, "_usd_shortfall_for_leg", new=AsyncMock()) as check,
        ):
            assert await svc_exec.recheck_fx_waiting_legs(mock_db, None) == 0
        check.assert_not_awaited()
        assert leg.status == "WAITING_FX"

    @pytest.mark.asyncio
    async def test_expires_past_deadline(self, mock_db):
        alert = _dca_alert()
        leg = _us_leg(status="WAITING_FX", fx_retry_until=datetime.now(tz=UTC) - timedelta(minutes=1))
        _wire_db(mock_db, leg, _plan(alert), alert)
        notify = AsyncMock()
        with (
            patch("app.utils.market_hours.is_us_market_open", return_value=False),
            patch("app.services.rebalancing.plan_notifications.notify_dca_fx_wait_expired", new=notify),
        ):
            assert await svc_exec.recheck_fx_waiting_legs(mock_db, None) == 1
        assert leg.status == "EXPIRED"
        assert leg.error_message == svc_exec.FX_WAIT_EXPIRED_MESSAGE
        notify.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unknown_usd_stays_waiting(self, mock_db):
        """잔고 조회 실패를 "충분"으로 보고 재개하면 달러 없이 발주된다 — 대기를 유지한다(plans/122 A2)."""
        from app.services.rebalancing.usd_buying_power import USD_UNKNOWN

        alert = _dca_alert()
        leg = _us_leg(status="WAITING_FX", fx_retry_until=datetime.now(tz=UTC) + timedelta(days=2))
        _wire_db(mock_db, leg, _plan(alert), alert)
        with (
            patch("app.utils.market_hours.is_us_market_open", return_value=True),
            patch.object(svc_exec, "_usd_shortfall_for_leg", new=AsyncMock(return_value=USD_UNKNOWN)),
        ):
            assert await svc_exec.recheck_fx_waiting_legs(mock_db, None) == 0
        assert leg.status == "WAITING_FX"

    @pytest.mark.asyncio
    async def test_still_short_stays_waiting(self, mock_db):
        from app.services.rebalancing.usd_buying_power import UsdShortfall

        alert = _dca_alert()
        leg = _us_leg(status="WAITING_FX", fx_retry_until=datetime.now(tz=UTC) + timedelta(days=2))
        _wire_db(mock_db, leg, _plan(alert), alert)
        with (
            patch("app.utils.market_hours.is_us_market_open", return_value=True),
            patch.object(svc_exec, "_usd_shortfall_for_leg", new=AsyncMock(return_value=UsdShortfall(300.0, 100.0))),
        ):
            assert await svc_exec.recheck_fx_waiting_legs(mock_db, None) == 0
        assert leg.status == "WAITING_FX"
        assert leg.available_usd == 100.0


class TestCancelWaitingLeg:
    @pytest.mark.asyncio
    async def test_cancel_accepts_waiting_fx(self, mock_db):
        leg = _us_leg(status="WAITING_FX")
        mock_db.scalar = AsyncMock(return_value=leg)
        mock_db.get = AsyncMock(return_value=None)
        await svc_exec.cancel_buy_leg(leg, mock_db, decided_by="USER_APP")
        assert leg.status == "CANCELED"


# ── 사전 부족 판정 ────────────────────────────────────────


class TestFixedAmountShortfall:
    def _portfolio(self):
        return SimpleNamespace(
            items=[
                SimpleNamespace(ticker="A", market="KOSPI", weight=50, group_key=None, members=[]),
                SimpleNamespace(ticker="VOO", market="NYSE", weight=50, group_key=None, members=[]),
            ]
        )

    def test_needs_split_kr_and_us(self):
        from app.services.dca_cash_shortfall_service import fixed_amount_needs

        account = SimpleNamespace(tax_type="GENERAL")
        krw, usd, has_us = fixed_amount_needs(1_000_000.0, account, self._portfolio(), 1400.0)
        assert krw == 500_000.0
        assert usd == pytest.approx(500_000.0 / 1400.0)
        assert has_us

    def test_usd_short_even_if_krw_plenty(self):
        from app.services.dca_cash_shortfall_service import _fixed_amount_shortfall, shortfall_detail

        alert = SimpleNamespace(id=uuid.uuid4(), dca_amount_krw=1_000_000.0)
        account = SimpleNamespace(tax_type="GENERAL", deposit_krw=5_000_000.0, deposit_usd=10.0)
        sf = _fixed_amount_shortfall(
            alert, self._portfolio(), account, SimpleNamespace(), None, date(2026, 11, 25), date(2026, 11, 23), 1400.0
        )
        assert sf is not None
        assert sf.expected_krw is None  # 원화는 충분
        assert sf.required_usd == pytest.approx(357.14, abs=0.01)
        assert "환전" in shortfall_detail(sf)

    def test_no_shortfall_when_both_enough(self):
        from app.services.dca_cash_shortfall_service import _fixed_amount_shortfall

        alert = SimpleNamespace(id=uuid.uuid4(), dca_amount_krw=1_000_000.0)
        account = SimpleNamespace(tax_type="GENERAL", deposit_krw=600_000.0, deposit_usd=400.0)
        sf = _fixed_amount_shortfall(
            alert, self._portfolio(), account, SimpleNamespace(), None, date(2026, 11, 25), date(2026, 11, 23), 1400.0
        )
        assert sf is None


# ── 알림·홈 할 일 ─────────────────────────────────────────


class TestFxNotifications:
    @pytest.mark.asyncio
    async def test_fx_required_sends_email_and_push(self, mock_db):
        from app.services.rebalancing import plan_notifications as pn

        plan = SimpleNamespace(id=uuid.uuid4(), user_id=uuid.uuid4(), portfolio_id=uuid.uuid4())
        push = AsyncMock()
        email = AsyncMock(return_value=True)
        with (
            patch.object(pn, "_plan_recipient", new=AsyncMock(return_value=("적립", "a@b.c", "tok"))),
            patch.object(pn, "send_push_safely", new=push),
            patch("app.services.notifications.email_service.send_dca_fx_required_email", new=email),
        ):
            await pn.notify_dca_fx_required(plan, 350.0, 12.0, datetime(2026, 11, 17, 21, 0, tzinfo=UTC), mock_db)
        email.assert_awaited_once()
        assert push.await_args.kwargs["data"]["type"] == "DCA_FX_REQUIRED"
        assert "$350.00" in push.await_args.kwargs["body"]

    @pytest.mark.asyncio
    async def test_fx_wait_expired_push(self, mock_db):
        from app.services.rebalancing import plan_notifications as pn

        plan = SimpleNamespace(id=uuid.uuid4(), user_id=uuid.uuid4(), portfolio_id=None)
        push = AsyncMock()
        with (
            patch.object(pn, "_plan_recipient", new=AsyncMock(return_value=("적립", None, "tok"))),
            patch.object(pn, "send_push_safely", new=push),
        ):
            await pn.notify_dca_fx_wait_expired(plan, mock_db)
        push.assert_awaited_once()

    def test_email_template(self):
        from app.services.notifications.email_templates import dca_fx_required_template

        subject, html = dca_fx_required_template("적립", 350.0, 12.0, "11/17")
        assert "환전" in subject
        assert "$338.00" in html  # 부족분

    @pytest.mark.asyncio
    async def test_send_email_uses_template(self):
        from app.services.notifications import email_service

        with patch.object(email_service, "_send_templated", new=AsyncMock(return_value=True)) as send:
            assert await email_service.send_dca_fx_required_email("a@b.c", "적립", 1.0, 0.0, "11/17")
        send.assert_awaited_once()


class TestFxWaitingActionItem:
    @pytest.mark.asyncio
    async def test_waiting_leg_becomes_action_item(self, mock_db):
        from app.services import action_items_service as svc

        leg = SimpleNamespace(
            id=uuid.uuid4(),
            required_usd=350.0,
            available_usd=12.0,
            fx_retry_until=datetime(2026, 11, 17, 21, 0, tzinfo=UTC),
        )
        result = MagicMock()
        result.all.return_value = [(leg, "적립")]
        mock_db.execute = AsyncMock(return_value=result)
        items = await svc._fx_waiting_items(uuid.uuid4(), mock_db)
        assert len(items) == 1
        assert items[0].kind == "DCA_FX_WAITING"
        assert "$350.00" in items[0].detail
        assert items[0].link == "/rebalancing?rtab=이력"
        assert items[0].deadline == "2026-11-18"


@pytest.mark.asyncio
async def test_fx_wait_retry_job_runs_recheck():
    from app.jobs import dca_fx_wait_retry as job

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=MagicMock())
    cm.__aexit__ = AsyncMock(return_value=False)
    with (
        patch.object(job, "AsyncSessionLocal", return_value=cm),
        patch.object(job, "get_cache_store", new=AsyncMock(return_value=MagicMock())),
        patch.object(job, "recheck_fx_waiting_legs", new=AsyncMock(return_value=2)) as recheck,
    ):
        await job.run_dca_fx_wait_retry()
    recheck.assert_awaited_once()
