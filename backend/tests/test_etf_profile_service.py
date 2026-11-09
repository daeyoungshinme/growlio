"""ETF 프로필(총보수·기초지수·운용사) 조회 테스트."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest
import requests

from app.core.cache_store import CacheStore
from app.services.etf import etf_profile_service as svc
from app.services.etf.etf_profile_service import parse_naver_etf_profile, parse_yahoo_etf_profile

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
            patch.object(svc, "fetch_naver_etf_analysis", return_value=_NAVER_360750) as mock_naver,
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
            patch.object(svc, "fetch_naver_etf_analysis", side_effect=requests.ConnectionError("down")) as mock_naver,
            patch.object(svc, "fetch_yf_info", return_value={}) as mock_yf,
        ):
            first = await svc.get_etf_profiles(cache, items)
            await svc.get_etf_profiles(cache, items)
        assert first == {("360750", "KOSPI"): None, ("SPY", "NYSE"): None}
        assert mock_naver.call_count == 2
        assert mock_yf.call_count == 2

    @pytest.mark.asyncio
    async def test_empty_info_cached_as_missing_when_other_symbols_resolved(self):
        """plans/118 B2: 다른 심볼은 응답을 받은 배치에서 연속으로 빈 응답이면 '데이터 없음'으로 캐싱해 확정한다 —
        상장폐지 종목 하나 때문에 겹침 분석이 매 요청 캐시 없이 다시 돌지 않게."""
        cache = CacheStore()
        items = [("SPY", "SPDR S&P 500", "NYSE"), ("DEAD", "Delisted", "NASDAQ")]
        with patch.object(
            svc, "fetch_yf_info", return_value={"SPY": {"quoteType": "ETF", "netExpenseRatio": 0.0945}}
        ) as mock_yf:
            runs = [await svc.get_etf_profiles_with_status(cache, items) for _ in range(4)]
        # 1·2번째 빈 응답은 일시 실패일 수 있어 미확정, 3번째에 '데이터 없음'으로 캐싱 → 4번째는 조회하지 않는다
        assert [r[1] for r in runs] == [{("DEAD", "NASDAQ")}, {("DEAD", "NASDAQ")}, set(), set()]
        assert runs[3][0][("DEAD", "NASDAQ")] is None
        assert mock_yf.call_count == 3

    @pytest.mark.asyncio
    async def test_open_circuit_does_not_advance_empty_streak(self):
        """plans/119 B2: 서킷이 열린 동안의 빈 응답은 세지 않는다 — 한 번 센 정상 ETF가 장애 중 요청으로
        '데이터 없음'에 닿지 않는다. 정상 응답이 오면 연속 횟수도 리셋한다."""
        cache = CacheStore()
        items = [("SPY", "SPDR S&P 500", "NYSE"), ("QQQ", "Invesco QQQ", "NASDAQ")]
        alive = {"SPY": {"quoteType": "ETF", "netExpenseRatio": 0.0945}}
        with patch.object(svc, "fetch_yf_info", return_value=alive):
            await svc.get_etf_profiles_with_status(cache, items)  # QQQ 빈 응답 1회(n=1)
        assert await svc.get_cached_json(cache, svc._empty_streak_key("QQQ", "NASDAQ")) == {"n": 1}

        with (
            patch.object(svc.yahoo_circuit, "is_available", return_value=False),
            patch.object(svc, "fetch_yf_info", return_value={}),
        ):
            for _ in range(3):
                _, unresolved = await svc.get_etf_profiles_with_status(cache, items)
                assert ("QQQ", "NASDAQ") in unresolved
        assert await svc.get_cached_json(cache, svc._empty_streak_key("QQQ", "NASDAQ")) == {"n": 1}

        qqq = {"QQQ": {"quoteType": "ETF", "netExpenseRatio": 0.2}}
        with patch.object(svc, "fetch_yf_info", return_value=qqq):
            profiles, _ = await svc.get_etf_profiles_with_status(cache, items)
        assert profiles[("QQQ", "NASDAQ")]["ter_pct"] == 0.2
        assert await svc.get_cached_json(cache, svc._empty_streak_key("QQQ", "NASDAQ")) is None

    @pytest.mark.asyncio
    async def test_non_etf_result_is_cached(self):
        cache = CacheStore()
        items = [("AAPL", "Apple", "NASDAQ")]
        with patch.object(svc, "fetch_yf_info", return_value={"AAPL": {"quoteType": "EQUITY"}}) as mock_yf:
            await svc.get_etf_profiles(cache, items)
            result = await svc.get_etf_profiles(cache, items)
        assert result == {("AAPL", "NASDAQ"): None}
        assert mock_yf.call_count == 1

    @pytest.mark.asyncio
    async def test_definitive_non_etf_uses_long_ttl(self):
        """Yahoo가 quoteType으로 ETF 아님을 명시하면 바뀔 일이 없어 프로필과 같은 장기 TTL로 캐싱한다."""
        with (
            patch.object(svc, "fetch_yf_info", return_value={"AAPL": {"quoteType": "EQUITY"}}),
            patch.object(svc, "set_cached_json", AsyncMock()) as mock_set,
        ):
            await svc.get_etf_profiles(CacheStore(), [("AAPL", "Apple", "NASDAQ")])
        assert mock_set.await_args.args[3] == svc.TTL_ETF_PROFILE

    @pytest.mark.asyncio
    async def test_deadline_keeps_partial_results(self):
        """전체 상한을 넘기면 그때까지 받은 프로필만 반환한다 — 느린 소스가 엔드포인트를 붙잡지 않는다."""

        def slow_info(_symbols):
            time.sleep(0.3)
            return {"SPY": {"quoteType": "ETF", "netExpenseRatio": 0.0945}}

        items = [("360750", "TIGER 미국S&P500", "KOSPI"), ("SPY", "SPDR S&P 500", "NYSE")]
        with (
            patch.object(svc, "_FETCH_DEADLINE_SECONDS", 0.1),
            patch.object(svc, "fetch_naver_etf_analysis", return_value=_NAVER_360750),
            patch.object(svc, "fetch_yf_info", side_effect=slow_info),
        ):
            result = await svc.get_etf_profiles(CacheStore(), items)
        assert result[("360750", "KOSPI")]["ter_pct"] == 0.0068
        assert result[("SPY", "NYSE")] is None

    @pytest.mark.asyncio
    async def test_with_status_reports_unresolved_keys(self):
        """네트워크 실패 키만 unresolved — 조회 생략(국내 개별주)·확정 non-ETF·캐시 적중은 포함하지 않는다."""
        cache = CacheStore()
        items = [
            ("360750", "TIGER 미국S&P500", "KOSPI"),  # Naver 실패
            ("005930", "삼성전자", "KOSPI"),  # 조회 생략
            ("AAPL", "Apple", "NASDAQ"),  # 확정 non-ETF
            ("SPY", "SPDR S&P 500", "NYSE"),  # Yahoo 빈 응답
        ]
        with (
            patch.object(svc, "fetch_naver_etf_analysis", side_effect=requests.ConnectionError("down")),
            patch.object(svc, "fetch_yf_info", return_value={"AAPL": {"quoteType": "EQUITY"}}),
        ):
            profiles, unresolved = await svc.get_etf_profiles_with_status(cache, items)
        assert unresolved == {("360750", "KOSPI"), ("SPY", "NYSE")}
        assert all(v is None for v in profiles.values())
