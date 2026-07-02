"""rebalancing_execution.py 라우터 — quick_execute_rebalancing() 단위 테스트.

FastAPI 의존성 주입 없이 라우터 함수를 직접 호출해, 원클릭 실행(quick-execute)이
AUTO 자동실행과 동일하게 ticker_account_map 기반으로 매도 주문을 분산 생성하는지 검증한다.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.schemas.rebalancing import RebalancingAnalysis, RebalancingItem, TickerAccountInfo


def _make_analysis(items: list[RebalancingItem], ticker_account_map: dict) -> RebalancingAnalysis:
    return RebalancingAnalysis(
        portfolio_id=str(uuid.uuid4()),
        portfolio_name="테스트",
        base_type="STOCK_ONLY",
        base_value_krw=1_000_000,
        items=items,
        untracked_holdings=[],
        analyzed_at="2026-01-01T00:00:00",
        current_portfolio_annual_dividend=0,
        target_portfolio_annual_dividend=0,
        ticker_account_map=ticker_account_map,
    )


def _make_item(ticker="005930", diff_krw=-100000.0, shares_to_trade=-5.0) -> RebalancingItem:
    return RebalancingItem(
        ticker=ticker,
        name="삼성전자",
        market="KOSPI",
        target_weight_pct=0.0,
        current_weight_pct=0.0,
        weight_diff_pct=0.0,
        current_value_krw=0,
        target_value_krw=0,
        diff_krw=diff_krw,
        shares_to_trade=shares_to_trade,
        current_price_krw=70000.0,
    )


class TestQuickExecuteRebalancing:
    @pytest.mark.asyncio
    async def test_sell_orders_distributed_across_holding_accounts(self, mock_db, mock_request):
        from app.api.v1.rebalancing_execution import quick_execute_rebalancing

        exec_account_id = uuid.uuid4()
        holder_account_id = uuid.uuid4()
        portfolio_id = uuid.uuid4()
        user = SimpleNamespace(id=uuid.uuid4())
        portfolio = SimpleNamespace(id=portfolio_id, account_ids=None)
        alert_row = SimpleNamespace(account_id=exec_account_id, strategy="FULL", order_type="MARKET")

        mock_db.scalar = AsyncMock(return_value=alert_row)
        holder_account = TickerAccountInfo(
            account_id=str(holder_account_id),
            account_name="계좌",
            asset_type="STOCK_KIS",
            quantity=10,
            value_krw=700000,
        )
        analysis = _make_analysis([_make_item()], {"005930": [holder_account]})

        captured = {}

        async def fake_execute_rebalancing(**kwargs):
            captured["orders"] = kwargs["orders"]
            return []

        with (
            patch("app.api.v1.rebalancing_execution.get_owned_or_404", new=AsyncMock(return_value=portfolio)),
            patch("app.api.v1.rebalancing_execution.build_portfolio_overview", new=AsyncMock(return_value={})),
            patch("app.api.v1.rebalancing_execution.analyze_rebalancing", return_value=analysis),
            patch("app.services.price_service.fetch_prices_batch", new=AsyncMock(return_value={})),
            patch("app.api.v1.rebalancing_execution.execute_rebalancing", new=fake_execute_rebalancing),
        ):
            await quick_execute_rebalancing(
                request=mock_request,
                portfolio_id=portfolio_id,
                current_user=user,
                db=mock_db,
                redis=None,
            )

        orders = captured["orders"]
        assert len(orders) == 1
        assert orders[0].side == "SELL"
        assert orders[0].account_id == str(holder_account_id)
        assert orders[0].quantity == 5

    @pytest.mark.asyncio
    async def test_portfolio_query_eager_loads_linked_accounts_and_items(self, mock_db, mock_request):
        """quick_execute_rebalancing()이 portfolio.account_ids / portfolio.items에 접근하기 전에
        selectinload로 미리 로드해야 한다. 누락 시 실제 DB에서 lazy-load가 시도되어
        async 세션에서 sqlalchemy.exc.MissingGreenlet이 발생한다 (get_owned_or_404는
        eager-load 옵션을 지원하지 않아 이 endpoint에서는 사용할 수 없음)."""
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
            "analyze_rebalancing() 내부의 portfolio.items 접근 시 MissingGreenlet 발생 위험"
        )


class TestQuickExecuteLivePrice:
    """quick-execute가 수동 실행 모달과 동일하게 실시간 시세를 지정가에 반영하는지 검증."""

    @pytest.mark.asyncio
    async def test_limit_order_uses_live_price_not_stale_analysis_price(self, mock_db, mock_request):
        from app.api.v1.rebalancing_execution import quick_execute_rebalancing

        exec_account_id = uuid.uuid4()
        portfolio_id = uuid.uuid4()
        user = SimpleNamespace(id=uuid.uuid4())
        portfolio = SimpleNamespace(id=portfolio_id, account_ids=None)
        # 저장된 알림 설정은 LIMIT + 분석 시점 가격(70000)이지만, 실시간 시세(72300)를 지정가로 써야 한다.
        alert_row = SimpleNamespace(account_id=exec_account_id, strategy="FULL", order_type="LIMIT")

        mock_db.scalar = AsyncMock(side_effect=[portfolio, alert_row])

        item = _make_item(ticker="005930", diff_krw=100000.0, shares_to_trade=3.0)
        analysis = _make_analysis([item], {})

        captured = {}

        async def fake_execute_rebalancing(**kwargs):
            captured["orders"] = kwargs["orders"]
            return []

        with (
            patch("app.api.v1.rebalancing_execution.build_portfolio_overview", new=AsyncMock(return_value={})),
            patch("app.api.v1.rebalancing_execution.analyze_rebalancing", return_value=analysis),
            patch(
                "app.services.price_service.fetch_prices_batch",
                new=AsyncMock(return_value={"005930": 72300.0}),
            ),
            patch("app.api.v1.rebalancing_execution.execute_rebalancing", new=fake_execute_rebalancing),
        ):
            await quick_execute_rebalancing(
                request=mock_request,
                portfolio_id=portfolio_id,
                current_user=user,
                db=mock_db,
                redis=None,
            )

        orders = captured["orders"]
        assert len(orders) == 1
        assert orders[0].order_type == "LIMIT"
        assert orders[0].limit_price == 72300.0


class TestQuickExecuteOverride:
    """quick-execute 요청 바디(QuickExecuteOverride)가 저장된 알림 설정보다
    우선 적용되는지 검증 — 화면에서 값을 바꾸고 저장하지 않은 채 '지금 테스트 실행'을
    눌러도 화면 값이 반영되어야 한다."""

    @pytest.mark.asyncio
    async def test_body_strategy_overrides_saved_alert_strategy(self, mock_db, mock_request):
        from app.api.v1.rebalancing_execution import quick_execute_rebalancing
        from app.schemas.rebalancing import QuickExecuteOverride

        exec_account_id = uuid.uuid4()
        portfolio_id = uuid.uuid4()
        user = SimpleNamespace(id=uuid.uuid4())
        portfolio = SimpleNamespace(id=portfolio_id, account_ids=None)
        # DB에는 FULL로 저장되어 있지만 body로 TWO_PHASE를 override
        alert_row = SimpleNamespace(account_id=exec_account_id, strategy="FULL", order_type="MARKET")

        mock_db.scalar = AsyncMock(side_effect=[portfolio, alert_row])

        holder_account = TickerAccountInfo(
            account_id=str(exec_account_id),
            account_name="계좌",
            asset_type="STOCK_KIS",
            quantity=10,
            value_krw=700000,
        )
        analysis = _make_analysis([_make_item()], {"005930": [holder_account]})

        captured = {}

        async def fake_execute_rebalancing(**kwargs):
            captured["strategy"] = kwargs["strategy"]
            return []

        with (
            patch("app.api.v1.rebalancing_execution.build_portfolio_overview", new=AsyncMock(return_value={})),
            patch("app.api.v1.rebalancing_execution.analyze_rebalancing", return_value=analysis),
            patch("app.services.price_service.fetch_prices_batch", new=AsyncMock(return_value={})),
            patch("app.api.v1.rebalancing_execution.execute_rebalancing", new=fake_execute_rebalancing),
        ):
            await quick_execute_rebalancing(
                request=mock_request,
                portfolio_id=portfolio_id,
                body=QuickExecuteOverride(strategy="TWO_PHASE"),
                current_user=user,
                db=mock_db,
                redis=None,
            )

        assert captured["strategy"] == "TWO_PHASE"

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
        alert_row = SimpleNamespace(account_id=saved_account_id, strategy="FULL", order_type="MARKET")

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
