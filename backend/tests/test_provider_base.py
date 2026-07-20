"""app/providers/base.py::raw_to_position 단위 테스트 — ticker/market 정규화."""

from __future__ import annotations

from app.providers.base import raw_to_position


class TestRawToPositionNormalization:
    def test_krw_position_strips_and_uppercases_ticker_and_market(self):
        """키움처럼 고정폭 필드로 트레일링 공백이 섞여 오는 경우에도 정규화되어야 한다."""
        raw = {
            "ticker": "005930  ",
            "name": "삼성전자",
            "market": "kospi",
            "qty": 10,
            "avg_price": 70000.0,
            "current_price": 75000.0,
            "value_krw": 750000.0,
            "currency": "KRW",
        }

        pos = raw_to_position(raw, usd_krw_rate=1300.0)

        assert pos.ticker == "005930"
        assert pos.market == "KOSPI"

    def test_usd_position_strips_and_uppercases_ticker_and_market(self):
        """해외 원장잔고(ust21070) stk_cd가 12자리 고정폭이라 트레일링 공백이 올 수 있다."""
        raw = {
            "ticker": "qqq         ",  # 12자리 고정폭 흉내
            "name": "Invesco QQQ Trust",
            "market": " nasdaq ",
            "qty": 5,
            "avg_price": 350.0,
            "current_price": 400.0,
            "value_usd": 2000.0,
            "currency": "USD",
        }

        pos = raw_to_position(raw, usd_krw_rate=1300.0)

        assert pos.ticker == "QQQ"
        assert pos.market == "NASDAQ"

    def test_already_normalized_ticker_market_unchanged(self):
        raw = {
            "ticker": "AAPL",
            "name": "Apple",
            "market": "NASDAQ",
            "qty": 3,
            "avg_price": 150.0,
            "current_price": 200.0,
            "value_usd": 600.0,
            "currency": "USD",
        }

        pos = raw_to_position(raw, usd_krw_rate=1300.0)

        assert pos.ticker == "AAPL"
        assert pos.market == "NASDAQ"

    def test_krw_conversion_math_unaffected_by_normalization(self):
        raw = {
            "ticker": "005930",
            "name": "삼성전자",
            "market": "KOSPI",
            "qty": 10,
            "avg_price": 70000.0,
            "current_price": 75000.0,
            "value_krw": 750000.0,
            "currency": "KRW",
        }

        pos = raw_to_position(raw, usd_krw_rate=1300.0)

        assert pos.currency == "KRW"
        assert pos.qty == 10
        assert pos.avg_price == 70000.0
        assert pos.current_price == 75000.0
        assert pos.value_krw == 750000.0
        assert pos.avg_price_usd is None
        assert pos.usd_rate is None

    def test_usd_conversion_math_unaffected_by_normalization(self):
        raw = {
            "ticker": "QQQ",
            "name": "Invesco QQQ Trust",
            "market": "NASDAQ",
            "qty": 5,
            "avg_price": 350.0,
            "current_price": 400.0,
            "value_usd": 2000.0,
            "currency": "USD",
        }

        pos = raw_to_position(raw, usd_krw_rate=1300.0)

        assert pos.currency == "USD"
        assert pos.qty == 5
        assert pos.avg_price == 350.0 * 1300.0
        assert pos.current_price == 400.0 * 1300.0
        assert pos.avg_price_usd == 350.0
        assert pos.usd_rate == 1300.0
