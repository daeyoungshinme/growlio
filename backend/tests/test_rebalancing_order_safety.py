"""이중 주문·조용한 누락을 막는 장치들(plans/109 A) — 실돈이 움직이는 경로라 따로 고정한다.

테스트가 실DB를 막으므로 실제 row 락 경합은 재현하지 못한다. A1은 그래서 "락 쿼리가 세션의 옛 값을
덮어쓰도록 만들어졌는가"를 쿼리 옵션으로 검증한다.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.schemas.rebalancing.execution import ExecutionRequest
from app.services.rebalancing import plan_execution as svc_exec


def _order(status: str, error_msg: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(status=status, error_msg=error_msg)


def _result(*orders: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(orders=list(orders))


class TestLockLegRefreshesSessionState:
    @pytest.mark.asyncio
    async def test_lock_query_overwrites_stale_identity_map_values(self):
        db = MagicMock()
        db.scalar = AsyncMock(return_value=None)

        await svc_exec._lock_leg(uuid.uuid4(), db)

        stmt = db.scalar.await_args.args[0]
        assert stmt.get_execution_options().get("populate_existing") is True
        assert stmt._for_update_arg is not None


class TestNoOrderSucceeded:
    @pytest.mark.parametrize(
        ("results", "expected"),
        [
            ([_result(_order("FAILED"), _order("FAILED"))], True),
            ([_result(_order("SKIPPED"))], True),
            ([_result(_order("FAILED")), _result(_order("SUCCESS"))], False),
            ([_result(_order("SUCCESS"), _order("FAILED"))], False),
            ([], False),
        ],
    )
    def test_only_when_orders_were_tried_and_none_accepted(self, results, expected):
        assert svc_exec._no_order_succeeded(results) is expected


class TestExecuteLegAllOrdersFailed:
    @pytest.mark.asyncio
    async def test_marks_failed_and_notifies_instead_of_executed(self):
        db = MagicMock()
        db.refresh = AsyncMock()
        db.commit = AsyncMock()
        db.add = MagicMock()
        leg = SimpleNamespace(id=uuid.uuid4(), side="BUY", items=[], status="PENDING", execution_id=None)
        plan = SimpleNamespace(
            id=uuid.uuid4(), user_id=uuid.uuid4(), account_id=None, portfolio_id=uuid.uuid4(), strategy="FULL"
        )
        execution_id = uuid.uuid4()
        notify = AsyncMock()

        with (
            patch.object(svc_exec, "_rebuild_orders_from_items", new=AsyncMock(return_value=[])),
            patch(
                "app.services.rebalancing.execution_service.execute_rebalancing",
                new=AsyncMock(return_value=([_result(_order("FAILED", "잔고 부족"))], execution_id)),
            ),
            patch.object(svc_exec, "_notify_leg_execution_failed", new=notify),
        ):
            returned = await svc_exec._execute_leg(leg, plan, db, None, "SYSTEM_AUTO")

        assert returned is None
        assert leg.status == "FAILED"
        assert leg.error_message == "잔고 부족"
        # 실행 기록은 남아 있으니 이력에서 종목별 실패를 볼 수 있어야 한다
        assert leg.execution_id == execution_id
        notify.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_partial_fill_stays_executed(self):
        db = MagicMock()
        db.refresh = AsyncMock()
        db.commit = AsyncMock()
        leg = SimpleNamespace(id=uuid.uuid4(), side="BUY", items=[], status="PENDING", execution_id=None)
        plan = SimpleNamespace(
            id=uuid.uuid4(), user_id=uuid.uuid4(), account_id=None, portfolio_id=uuid.uuid4(), strategy="FULL"
        )
        execution_id = uuid.uuid4()
        results = [_result(_order("SUCCESS"), _order("FAILED", "x"))]

        with (
            patch.object(svc_exec, "_rebuild_orders_from_items", new=AsyncMock(return_value=[])),
            patch(
                "app.services.rebalancing.execution_service.execute_rebalancing",
                new=AsyncMock(return_value=(results, execution_id)),
            ),
        ):
            returned = await svc_exec._execute_leg(leg, plan, db, None, "SYSTEM_AUTO")

        assert returned == execution_id
        assert leg.status == "EXECUTED"


class TestCancelPendingBuyLegs:
    @staticmethod
    def _db(rows):
        db = MagicMock()
        query_result = MagicMock()
        query_result.all.return_value = rows
        db.execute = AsyncMock(return_value=query_result)
        db.add = MagicMock()
        return db

    @pytest.mark.asyncio
    async def test_cancels_pending_leg_without_committing(self):
        user_id = uuid.uuid4()
        leg_id = uuid.uuid4()
        db = self._db([(leg_id, user_id)])
        db.commit = AsyncMock()
        leg = SimpleNamespace(id=leg_id, status="PENDING", token_consumed_at=None)

        with patch.object(svc_exec, "_lock_leg", new=AsyncMock(return_value=leg)):
            canceled = await svc_exec.cancel_pending_buy_legs(db, alert_id=uuid.uuid4())

        assert canceled == 1
        assert leg.status == "CANCELED"
        assert leg.decided_by == svc_exec.AUTOMATION_OFF_DECIDED_BY
        # 알림 삭제와 같은 트랜잭션이어야 하므로 여기서 커밋하지 않는다
        db.commit.assert_not_awaited()

    def test_decided_by_fits_column(self):
        from app.models.rebalancing_plan import RebalancingPlanLeg

        column_length = RebalancingPlanLeg.__table__.c.decided_by.type.length
        assert len(svc_exec.AUTOMATION_OFF_DECIDED_BY) <= column_length

    @pytest.mark.asyncio
    async def test_leg_consumed_while_waiting_for_lock_is_left_alone(self):
        leg_id = uuid.uuid4()
        db = self._db([(leg_id, uuid.uuid4())])
        leg = SimpleNamespace(id=leg_id, status="PENDING", token_consumed_at="2026-11-02")

        with patch.object(svc_exec, "_lock_leg", new=AsyncMock(return_value=leg)):
            canceled = await svc_exec.cancel_pending_buy_legs(db, portfolio_id=uuid.uuid4())

        assert canceled == 0
        assert leg.status == "PENDING"


class TestAlertRoutesStopPendingBuys:
    @pytest.mark.asyncio
    async def test_cancels_only_when_auto_is_turned_off(self):
        from app.api.v1.rebalancing_alerts import _cancel_pending_buys_if_auto_turned_off

        cancel = AsyncMock()
        with patch("app.api.v1.rebalancing_alerts.cancel_pending_buy_legs", new=cancel):
            alert = SimpleNamespace(id=uuid.uuid4(), mode="AUTO")
            await _cancel_pending_buys_if_auto_turned_off(MagicMock(), alert, SimpleNamespace(mode="AUTO"))
            cancel.assert_not_awaited()

            await _cancel_pending_buys_if_auto_turned_off(MagicMock(), alert, SimpleNamespace(mode="NOTIFY"))
            cancel.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_notify_alert_save_is_not_a_turn_off(self):
        from app.api.v1.rebalancing_alerts import _cancel_pending_buys_if_auto_turned_off

        cancel = AsyncMock()
        with patch("app.api.v1.rebalancing_alerts.cancel_pending_buy_legs", new=cancel):
            alert = SimpleNamespace(id=uuid.uuid4(), mode="NOTIFY")
            await _cancel_pending_buys_if_auto_turned_off(MagicMock(), alert, SimpleNamespace(mode="NOTIFY"))

        cancel.assert_not_awaited()


class TestBuyLegExpiryIsAnnounced:
    @pytest.mark.asyncio
    async def test_market_closed_expiry_records_history_and_pushes(self):
        leg = SimpleNamespace(
            id=uuid.uuid4(), plan_id=uuid.uuid4(), status="PENDING", token_consumed_at=None, market="KR"
        )
        plan = SimpleNamespace(id=leg.plan_id, user_id=uuid.uuid4())
        db = MagicMock()
        db.commit = AsyncMock()
        db.get = AsyncMock(return_value=plan)
        history = AsyncMock()
        notify = AsyncMock()

        with (
            patch.object(svc_exec, "_lock_leg", new=AsyncMock(return_value=leg)),
            patch("app.utils.market_hours.is_korean_market_open", return_value=False),
            patch.object(svc_exec, "save_alert_history", new=history),
            patch.object(svc_exec, "_notify_buy_leg_expired", new=notify),
        ):
            processed = await svc_exec._run_due_buy_leg(leg.id, MagicMock(), "GREEN", "FRESH", db, None)

        assert processed is True
        assert leg.status == "EXPIRED"
        history.assert_awaited_once()
        notify.assert_awaited_once_with(plan, "KR", db)


class TestAnyPortfolioMarketOpen:
    @staticmethod
    def _portfolio(*markets: str, members: tuple[str, ...] = ()) -> SimpleNamespace:
        items = [SimpleNamespace(market=market, members=[]) for market in markets]
        if members:
            items.append(SimpleNamespace(market="KOSPI", members=[SimpleNamespace(market=m) for m in members]))
        return SimpleNamespace(items=items)

    @pytest.mark.parametrize(
        ("markets", "kr_open", "us_open", "expected"),
        [
            (("KOSPI",), False, True, False),  # 00:00 KST 미국장 — 국내 전용은 평가 보류
            (("KOSPI",), True, False, True),
            (("NASDAQ",), False, True, True),
            (("NASDAQ",), True, False, False),
            (("KOSPI", "NASDAQ"), False, True, True),
        ],
    )
    def test_matches_market_group(self, markets, kr_open, us_open, expected):
        from app.jobs import rebalancing_auto_execution as job

        with (
            patch.object(job, "is_korean_market_open", return_value=kr_open),
            patch.object(job, "is_us_market_open", return_value=us_open),
        ):
            assert job._any_portfolio_market_open(self._portfolio(*markets)) is expected

    def test_index_group_members_count(self):
        from app.jobs import rebalancing_auto_execution as job

        with (
            patch.object(job, "is_korean_market_open", return_value=False),
            patch.object(job, "is_us_market_open", return_value=True),
        ):
            assert job._any_portfolio_market_open(self._portfolio(members=("NASDAQ",))) is True


class TestManualExecuteIdempotency:
    @staticmethod
    def _body(key: str | None) -> SimpleNamespace:
        return SimpleNamespace(account_id=None, orders=[], strategy="FULL", idempotency_key=key)

    @pytest.mark.asyncio
    async def test_duplicate_key_returns_409_without_ordering(self, mock_db, mock_request):
        from app.api.v1 import rebalancing_execution as api

        execute = AsyncMock()
        with (
            patch.object(api, "get_owned_or_404", new=AsyncMock()),
            patch.object(api, "claim_durable", new=AsyncMock(return_value=False)),
            patch.object(api, "execute_rebalancing", new=execute),
            pytest.raises(HTTPException) as exc_info,
        ):
            await api.execute_portfolio_rebalancing(
                request=mock_request,
                portfolio_id=uuid.uuid4(),
                body=self._body("abcdefgh-1234"),
                current_user=SimpleNamespace(id=uuid.uuid4()),
                db=mock_db,
                cache=None,
            )

        assert exc_info.value.status_code == 409
        execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_first_request_orders_and_claim_is_user_scoped(self, mock_db, mock_request):
        from app.api.v1 import rebalancing_execution as api

        user_id = uuid.uuid4()
        claim = AsyncMock(return_value=True)
        execute = AsyncMock(return_value=([], uuid.uuid4()))
        with (
            patch.object(api, "get_owned_or_404", new=AsyncMock()),
            patch.object(api, "claim_durable", new=claim),
            patch.object(api, "execute_rebalancing", new=execute),
        ):
            await api.execute_portfolio_rebalancing(
                request=mock_request,
                portfolio_id=uuid.uuid4(),
                body=self._body("abcdefgh-1234"),
                current_user=SimpleNamespace(id=user_id),
                db=mock_db,
                cache=None,
            )

        assert str(user_id) in claim.await_args.args[1]
        execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_without_key_keeps_old_behavior_for_old_apk(self, mock_db, mock_request):
        from app.api.v1 import rebalancing_execution as api

        claim = AsyncMock()
        execute = AsyncMock(return_value=([], uuid.uuid4()))
        with (
            patch.object(api, "get_owned_or_404", new=AsyncMock()),
            patch.object(api, "claim_durable", new=claim),
            patch.object(api, "execute_rebalancing", new=execute),
        ):
            await api.execute_portfolio_rebalancing(
                request=mock_request,
                portfolio_id=uuid.uuid4(),
                body=self._body(None),
                current_user=SimpleNamespace(id=uuid.uuid4()),
                db=mock_db,
                cache=None,
            )

        claim.assert_not_awaited()
        execute.assert_awaited_once()

    def test_schema_rejects_malformed_key(self):
        order = {
            "ticker": "005930",
            "name": "삼성전자",
            "market": "KOSPI",
            "side": "BUY",
            "quantity": 1,
            "account_id": str(uuid.uuid4()),
        }
        with pytest.raises(ValidationError):
            ExecutionRequest(orders=[order], idempotency_key="bad key!")


class TestPlanGenerationRechecksPendingInsideLock:
    @pytest.mark.asyncio
    async def test_second_request_after_lock_does_not_create_plan(self, mock_db):
        from app.services.rebalancing import plan_generation as gen

        alert = SimpleNamespace(
            id=uuid.uuid4(), user_id=uuid.uuid4(), account_id=None, strategy="FULL", order_type="MARKET"
        )
        lock_cm = MagicMock()
        lock_cm.__aenter__ = AsyncMock(return_value=True)
        lock_cm.__aexit__ = AsyncMock(return_value=False)
        generate = AsyncMock()

        with (
            patch.object(
                gen,
                "_drifting_items_for_alert",
                new=AsyncMock(return_value=(SimpleNamespace(ticker_account_map={}), MagicMock(), [MagicMock()])),
            ),
            patch.object(gen, "_check_tax_gate", return_value=None),
            patch("app.utils.inproc_lock.inproc_lock", return_value=lock_cm),
            patch.object(gen, "has_pending_plan_for_alert", new=AsyncMock(return_value=True)),
            patch.object(gen, "generate_pending_plan_for_alert", new=generate),
        ):
            result = await gen.build_pending_plan_for_alert(alert, MagicMock(), mock_db, "GREEN", cache=MagicMock())

        assert isinstance(result, gen.PlanGenerationInProgress)
        generate.assert_not_awaited()


class TestPlanGenerationRequiresRealUsdRate:
    @staticmethod
    def _portfolio(*markets: str) -> SimpleNamespace:
        return SimpleNamespace(id=uuid.uuid4(), items=[SimpleNamespace(market=m, members=[]) for m in markets])

    @pytest.mark.asyncio
    async def test_overseas_portfolio_without_real_rate_skips_analysis(self, mock_db):
        from app.services.rebalancing import plan_generation as gen

        analyze = AsyncMock()
        with (
            patch.object(gen, "get_live_or_cached_usd_krw", new=AsyncMock(return_value=(1300.0, False))),
            patch.object(gen, "_drifting_items_for_alert", new=analyze),
        ):
            result = await gen.build_pending_plan_for_alert(
                SimpleNamespace(id=uuid.uuid4()), self._portfolio("NASDAQ"), mock_db, "GREEN"
            )

        assert isinstance(result, gen.UsdRateUnavailable)
        analyze.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_domestic_portfolio_does_not_need_rate(self, mock_db):
        from app.services.rebalancing import plan_generation as gen

        rate = AsyncMock()
        with (
            patch.object(gen, "get_live_or_cached_usd_krw", new=rate),
            patch.object(gen, "_drifting_items_for_alert", new=AsyncMock(return_value=None)),
        ):
            result = await gen.build_pending_plan_for_alert(
                SimpleNamespace(id=uuid.uuid4(), user_id=uuid.uuid4(), account_id=None),
                self._portfolio("KOSPI"),
                mock_db,
                "GREEN",
            )

        assert result is None
        rate.assert_not_awaited()
