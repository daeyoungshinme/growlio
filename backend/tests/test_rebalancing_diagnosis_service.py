"""rebalancing_diagnosis_service.py 단위 테스트."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.schemas.rebalancing import RebalancingAnalysis, RebalancingItem
from app.services.rebalancing_diagnosis_service import (
    _aggregate_position_costs,
    _build_tax_preview,
    _risk_note,
    build_diagnosis_context,
    check_composite_signal,
    fetch_market_and_risk_signal,
)


def _make_item(
    ticker="AAPL",
    market="NASDAQ",
    diff_krw=-1_000_000.0,
    shares_to_trade: float | None = -10.0,
    weight_diff_pct=-3.0,
) -> RebalancingItem:
    return RebalancingItem(
        ticker=ticker,
        name=ticker,
        market=market,
        target_weight_pct=10.0,
        current_weight_pct=13.0,
        weight_diff_pct=weight_diff_pct,
        current_value_krw=1_300_000.0,
        target_value_krw=1_000_000.0,
        diff_krw=diff_krw,
        shares_to_trade=shares_to_trade,
        current_price_krw=100_000.0,
    )


def _make_analysis(items: list[RebalancingItem]) -> RebalancingAnalysis:
    return RebalancingAnalysis(
        portfolio_id=uuid.uuid4(),
        portfolio_name="테스트 포트폴리오",
        base_type="STOCK_ONLY",
        base_value_krw=10_000_000.0,
        items=items,
        untracked_holdings=[],
        analyzed_at="2026-07-03T00:00:00+00:00",
    )


def _make_overview(positions: list[dict], accounts: list[dict] | None = None) -> dict:
    if accounts is None:
        # 기존 테스트 호환: 포지션에 등장하는 계좌를 기본 GENERAL로 구성
        seen: dict[str, dict] = {}
        for p in positions:
            acc_id = p.get("account_id")
            if acc_id and acc_id not in seen:
                seen[acc_id] = {"id": acc_id, "tax_type": "GENERAL"}
        accounts = list(seen.values())
    return {
        "all_positions": positions,
        "accounts": accounts,
        "total_assets_krw": 10_000_000.0,
        "total_stock_krw": 9_000_000.0,
    }


def _make_position(
    ticker="AAPL", market="NASDAQ", qty=10.0, avg_price=100_000.0, current_price=120_000.0, account_id="acc-1"
) -> dict:
    value_krw = qty * current_price
    invested_krw = qty * avg_price
    return {
        "ticker": ticker,
        "market": market,
        "qty": qty,
        "avg_price": avg_price,
        "current_price": current_price,
        "value_krw": value_krw,
        "invested_krw": invested_krw,
        "currency": "USD" if market == "NASDAQ" else "KRW",
        "account_id": account_id,
        "account_name": "테스트 계좌",
    }


class TestAggregatePositionCosts:
    def test_single_position(self):
        overview = _make_overview([_make_position()])
        costs = _aggregate_position_costs(overview)
        key = ("AAPL", "NASDAQ")
        assert len(costs[key]) == 1
        lot = costs[key][0]
        assert lot["qty"] == pytest.approx(10.0)
        assert lot["value_krw"] == pytest.approx(1_200_000.0)
        assert lot["invested_krw"] == pytest.approx(1_000_000.0)
        assert lot["is_tax_deferred"] is False

    def test_multiple_accounts_same_ticker_listed_separately(self):
        overview = _make_overview(
            [
                _make_position(qty=10.0, account_id="acc-1"),
                _make_position(qty=5.0, account_id="acc-2"),
            ]
        )
        costs = _aggregate_position_costs(overview)
        key = ("AAPL", "NASDAQ")
        assert len(costs[key]) == 2
        assert sum(lot["qty"] for lot in costs[key]) == pytest.approx(15.0)
        assert sum(lot["invested_krw"] for lot in costs[key]) == pytest.approx(1_500_000.0)

    def test_tax_deferred_lots_sorted_after_general_lots(self):
        """매도 우선순위와 동일하게 과세이연 계좌 lot이 뒤로 정렬된다(보유수량은 오히려 더 커도)."""
        overview = _make_overview(
            [
                _make_position(qty=5.0, account_id="general-acc"),
                _make_position(qty=100.0, account_id="isa-acc"),
            ],
            accounts=[
                {"id": "general-acc", "tax_type": "GENERAL"},
                {"id": "isa-acc", "tax_type": "ISA"},
            ],
        )
        costs = _aggregate_position_costs(overview)
        key = ("AAPL", "NASDAQ")
        assert costs[key][0]["account_id"] == "general-acc"
        assert costs[key][0]["is_tax_deferred"] is False
        assert costs[key][1]["account_id"] == "isa-acc"
        assert costs[key][1]["is_tax_deferred"] is True

    def test_empty_overview_returns_empty_dict(self):
        assert _aggregate_position_costs({}) == {}


class TestBuildTaxPreview:
    def test_domestic_sell_gain_not_added_to_overseas_tax(self):
        item = _make_item(ticker="005930", market="KOSPI", diff_krw=-500_000.0, shares_to_trade=-5.0)
        overview = _make_overview(
            [_make_position(ticker="005930", market="KOSPI", qty=5.0, avg_price=60_000.0, current_price=70_000.0)]
        )
        analysis = _make_analysis([item])

        total_gain, overseas_tax, fee, notes, items = _build_tax_preview(analysis, overview)

        assert total_gain == pytest.approx(50_000.0)  # (70k-60k)*5
        assert overseas_tax == 0.0
        assert items[0].is_overseas is False

    def test_overseas_sell_gain_above_deduction_applies_tax(self):
        # 매도 10주, 평단 100_000 현재가 350_000 → 실현이익 250만 (공제 250만 초과분 0 → tax 0)
        # 공제 초과하도록 더 크게: 현재가 400_000
        item = _make_item(ticker="AAPL", market="NASDAQ", diff_krw=-1_000_000.0, shares_to_trade=-10.0)
        overview = _make_overview(
            [_make_position(ticker="AAPL", market="NASDAQ", qty=10.0, avg_price=100_000.0, current_price=400_000.0)]
        )
        analysis = _make_analysis([item])

        total_gain, overseas_tax, fee, notes, items = _build_tax_preview(analysis, overview)

        # gain = (400_000-100_000)*10 = 3_000_000, taxable = 3_000_000-2_500_000=500_000, tax=500_000*0.22=110_000
        assert total_gain == pytest.approx(3_000_000.0)
        assert overseas_tax == pytest.approx(110_000.0)
        assert any("양도세" in n for n in notes)

    def test_shares_to_trade_none_falls_back_to_held_qty(self):
        """shares_to_trade=None(가격 데이터 누락)이어도 cost_map의 보유수량으로 폴백해 크래시하지 않는다."""
        item = _make_item(ticker="AAPL", market="NASDAQ", diff_krw=-1_000_000.0, shares_to_trade=None)
        overview = _make_overview(
            [_make_position(ticker="AAPL", market="NASDAQ", qty=10.0, avg_price=100_000.0, current_price=120_000.0)]
        )
        analysis = _make_analysis([item])

        total_gain, overseas_tax, fee, notes, items = _build_tax_preview(analysis, overview)

        assert items[0].sell_qty == pytest.approx(10.0)
        assert items[0].excluded_reason is None
        assert total_gain == pytest.approx(200_000.0)  # (120k-100k)*10

    def test_shares_to_trade_none_and_no_cost_data_excluded(self):
        """shares_to_trade=None이고 보유 정보도 없으면 크래시 없이 추정 제외 처리된다."""
        item = _make_item(ticker="AAPL", market="NASDAQ", diff_krw=-1_000_000.0, shares_to_trade=None)
        overview = _make_overview([])  # 가격/평단가 정보 전무
        analysis = _make_analysis([item])

        total_gain, overseas_tax, fee, notes, items = _build_tax_preview(analysis, overview)

        assert total_gain == 0.0
        assert items[0].excluded_reason == "가격/평단가 정보 부족으로 추정 제외"
        assert any("제외" in n for n in notes)

    def test_cash_and_kr_property_skipped(self):
        cash_item = _make_item(ticker="CASH", market="KRW_CASH", diff_krw=-100_000.0, shares_to_trade=None)
        property_item = _make_item(ticker="HOME", market="KR_PROPERTY", diff_krw=-100_000.0, shares_to_trade=None)
        analysis = _make_analysis([cash_item, property_item])

        total_gain, overseas_tax, fee, notes, items = _build_tax_preview(analysis, _make_overview([]))

        assert total_gain == 0.0
        assert items == []

    def test_buy_items_not_included(self):
        item = _make_item(diff_krw=500_000.0, weight_diff_pct=3.0)  # 매수(diff_krw > 0)
        analysis = _make_analysis([item])

        total_gain, overseas_tax, fee, notes, items = _build_tax_preview(analysis, _make_overview([]))

        assert total_gain == 0.0
        assert items == []

    def test_isa_account_sell_excluded_from_realized_gain(self):
        """ISA 계좌 보유분 매도는 과세이연되어 실현손익 추정에서 제외되고 is_tax_deferred=True로 표시된다."""
        item = _make_item(ticker="AAPL", market="NASDAQ", diff_krw=-1_000_000.0, shares_to_trade=-10.0)
        overview = _make_overview(
            [
                _make_position(
                    ticker="AAPL",
                    market="NASDAQ",
                    qty=10.0,
                    avg_price=100_000.0,
                    current_price=150_000.0,
                    account_id="isa-acc",
                )
            ],
            accounts=[{"id": "isa-acc", "tax_type": "ISA"}],
        )
        analysis = _make_analysis([item])

        total_gain, overseas_tax, fee, notes, items = _build_tax_preview(analysis, overview)

        assert total_gain == 0.0
        assert overseas_tax == 0.0
        assert items[0].is_tax_deferred is True
        assert items[0].estimated_realized_gain_krw == 0.0
        assert any("과세이연" in n for n in notes)

    def test_general_account_sold_before_isa_when_mixed(self):
        """동일 종목을 일반+ISA 계좌에 나눠 보유 시, 일반계좌 보유분부터 소진해 실현손익을 계산한다."""
        item = _make_item(ticker="AAPL", market="NASDAQ", diff_krw=-1_000_000.0, shares_to_trade=-5.0)
        overview = _make_overview(
            [
                _make_position(
                    ticker="AAPL",
                    market="NASDAQ",
                    qty=5.0,
                    avg_price=100_000.0,
                    current_price=150_000.0,
                    account_id="general-acc",
                ),
                _make_position(
                    ticker="AAPL",
                    market="NASDAQ",
                    qty=5.0,
                    avg_price=100_000.0,
                    current_price=150_000.0,
                    account_id="isa-acc",
                ),
            ],
            accounts=[
                {"id": "general-acc", "tax_type": "GENERAL"},
                {"id": "isa-acc", "tax_type": "ISA"},
            ],
        )
        analysis = _make_analysis([item])

        total_gain, overseas_tax, fee, notes, items = _build_tax_preview(analysis, overview)

        # 매도 5주 전량 일반계좌(5주 보유)에서 소진 → (150k-100k)*5 = 250_000, ISA 계좌는 건드리지 않음
        assert total_gain == pytest.approx(250_000.0)
        assert items[0].is_tax_deferred is False


class TestRiskNote:
    def test_all_normal_returns_none(self):
        risk = {"diversification_score": 80, "top_holding_weight_pct": 20.0, "annualized_volatility_pct": 10.0}
        assert _risk_note(risk) is None

    def test_low_diversification_flagged(self):
        risk = {"diversification_score": 30, "top_holding_weight_pct": 20.0, "annualized_volatility_pct": 10.0}
        note = _risk_note(risk)
        assert note is not None
        assert "분산도" in note

    def test_high_concentration_flagged(self):
        risk = {"diversification_score": 80, "top_holding_weight_pct": 45.0, "annualized_volatility_pct": 10.0}
        note = _risk_note(risk)
        assert note is not None
        assert "과집중" in note

    def test_high_volatility_flagged(self):
        risk = {"diversification_score": 80, "top_holding_weight_pct": 20.0, "annualized_volatility_pct": 25.0}
        note = _risk_note(risk)
        assert note is not None
        assert "변동성" in note


class TestCheckCompositeSignal:
    def test_all_normal_returns_false(self):
        triggered, reason = check_composite_signal("GREEN", True, 80, 20.0, 10.0)
        assert triggered is False
        assert reason is None

    def test_market_red_triggers(self):
        triggered, reason = check_composite_signal("RED", False, None, None, None)
        assert triggered is True
        assert "시장" in reason

    def test_risk_unavailable_ignored(self):
        # risk_available=False면 리스크 수치가 임계값을 넘어도 무시됨
        triggered, reason = check_composite_signal("GREEN", False, 10, 90.0, 50.0)
        assert triggered is False
        assert reason is None

    def test_low_diversification_triggers(self):
        triggered, reason = check_composite_signal("GREEN", True, 30, 20.0, 10.0)
        assert triggered is True
        assert "분산도" in reason

    def test_market_and_risk_combined_reason(self):
        triggered, reason = check_composite_signal("RED", True, 30, 20.0, 10.0)
        assert triggered is True
        assert "시장" in reason
        assert "분산도" in reason


class TestFetchMarketAndRiskSignal:
    @pytest.mark.asyncio
    async def test_success_returns_level_and_risk_dict(self, mock_db, mock_redis):
        with (
            patch(
                "app.services.rebalancing_diagnosis_service.get_market_signal",
                new=AsyncMock(return_value={"composite_level": "RED"}),
            ),
            patch(
                "app.services.rebalancing_diagnosis_service.get_portfolio_risk_metrics",
                new=AsyncMock(return_value={"data_available": True, "diversification_score": 50}),
            ),
        ):
            market_level, risk = await fetch_market_and_risk_signal(uuid.uuid4(), mock_db, mock_redis)

        assert market_level == "RED"
        assert risk["diversification_score"] == 50

    @pytest.mark.asyncio
    async def test_both_failures_return_safe_defaults(self, mock_db, mock_redis):
        with (
            patch(
                "app.services.rebalancing_diagnosis_service.get_market_signal",
                new=AsyncMock(side_effect=RuntimeError("down")),
            ),
            patch(
                "app.services.rebalancing_diagnosis_service.get_portfolio_risk_metrics",
                new=AsyncMock(side_effect=RuntimeError("down")),
            ),
        ):
            market_level, risk = await fetch_market_and_risk_signal(uuid.uuid4(), mock_db, mock_redis)

        assert market_level is None
        assert risk == {}


class TestBuildDiagnosisContext:
    @pytest.mark.asyncio
    async def test_market_yellow_and_risk_normal_shows_market_note(self, mock_db, mock_redis):
        """복합신호 조건 미충족 시(YELLOW는 단독 트리거 안 됨) 기존처럼 market_note가 노출된다."""
        analysis = _make_analysis([])
        overview = _make_overview([])

        with (
            patch(
                "app.services.rebalancing_diagnosis_service.get_market_signal",
                new=AsyncMock(return_value={"composite_level": "YELLOW"}),
            ),
            patch(
                "app.services.rebalancing_diagnosis_service.get_portfolio_risk_metrics",
                new=AsyncMock(
                    return_value={
                        "data_available": True,
                        "annualized_volatility_pct": 10.0,
                        "beta_sp500": 1.1,
                        "diversification_score": 80,
                        "top_holding_weight_pct": 20.0,
                    }
                ),
            ),
        ):
            ctx = await build_diagnosis_context(uuid.uuid4(), mock_db, mock_redis, analysis, overview)

        assert ctx.market_level == "YELLOW"
        assert ctx.market_note is not None
        assert ctx.risk_available is True
        assert ctx.diversification_score == 80
        assert ctx.risk_note is None
        assert ctx.composite_signal_triggered is False
        assert ctx.composite_signal_reason is None

    @pytest.mark.asyncio
    async def test_composite_triggered_suppresses_market_and_risk_notes(self, mock_db, mock_redis):
        """복합신호(check_composite_signal)가 충족되면 진단탭 상단 배너와 중복되지 않도록
        market_note/risk_note를 생략하고 composite_signal_triggered/reason만 채운다."""
        analysis = _make_analysis([])
        overview = _make_overview([])

        with (
            patch(
                "app.services.rebalancing_diagnosis_service.get_market_signal",
                new=AsyncMock(return_value={"composite_level": "YELLOW"}),
            ),
            patch(
                "app.services.rebalancing_diagnosis_service.get_portfolio_risk_metrics",
                new=AsyncMock(
                    return_value={
                        "data_available": True,
                        "annualized_volatility_pct": 25.0,
                        "beta_sp500": 1.1,
                        "diversification_score": 30,
                        "top_holding_weight_pct": 20.0,
                    }
                ),
            ),
        ):
            ctx = await build_diagnosis_context(uuid.uuid4(), mock_db, mock_redis, analysis, overview)

        assert ctx.market_note is None
        assert ctx.risk_note is None
        assert ctx.composite_signal_triggered is True
        assert ctx.composite_signal_reason is not None
        assert "분산도" in ctx.composite_signal_reason

    @pytest.mark.asyncio
    async def test_enable_composite_signals_false_keeps_granular_notes(self, mock_db, mock_redis):
        """enable_composite_signals=False(유저가 해당 알림을 꺼둠)면 조건을 충족해도
        composite_signal_triggered는 False로 고정되고, 기존 market_note/risk_note는 그대로 노출된다."""
        analysis = _make_analysis([])
        overview = _make_overview([])

        with (
            patch(
                "app.services.rebalancing_diagnosis_service.get_market_signal",
                new=AsyncMock(return_value={"composite_level": "RED"}),
            ),
            patch(
                "app.services.rebalancing_diagnosis_service.get_portfolio_risk_metrics",
                new=AsyncMock(
                    return_value={
                        "data_available": True,
                        "annualized_volatility_pct": 25.0,
                        "beta_sp500": 1.1,
                        "diversification_score": 30,
                        "top_holding_weight_pct": 20.0,
                    }
                ),
            ),
        ):
            ctx = await build_diagnosis_context(
                uuid.uuid4(), mock_db, mock_redis, analysis, overview, enable_composite_signals=False
            )

        assert ctx.composite_signal_triggered is False
        assert ctx.composite_signal_reason is None
        assert ctx.market_note is not None
        assert ctx.risk_note is not None

    @pytest.mark.asyncio
    async def test_market_signal_failure_does_not_crash(self, mock_db, mock_redis):
        analysis = _make_analysis([])
        overview = _make_overview([])

        with (
            patch(
                "app.services.rebalancing_diagnosis_service.get_market_signal",
                new=AsyncMock(side_effect=RuntimeError("fred down")),
            ),
            patch(
                "app.services.rebalancing_diagnosis_service.get_portfolio_risk_metrics",
                new=AsyncMock(return_value={"data_available": False}),
            ),
        ):
            ctx = await build_diagnosis_context(uuid.uuid4(), mock_db, mock_redis, analysis, overview)

        assert ctx.market_level is None
        assert ctx.market_note is None

    @pytest.mark.asyncio
    async def test_risk_failure_does_not_crash_and_tax_still_computed(self, mock_db, mock_redis):
        item = _make_item(ticker="005930", market="KOSPI", diff_krw=-500_000.0, shares_to_trade=-5.0)
        analysis = _make_analysis([item])
        overview = _make_overview(
            [_make_position(ticker="005930", market="KOSPI", qty=5.0, avg_price=60_000.0, current_price=70_000.0)]
        )

        with (
            patch(
                "app.services.rebalancing_diagnosis_service.get_market_signal",
                new=AsyncMock(return_value={"composite_level": "GREEN"}),
            ),
            patch(
                "app.services.rebalancing_diagnosis_service.get_portfolio_risk_metrics",
                new=AsyncMock(side_effect=RuntimeError("yfinance down")),
            ),
        ):
            ctx = await build_diagnosis_context(uuid.uuid4(), mock_db, mock_redis, analysis, overview)

        assert ctx.risk_available is False
        assert ctx.diversification_score is None
        # 세금 미리보기는 리스크 실패와 무관하게 정상 계산됨
        assert ctx.estimated_sell_realized_gain_krw == pytest.approx(50_000.0)

    @pytest.mark.asyncio
    async def test_both_fail_tax_preview_still_computed(self, mock_db, mock_redis):
        item = _make_item(ticker="005930", market="KOSPI", diff_krw=-500_000.0, shares_to_trade=-5.0)
        analysis = _make_analysis([item])
        overview = _make_overview(
            [_make_position(ticker="005930", market="KOSPI", qty=5.0, avg_price=60_000.0, current_price=70_000.0)]
        )

        with (
            patch(
                "app.services.rebalancing_diagnosis_service.get_market_signal",
                new=AsyncMock(side_effect=RuntimeError("fred down")),
            ),
            patch(
                "app.services.rebalancing_diagnosis_service.get_portfolio_risk_metrics",
                new=AsyncMock(side_effect=RuntimeError("yfinance down")),
            ),
        ):
            ctx = await build_diagnosis_context(uuid.uuid4(), mock_db, mock_redis, analysis, overview)

        assert ctx.market_level is None
        assert ctx.risk_available is False
        assert ctx.estimated_sell_realized_gain_krw == pytest.approx(50_000.0)

    @pytest.mark.asyncio
    async def test_settings_row_none_leaves_goal_fields_none(self, mock_db, mock_redis):
        """목표를 아예 설정하지 않은 유저(settings_row=None)는 목표 비교 필드가 조용히 생략된다."""
        analysis = _make_analysis([])
        overview = _make_overview([])

        with (
            patch(
                "app.services.rebalancing_diagnosis_service.get_market_signal",
                new=AsyncMock(return_value={"composite_level": "GREEN"}),
            ),
            patch(
                "app.services.rebalancing_diagnosis_service.get_portfolio_risk_metrics",
                new=AsyncMock(return_value={"data_available": False}),
            ),
        ):
            ctx = await build_diagnosis_context(uuid.uuid4(), mock_db, mock_redis, analysis, overview)

        assert ctx.goal_annual_return_pct is None
        assert ctx.goal_annual_dividend_krw is None

    @pytest.mark.asyncio
    async def test_settings_row_provided_populates_goal_fields(self, mock_db, mock_redis):
        """settings_row가 전달되면 신규 DB 쿼리 없이 UserSettings의 목표 필드를 그대로 반영한다."""
        analysis = _make_analysis([])
        overview = _make_overview([])
        settings_row = SimpleNamespace(goal_annual_return_pct=8.0, annual_dividend_goal=3_000_000.0)

        with (
            patch(
                "app.services.rebalancing_diagnosis_service.get_market_signal",
                new=AsyncMock(return_value={"composite_level": "GREEN"}),
            ),
            patch(
                "app.services.rebalancing_diagnosis_service.get_portfolio_risk_metrics",
                new=AsyncMock(return_value={"data_available": False}),
            ),
        ):
            ctx = await build_diagnosis_context(
                uuid.uuid4(), mock_db, mock_redis, analysis, overview, settings_row=settings_row
            )

        assert ctx.goal_annual_return_pct == pytest.approx(8.0)
        assert ctx.goal_annual_dividend_krw == pytest.approx(3_000_000.0)
