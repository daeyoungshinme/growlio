"""ETF 프로필(총보수·기초지수·운용사) 조회 테스트."""

from __future__ import annotations

from unittest.mock import patch

import pytest
import requests

from app.core.cache_store import CacheStore
from app.services import etf_profile_service as svc
from app.services.etf_profile_service import parse_naver_etf_profile, parse_yahoo_etf_profile

_NAVER_360750 = {
    "itemCode": "360750",
    "itemName": "TIGER 미국S&P500",
    "issuerName": "미래에셋자산운용",
    "etfBaseIndex": "S&P 500",
    "totalFee": 0.0068,
    "chaseErrorRate": 0.09,
}


class TestParse:
    def test_naver(self):
        p = parse_naver_etf_profile(_NAVER_360750)
        assert p == {
            "ter_pct": 0.0068,
            "base_index": "S&P 500",
            "issuer": "미래에셋자산운용",
            "long_name": "TIGER 미국S&P500",
            "tracking_error_pct": 0.09,
        }

    def test_naver_empty_is_none(self):
        assert parse_naver_etf_profile({"itemCode": "005930"}) is None

    def test_naver_bad_fee(self):
        p = parse_naver_etf_profile({**_NAVER_360750, "totalFee": "N/A"})
        assert p is not None
        assert p["ter_pct"] is None

    def test_yahoo_etf(self):
        p = parse_yahoo_etf_profile(
            {"quoteType": "ETF", "netExpenseRatio": 0.0945, "fundFamily": "State Street", "longName": "SPDR S&P 500"}
        )
        assert p is not None
        assert p["ter_pct"] == 0.0945
        assert p["issuer"] == "State Street"

    def test_yahoo_fallback_expense_ratio(self):
        p = parse_yahoo_etf_profile({"quoteType": "ETF", "annualReportExpenseRatio": 0.2})
        assert p is not None
        assert p["ter_pct"] == 0.2

    def test_yahoo_stock_is_none(self):
        assert parse_yahoo_etf_profile({"quoteType": "EQUITY", "longName": "Apple"}) is None


class TestGetProfiles:
    @pytest.mark.asyncio
    async def test_routes_sources_and_caches(self):
        cache = CacheStore()
        items = [
            ("360750", "TIGER 미국S&P500", "KOSPI"),
            ("005930", "삼성전자", "KOSPI"),  # 국내 개별주 — 조회하지 않음
            ("SPY", "SPDR S&P 500", "NYSE"),
        ]
        with (
            patch.object(svc, "_fetch_naver_etf_analysis", return_value=_NAVER_360750) as mock_naver,
            patch.object(
                svc, "fetch_yf_info", return_value={"SPY": {"quoteType": "ETF", "netExpenseRatio": 0.0945}}
            ) as mock_yf,
        ):
            first = await svc.get_etf_profiles(cache, items)
            second = await svc.get_etf_profiles(cache, items)

        assert first == second
        assert mock_naver.call_count == 1
        assert mock_yf.call_count == 1
        assert first[("360750", "KOSPI")]["ter_pct"] == 0.0068
        assert first[("005930", "KOSPI")] is None
        assert first[("SPY", "NYSE")]["ter_pct"] == 0.0945

    @pytest.mark.asyncio
    async def test_network_errors_not_cached(self):
        cache = CacheStore()
        items = [("360750", "TIGER 미국S&P500", "KOSPI"), ("SPY", "SPDR S&P 500", "NYSE")]
        with (
            patch.object(svc, "_fetch_naver_etf_analysis", side_effect=requests.ConnectionError("down")) as mock_naver,
            patch.object(svc, "fetch_yf_info", return_value={}) as mock_yf,
        ):
            first = await svc.get_etf_profiles(cache, items)
            await svc.get_etf_profiles(cache, items)
        assert first == {("360750", "KOSPI"): None, ("SPY", "NYSE"): None}
        assert mock_naver.call_count == 2
        assert mock_yf.call_count == 2

    @pytest.mark.asyncio
    async def test_non_etf_result_is_cached(self):
        cache = CacheStore()
        items = [("AAPL", "Apple", "NASDAQ")]
        with patch.object(svc, "fetch_yf_info", return_value={"AAPL": {"quoteType": "EQUITY"}}) as mock_yf:
            await svc.get_etf_profiles(cache, items)
            result = await svc.get_etf_profiles(cache, items)
        assert result == {("AAPL", "NASDAQ"): None}
        assert mock_yf.call_count == 1
