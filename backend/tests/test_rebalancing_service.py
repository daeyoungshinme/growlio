"""rebalancing_service 단위 테스트."""

import uuid
from types import SimpleNamespace

import pytest

from app.services.rebalancing_service import analyze_rebalancing


def _make_portfolio(items: list[dict], base_type: str = "STOCK_ONLY") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        name="테스트 포트폴리오",
        base_type=base_type,
        items=items,
    )


def _make_overview(
    total_assets_krw: float | None = None,  # None이면 total_stock_krw와 동일 (예수금 0)
    total_stock_krw: float = 1_000_000,
    all_positions: list[dict] | None = None,
) -> dict:
    return {
        "total_assets_krw": total_assets_krw if total_assets_krw is not None else total_stock_krw,
        "total_stock_krw": total_stock_krw,
        "all_positions": all_positions or [],
    }


class TestAnalyzeRebalancingBuyCase:
    """매수 필요 케이스."""

    def test_buy_diff_and_shares(self):
        """현재 30%, 목표 50% → diff +700,000, shares 매수."""
        portfolio = _make_portfolio(
            [
                {"ticker": "AAPL", "name": "Apple", "market": "NASDAQ", "weight": 100},
            ]
        )
        overview = _make_overview(
            total_stock_krw=1_000_000,
            all_positions=[
                {
                    "ticker": "AAPL",
                    "market": "NASDAQ",
                    "name": "Apple",
                    "value_krw": 300_000,
                    "current_price": 250_000,
                    "qty": 1,
                },
            ],
        )
        result = analyze_rebalancing(portfolio, overview)
        item = result.items[0]
        assert item.diff_krw == 700_000
        assert item.shares_to_trade == 3  # floor(1_000_000/250_000)=4, shares=4-1=3

    def test_not_held_position(self):
        """보유 없는 종목 → current_value=0, diff=target_value."""
        portfolio = _make_portfolio(
            [
                {"ticker": "TSLA", "name": "Tesla", "market": "NASDAQ", "weight": 100},
            ]
        )
        overview = _make_overview(total_stock_krw=1_000_000, all_positions=[])
        result = analyze_rebalancing(portfolio, overview)
        item = result.items[0]
        assert item.current_value_krw == 0
        assert item.diff_krw == 1_000_000
        assert item.shares_to_trade is None  # current_price 없음


class TestAnalyzeRebalancingSellCase:
    """매도 필요 케이스."""

    def test_sell_diff_negative(self):
        """현재 80%, 목표 50% → diff 음수."""
        portfolio = _make_portfolio(
            [
                {"ticker": "AAPL", "name": "Apple", "market": "NASDAQ", "weight": 50},
                {"ticker": "TSLA", "name": "Tesla", "market": "NASDAQ", "weight": 50},
            ]
        )
        overview = _make_overview(
            total_stock_krw=1_000_000,
            all_positions=[
                {
                    "ticker": "AAPL",
                    "market": "NASDAQ",
                    "name": "Apple",
                    "value_krw": 800_000,
                    "current_price": 200_000,
                    "qty": 4,
                },
                {
                    "ticker": "TSLA",
                    "market": "NASDAQ",
                    "name": "Tesla",
                    "value_krw": 200_000,
                    "current_price": 100_000,
                    "qty": 2,
                },
            ],
        )
        result = analyze_rebalancing(portfolio, overview)
        aapl = next(i for i in result.items if i.ticker == "AAPL")
        tsla = next(i for i in result.items if i.ticker == "TSLA")
        assert aapl.diff_krw == -300_000  # 매도
        assert tsla.diff_krw == 300_000  # 매수
        assert aapl.shares_to_trade == -2  # floor(500_000/200_000)=2, shares=2-4=-2


class TestCashItem:
    """CASH 항목 처리."""

    def test_cash_has_no_shares(self):
        """CASH 항목은 shares_to_trade=None."""
        portfolio = _make_portfolio(
            [
                {"ticker": "CASH", "name": "현금", "market": "KRW", "weight": 100},
            ]
        )
        overview = _make_overview(total_assets_krw=2_000_000, total_stock_krw=1_500_000)
        result = analyze_rebalancing(portfolio, overview)
        item = result.items[0]
        assert item.shares_to_trade is None
        assert item.current_value_krw == 500_000  # 2M - 1.5M

    def test_cash_current_weight(self):
        """CASH 현재 비중 = (전체자산 - 주식자산) / base."""
        portfolio = _make_portfolio(
            [{"ticker": "CASH", "name": "현금", "market": "KRW", "weight": 100}],
            base_type="TOTAL_ASSETS",
        )
        overview = _make_overview(total_assets_krw=1_000_000, total_stock_krw=600_000)
        result = analyze_rebalancing(portfolio, overview)
        item = result.items[0]
        # base = total_assets = 1M, cash = 400K → 40%
        assert item.current_weight_pct == 40.0
        assert item.diff_krw == 600_000  # 목표 100% - 현재 40% → 60% = 600K 매수 필요


class TestTotalAssetsBaseType:
    """TOTAL_ASSETS base_type 테스트."""

    def test_base_is_total_assets(self):
        """base_type=TOTAL_ASSETS → base_value = total_assets_krw."""
        portfolio = _make_portfolio(
            [{"ticker": "AAPL", "name": "Apple", "market": "NASDAQ", "weight": 100}],
            base_type="TOTAL_ASSETS",
        )
        overview = _make_overview(
            total_assets_krw=2_000_000,
            total_stock_krw=1_000_000,
            all_positions=[
                {
                    "ticker": "AAPL",
                    "market": "NASDAQ",
                    "name": "Apple",
                    "value_krw": 1_000_000,
                    "current_price": 500_000,
                },
            ],
        )
        result = analyze_rebalancing(portfolio, overview)
        assert result.base_value_krw == 2_000_000
        item = result.items[0]
        assert item.target_value_krw == 2_000_000  # 100% of 2M


class TestUntrackedHoldings:
    """목표 포트폴리오에 없는 보유 종목 → 전량 매도 아이템으로 분류."""

    def test_untracked_appears_as_sell_item(self):
        """TSLA 보유 중인데 목표 포트폴리오에 없으면 items에 target=0 매도 아이템으로 포함."""
        portfolio = _make_portfolio(
            [
                {"ticker": "AAPL", "name": "Apple", "market": "NASDAQ", "weight": 100},
            ]
        )
        overview = _make_overview(
            total_stock_krw=1_000_000,
            all_positions=[
                {
                    "ticker": "AAPL",
                    "market": "NASDAQ",
                    "name": "Apple",
                    "value_krw": 600_000,
                    "current_price": 200_000,
                    "qty": 3,
                },
                {
                    "ticker": "TSLA",
                    "market": "NASDAQ",
                    "name": "Tesla",
                    "value_krw": 400_000,
                    "current_price": 100_000,
                    "qty": 4,
                },
            ],
        )
        result = analyze_rebalancing(portfolio, overview)
        assert result.untracked_holdings == []
        tsla = next(i for i in result.items if i.ticker == "TSLA")
        assert tsla.target_weight_pct == 0.0
        assert tsla.target_value_krw == 0.0
        assert tsla.diff_krw == -400_000  # 전량 매도
        assert tsla.shares_to_trade == -4  # qty=4 전량 매도 → -4

    def test_all_tracked_empty_untracked(self):
        """모든 보유 종목이 목표 포트폴리오에 있으면 untracked_holdings 비어 있음."""
        portfolio = _make_portfolio(
            [
                {"ticker": "AAPL", "name": "Apple", "market": "NASDAQ", "weight": 100},
            ]
        )
        overview = _make_overview(
            total_stock_krw=1_000_000,
            all_positions=[
                {
                    "ticker": "AAPL",
                    "market": "NASDAQ",
                    "name": "Apple",
                    "value_krw": 1_000_000,
                    "current_price": 200_000,
                },
            ],
        )
        result = analyze_rebalancing(portfolio, overview)
        assert result.untracked_holdings == []


class TestShareCalculationEdgeCases:
    """주수 계산 엣지 케이스."""

    def test_buy_shares_no_overshoot(self):
        """매수 수량 × 현재가 ≤ 배분예산 — floor 기반으로 예산 초과 없음."""
        portfolio = _make_portfolio(
            [
                {"ticker": "ACE", "name": "ACE 나스닥", "market": "KR", "weight": 50},
                {"ticker": "SAMSUNGE", "name": "삼성전자우", "market": "KR", "weight": 50},
            ]
        )
        overview = _make_overview(
            total_stock_krw=600_000,
            all_positions=[
                {
                    "ticker": "ACE",
                    "market": "KR",
                    "name": "ACE 나스닥",
                    "value_krw": 0,
                    "current_price": 35_000,
                    "qty": 0,
                },
                {
                    "ticker": "SAMSUNGE",
                    "market": "KR",
                    "name": "삼성전자우",
                    "value_krw": 0,
                    "current_price": 230_000,
                    "qty": 0,
                },
            ],
        )
        result = analyze_rebalancing(portfolio, overview)
        for item in result.items:
            if item.shares_to_trade is not None and item.shares_to_trade > 0 and item.current_price_krw:
                actual_cost = item.shares_to_trade * item.current_price_krw
                assert actual_cost <= item.target_value_krw, (
                    f"{item.ticker}: {actual_cost} > {item.target_value_krw} 예산 초과!"
                )

    def test_zero_price_no_shares(self):
        """current_price=0이고 보유수량도 0이면 shares_to_trade=None (계산 불가)."""
        portfolio = _make_portfolio(
            [
                {"ticker": "AAPL", "name": "Apple", "market": "NASDAQ", "weight": 100},
            ]
        )
        overview = _make_overview(
            total_stock_krw=1_000_000,
            all_positions=[
                {"ticker": "AAPL", "market": "NASDAQ", "name": "Apple", "value_krw": 500_000, "current_price": 0},
            ],
        )
        result = analyze_rebalancing(portfolio, overview)
        assert result.items[0].shares_to_trade is None

    def test_zero_price_with_holding_falls_back_to_implied_price(self):
        """current_price=0이지만 보유수량>0이면 value_krw/qty를 폴백 가격으로 사용해 매도 수량 계산."""
        portfolio = _make_portfolio(
            [
                {"ticker": "AAPL", "name": "Apple", "market": "NASDAQ", "weight": 0},
            ]
        )
        overview = _make_overview(
            total_stock_krw=1_000_000,
            all_positions=[
                {
                    "ticker": "AAPL",
                    "market": "NASDAQ",
                    "name": "Apple",
                    "value_krw": 1_000_000,
                    "current_price": 0,
                    "qty": 10,
                },
            ],
        )
        result = analyze_rebalancing(portfolio, overview)
        item = result.items[0]
        # implied_price = 1_000_000/10 = 100_000, target_qty = floor(0/100_000) = 0, shares = 0-10 = -10
        assert item.shares_to_trade == -10

    def test_untracked_item_sells_full_qty_even_without_price(self):
        """목표 포트폴리오에 없는(untracked) 보유 종목은 가격 데이터가 없어도 전량 매도 수량 계산."""
        portfolio = _make_portfolio(
            [
                {"ticker": "MSFT", "name": "Microsoft", "market": "NASDAQ", "weight": 100},
            ]
        )
        overview = _make_overview(
            total_stock_krw=1_000_000,
            all_positions=[
                {
                    "ticker": "MSFT",
                    "market": "NASDAQ",
                    "name": "Microsoft",
                    "value_krw": 500_000,
                    "current_price": 200_000,
                    "qty": 2.5,
                },
                {
                    "ticker": "AAPL",
                    "market": "NASDAQ",
                    "name": "Apple",
                    "value_krw": 300_000,
                    "current_price": None,
                    "qty": 3,
                },
            ],
        )
        result = analyze_rebalancing(portfolio, overview)
        aapl = next(i for i in result.items if i.ticker == "AAPL")
        assert aapl.shares_to_trade == -3

    def test_no_positions_zero_base(self):
        """보유 자산이 없어 base_krw=0 이면 current_weight_pct=0."""
        portfolio = _make_portfolio(
            [
                {"ticker": "AAPL", "name": "Apple", "market": "NASDAQ", "weight": 100},
            ]
        )
        overview = _make_overview(total_stock_krw=0, all_positions=[])
        result = analyze_rebalancing(portfolio, overview)
        assert result.base_value_krw == 0
        assert result.items[0].current_weight_pct == 0.0

    def test_new_portfolio_cash_only(self):
        """신규 포트폴리오: 주식 미보유, 예수금 600,000원 → 비중별 수량 정상 계산."""
        portfolio = _make_portfolio(
            [
                {"ticker": "ACE", "name": "ACE 나스닥", "market": "KR", "weight": 50},
                {"ticker": "SAMSUNGE", "name": "삼성전자우", "market": "KR", "weight": 50},
            ]
        )
        overview = _make_overview(
            total_stock_krw=0,
            total_assets_krw=600_000,
            all_positions=[
                {
                    "ticker": "ACE",
                    "market": "KR",
                    "name": "ACE 나스닥",
                    "value_krw": 0,
                    "current_price": 35_000,
                    "qty": 0,
                },
                {
                    "ticker": "SAMSUNGE",
                    "market": "KR",
                    "name": "삼성전자우",
                    "value_krw": 0,
                    "current_price": 230_000,
                    "qty": 0,
                },
            ],
        )
        result = analyze_rebalancing(portfolio, overview)
        ace = next(i for i in result.items if i.ticker == "ACE")
        samsung = next(i for i in result.items if i.ticker == "SAMSUNGE")
        assert result.base_value_krw == 600_000
        assert ace.shares_to_trade == 8  # floor(300_000/35_000)=8
        assert samsung.shares_to_trade == 1  # floor(300_000/230_000)=1
        assert ace.shares_to_trade * ace.current_price_krw <= ace.target_value_krw
        assert samsung.shares_to_trade * samsung.current_price_krw <= samsung.target_value_krw


class TestWeightValidation:
    """Pydantic 비중 합계 검증."""

    def test_weight_sum_not_100_raises(self):
        from pydantic import ValidationError

        from app.schemas.portfolio import PortfolioCreate, PortfolioItem

        with pytest.raises(ValidationError, match="비중 합계"):
            PortfolioCreate(
                name="테스트",
                items=[
                    PortfolioItem(ticker="AAPL", name="Apple", market="NASDAQ", weight=60),
                    PortfolioItem(ticker="TSLA", name="Tesla", market="NASDAQ", weight=30),
                ],
            )

    def test_weight_sum_100_ok(self):
        from app.schemas.portfolio import PortfolioCreate, PortfolioItem

        schema = PortfolioCreate(
            name="테스트",
            items=[
                PortfolioItem(ticker="AAPL", name="Apple", market="NASDAQ", weight=70),
                PortfolioItem(ticker="TSLA", name="Tesla", market="NASDAQ", weight=30),
            ],
        )
        assert len(schema.items) == 2

    def test_empty_items_raises(self):
        from pydantic import ValidationError

        from app.schemas.portfolio import PortfolioCreate

        with pytest.raises(ValidationError, match="최소 1개"):
            PortfolioCreate(name="테스트", items=[])


# ── _div_info 순수 함수 ─────────────────────────────────────


class TestDivInfo:
    def test_none_map_returns_none_zero(self):
        from app.services.rebalancing_service import _div_info

        assert _div_info("AAPL", "NASDAQ", None) == (None, 0.0)

    def test_ticker_not_in_map_returns_none_zero(self):
        from app.services.rebalancing_service import _div_info

        div_map = {("TSLA", "NASDAQ"): {"dividend_yield": 1.5, "estimated_annual_krw": 1000}}
        assert _div_info("AAPL", "NASDAQ", div_map) == (None, 0.0)

    def test_with_positive_yield(self):
        from app.services.rebalancing_service import _div_info

        div_map = {("AAPL", "NASDAQ"): {"dividend_yield": 2.5, "estimated_annual_krw": 50_000}}
        yp, annual = _div_info("AAPL", "NASDAQ", div_map)
        assert yp == pytest.approx(2.5)
        assert annual == pytest.approx(50_000.0)

    def test_zero_yield_and_annual_returns_none_zero(self):
        from app.services.rebalancing_service import _div_info

        div_map = {("AAPL", "NASDAQ"): {"dividend_yield": 0, "estimated_annual_krw": 0}}
        assert _div_info("AAPL", "NASDAQ", div_map) == (None, 0.0)

    def test_only_annual_positive_returns_none_and_annual(self):
        from app.services.rebalancing_service import _div_info

        div_map = {("AAPL", "NASDAQ"): {"dividend_yield": 0, "estimated_annual_krw": 30_000}}
        yp, annual = _div_info("AAPL", "NASDAQ", div_map)
        assert yp is None
        assert annual == pytest.approx(30_000.0)


# ── KR_PROPERTY 시장 ────────────────────────────────────────


class TestKrPropertyItem:
    def test_kr_property_uses_real_estate_value(self):
        """KR_PROPERTY 항목은 REAL_ESTATE 계좌 값 합산."""
        portfolio = _make_portfolio(
            [
                {"ticker": "HOUSE", "name": "아파트", "market": "KR_PROPERTY", "weight": 100},
            ]
        )
        overview = {
            "total_assets_krw": 500_000_000,
            "total_stock_krw": 0,
            "all_positions": [],
            "accounts": [
                {"asset_type": "REAL_ESTATE", "amount_krw": 300_000_000, "include_in_total": True},
            ],
        }
        result = analyze_rebalancing(portfolio, overview)
        item = result.items[0]
        assert item.shares_to_trade is None
        assert item.current_value_krw == pytest.approx(300_000_000)

    def test_kr_property_no_real_estate_accounts_gives_zero(self):
        """REAL_ESTATE 계좌 없으면 current_value=0."""
        portfolio = _make_portfolio(
            [
                {"ticker": "HOUSE", "name": "아파트", "market": "KR_PROPERTY", "weight": 100},
            ]
        )
        overview = {
            "total_assets_krw": 1_000_000,
            "total_stock_krw": 1_000_000,
            "all_positions": [],
            "accounts": [],
        }
        result = analyze_rebalancing(portfolio, overview)
        item = result.items[0]
        assert item.current_value_krw == 0


# ── 배당 정보가 있는 포트폴리오 ─────────────────────────────


class TestDividendMapInAnalysis:
    def test_dividend_info_included_in_items(self):
        """dividend_map 전달 시 배당 정보가 items에 포함된다."""
        portfolio = _make_portfolio(
            [
                {"ticker": "AAPL", "name": "Apple", "market": "NASDAQ", "weight": 100},
            ]
        )
        overview = _make_overview(
            total_stock_krw=1_000_000,
            all_positions=[
                {
                    "ticker": "AAPL",
                    "market": "NASDAQ",
                    "name": "Apple",
                    "value_krw": 1_000_000,
                    "current_price": 200_000,
                },
            ],
        )
        div_map = {
            ("AAPL", "NASDAQ"): {"dividend_yield": 1.5, "estimated_annual_krw": 15_000},
        }
        result = analyze_rebalancing(portfolio, overview, dividend_map=div_map)
        item = result.items[0]
        assert item.dividend_yield == pytest.approx(1.5)

    def test_dividend_target_estimated_from_yield(self):
        """annual_div_current=0이지만 yield>0이면 target 배당금 추정."""
        portfolio = _make_portfolio(
            [
                {"ticker": "AAPL", "name": "Apple", "market": "NASDAQ", "weight": 100},
            ]
        )
        overview = _make_overview(total_stock_krw=1_000_000, all_positions=[])
        div_map = {("AAPL", "NASDAQ"): {"dividend_yield": 2.0, "estimated_annual_krw": 0}}
        result = analyze_rebalancing(portfolio, overview, dividend_map=div_map)
        item = result.items[0]
        # annual_div_target = target_value * (yield/100) = 1_000_000 * 0.02 = 20_000
        assert item.annual_dividend_target_krw == pytest.approx(20_000, rel=0.01)


# ── weighted CAGR (_calc_portfolio_cagrs) ────────────────────


class TestWeightedCagr:
    def test_weighted_cagr_set_with_returns_map(self):
        """returns_map이 있으면 target/current weighted CAGR 계산."""
        portfolio = _make_portfolio(
            [
                {"ticker": "AAPL", "name": "Apple", "market": "NASDAQ", "weight": 60},
                {"ticker": "TSLA", "name": "Tesla", "market": "NASDAQ", "weight": 40},
            ]
        )
        overview = _make_overview(
            total_stock_krw=1_000_000,
            all_positions=[
                {
                    "ticker": "AAPL",
                    "market": "NASDAQ",
                    "name": "Apple",
                    "value_krw": 600_000,
                    "current_price": 100_000,
                    "account_id": str(uuid.uuid4()),
                    "account_name": "계좌",
                    "qty": 6,
                },
                {
                    "ticker": "TSLA",
                    "market": "NASDAQ",
                    "name": "Tesla",
                    "value_krw": 400_000,
                    "current_price": 80_000,
                    "account_id": str(uuid.uuid4()),
                    "account_name": "계좌",
                    "qty": 5,
                },
            ],
        )
        returns_map = {
            ("AAPL", "NASDAQ"): {"cumulative_return_pct": 150.0, "cagr_pct": 8.5, "actual_years": 10},
            ("TSLA", "NASDAQ"): {"cumulative_return_pct": 300.0, "cagr_pct": 14.9, "actual_years": 10},
        }
        result = analyze_rebalancing(portfolio, overview, returns_map=returns_map)
        assert result.target_weighted_cagr_10y_pct is not None
        assert result.current_weighted_cagr_10y_pct is not None

    def test_no_returns_map_gives_none_cagr(self):
        """returns_map 없으면 cagr=None."""
        portfolio = _make_portfolio(
            [
                {"ticker": "AAPL", "name": "Apple", "market": "NASDAQ", "weight": 100},
            ]
        )
        overview = _make_overview(total_stock_krw=1_000_000)
        result = analyze_rebalancing(portfolio, overview, returns_map=None)
        assert result.target_weighted_cagr_10y_pct is None


# ── _build_ticker_account_map ─────────────────────────────────


class TestTickerAccountMap:
    def test_ticker_account_map_populated(self):
        """all_positions + accounts → ticker_account_map 구성."""
        acc_id = str(uuid.uuid4())
        portfolio = _make_portfolio(
            [
                {"ticker": "AAPL", "name": "Apple", "market": "NASDAQ", "weight": 100},
            ]
        )
        overview = {
            "total_assets_krw": 1_000_000,
            "total_stock_krw": 1_000_000,
            "all_positions": [
                {
                    "ticker": "AAPL",
                    "market": "NASDAQ",
                    "name": "Apple",
                    "value_krw": 1_000_000,
                    "current_price": 200_000,
                    "account_id": acc_id,
                    "account_name": "계좌1",
                    "qty": 5,
                },
            ],
            "accounts": [
                {"id": acc_id, "asset_type": "STOCK_KIS", "is_mock_mode": False},
            ],
        }
        result = analyze_rebalancing(portfolio, overview)
        assert "AAPL" in result.ticker_account_map
        assert len(result.ticker_account_map["AAPL"]) == 1
        assert result.ticker_account_map["AAPL"][0].account_id == acc_id

    def test_empty_positions_gives_empty_map(self):
        """all_positions 없으면 ticker_account_map 비어 있음."""
        portfolio = _make_portfolio(
            [
                {"ticker": "AAPL", "name": "Apple", "market": "NASDAQ", "weight": 100},
            ]
        )
        result = analyze_rebalancing(portfolio, _make_overview())
        assert result.ticker_account_map == {}


# ── include_implicit_cash 테스트 ─────────────────────────────


class TestImplicitCash:
    """analyze_rebalancing include_implicit_cash=True 동작 검증."""

    def test_implicit_cash_added_when_weights_under_100(self):
        """포트폴리오 비중 합 <100%이면 암묵적 CASH 항목이 추가된다."""
        portfolio = _make_portfolio(
            [{"ticker": "AAPL", "name": "Apple", "market": "NASDAQ", "weight": 70}],
            base_type="TOTAL_ASSETS",
        )
        overview = _make_overview(total_assets_krw=1_000_000, total_stock_krw=500_000)
        result = analyze_rebalancing(portfolio, overview, include_implicit_cash=True)
        tickers = [i.ticker for i in result.items]
        assert "CASH" in tickers
        cash = next(i for i in result.items if i.ticker == "CASH")
        # 목표 현금 비중 = 100 - 70 = 30%
        assert cash.target_weight_pct == 30.0
        # 현재 현금 = 1M - 500K = 500K → 현재 비중 = 50%
        assert cash.current_weight_pct == 50.0
        # diff_krw = 목표 300K - 현재 500K = -200K (현금 초과)
        assert cash.diff_krw == -200_000

    def test_implicit_cash_not_added_when_cash_already_in_portfolio(self):
        """포트폴리오에 이미 CASH 항목이 있으면 중복 추가 안 함."""
        portfolio = _make_portfolio(
            [
                {"ticker": "AAPL", "name": "Apple", "market": "NASDAQ", "weight": 70},
                {"ticker": "CASH", "name": "현금", "market": "KRW", "weight": 30},
            ],
            base_type="TOTAL_ASSETS",
        )
        overview = _make_overview(total_assets_krw=1_000_000, total_stock_krw=700_000)
        result = analyze_rebalancing(portfolio, overview, include_implicit_cash=True)
        cash_items = [i for i in result.items if i.ticker == "CASH"]
        assert len(cash_items) == 1

    def test_implicit_cash_not_added_when_stock_only_base(self):
        """base_type=STOCK_ONLY이면 include_implicit_cash=True여도 CASH 추가 안 함."""
        portfolio = _make_portfolio(
            [{"ticker": "AAPL", "name": "Apple", "market": "NASDAQ", "weight": 70}],
            base_type="STOCK_ONLY",
        )
        overview = _make_overview(total_assets_krw=1_000_000, total_stock_krw=700_000)
        result = analyze_rebalancing(portfolio, overview, include_implicit_cash=True)
        tickers = [i.ticker for i in result.items]
        assert "CASH" not in tickers

    def test_implicit_cash_skipped_when_no_actual_cash(self):
        """실제 예수금이 0이면 CASH 항목이 추가되지 않는다."""
        portfolio = _make_portfolio(
            [{"ticker": "AAPL", "name": "Apple", "market": "NASDAQ", "weight": 70}],
            base_type="TOTAL_ASSETS",
        )
        # total_assets == total_stock → 예수금 0
        overview = _make_overview(total_assets_krw=1_000_000, total_stock_krw=1_000_000)
        result = analyze_rebalancing(portfolio, overview, include_implicit_cash=True)
        tickers = [i.ticker for i in result.items]
        assert "CASH" not in tickers

    def test_implicit_cash_false_by_default(self):
        """기본 호출(include_implicit_cash=False)에는 CASH가 추가되지 않는다."""
        portfolio = _make_portfolio(
            [{"ticker": "AAPL", "name": "Apple", "market": "NASDAQ", "weight": 70}],
            base_type="TOTAL_ASSETS",
        )
        overview = _make_overview(total_assets_krw=1_000_000, total_stock_krw=500_000)
        result = analyze_rebalancing(portfolio, overview)
        tickers = [i.ticker for i in result.items]
        assert "CASH" not in tickers


class TestAvailableCashKrw:
    """available_cash_krw 필드 테스트."""

    def test_available_cash_is_assets_minus_stock(self):
        """예수금 = total_assets - total_stock."""
        portfolio = _make_portfolio([{"ticker": "AAPL", "name": "Apple", "market": "NASDAQ", "weight": 100}])
        overview = _make_overview(total_assets_krw=1_500_000, total_stock_krw=1_000_000)
        result = analyze_rebalancing(portfolio, overview)
        assert result.available_cash_krw == pytest.approx(500_000)

    def test_available_cash_zero_when_no_cash(self):
        """주식만 있을 때(예수금 없음) 0이어야 한다."""
        portfolio = _make_portfolio([{"ticker": "AAPL", "name": "Apple", "market": "NASDAQ", "weight": 100}])
        overview = _make_overview(total_assets_krw=1_000_000, total_stock_krw=1_000_000)
        result = analyze_rebalancing(portfolio, overview)
        assert result.available_cash_krw == pytest.approx(0)

    def test_available_cash_clamped_to_zero(self):
        """total_stock이 total_assets를 초과할 경우 0 이하로 내려가지 않는다."""
        portfolio = _make_portfolio([{"ticker": "AAPL", "name": "Apple", "market": "NASDAQ", "weight": 100}])
        overview = _make_overview(total_assets_krw=900_000, total_stock_krw=1_000_000)
        result = analyze_rebalancing(portfolio, overview)
        assert result.available_cash_krw == pytest.approx(0)

    def test_available_cash_present_in_total_assets_base_type(self):
        """TOTAL_ASSETS base_type에서도 예수금이 올바르게 반환된다."""
        portfolio = _make_portfolio(
            [{"ticker": "AAPL", "name": "Apple", "market": "NASDAQ", "weight": 80}],
            base_type="TOTAL_ASSETS",
        )
        overview = _make_overview(total_assets_krw=2_000_000, total_stock_krw=1_500_000)
        result = analyze_rebalancing(portfolio, overview)
        assert result.available_cash_krw == pytest.approx(500_000)
