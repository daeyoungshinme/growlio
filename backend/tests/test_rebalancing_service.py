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
    total_assets_krw: float = 2_000_000,
    total_stock_krw: float = 1_000_000,
    all_positions: list[dict] | None = None,
) -> dict:
    return {
        "total_assets_krw": total_assets_krw,
        "total_stock_krw": total_stock_krw,
        "all_positions": all_positions or [],
    }


class TestAnalyzeRebalancingBuyCase:
    """매수 필요 케이스."""

    def test_buy_diff_and_shares(self):
        """현재 30%, 목표 50% → diff +200,000, shares 매수."""
        portfolio = _make_portfolio([
            {"ticker": "AAPL", "name": "Apple", "market": "NASDAQ", "weight": 100},
        ])
        overview = _make_overview(
            total_stock_krw=1_000_000,
            all_positions=[
                {"ticker": "AAPL", "market": "NASDAQ", "name": "Apple",
                 "value_krw": 300_000, "current_price": 250_000},
            ],
        )
        result = analyze_rebalancing(portfolio, overview)
        item = result.items[0]
        assert item.diff_krw == 700_000
        assert item.shares_to_trade == 3  # 700000 / 250000 = 2.8 → round = 3

    def test_not_held_position(self):
        """보유 없는 종목 → current_value=0, diff=target_value."""
        portfolio = _make_portfolio([
            {"ticker": "TSLA", "name": "Tesla", "market": "NASDAQ", "weight": 100},
        ])
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
        portfolio = _make_portfolio([
            {"ticker": "AAPL", "name": "Apple", "market": "NASDAQ", "weight": 50},
            {"ticker": "TSLA", "name": "Tesla", "market": "NASDAQ", "weight": 50},
        ])
        overview = _make_overview(
            total_stock_krw=1_000_000,
            all_positions=[
                {"ticker": "AAPL", "market": "NASDAQ", "name": "Apple",
                 "value_krw": 800_000, "current_price": 200_000},
                {"ticker": "TSLA", "market": "NASDAQ", "name": "Tesla",
                 "value_krw": 200_000, "current_price": 100_000},
            ],
        )
        result = analyze_rebalancing(portfolio, overview)
        aapl = next(i for i in result.items if i.ticker == "AAPL")
        tsla = next(i for i in result.items if i.ticker == "TSLA")
        assert aapl.diff_krw == -300_000  # 매도
        assert tsla.diff_krw == 300_000   # 매수
        assert aapl.shares_to_trade == -2  # -300000 / 200000 = -1.5 → round = -2


class TestCashItem:
    """CASH 항목 처리."""

    def test_cash_has_no_shares(self):
        """CASH 항목은 shares_to_trade=None."""
        portfolio = _make_portfolio([
            {"ticker": "CASH", "name": "현금", "market": "KRW", "weight": 100},
        ])
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
        overview = _make_overview(total_assets_krw=2_000_000, total_stock_krw=1_000_000, all_positions=[
            {"ticker": "AAPL", "market": "NASDAQ", "name": "Apple",
             "value_krw": 1_000_000, "current_price": 500_000},
        ])
        result = analyze_rebalancing(portfolio, overview)
        assert result.base_value_krw == 2_000_000
        item = result.items[0]
        assert item.target_value_krw == 2_000_000  # 100% of 2M


class TestUntrackedHoldings:
    """목표 포트폴리오에 없는 보유 종목 → 전량 매도 아이템으로 분류."""

    def test_untracked_appears_as_sell_item(self):
        """TSLA 보유 중인데 목표 포트폴리오에 없으면 items에 target=0 매도 아이템으로 포함."""
        portfolio = _make_portfolio([
            {"ticker": "AAPL", "name": "Apple", "market": "NASDAQ", "weight": 100},
        ])
        overview = _make_overview(
            total_stock_krw=1_000_000,
            all_positions=[
                {"ticker": "AAPL", "market": "NASDAQ", "name": "Apple",
                 "value_krw": 600_000, "current_price": 200_000},
                {"ticker": "TSLA", "market": "NASDAQ", "name": "Tesla",
                 "value_krw": 400_000, "current_price": 100_000},
            ],
        )
        result = analyze_rebalancing(portfolio, overview)
        assert result.untracked_holdings == []
        tsla = next(i for i in result.items if i.ticker == "TSLA")
        assert tsla.target_weight_pct == 0.0
        assert tsla.target_value_krw == 0.0
        assert tsla.diff_krw == -400_000  # 전량 매도
        assert tsla.shares_to_trade == -4  # -400000 / 100000 = -4

    def test_all_tracked_empty_untracked(self):
        """모든 보유 종목이 목표 포트폴리오에 있으면 untracked_holdings 비어 있음."""
        portfolio = _make_portfolio([
            {"ticker": "AAPL", "name": "Apple", "market": "NASDAQ", "weight": 100},
        ])
        overview = _make_overview(
            total_stock_krw=1_000_000,
            all_positions=[
                {"ticker": "AAPL", "market": "NASDAQ", "name": "Apple",
                 "value_krw": 1_000_000, "current_price": 200_000},
            ],
        )
        result = analyze_rebalancing(portfolio, overview)
        assert result.untracked_holdings == []


class TestShareCalculationEdgeCases:
    """주수 계산 엣지 케이스."""

    def test_zero_price_no_shares(self):
        """current_price=0 이면 shares_to_trade=None."""
        portfolio = _make_portfolio([
            {"ticker": "AAPL", "name": "Apple", "market": "NASDAQ", "weight": 100},
        ])
        overview = _make_overview(
            total_stock_krw=1_000_000,
            all_positions=[
                {"ticker": "AAPL", "market": "NASDAQ", "name": "Apple",
                 "value_krw": 500_000, "current_price": 0},
            ],
        )
        result = analyze_rebalancing(portfolio, overview)
        assert result.items[0].shares_to_trade is None

    def test_no_positions_zero_base(self):
        """보유 자산이 없어 base_krw=0 이면 current_weight_pct=0."""
        portfolio = _make_portfolio([
            {"ticker": "AAPL", "name": "Apple", "market": "NASDAQ", "weight": 100},
        ])
        overview = _make_overview(total_stock_krw=0, all_positions=[])
        result = analyze_rebalancing(portfolio, overview)
        assert result.base_value_krw == 0
        assert result.items[0].current_weight_pct == 0.0


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
