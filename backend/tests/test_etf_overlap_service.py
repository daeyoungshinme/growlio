"""후보 ETF 중복(같은 지수/사실상 같은 움직임) 분석 + 총보수 비교 테스트."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import numpy as np
import pandas as pd
import pytest

from app.core.cache_store import CacheStore
from app.services import etf_overlap_service as svc
from app.services.etf_overlap_service import _Item, build_items, find_overlap_groups, weekly_returns_frame


def _profile(ter: float | None = None, base_index: str | None = None, long_name: str | None = None) -> dict:
    return {
        "ter_pct": ter,
        "base_index": base_index,
        "issuer": None,
        "long_name": long_name,
        "tracking_error_pct": None,
    }


def _series(returns: np.ndarray, start: str = "2025-01-01") -> pd.Series:
    idx = pd.bdate_range(start, periods=len(returns) + 1)
    prices = 100 * np.cumprod(np.concatenate([[1.0], 1 + returns]))
    return pd.Series(prices, index=idx)


@pytest.fixture
def base_returns() -> np.ndarray:
    rng = np.random.default_rng(42)
    return rng.normal(0.0005, 0.01, 260)


def _weekly(**series: pd.Series) -> pd.DataFrame:
    return weekly_returns_frame(series)


class TestSameIndex:
    def test_held_vs_candidate_same_index_with_cheapest(self):
        items = [
            _Item("360200", "ACE 미국S&P500", "KOSPI", held=True, profile=_profile(0.0047, "S&P 500")),
            _Item("360750", "TIGER 미국S&P500", "KOSPI", candidate=True, profile=_profile(0.0068, "S&P 500")),
        ]
        groups = find_overlap_groups(items, None)
        assert len(groups) == 1
        g = groups[0]
        assert g.reasons == ["SAME_INDEX"]
        assert g.cheapest_ticker == "360200"
        assert g.ter_gap_pct == pytest.approx(0.0021)
        assert {m.ticker for m in g.members} == {"360200", "360750"}

    def test_candidates_across_listing_not_compared_unless_held(self):
        """SPY(해외전용 계좌용)와 TIGER 미국S&P500(ISA용)을 함께 등록하는 건 의도된 조합."""
        items = [
            _Item("SPY", "SPDR S&P 500", "NYSE", candidate=True),
            _Item("360750", "TIGER 미국S&P500", "KOSPI", candidate=True),
        ]
        assert find_overlap_groups(items, None) == []

    def test_cross_listing_compared_when_one_is_held(self):
        items = [
            _Item("SPY", "SPDR S&P 500", "NYSE", held=True),
            _Item("360750", "TIGER 미국S&P500", "KOSPI", candidate=True),
        ]
        groups = find_overlap_groups(items, None)
        assert len(groups) == 1

    def test_held_only_pairs_ignored(self):
        items = [
            _Item("360200", "ACE 미국S&P500", "KOSPI", held=True),
            _Item("360750", "TIGER 미국S&P500", "KOSPI", held=True),
        ]
        assert find_overlap_groups(items, None) == []

    def test_leveraged_and_distribution_frequency_excluded(self):
        items = [
            _Item("069500", "KODEX 200", "KOSPI", held=True),
            _Item("122630", "KODEX 레버리지", "KOSPI", candidate=True, profile=_profile(0.64, "코스피 200")),
            _Item("458730", "TIGER 미국배당다우존스", "KOSPI", held=True),
            _Item(
                "446720",
                "SOL 미국배당다우존스(H)",
                "KOSPI",
                candidate=True,
                distribution_frequency="MONTHLY",
            ),
        ]
        assert find_overlap_groups(items, None) == []

    def test_raw_base_index_match(self):
        """정규식 라벨이 없는 지수는 기초지수명 원문(공백 무시)으로 비교한다."""
        items = [
            _Item("091160", "KODEX 반도체", "KOSPI", candidate=True, profile=_profile(0.45, "KRX 반도체")),
            _Item("091230", "TIGER 반도체", "KOSPI", candidate=True, profile=_profile(0.46, "KRX반도체")),
        ]
        groups = find_overlap_groups(items, None)
        assert len(groups) == 1
        assert groups[0].cheapest_ticker == "091160"

    def test_nasdaq_hyphen_base_index(self):
        items = [
            _Item("133690", "TIGER 미국나스닥100", "KOSPI", held=True),
            _Item("379810", "KODEX 미국나스닥", "KOSPI", candidate=True, profile=_profile(0.0062, "NASDAQ-100")),
        ]
        assert len(find_overlap_groups(items, None)) == 1

    def test_equal_ter_has_no_cheapest(self):
        items = [
            _Item("A", "TIGER 미국S&P500", "KOSPI", held=True, profile=_profile(0.01)),
            _Item("B", "KODEX 미국S&P500", "KOSPI", candidate=True, profile=_profile(0.01)),
        ]
        g = find_overlap_groups(items, None)[0]
        assert g.cheapest_ticker is None
        assert g.ter_gap_pct is None


class TestHighCorrelation:
    def test_same_movement_different_labels(self, base_returns):
        rng = np.random.default_rng(1)
        items = [
            _Item("AAA", "Alpha Growth", "NYSE", held=True, profile=_profile(0.2)),
            _Item("BBB", "Beta Growth", "NYSE", candidate=True, profile=_profile(0.05)),
        ]
        weekly = _weekly(
            AAA=_series(base_returns),
            BBB=_series(base_returns + rng.normal(0, 0.0005, len(base_returns))),
        )
        groups = find_overlap_groups(items, weekly)
        assert len(groups) == 1
        assert groups[0].reasons == ["HIGH_CORR"]
        assert groups[0].max_correlation is not None
        assert groups[0].max_correlation >= 0.97
        assert groups[0].cheapest_ticker == "BBB"

    def test_leverage_not_flagged_despite_correlation(self, base_returns):
        items = [
            _Item("AAA", "Alpha", "NYSE", held=True),
            _Item("BBB", "Beta", "NYSE", candidate=True),
        ]
        weekly = _weekly(AAA=_series(base_returns), BBB=_series(base_returns * 2))
        assert find_overlap_groups(items, weekly) == []

    def test_uncorrelated_not_flagged(self, base_returns):
        rng = np.random.default_rng(7)
        items = [_Item("AAA", "Alpha", "NYSE", held=True), _Item("BBB", "Beta", "NYSE", candidate=True)]
        weekly = _weekly(AAA=_series(base_returns), BBB=_series(rng.normal(0.0005, 0.01, 260)))
        assert find_overlap_groups(items, weekly) == []

    def test_insufficient_history(self, base_returns):
        items = [_Item("AAA", "Alpha", "NYSE", held=True), _Item("BBB", "Beta", "NYSE", candidate=True)]
        short = base_returns[:60]  # ~12주 < 26주
        weekly = _weekly(AAA=_series(short), BBB=_series(short))
        assert find_overlap_groups(items, weekly) == []

    def test_cross_listing_skips_correlation(self, base_returns):
        items = [_Item("AAA", "Alpha", "NYSE", held=True), _Item("000001", "베타", "KOSPI", candidate=True)]
        weekly = _weekly(**{"AAA": _series(base_returns), "000001.KS": _series(base_returns)})
        assert find_overlap_groups(items, weekly) == []

    def test_union_find_chains_three_members(self, base_returns):
        items = [
            _Item("360200", "ACE 미국S&P500", "KOSPI", held=True),
            _Item("360750", "TIGER 미국S&P500", "KOSPI", candidate=True),
            _Item("999999", "무명 대형주", "KOSPI", candidate=True),
        ]
        weekly = _weekly(
            **{
                "360750.KS": _series(base_returns),
                "999999.KS": _series(base_returns),
            }
        )
        groups = find_overlap_groups(items, weekly)
        assert len(groups) == 1
        assert set(groups[0].reasons) == {"SAME_INDEX", "HIGH_CORR"}
        assert len(groups[0].members) == 3


class TestBuildItems:
    def test_merges_held_and_candidate_and_drops_cash(self):
        items = build_items(
            [
                {"ticker": "360750", "name": "TIGER 미국S&P500", "market": "KOSPI", "asset_class": "EQUITY"},
                {"ticker": "153130", "name": "KODEX 단기채권", "market": "KOSPI", "asset_class": "CASH"},
            ],
            [("360750", "TIGER 미국S&P500", "KOSPI"), ("005930", "삼성전자", "KOSPI")],
        )
        by_key = {i.key: i for i in items}
        assert ("153130", "KOSPI") not in by_key
        assert by_key[("360750", "KOSPI")].held
        assert by_key[("360750", "KOSPI")].candidate
        assert by_key[("005930", "KOSPI")].held
        assert not by_key[("005930", "KOSPI")].candidate


class TestAnalyze:
    @pytest.mark.asyncio
    async def test_no_candidates_returns_empty(self):
        result = await svc.analyze_candidate_overlap(None, [], [("360750", "TIGER 미국S&P500", "KOSPI")])
        assert result.groups == []
        assert result.profiles == []

    @pytest.mark.asyncio
    async def test_end_to_end_with_cache(self, base_returns):
        cache = CacheStore()
        candidates = [{"ticker": "360750", "name": "TIGER 미국S&P500", "market": "KOSPI"}]
        held = [("360200", "ACE 미국S&P500", "KOSPI"), ("005930", "삼성전자", "KOSPI")]
        profiles = {
            ("360750", "KOSPI"): _profile(0.0068, "S&P 500"),
            ("360200", "KOSPI"): _profile(0.0047, "S&P 500"),
            ("005930", "KOSPI"): None,
        }
        close = {"360750.KS": _series(base_returns), "360200.KS": _series(base_returns)}
        with (
            patch.object(svc, "get_etf_profiles", AsyncMock(return_value=profiles)) as mock_profiles,
            patch.object(svc, "fetch_yf_close_series", return_value=close) as mock_close,
        ):
            first = await svc.analyze_candidate_overlap(cache, candidates, held)
            second = await svc.analyze_candidate_overlap(cache, candidates, held)

        assert first == second
        assert mock_profiles.await_count == 1
        assert mock_close.call_count == 1
        # 개별주(삼성전자)는 프로필·지수 판별이 없어 시세 조회 대상에서 빠진다
        assert sorted(mock_close.call_args.args[0]) == ["360200.KS", "360750.KS"]
        assert len(first.groups) == 1
        assert {p.ticker for p in first.profiles} == {"360750", "360200"}
        assert first.price_data_available

    @pytest.mark.asyncio
    async def test_price_failure_not_cached(self):
        cache = CacheStore()
        candidates = [{"ticker": "360750", "name": "TIGER 미국S&P500", "market": "KOSPI"}]
        held = [("360200", "ACE 미국S&P500", "KOSPI")]
        with (
            patch.object(svc, "get_etf_profiles", AsyncMock(return_value={})),
            patch.object(svc, "fetch_yf_close_series", return_value={}) as mock_close,
        ):
            first = await svc.analyze_candidate_overlap(cache, candidates, held)
            await svc.analyze_candidate_overlap(cache, candidates, held)
        assert not first.price_data_available
        assert len(first.groups) == 1  # SAME_INDEX는 시세 없이도 판정
        assert mock_close.call_count == 2
