"""rebalancing_execution.py 라우터 — quick_execute_rebalancing() 단위 테스트.

FastAPI 의존성 주입 없이 라우터 함수를 직접 호출해, "지금 테스트 실행"이 AUTO 스케줄러와
동일한 파이프라인(대기 플랜 생성 → 이메일 발송)을 태우는지 검증한다. 드리프트 분석 자체는
`build_pending_plan_for_alert()`에 위임되므로(별도 단위 테스트는
test_rebalancing_auto_execution.py 참고), 여기서는 게이트 순서·override 전달·응답 매핑에 집중한다.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


def _make_plan(plan_id=None, buy_items=None, sell_items=None):
    legs = []
    if buy_items is not None:
        legs.append(SimpleNamespace(side="BUY", items=buy_items))
    if sell_items is not None:
        legs.append(SimpleNamespace(side="SELL", items=sell_items))
    return SimpleNamespace(id=plan_id or uuid.uuid4(), legs=legs)


class TestQuickExecuteGates:
    @pytest.mark.asyncio
    async def test_already_pending_short_circuits_before_plan_generation(self, mock_db, mock_request):
        from app.api.v1.rebalancing_execution import quick_execute_rebalancing

        portfolio_id = uuid.uuid4()
        user = SimpleNamespace(id=uuid.uuid4())
        portfolio = SimpleNamespace(id=portfolio_id, account_ids=None)
        alert_row = SimpleNamespace(
            id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            strategy="FULL",
            order_type="MARKET",
            market_condition_mode="DISABLED",
        )
        mock_db.scalar = AsyncMock(side_effect=[portfolio, alert_row])

        mock_build_plan = AsyncMock()
        with (
            patch("app.api.v1.rebalancing_execution.has_pending_plan_for_alert", new=AsyncMock(return_value=True)),
            patch("app.api.v1.rebalancing_execution.build_pending_plan_for_alert", new=mock_build_plan),
        ):
            result = await quick_execute_rebalancing(
                request=mock_request,
                portfolio_id=portfolio_id,
                current_user=user,
                db=mock_db,
                redis=None,
            )

        assert result.status == "ALREADY_PENDING"
        mock_build_plan.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_market_blocked_when_strict_mode_and_red_signal(self, mock_db, mock_request):
        from app.api.v1.rebalancing_execution import quick_execute_rebalancing

        portfolio_id = uuid.uuid4()
        user = SimpleNamespace(id=uuid.uuid4())
        portfolio = SimpleNamespace(id=portfolio_id, account_ids=None)
        alert_row = SimpleNamespace(
            id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            strategy="FULL",
            order_type="MARKET",
            market_condition_mode="STRICT",
        )
        mock_db.scalar = AsyncMock(side_effect=[portfolio, alert_row])

        mock_build_plan = AsyncMock()
        with (
            patch("app.api.v1.rebalancing_execution.has_pending_plan_for_alert", new=AsyncMock(return_value=False)),
            patch(
                "app.services.market_signal_service.get_market_signal",
                new=AsyncMock(return_value={"composite_level": "RED"}),
            ),
            patch("app.api.v1.rebalancing_execution.build_pending_plan_for_alert", new=mock_build_plan),
        ):
            result = await quick_execute_rebalancing(
                request=mock_request,
                portfolio_id=portfolio_id,
                current_user=user,
                db=mock_db,
                redis=None,
            )

        assert result.status == "MARKET_BLOCKED"
        mock_build_plan.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_market_blocked_when_cautious_mode_and_stale_freshness(self, mock_db, mock_request):
        """시장 신호가 STALE(신뢰 불가)이면 composite_level이 GREEN이어도 CAUTIOUS는 차단한다.

        회귀 테스트 — FRED_API_KEY 미설정 등으로 대부분 신호가 실패해도 과거에는 GREEN으로
        오판되어 원클릭 실행이 그대로 통과했다."""
        from app.api.v1.rebalancing_execution import quick_execute_rebalancing

        portfolio_id = uuid.uuid4()
        user = SimpleNamespace(id=uuid.uuid4())
        portfolio = SimpleNamespace(id=portfolio_id, account_ids=None)
        alert_row = SimpleNamespace(
            id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            strategy="FULL",
            order_type="MARKET",
            market_condition_mode="CAUTIOUS",
        )
        mock_db.scalar = AsyncMock(side_effect=[portfolio, alert_row])

        mock_build_plan = AsyncMock()
        with (
            patch("app.api.v1.rebalancing_execution.has_pending_plan_for_alert", new=AsyncMock(return_value=False)),
            patch(
                "app.services.market_signal_service.get_market_signal",
                new=AsyncMock(return_value={"composite_level": "GREEN", "data_freshness": "STALE"}),
            ),
            patch("app.api.v1.rebalancing_execution.build_pending_plan_for_alert", new=mock_build_plan),
        ):
            result = await quick_execute_rebalancing(
                request=mock_request,
                portfolio_id=portfolio_id,
                current_user=user,
                db=mock_db,
                redis=None,
            )

        assert result.status == "MARKET_BLOCKED"
        mock_build_plan.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_drift_when_build_pending_plan_returns_none(self, mock_db, mock_request):
        from app.api.v1.rebalancing_execution import quick_execute_rebalancing

        portfolio_id = uuid.uuid4()
        user = SimpleNamespace(id=uuid.uuid4())
        portfolio = SimpleNamespace(id=portfolio_id, account_ids=None)
        alert_row = SimpleNamespace(
            id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            strategy="FULL",
            order_type="MARKET",
            market_condition_mode="DISABLED",
        )
        mock_db.scalar = AsyncMock(side_effect=[portfolio, alert_row])

        with (
            patch("app.api.v1.rebalancing_execution.has_pending_plan_for_alert", new=AsyncMock(return_value=False)),
            patch(
                "app.services.market_signal_service.get_market_signal",
                new=AsyncMock(return_value={"composite_level": "GREEN"}),
            ),
            patch("app.api.v1.rebalancing_execution.build_pending_plan_for_alert", new=AsyncMock(return_value=None)),
        ):
            result = await quick_execute_rebalancing(
                request=mock_request,
                portfolio_id=portfolio_id,
                current_user=user,
                db=mock_db,
                redis=None,
            )

        assert result.status == "NO_DRIFT"

    @pytest.mark.asyncio
    async def test_tax_blocked_when_build_pending_plan_returns_tax_gate_blocked(self, mock_db, mock_request):
        from app.api.v1.rebalancing_execution import quick_execute_rebalancing
        from app.services.rebalancing.plan_service import TaxGateBlocked

        portfolio_id = uuid.uuid4()
        user = SimpleNamespace(id=uuid.uuid4())
        portfolio = SimpleNamespace(id=portfolio_id, account_ids=None)
        alert_row = SimpleNamespace(
            id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            strategy="FULL",
            order_type="MARKET",
            market_condition_mode="DISABLED",
        )
        mock_db.scalar = AsyncMock(side_effect=[portfolio, alert_row])
        blocked = TaxGateBlocked(estimated_tax_krw=600_000.0, max_tax_impact_krw=500_000.0)

        with (
            patch("app.api.v1.rebalancing_execution.has_pending_plan_for_alert", new=AsyncMock(return_value=False)),
            patch(
                "app.services.market_signal_service.get_market_signal",
                new=AsyncMock(return_value={"composite_level": "GREEN"}),
            ),
            patch(
                "app.api.v1.rebalancing_execution.build_pending_plan_for_alert",
                new=AsyncMock(return_value=blocked),
            ),
        ):
            result = await quick_execute_rebalancing(
                request=mock_request,
                portfolio_id=portfolio_id,
                current_user=user,
                db=mock_db,
                redis=None,
            )

        assert result.status == "TAX_BLOCKED"
        assert "600,000" in result.message
        assert "500,000" in result.message


class TestQuickExecutePlanGenerated:
    @pytest.mark.asyncio
    async def test_plan_generated_happy_path_sends_email_and_maps_counts(self, mock_db, mock_request):
        from app.api.v1.rebalancing_execution import quick_execute_rebalancing

        portfolio_id = uuid.uuid4()
        user = SimpleNamespace(id=uuid.uuid4())
        portfolio = SimpleNamespace(id=portfolio_id, account_ids=None)
        alert_row = SimpleNamespace(
            id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            strategy="FULL",
            order_type="MARKET",
            market_condition_mode="DISABLED",
        )
        mock_db.scalar = AsyncMock(side_effect=[portfolio, alert_row])

        plan = _make_plan(buy_items=[object(), object()], sell_items=[object()])
        execute_result = SimpleNamespace(first=lambda: ("user@test.com", None, None))
        mock_db.execute = AsyncMock(return_value=execute_result)

        with (
            patch("app.api.v1.rebalancing_execution.has_pending_plan_for_alert", new=AsyncMock(return_value=False)),
            patch(
                "app.services.market_signal_service.get_market_signal",
                new=AsyncMock(return_value={"composite_level": "GREEN"}),
            ),
            patch(
                "app.api.v1.rebalancing_execution.build_pending_plan_for_alert",
                new=AsyncMock(return_value=(plan, "buy-token", "sell-token")),
            ),
            patch("app.api.v1.rebalancing_execution.notify_plan_generated", new=AsyncMock(return_value=True)),
        ):
            result = await quick_execute_rebalancing(
                request=mock_request,
                portfolio_id=portfolio_id,
                current_user=user,
                db=mock_db,
                redis=None,
            )

        assert result.status == "PLAN_GENERATED"
        assert result.email_sent is True
        assert result.plan_id == plan.id
        assert result.buy_count == 2
        assert result.sell_count == 1
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_plan_generated_but_email_not_sent_reports_honest_message(self, mock_db, mock_request):
        """email_sent=False(발송 실패/이메일 미등록)인 경우, 메시지가 '이메일로 발송되었습니다'라고
        거짓으로 알리면 안 된다 — 실제로 이메일이 안 갔는데도 성공 메시지가 뜨던 버그 재발 방지."""
        from app.api.v1.rebalancing_execution import quick_execute_rebalancing

        portfolio_id = uuid.uuid4()
        user = SimpleNamespace(id=uuid.uuid4())
        portfolio = SimpleNamespace(id=portfolio_id, account_ids=None)
        alert_row = SimpleNamespace(
            id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            strategy="FULL",
            order_type="MARKET",
            market_condition_mode="DISABLED",
        )
        mock_db.scalar = AsyncMock(side_effect=[portfolio, alert_row])

        plan = _make_plan(buy_items=[object()])
        execute_result = SimpleNamespace(first=lambda: (None, None, None))  # 등록된 이메일 없음
        mock_db.execute = AsyncMock(return_value=execute_result)

        with (
            patch("app.api.v1.rebalancing_execution.has_pending_plan_for_alert", new=AsyncMock(return_value=False)),
            patch(
                "app.services.market_signal_service.get_market_signal",
                new=AsyncMock(return_value={"composite_level": "GREEN"}),
            ),
            patch(
                "app.api.v1.rebalancing_execution.build_pending_plan_for_alert",
                new=AsyncMock(return_value=(plan, "buy-token", None)),
            ),
            patch("app.api.v1.rebalancing_execution.notify_plan_generated", new=AsyncMock(return_value=False)),
        ):
            result = await quick_execute_rebalancing(
                request=mock_request,
                portfolio_id=portfolio_id,
                current_user=user,
                db=mock_db,
                redis=None,
            )

        assert result.status == "PLAN_GENERATED"
        assert result.email_sent is False
        assert "발송되었습니다" not in result.message

    @pytest.mark.asyncio
    async def test_body_strategy_override_passed_through(self, mock_db, mock_request):
        from app.api.v1.rebalancing_execution import quick_execute_rebalancing
        from app.schemas.rebalancing import QuickExecuteOverride

        portfolio_id = uuid.uuid4()
        user = SimpleNamespace(id=uuid.uuid4())
        portfolio = SimpleNamespace(id=portfolio_id, account_ids=None)
        alert_row = SimpleNamespace(
            id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            strategy="FULL",
            order_type="MARKET",
            market_condition_mode="DISABLED",
        )
        mock_db.scalar = AsyncMock(side_effect=[portfolio, alert_row])

        plan = _make_plan(buy_items=[])
        execute_result = SimpleNamespace(first=lambda: (None, None, None))
        mock_db.execute = AsyncMock(return_value=execute_result)

        mock_build_plan = AsyncMock(return_value=(plan, None, None))
        with (
            patch("app.api.v1.rebalancing_execution.has_pending_plan_for_alert", new=AsyncMock(return_value=False)),
            patch(
                "app.services.market_signal_service.get_market_signal",
                new=AsyncMock(return_value={"composite_level": "GREEN"}),
            ),
            patch("app.api.v1.rebalancing_execution.build_pending_plan_for_alert", new=mock_build_plan),
            patch("app.api.v1.rebalancing_execution.notify_plan_generated", new=AsyncMock(return_value=False)),
        ):
            await quick_execute_rebalancing(
                request=mock_request,
                portfolio_id=portfolio_id,
                body=QuickExecuteOverride(strategy="TWO_PHASE"),
                current_user=user,
                db=mock_db,
                redis=None,
            )

        _, kwargs = mock_build_plan.call_args
        assert kwargs["strategy_override"] == "TWO_PHASE"
        assert kwargs["order_type_override"] is None
        assert kwargs["account_id_override"] is None

    @pytest.mark.asyncio
    async def test_body_account_id_override_requires_ownership(self, mock_db, mock_request):
        from fastapi import HTTPException

        from app.api.v1.rebalancing_execution import quick_execute_rebalancing
        from app.schemas.rebalancing import QuickExecuteOverride

        saved_account_id = uuid.uuid4()
        other_account_id = uuid.uuid4()
        portfolio_id = uuid.uuid4()
        user = SimpleNamespace(id=uuid.uuid4())
        portfolio = SimpleNamespace(id=portfolio_id, account_ids=None)
        alert_row = SimpleNamespace(
            id=uuid.uuid4(),
            account_id=saved_account_id,
            strategy="FULL",
            order_type="MARKET",
            market_condition_mode="DISABLED",
        )

        mock_db.scalar = AsyncMock(side_effect=[portfolio, alert_row])

        mock_get_owned = AsyncMock(side_effect=HTTPException(status_code=404, detail="계좌를 찾을 수 없습니다"))
        with (
            patch("app.api.v1.rebalancing_execution.get_owned_account", new=mock_get_owned),
            pytest.raises(HTTPException) as exc_info,
        ):
            await quick_execute_rebalancing(
                request=mock_request,
                portfolio_id=portfolio_id,
                body=QuickExecuteOverride(account_id=other_account_id),
                current_user=user,
                db=mock_db,
                redis=None,
            )

        assert exc_info.value.status_code == 404
        mock_get_owned.assert_awaited_once_with(other_account_id, user.id, mock_db)


class TestQuickExecutePortfolioQuery:
    @pytest.mark.asyncio
    async def test_portfolio_query_eager_loads_linked_accounts_and_items(self, mock_db, mock_request):
        """quick_execute_rebalancing()이 portfolio.account_ids / portfolio.items에 접근하기 전에
        selectinload로 미리 로드해야 한다. 누락 시 실제 DB에서 lazy-load가 시도되어
        async 세션에서 sqlalchemy.exc.MissingGreenlet이 발생한다."""
        from app.api.v1.rebalancing_execution import quick_execute_rebalancing

        portfolio_id = uuid.uuid4()
        user = SimpleNamespace(id=uuid.uuid4())

        captured_stmt = {}

        async def fake_scalar(stmt):
            if "portfolio" not in captured_stmt:
                captured_stmt["portfolio"] = stmt
                return None  # 404로 즉시 종료시켜 이후 로직은 검증하지 않음
            return None

        mock_db.scalar = fake_scalar

        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            await quick_execute_rebalancing(
                request=mock_request,
                portfolio_id=portfolio_id,
                current_user=user,
                db=mock_db,
                redis=None,
            )

        stmt = captured_stmt["portfolio"]
        loaded_paths = {str(opt.path) for opt in stmt._with_options}
        assert any("linked_accounts" in path for path in loaded_paths), (
            "Portfolio 쿼리가 linked_accounts를 selectinload하지 않음 — "
            "portfolio.account_ids 접근 시 MissingGreenlet 발생 위험"
        )
        assert any(".items" in path or "-> Portfolio.items" in path for path in loaded_paths), (
            "Portfolio 쿼리가 items를 selectinload하지 않음 — "
            "드리프트 분석 내부의 portfolio.items 접근 시 MissingGreenlet 발생 위험"
        )
