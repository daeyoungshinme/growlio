"""order_builder.py의 시장 분류 헬퍼(market_group/split_orders_by_market) 단위 테스트.

NYSE 시간대 AUTO 지원(leg를 KR/US로 분리)의 기반이 되는 순수 함수 — 국내/해외 혼재 주문
목록을 정확히 분리하지 못하면 leg 분리·게이팅 전체가 잘못된다.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.services.rebalancing.order_builder import market_group, split_orders_by_market


def _order(ticker: str, market: str, side: str = "BUY") -> SimpleNamespace:
    return SimpleNamespace(ticker=ticker, market=market, side=side)


class TestMarketGroup:
    def test_kospi_is_kr(self):
        assert market_group("KOSPI") == "KR"

    def test_kosdaq_is_kr(self):
        assert market_group("KOSDAQ") == "KR"

    def test_nasdaq_is_us(self):
        assert market_group("NASDAQ") == "US"

    def test_nyse_is_us(self):
        assert market_group("NYSE") == "US"

    def test_amex_is_us(self):
        assert market_group("AMEX") == "US"

    def test_lowercase_market_still_classified(self):
        assert market_group("nasdaq") == "US"
        assert market_group("kospi") == "KR"


class TestSplitOrdersByMarket:
    def test_splits_mixed_kr_us_orders(self):
        orders = [
            _order("005930", "KOSPI"),
            _order("AAPL", "NASDAQ"),
            _order("000660", "KOSDAQ"),
            _order("TSLA", "NASDAQ"),
        ]

        kr_orders, us_orders = split_orders_by_market(orders)

        assert [o.ticker for o in kr_orders] == ["005930", "000660"]
        assert [o.ticker for o in us_orders] == ["AAPL", "TSLA"]

    def test_all_kr_returns_empty_us_group(self):
        orders = [_order("005930", "KOSPI"), _order("000660", "KOSDAQ")]

        kr_orders, us_orders = split_orders_by_market(orders)

        assert len(kr_orders) == 2
        assert us_orders == []

    def test_empty_input_returns_two_empty_lists(self):
        kr_orders, us_orders = split_orders_by_market([])

        assert kr_orders == []
        assert us_orders == []
