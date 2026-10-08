"""index_exposure_service — 추종 지수별 비중 집계."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.services.etf_index_classifier import classify_holding
from app.services.etf_profile_service import EtfProfile
from app.services.index_exposure_service import build_index_exposure, get_index_exposure, merge_holdings


def _pos(ticker: str, market: str, name: str, value: float) -> dict:
    return {"ticker": ticker, "market": market, "name": name, "value_krw": value}


def _etf(long_name: str | None = None) -> EtfProfile:
    return EtfProfile(ter_pct=0.1, base_index=None, issuer=None, long_name=long_name, tracking_error_pct=None)


_POSITIONS = [
    _pos("SPY", "AMEX", "SPDR S&P 500 ETF Trust", 3_000_000),
    _pos("360750", "KOSPI", "TIGER 미국S&P500", 1_000_000),  # 계좌 A
    _pos("360750", "KOSPI", "TIGER 미국S&P500", 1_000_000),  # 계좌 B
    _pos("448290", "KOSPI", "TIGER 미국S&P500선물(H)", 1_000_000),
    _pos("QQQ", "NASDAQ", "Invesco QQQ Trust", 2_000_000),
    _pos("TQQQ", "NASDAQ", "ProShares UltraPro QQQ", 500_000),
    _pos("005930", "KOSPI", "삼성전자", 1_500_000),
    _pos("CASH", "KRW", "예수금", 9_999_999),
    _pos("CASH_EQUIVALENT", "CASH", "현금성", 9_999_999),
]


def _classify(holdings: list[dict]) -> dict:
    return {(h["ticker"], h["market"]): classify_holding(h["ticker"], h["market"], h["name"], None) for h in holdings}


class TestMergeHoldings:
    def test_merges_same_ticker_across_accounts_and_excludes_cash(self):
        merged = {(h["ticker"], h["market"]): h["value_krw"] for h in merge_holdings(_POSITIONS)}
        assert merged[("360750", "KOSPI")] == 2_000_000
        assert ("CASH", "KRW") not in merged
        assert ("CASH_EQUIVALENT", "CASH") not in merged

    def test_drops_zero_value(self):
        assert merge_holdings([_pos("SPY", "NYSE", "SPY", 0)]) == []


class TestBuildIndexExposure:
    def setup_method(self):
        self.holdings = merge_holdings(_POSITIONS)
        self.result = build_index_exposure(self.holdings, _classify(self.holdings))
        self.by_key = {g.key: g for g in self.result.groups}

    def test_sp500_group_combines_domestic_and_overseas(self):
        sp = self.by_key["US_SP500"]
        assert sp.value_krw == 6_000_000
        assert sp.overseas_krw == 3_000_000
        assert sp.domestic_krw == 3_000_000
        assert sp.has_hedged is True
        assert [m.ticker for m in sp.members] == ["SPY", "360750", "448290"]
        assert {m.listing for m in sp.members} == {"DOMESTIC", "OVERSEAS"}

    def test_percentages_over_stock_total_and_etf_total(self):
        assert self.result.total_stock_krw == 10_000_000
        assert self.result.total_etf_krw == 8_500_000
        assert sum(g.pct_of_stock for g in self.result.groups) == pytest.approx(100, abs=0.05)
        etf_groups = [g for g in self.result.groups if g.kind != "STOCK"]
        assert sum(g.pct_of_etf or 0 for g in etf_groups) == pytest.approx(100, abs=0.05)
        assert self.by_key["US_SP500"].pct_of_stock == 60.0
        assert self.by_key["STOCK"].pct_of_etf is None

    def test_group_order_index_then_other_then_leveraged_then_stock(self):
        assert [g.key for g in self.result.groups] == ["US_SP500", "US_NASDAQ100", "LEVERAGED", "STOCK"]
        assert self.by_key["LEVERAGED"].label == "레버리지·인버스"
        assert self.by_key["STOCK"].label == "개별주"

    def test_region_exposure_looks_through_domestic_listed_us_etfs(self):
        region = self.result.region_exposure
        # 국내상장 TIGER 미국S&P500(+선물H) 300만은 해외로, 국내는 삼성전자 150만뿐
        assert region.domestic_krw == 1_500_000
        assert region.overseas_krw == 8_500_000
        assert region.unknown_krw == 0
        assert region.domestic_krw + region.overseas_krw + region.unknown_krw == self.result.total_stock_krw
        assert {m.region for m in self.by_key["US_SP500"].members} == {"OVERSEAS"}

    def test_region_unknown_bucket(self):
        holdings = merge_holdings([_pos("161510", "KOSPI", "PLUS 고배당주", 1_000_000)])
        assert build_index_exposure(holdings, _classify(holdings)).region_exposure.unknown_krw == 1_000_000

    def test_empty_holdings(self):
        result = build_index_exposure([], {})
        assert result.groups == []
        assert result.total_stock_krw == 0


class TestGetIndexExposure:
    async def test_uses_overview_positions_and_profiles(self, mock_db, mock_cache):
        overview = {"all_positions": _POSITIONS}
        profiles = {("TQQQ", "NASDAQ"): _etf("ProShares UltraPro QQQ")}
        with (
            patch(
                "app.services.index_exposure_service.build_portfolio_overview",
                new_callable=AsyncMock,
                return_value=overview,
            ) as overview_mock,
            patch(
                "app.services.index_exposure_service.get_etf_profiles_with_status",
                new_callable=AsyncMock,
                return_value=(profiles, set()),
            ),
        ):
            account_id = uuid.uuid4()
            result = await get_index_exposure(mock_cache, mock_db, uuid.uuid4(), [account_id])
        assert overview_mock.await_args.kwargs["account_ids"] == [account_id]
        assert result.profiles_complete is True
        assert result.groups[0].key == "US_SP500"

    async def test_incomplete_when_unresolved_profile_falls_back_to_stock(self, mock_db, mock_cache):
        overview = {"all_positions": [_pos("ARKK", "AMEX", "ARK Innovation ETF", 100), _pos("SPY", "AMEX", "SPY", 100)]}
        with (
            patch(
                "app.services.index_exposure_service.build_portfolio_overview",
                new_callable=AsyncMock,
                return_value=overview,
            ),
            patch(
                "app.services.index_exposure_service.get_etf_profiles_with_status",
                new_callable=AsyncMock,
                return_value=({}, {("ARKK", "AMEX"), ("SPY", "AMEX")}),
            ),
        ):
            result = await get_index_exposure(mock_cache, mock_db, uuid.uuid4())
        # ARKK는 조회 실패로 개별주로 떨어졌으므로 불완전. SPY는 ticker 맵으로 판별돼 영향 없음.
        assert result.profiles_complete is False
        assert {g.key for g in result.groups} == {"US_SP500", "STOCK"}

    async def test_no_holdings_skips_profile_fetch(self, mock_db, mock_cache):
        with (
            patch(
                "app.services.index_exposure_service.build_portfolio_overview",
                new_callable=AsyncMock,
                return_value={"all_positions": []},
            ),
            patch(
                "app.services.index_exposure_service.get_etf_profiles_with_status", new_callable=AsyncMock
            ) as profiles_mock,
        ):
            result = await get_index_exposure(mock_cache, mock_db, uuid.uuid4())
        assert result.groups == []
        profiles_mock.assert_not_awaited()
