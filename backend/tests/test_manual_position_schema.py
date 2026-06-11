"""ManualPosition Pydantic 스키마 유효성 검증 테스트."""
from __future__ import annotations

import pytest
from pydantic import ValidationError


def _valid_position(**overrides):
    base = {
        "ticker": "AAPL",
        "name": "Apple Inc",
        "market": "NASDAQ",
        "qty": 10.0,
        "avg_price": 150.0,
    }
    base.update(overrides)
    return base


class TestManualPositionSchema:
    def _make(self, **kwargs):
        from app.schemas.asset import ManualPosition
        return ManualPosition(**{**_valid_position(), **kwargs})

    def _raises(self, **kwargs):
        from app.schemas.asset import ManualPosition
        with pytest.raises(ValidationError):
            ManualPosition(**{**_valid_position(), **kwargs})

    def test_valid_position_creates_successfully(self):
        pos = self._make()
        assert pos.ticker == "AAPL"
        assert pos.name == "Apple Inc"

    def test_ticker_uppercased(self):
        pos = self._make(ticker="aapl")
        assert pos.ticker == "AAPL"

    def test_name_whitespace_stripped(self):
        pos = self._make(name="  Samsung  ")
        assert pos.name == "Samsung"

    def test_name_empty_raises(self):
        self._raises(name="")

    def test_name_whitespace_only_raises(self):
        self._raises(name="   ")

    def test_name_too_long_raises(self):
        self._raises(name="A" * 201)

    def test_ticker_empty_raises(self):
        self._raises(ticker="")

    def test_ticker_too_long_raises(self):
        self._raises(ticker="X" * 21)

    def test_qty_zero_raises(self):
        self._raises(qty=0)

    def test_qty_negative_raises(self):
        self._raises(qty=-1)

    def test_qty_over_max_raises(self):
        self._raises(qty=1_000_001)

    def test_avg_price_zero_raises(self):
        self._raises(avg_price=0)

    def test_avg_price_usd_negative_raises(self):
        self._raises(avg_price_usd=-1.0)

    def test_usd_rate_out_of_range_raises(self):
        self._raises(usd_rate=0)
        self._raises(usd_rate=10000)

    def test_invalid_market_raises(self):
        self._raises(market="INVALID_EXCHANGE")

    def test_optional_fields_none(self):
        pos = self._make(avg_price_usd=None, usd_rate=None, current_price=None)
        assert pos.avg_price_usd is None
