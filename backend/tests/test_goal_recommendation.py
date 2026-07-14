"""goal_return_solver.py / goal_recommendation_service.py 단위 테스트."""

from __future__ import annotations

import random
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.goal_recommendation_service import (
    _apply_index_region_preference,
    _months_until_year_end,
    _optimize_goal_portfolio,
    _persist_added_candidates,
    existing_items_from_positions,
    get_goal_recommendation,
    get_horizon_recommendations,
)
from app.services.goal_return_solver import solve_required_annual_return_pct
from app.services.recommendation_universe import (
    MAX_GOAL_CANDIDATE_TICKERS,
    RECOMMENDATION_UNIVERSE,
    guess_asset_class,
    resolve_index_region,
)


class TestSolveRequiredAnnualReturnPct:
    def test_low_return_sufficient_when_deposits_dominate(self):
        r = solve_required_annual_return_pct(pv=0, pmt=1000, n_months=100, goal_amount=90_000)
        assert r is not None
        assert r < 5

    def test_known_case_matches_fv_formula(self):
        pv, pmt, n = 10_000_000.0, 500_000.0, 120
        annual_r = 0.06
        r_m = annual_r / 12
        fv = pv * (1 + r_m) ** n + pmt * (((1 + r_m) ** n - 1) / r_m)

        solved = solve_required_annual_return_pct(pv, pmt, n, fv)

        assert solved is not None
        assert solved == pytest.approx(6.0, abs=0.05)

    def test_unreachable_goal_returns_none(self):
        r = solve_required_annual_return_pct(pv=1.0, pmt=0.0, n_months=1, goal_amount=1_000_000_000.0)
        assert r is None


class TestMonthsUntilYearEnd:
    def test_future_year_is_positive(self):
        from datetime import date

        assert _months_until_year_end(date.today().year + 5) > 0

    def test_past_year_is_non_positive(self):
        from datetime import date

        assert _months_until_year_end(date.today().year - 5) <= 0


class TestOptimizeGoalPortfolio:
    def test_insufficient_candidates_returns_note(self):
        items, expected, note = _optimize_goal_portfolio(
            symbols=["A"],
            tickers=[("A", "A Inc", "NASDAQ")],
            cagr_pct=[10.0],
            returns_map={"A": [0.001] * 252},
            required_return_pct=5.0,
        )
        assert items == []
        assert expected is None
        assert note is not None

    def test_unreachable_required_return_returns_note(self):
        items, expected, note = _optimize_goal_portfolio(
            symbols=["A", "B"],
            tickers=[("A", "A Inc", "NASDAQ"), ("B", "B Inc", "NASDAQ")],
            cagr_pct=[5.0, 6.0],
            returns_map={"A": [0.001] * 252, "B": [0.0012] * 252},
            required_return_pct=50.0,
        )
        assert items == []
        assert expected is None
        assert "달성하기 어렵습니다" in note

    def test_feasible_case_produces_weights_summing_to_100(self):
        random.seed(1)
        r_a = [random.gauss(0.0006, 0.008) for _ in range(252)]
        r_b = [random.gauss(0.0003, 0.004) for _ in range(252)]

        items, expected, note = _optimize_goal_portfolio(
            symbols=["A", "B"],
            tickers=[("A", "고성장 ETF", "NASDAQ"), ("B", "저변동 ETF", "NASDAQ")],
            cagr_pct=[15.0, 4.0],
            returns_map={"A": r_a, "B": r_b},
            required_return_pct=8.0,
        )

        assert note is None
        assert items
        assert sum(i["weight"] for i in items) == pytest.approx(100.0, abs=0.1)
        assert expected >= 8.0 - 0.01

    def test_max_weight_param_caps_dominant_asset(self):
        """저변동 종목으로의 쏠림을 max_weight 파라미터로 제한할 수 있다(n=4 → 1/n=25%와 동일한 상한)."""
        random.seed(3)
        returns_map = {
            "A": [random.gauss(0.0002, 0.0005) for _ in range(252)],  # 매우 저변동 → 무제한이면 쏠림
            "B": [random.gauss(0.0004, 0.01) for _ in range(252)],
            "C": [random.gauss(0.0004, 0.01) for _ in range(252)],
            "D": [random.gauss(0.0004, 0.01) for _ in range(252)],
        }
        tickers = [(t, t, "NASDAQ") for t in ("A", "B", "C", "D")]

        items, _, note = _optimize_goal_portfolio(
            symbols=["A", "B", "C", "D"],
            tickers=tickers,
            cagr_pct=[3.0, 3.0, 3.0, 3.0],
            returns_map=returns_map,
            required_return_pct=2.0,
            max_weight=0.25,
        )

        assert note is None
        assert items
        assert max(i["weight"] for i in items) <= 25.0 + 0.5

    def test_risk_tolerance_frontier_raises_expected_return_monotonically(self):
        """CONSERVATIVE는 기존과 동일한 부등식 제약(순수 최소분산)을 쓰고, BALANCED/AGGRESSIVE는
        자연 수익률↔최대 달성가능 수익률 사이를 성향 비율로 보간한 지점을 등식 제약으로 고정하므로
        자연 최적해가 이미 목표를 넘는 경우에도 성향에 따라 항상 기대수익률·비중이 달라져야 한다."""
        random.seed(4)
        returns_map = {
            "A": [random.gauss(0.0003, 0.001) for _ in range(252)],  # 저변동
            "B": [random.gauss(0.0006, 0.006) for _ in range(252)],  # 중변동
            "C": [random.gauss(0.0006, 0.02) for _ in range(252)],  # 고변동
        }
        tickers = [("A", "A", "NASDAQ"), ("B", "B", "NASDAQ"), ("C", "C", "NASDAQ")]
        cagr_pct = [3.0, 6.0, 15.0]

        conservative_items, conservative_expected, conservative_note = _optimize_goal_portfolio(
            symbols=["A", "B", "C"],
            tickers=tickers,
            cagr_pct=cagr_pct,
            returns_map=returns_map,
            required_return_pct=5.0,
            risk_tolerance="CONSERVATIVE",
        )
        balanced_items, balanced_expected, balanced_note = _optimize_goal_portfolio(
            symbols=["A", "B", "C"],
            tickers=tickers,
            cagr_pct=cagr_pct,
            returns_map=returns_map,
            required_return_pct=5.0,
            risk_tolerance="BALANCED",
        )
        aggressive_items, aggressive_expected, aggressive_note = _optimize_goal_portfolio(
            symbols=["A", "B", "C"],
            tickers=tickers,
            cagr_pct=cagr_pct,
            returns_map=returns_map,
            required_return_pct=5.0,
            risk_tolerance="AGGRESSIVE",
        )

        assert conservative_items
        assert balanced_items
        assert aggressive_items
        assert conservative_note is None
        assert balanced_note is None
        assert aggressive_note is None
        assert conservative_expected < balanced_expected < aggressive_expected
        # 기본 40% 캡 하 달성 가능한 최대 가중평균 CAGR(0.4*15+0.4*6+0.2*3=9.0)을 넘지 않는다.
        assert aggressive_expected <= 9.0 + 0.05

    def test_risk_tolerance_no_spread_returns_note(self):
        """후보 종목의 CAGR이 전부 동일하면 리스크 성향을 바꿔도 반영할 여지가 없으므로,
        note로 안내하고(크래시/실패 없이) 여전히 추천을 반환해야 한다."""
        random.seed(5)
        returns_map = {
            "A": [random.gauss(0.0003, 0.006) for _ in range(252)],
            "B": [random.gauss(0.0006, 0.02) for _ in range(252)],
        }
        tickers = [("A", "A", "NASDAQ"), ("B", "B", "NASDAQ")]

        items, expected, note = _optimize_goal_portfolio(
            symbols=["A", "B"],
            tickers=tickers,
            cagr_pct=[7.0, 7.0],
            returns_map=returns_map,
            required_return_pct=5.0,
            risk_tolerance="AGGRESSIVE",
        )

        assert items
        assert note is not None
        assert "차이가 크지 않습니다" in note
        assert expected == pytest.approx(7.0, abs=0.05)

    def test_equity_floor_forces_minimum_equity_weight(self):
        """is_equity+equity_floor를 주면 저변동 비주식 종목으로 쏠리지 않고 주식 비중 하한이 강제된다."""
        random.seed(6)
        returns_map = {
            "SAFE": [random.gauss(0.0001, 0.0005) for _ in range(252)],  # 매우 저변동 — 무제한이면 쏠림
            "STOCK": [random.gauss(0.0004, 0.01) for _ in range(252)],
        }
        tickers = [("SAFE", "안전자산", "KOSPI"), ("STOCK", "주식", "KOSPI")]

        items, _, note = _optimize_goal_portfolio(
            symbols=["SAFE", "STOCK"],
            tickers=tickers,
            cagr_pct=[3.0, 8.0],
            returns_map=returns_map,
            required_return_pct=-50.0,
            is_equity=[False, True],
            equity_floor=0.8,
        )

        assert note is None
        stock_weight = next(i["weight"] for i in items if i["ticker"] == "STOCK")
        assert stock_weight == pytest.approx(80.0, abs=1.0)

    def test_equity_floor_ignored_when_all_candidates_are_equity(self):
        """후보가 전부 주식이면 비교 대상이 없어 제약이 무의미하므로 무시되고 일반 최소분산으로 계산된다."""
        random.seed(7)
        returns_map = {
            "A": [random.gauss(0.0002, 0.002) for _ in range(252)],
            "B": [random.gauss(0.0004, 0.01) for _ in range(252)],
        }
        tickers = [("A", "A", "KOSPI"), ("B", "B", "KOSPI")]

        items, _, note = _optimize_goal_portfolio(
            symbols=["A", "B"],
            tickers=tickers,
            cagr_pct=[3.0, 8.0],
            returns_map=returns_map,
            required_return_pct=-50.0,
            is_equity=[True, True],
            equity_floor=0.8,
        )

        assert note is None
        assert sum(i["weight"] for i in items) == pytest.approx(100.0, abs=0.1)

    def test_equity_floor_zero_disables_constraint(self):
        """equity_floor=0이면 하한 제약이 적용되지 않고 일반 최소분산 결과와 동일해야 한다.

        후보가 2개뿐이면 기본 max_weight(40%) 상한이 1/n=50%로 완화되어 두 후보 모두 정확히
        50%로 강제되므로(변동성과 무관한 코너 해), 이 테스트는 후보를 3개로 구성해 옵티마이저가
        실제로 변동성 차이를 반영할 여지를 남긴다.
        """
        random.seed(6)
        returns_map = {
            "SAFE1": [random.gauss(0.0001, 0.0005) for _ in range(252)],
            "SAFE2": [random.gauss(0.00012, 0.0006) for _ in range(252)],
            "STOCK": [random.gauss(0.0004, 0.01) for _ in range(252)],
        }
        tickers = [("SAFE1", "안전자산1", "KOSPI"), ("SAFE2", "안전자산2", "KOSPI"), ("STOCK", "주식", "KOSPI")]

        items, _, note = _optimize_goal_portfolio(
            symbols=["SAFE1", "SAFE2", "STOCK"],
            tickers=tickers,
            cagr_pct=[3.0, 3.0, 8.0],
            returns_map=returns_map,
            required_return_pct=-50.0,
            is_equity=[False, False, True],
            equity_floor=0.0,
        )

        assert note is None
        stock_weight = next(i["weight"] for i in items if i["ticker"] == "STOCK")
        assert stock_weight < 40.0  # 고변동 STOCK 쪽 비중이 억제되어야 함 (하한 제약 없음)


class TestResolveIndexRegion:
    def test_explicit_tag_wins(self):
        assert resolve_index_region("069500", "KOSPI", "OVERSEAS") == "OVERSEAS"

    def test_overseas_listed_is_always_overseas(self):
        assert resolve_index_region("AAPL", "NASDAQ", None) == "OVERSEAS"

    def test_known_curated_overseas_tracking_krx_etf(self):
        """133690(TIGER 미국나스닥100)은 KRX 상장이지만 해외지수를 추종하는 것으로 알려진 큐레이션 티커."""
        assert resolve_index_region("133690", "KOSPI", None) == "OVERSEAS"

    def test_unknown_krx_ticker_defaults_to_domestic(self):
        assert resolve_index_region("005930", "KOSPI", None) == "DOMESTIC"


class TestGuessAssetClass:
    def test_matches_recommendation_universe_tags(self):
        """RECOMMENDATION_UNIVERSE에 이미 큐레이션된 종목명으로 추정했을 때 실제 태그와 일치해야
        휴리스틱이 신뢰할 만하다는 최소 근거가 된다."""
        for c in RECOMMENDATION_UNIVERSE:
            assert guess_asset_class(c["name"]) == c["asset_class"], c["name"]

    def test_plain_equity_name_defaults_to_equity(self):
        assert guess_asset_class("삼성전자") == "EQUITY"
        assert guess_asset_class("SPDR S&P 500 ETF") == "EQUITY"

    def test_bond_keyword_detected(self):
        assert guess_asset_class("KODEX 국고채3년") == "BOND"
        assert guess_asset_class("iShares 20+ Year Treasury Bond ETF") == "BOND"

    def test_cash_keyword_detected(self):
        assert guess_asset_class("KODEX 단기채권") == "CASH"
        assert guess_asset_class("TIGER CD금리투자KIS(합성)") == "CASH"


class TestApplyIndexRegionPreference:
    def test_general_prefers_domestic_and_excludes_overseas_tracking(self):
        candidates = [
            {"ticker": "069500", "name": "KODEX 200", "market": "KOSPI", "asset_class": "EQUITY"},
            {"ticker": "133690", "name": "TIGER 미국나스닥100", "market": "KOSPI", "asset_class": "EQUITY"},
        ]
        filtered, note, added = _apply_index_region_preference(candidates, "GENERAL", capacity_remaining=20)
        assert [c["ticker"] for c in filtered] == ["069500"]
        assert note is None
        assert added == []

    def test_isa_prefers_overseas_tracking(self):
        candidates = [
            {"ticker": "069500", "name": "KODEX 200", "market": "KOSPI", "asset_class": "EQUITY"},
            {"ticker": "133690", "name": "TIGER 미국나스닥100", "market": "KOSPI", "asset_class": "EQUITY"},
        ]
        filtered, note, added = _apply_index_region_preference(candidates, "ISA", capacity_remaining=20)
        assert [c["ticker"] for c in filtered] == ["133690"]
        assert note is None
        assert added == []

    def test_non_equity_candidates_pass_through_unfiltered(self):
        candidates = [
            {"ticker": "069500", "name": "KODEX 200", "market": "KOSPI", "asset_class": "EQUITY"},
            {"ticker": "133690", "name": "TIGER 미국나스닥100", "market": "KOSPI", "asset_class": "EQUITY"},
            {"ticker": "153130", "name": "KODEX 단기채권", "market": "KOSPI", "asset_class": "CASH"},
        ]
        filtered, note, added = _apply_index_region_preference(candidates, "ISA", capacity_remaining=20)
        assert {c["ticker"] for c in filtered} == {"133690", "153130"}
        assert note is None
        assert added == []

    def test_fallback_auto_augments_with_curated_overseas_etfs(self):
        """ISA인데 해외지수 추종 EQUITY 후보가 하나도 없으면 큐레이션 유니버스에서 자동 보강하고,
        보강분을 그대로 등록 대상(added)으로도 돌려준다."""
        candidates = [
            {"ticker": "069500", "name": "KODEX 200", "market": "KOSPI", "asset_class": "EQUITY"},
            {"ticker": "153130", "name": "KODEX 단기채권", "market": "KOSPI", "asset_class": "CASH"},
        ]
        filtered, note, added = _apply_index_region_preference(candidates, "ISA", capacity_remaining=20)
        tickers = {c["ticker"] for c in filtered}
        assert "069500" not in tickers  # 국내지수 추종 개별 EQUITY 후보는 제외됨
        assert tickers >= {"133690", "360750", "458730"}  # 큐레이션 해외지수 추종 ETF로 보강됨
        assert "153130" in tickers  # CASH 후보는 영향받지 않고 그대로 유지
        assert note is not None
        assert "자동 등록" in note
        assert {c["ticker"] for c in added} == {"133690", "360750", "458730"}

    def test_fallback_gives_up_augmenting_when_not_enough_capacity(self):
        """보강 후보 수가 capacity_remaining을 넘으면(등록 한도 초과) 보강을 포기하고 전체 후보로 대체한다."""
        candidates = [
            {"ticker": "069500", "name": "KODEX 200", "market": "KOSPI", "asset_class": "EQUITY"},
        ]
        # 큐레이션 해외지수 추종 EQUITY는 3개(133690/360750/458730)인데 잔여 슬롯은 2개뿐 — 전부 아니면 전무
        filtered, note, added = _apply_index_region_preference(candidates, "ISA", capacity_remaining=2)
        assert filtered == candidates
        assert added == []
        assert note is not None
        assert "해외지수" in note
        assert "자동 등록" not in note

    def test_fallback_to_full_candidates_when_curated_universe_has_no_match(self):
        """큐레이션 유니버스에서도 선호 지역 후보를 찾지 못하면(안전장치) 원본 후보 그대로 반환한다."""
        candidates = [
            {"ticker": "069500", "name": "KODEX 200", "market": "KOSPI", "asset_class": "EQUITY"},
        ]
        with patch("app.services.goal_recommendation_service.RECOMMENDATION_UNIVERSE", []):
            filtered, note, added = _apply_index_region_preference(candidates, "ISA", capacity_remaining=20)
        assert filtered == candidates
        assert added == []
        assert note is not None
        assert "해외지수" in note
        assert "자동 등록" not in note

    def test_overseas_dedicated_passes_through_genuinely_overseas_listed_candidates(self):
        """해외전용은 상장거래소가 이미 해외이므로 등록된 해외상장 EQUITY 후보는 그대로 통과한다."""
        candidates = [{"ticker": "SPY", "name": "SPDR S&P 500 ETF", "market": "NYSE", "asset_class": "EQUITY"}]
        filtered, note, added = _apply_index_region_preference(candidates, "OVERSEAS_DEDICATED", capacity_remaining=20)
        assert filtered == candidates
        assert note is None
        assert added == []

    def test_overseas_dedicated_excludes_krx_listed_overseas_tracking_etf_even_if_tagged(self):
        """133690(TIGER 미국나스닥100)은 index_region=OVERSEAS로 태그돼도 KRX 상장이라 해외전용
        계좌에서는 실제로 매수할 수 없으므로 여전히 제외돼야 한다(시장구분이 우선)."""
        candidates = [
            {
                "ticker": "133690",
                "name": "TIGER 미국나스닥100",
                "market": "KOSPI",
                "asset_class": "EQUITY",
                "index_region": "OVERSEAS",
            },
        ]
        filtered, note, added = _apply_index_region_preference(candidates, "OVERSEAS_DEDICATED", capacity_remaining=20)
        # 등록된 해외상장 EQUITY 후보가 없으므로 큐레이션 해외상장 ETF로 보강된다
        tickers = {c["ticker"] for c in filtered}
        assert "133690" not in tickers
        assert tickers >= {"SPY", "QQQ", "VOO", "VTI", "SCHD", "VYM"}
        assert note is not None
        assert "자동 등록" in note

    def test_overseas_dedicated_auto_augments_with_curated_overseas_listed_etfs_when_none_registered(self):
        """등록된 해외상장 EQUITY 후보가 하나도 없으면(예: 국내주식만 등록) 큐레이션 해외상장
        ETF로 자동 보강한다 — "충분한 시세 데이터가 있는 종목이 2개 미만" 문제의 근본 수정."""
        candidates = [
            {"ticker": "005930", "name": "삼성전자", "market": "KOSPI", "asset_class": "EQUITY"},
        ]
        filtered, note, added = _apply_index_region_preference(candidates, "OVERSEAS_DEDICATED", capacity_remaining=20)
        tickers = {c["ticker"] for c in filtered}
        assert "005930" not in tickers
        assert tickers >= {"SPY", "QQQ", "VOO", "VTI", "SCHD", "VYM"}
        assert {c["ticker"] for c in added} == tickers


class TestExistingItemsHelpers:
    def test_existing_items_from_positions_filters_cash_and_property(self):
        pos_map = {
            "SPY-NYSE": {"ticker": "SPY", "name": "SPDR S&P 500 ETF", "market": "NYSE", "value_krw": 1000.0},
            "CASH-KRW": {"ticker": "CASH", "name": "현금", "market": "KRW", "value_krw": 500.0},
            "APT1-KR_PROPERTY": {
                "ticker": "APT1",
                "name": "아파트",
                "market": "KR_PROPERTY",
                "value_krw": 300_000.0,
            },
        }
        result = existing_items_from_positions(pos_map)
        assert result == [("SPY", "SPDR S&P 500 ETF", "NYSE")]

    def test_existing_items_from_positions_falls_back_to_ticker_when_name_missing(self):
        pos_map = {"QQQ-NASDAQ": {"ticker": "QQQ", "market": "NASDAQ", "value_krw": 1000.0}}
        result = existing_items_from_positions(pos_map)
        assert result == [("QQQ", "QQQ", "NASDAQ")]


@pytest.mark.asyncio
class TestPersistAddedCandidates:
    async def test_merges_against_freshly_locked_row_not_stale_caller_snapshot(self):
        """settings_row가 요청 초반에 로드된 뒤, 동시 요청이 그사이 다른 후보를 커밋한 상황을
        흉내낸다 — 병합은 호출측이 들고 있는 스테일한 스냅샷이 아니라 락 시점에 반환된(신선한)
        행의 값을 기준으로 이뤄져야 동시 요청의 추가분이 유실되지 않는다."""
        user_id = uuid.uuid4()
        stale_snapshot = [{"ticker": "005930", "name": "삼성전자", "market": "KOSPI"}]
        fresh_row = SimpleNamespace(
            user_id=user_id,
            goal_candidate_tickers=[
                {"ticker": "005930", "name": "삼성전자", "market": "KOSPI"},
                {"ticker": "QQQ", "name": "Invesco QQQ Trust", "market": "NASDAQ"},
            ],
        )
        mock_db = AsyncMock()
        mock_db.scalar = AsyncMock(return_value=fresh_row)

        merged = await _persist_added_candidates(
            mock_db, user_id, [{"ticker": "SPY", "name": "SPDR S&P 500 ETF", "market": "NYSE"}]
        )

        # 호출측의 stale_snapshot에는 QQQ가 없었지만, 락으로 얻은 fresh_row 기준으로 병합되어
        # 동시 요청이 이미 커밋한 QQQ와 이번 추가분(SPY)이 모두 보존된다.
        assert {c["ticker"] for c in merged} == {"005930", "QQQ", "SPY"}
        assert stale_snapshot == [{"ticker": "005930", "name": "삼성전자", "market": "KOSPI"}]
        mock_db.commit.assert_awaited()

    async def test_dedups_when_added_already_present_in_fresh_row(self):
        """동시 요청이 이미 같은 티커를 추가해뒀다면 중복 등록하지 않는다."""
        user_id = uuid.uuid4()
        fresh_row = SimpleNamespace(
            user_id=user_id,
            goal_candidate_tickers=[{"ticker": "QQQ", "name": "Invesco QQQ Trust", "market": "NASDAQ"}],
        )
        mock_db = AsyncMock()
        mock_db.scalar = AsyncMock(return_value=fresh_row)

        merged = await _persist_added_candidates(
            mock_db, user_id, [{"ticker": "QQQ", "name": "Invesco QQQ Trust", "market": "NASDAQ"}]
        )

        assert len(merged) == 1

    async def test_returns_added_unchanged_when_row_not_found(self):
        mock_db = AsyncMock()
        mock_db.scalar = AsyncMock(return_value=None)
        added = [{"ticker": "SPY", "name": "SPDR S&P 500 ETF", "market": "NYSE"}]

        merged = await _persist_added_candidates(mock_db, uuid.uuid4(), added)

        assert merged == added
        mock_db.commit.assert_not_awaited()


@pytest.mark.asyncio
class TestGetGoalRecommendation:
    async def test_not_configured_without_goal_amount(self):
        settings_row = SimpleNamespace(goal_amount=None, retirement_target_year=None)

        result = await get_goal_recommendation(None, 0.0, [], settings_row, AsyncMock())

        assert result.is_configured is False

    async def test_already_achieved_goal(self):
        settings_row = SimpleNamespace(
            goal_amount=1_000_000.0,
            retirement_target_year=9999,
            monthly_deposit_amount=100_000.0,
            annual_deposit_goal=None,
            annual_dividend_goal=None,
        )

        result = await get_goal_recommendation(None, 2_000_000.0, [], settings_row, AsyncMock())

        assert result.is_configured is True
        assert "이미" in result.note

    async def test_target_year_already_passed(self):
        settings_row = SimpleNamespace(
            goal_amount=1_000_000_000.0,
            retirement_target_year=2000,
            monthly_deposit_amount=100_000.0,
            annual_deposit_goal=None,
            annual_dividend_goal=None,
        )

        result = await get_goal_recommendation(None, 0.0, [], settings_row, AsyncMock())

        assert result.is_configured is True
        assert "지났습니다" in result.note

    async def test_full_happy_path_returns_recommended_items(self):
        """후보를 한 번도 등록한 적 없으면(goal_candidate_tickers=None) 큐레이션 유니버스로 시드되어 계산된다."""
        settings_row = SimpleNamespace(
            goal_amount=100_000_000.0,
            retirement_target_year=9999,
            monthly_deposit_amount=1_000_000.0,
            annual_deposit_goal=None,
            annual_dividend_goal=2_000_000.0,
            goal_candidate_tickers=None,
        )

        cagr_map = {
            ("SPY", "NYSE"): {"cagr_pct": 10.0},
            ("QQQ", "NASDAQ"): {"cagr_pct": 15.0},
            ("VOO", "NYSE"): {"cagr_pct": 9.0},
            ("VTI", "NYSE"): {"cagr_pct": 9.5},
            ("SCHD", "NYSE"): {"cagr_pct": 8.0},
            ("VYM", "NYSE"): {"cagr_pct": 7.0},
            ("069500", "KOSPI"): {"cagr_pct": 6.0},
            ("360750", "KOSPI"): {"cagr_pct": 9.0},
            ("133690", "KOSPI"): {"cagr_pct": 14.0},
            ("458730", "KOSPI"): {"cagr_pct": 5.0},
        }
        random.seed(7)
        returns_map = {
            sym: [random.gauss(0.0005, 0.01) for _ in range(252)]
            for sym in ["SPY", "QQQ", "VOO", "VTI", "SCHD", "VYM", "069500.KS", "360750.KS", "133690.KS", "458730.KS"]
        }
        dividend_map = {("SCHD", "NYSE"): 3.5, ("VYM", "NYSE"): 2.9}

        with (
            patch(
                "app.services.goal_recommendation_service.get_historical_returns",
                AsyncMock(return_value=cagr_map),
            ),
            patch(
                "app.services.goal_recommendation_service._fetch_dividend_yields",
                AsyncMock(return_value=dividend_map),
            ),
            patch(
                "app.services.goal_recommendation_service.fetch_yf_daily_returns",
                return_value=returns_map,
            ),
        ):
            mock_db = AsyncMock()
            result = await get_goal_recommendation(None, 10_000_000.0, [], settings_row, mock_db)

        assert result.is_configured is True
        assert result.required_return_pct is not None
        assert result.recommended_items
        assert sum(i.weight for i in result.recommended_items) == pytest.approx(100.0, abs=0.5)
        # 최초 시드가 settings_row에 반영되어 커밋됨
        assert settings_row.goal_candidate_tickers is not None
        mock_db.commit.assert_awaited()
        # 신규 추천 설정을 건드리지 않은 경우 기존 하드코딩 기본값과 동일하게 echo된다
        assert result.cagr_lookback_years == 10
        assert result.risk_tolerance == "CONSERVATIVE"
        assert result.max_weight_pct == 40.0

    async def test_infeasible_required_return_reports_note(self):
        """필요수익률(연 60%)이 해석 가능한 범위 내지만 모든 후보 CAGR을 초과하면 추천 없이 note만 채워진다."""
        from datetime import date

        settings_row = SimpleNamespace(
            goal_amount=1_600_000.0,  # pv 100만원, 무적립, 1년 내 60% 수익률 필요
            retirement_target_year=date.today().year + 1,
            monthly_deposit_amount=0.0,
            annual_deposit_goal=None,
            annual_dividend_goal=None,
            goal_candidate_tickers=None,
        )
        cagr_map = {("SPY", "NYSE"): {"cagr_pct": 10.0}, ("QQQ", "NASDAQ"): {"cagr_pct": 12.0}}
        returns_map = {"SPY": [0.0005] * 252, "QQQ": [0.0006] * 252}

        with (
            patch(
                "app.services.goal_recommendation_service.get_historical_returns",
                AsyncMock(return_value=cagr_map),
            ),
            patch(
                "app.services.goal_recommendation_service._fetch_dividend_yields",
                AsyncMock(return_value={}),
            ),
            patch(
                "app.services.goal_recommendation_service.fetch_yf_daily_returns",
                return_value=returns_map,
            ),
        ):
            result = await get_goal_recommendation(None, 1_000_000.0, [], settings_row, AsyncMock())

        assert result.is_configured is True
        assert result.recommended_items == []
        assert result.note is not None

    async def test_user_candidate_tickers_replace_universe_when_set(self):
        """settings_row.goal_candidate_tickers가 저장되어 있으면 그 목록만 후보로 조회된다(병합 아님)."""
        settings_row = SimpleNamespace(
            goal_amount=100_000_000.0,
            retirement_target_year=9999,
            monthly_deposit_amount=1_000_000.0,
            annual_deposit_goal=None,
            annual_dividend_goal=None,
            goal_candidate_tickers=[{"ticker": "TLT", "name": "iShares 20+ Year Treasury Bond ETF", "market": "NYSE"}],
        )
        cagr_map = {("TLT", "NYSE"): {"cagr_pct": 4.0}}
        returns_map = {"TLT": [0.0002] * 252}

        get_historical_returns_mock = AsyncMock(return_value=cagr_map)
        with (
            patch(
                "app.services.goal_recommendation_service.get_historical_returns",
                get_historical_returns_mock,
            ),
            patch(
                "app.services.goal_recommendation_service._fetch_dividend_yields",
                AsyncMock(return_value={}),
            ),
            patch(
                "app.services.goal_recommendation_service.fetch_yf_daily_returns",
                return_value=returns_map,
            ),
        ):
            await get_goal_recommendation(None, 10_000_000.0, [], settings_row, AsyncMock())

        queried_tickers = get_historical_returns_mock.call_args.args[0]
        assert queried_tickers == [("TLT", "NYSE")]

    async def test_existing_items_ignored_when_user_candidates_already_saved(self):
        """사용자가 이미 후보를 저장한 상태에서는 보유 종목(existing_items)이 자동 병합되지 않는다."""
        settings_row = SimpleNamespace(
            goal_amount=100_000_000.0,
            retirement_target_year=9999,
            monthly_deposit_amount=1_000_000.0,
            annual_deposit_goal=None,
            annual_dividend_goal=None,
            goal_candidate_tickers=[{"ticker": "SPY", "name": "SPDR S&P 500 ETF", "market": "NYSE"}],
        )
        cagr_map = {("SPY", "NYSE"): {"cagr_pct": 10.0}, ("QQQ", "NASDAQ"): {"cagr_pct": 15.0}}
        returns_map = {"SPY": [0.0005] * 252, "QQQ": [0.0006] * 252}

        get_historical_returns_mock = AsyncMock(return_value=cagr_map)
        with (
            patch(
                "app.services.goal_recommendation_service.get_historical_returns",
                get_historical_returns_mock,
            ),
            patch(
                "app.services.goal_recommendation_service._fetch_dividend_yields",
                AsyncMock(return_value={}),
            ),
            patch(
                "app.services.goal_recommendation_service.fetch_yf_daily_returns",
                return_value=returns_map,
            ),
        ):
            await get_goal_recommendation(
                None, 10_000_000.0, [("QQQ", "Invesco QQQ Trust", "NASDAQ")], settings_row, AsyncMock()
            )

        queried_tickers = get_historical_returns_mock.call_args.args[0]
        assert queried_tickers == [("SPY", "NYSE")]

    async def test_seeds_and_persists_candidates_when_never_configured(self):
        """goal_candidate_tickers가 None(최초 상태)이면 보유종목+큐레이션 유니버스로 시드해 DB에 커밋한다."""
        settings_row = SimpleNamespace(
            goal_amount=100_000_000.0,
            retirement_target_year=9999,
            monthly_deposit_amount=1_000_000.0,
            annual_deposit_goal=None,
            annual_dividend_goal=None,
            goal_candidate_tickers=None,
        )
        existing_items = [("SPY", "SPDR S&P 500 ETF", "NYSE")]

        with (
            patch(
                "app.services.goal_recommendation_service.get_historical_returns",
                AsyncMock(return_value={}),
            ),
            patch(
                "app.services.goal_recommendation_service._fetch_dividend_yields",
                AsyncMock(return_value={}),
            ),
        ):
            mock_db = AsyncMock()
            result = await get_goal_recommendation(None, 10_000_000.0, existing_items, settings_row, mock_db)

        assert settings_row.goal_candidate_tickers is not None
        assert {"ticker": "SPY", "name": "SPDR S&P 500 ETF", "market": "NYSE"} in settings_row.goal_candidate_tickers
        assert len(settings_row.goal_candidate_tickers) <= MAX_GOAL_CANDIDATE_TICKERS
        mock_db.commit.assert_awaited_once()
        # 시드된 후보의 시세 데이터가 하나도 없으므로(cagr_map={}) 추천 없이 note만 채워짐
        assert result.recommended_items == []

    async def test_empty_saved_candidates_skips_optimizer(self):
        """사용자가 후보를 전부 제거하고 저장한 경우(빈 리스트)는 옵티마이저 호출 없이 안내 메시지만 반환한다."""
        settings_row = SimpleNamespace(
            goal_amount=100_000_000.0,
            retirement_target_year=9999,
            monthly_deposit_amount=1_000_000.0,
            annual_deposit_goal=None,
            annual_dividend_goal=None,
            goal_candidate_tickers=[],
        )

        get_historical_returns_mock = AsyncMock(return_value={})
        with patch(
            "app.services.goal_recommendation_service.get_historical_returns",
            get_historical_returns_mock,
        ):
            result = await get_goal_recommendation(None, 10_000_000.0, [], settings_row, AsyncMock())

        assert result.is_configured is True
        assert result.recommended_items == []
        assert "등록된 후보 종목이 없습니다" in result.note
        get_historical_returns_mock.assert_not_called()

    async def test_seed_capped_at_max_candidates(self):
        """보유 종목이 많아도 시드는 MAX_GOAL_CANDIDATE_TICKERS(20)개를 넘지 않는다."""
        settings_row = SimpleNamespace(
            goal_amount=100_000_000.0,
            retirement_target_year=9999,
            monthly_deposit_amount=1_000_000.0,
            annual_deposit_goal=None,
            annual_dividend_goal=None,
            goal_candidate_tickers=None,
        )
        existing_items = [(f"T{i}", f"Ticker {i}", "NASDAQ") for i in range(25)]

        with (
            patch(
                "app.services.goal_recommendation_service.get_historical_returns",
                AsyncMock(return_value={}),
            ),
            patch(
                "app.services.goal_recommendation_service._fetch_dividend_yields",
                AsyncMock(return_value={}),
            ),
        ):
            mock_db = AsyncMock()
            await get_goal_recommendation(None, 10_000_000.0, existing_items, settings_row, mock_db)

        assert len(settings_row.goal_candidate_tickers) == 20
        # 보유 종목이 이미 상한을 채우므로 큐레이션 유니버스는 하나도 섞이지 않는다
        assert all(t["ticker"].startswith("T") for t in settings_row.goal_candidate_tickers)

    async def test_cagr_lookback_years_setting_passed_to_get_historical_returns(self):
        settings_row = SimpleNamespace(
            goal_amount=100_000_000.0,
            retirement_target_year=9999,
            monthly_deposit_amount=1_000_000.0,
            annual_deposit_goal=None,
            annual_dividend_goal=None,
            goal_candidate_tickers=[
                {"ticker": "SPY", "name": "SPDR S&P 500 ETF", "market": "NYSE"},
                {"ticker": "VOO", "name": "Vanguard S&P 500 ETF", "market": "NYSE"},
            ],
            goal_cagr_lookback_years=5,
        )
        cagr_map = {("SPY", "NYSE"): {"cagr_pct": 10.0}, ("VOO", "NYSE"): {"cagr_pct": 9.0}}
        random.seed(11)
        returns_map = {
            "SPY": [random.gauss(0.0004, 0.008) for _ in range(252)],
            "VOO": [random.gauss(0.0004, 0.008) for _ in range(252)],
        }
        get_historical_returns_mock = AsyncMock(return_value=cagr_map)

        with (
            patch(
                "app.services.goal_recommendation_service.get_historical_returns",
                get_historical_returns_mock,
            ),
            patch(
                "app.services.goal_recommendation_service._fetch_dividend_yields",
                AsyncMock(return_value={}),
            ),
            patch(
                "app.services.goal_recommendation_service.fetch_yf_daily_returns",
                return_value=returns_map,
            ),
        ):
            result = await get_goal_recommendation(None, 10_000_000.0, [], settings_row, AsyncMock())

        assert get_historical_returns_mock.call_args.kwargs["years"] == 5
        assert result.cagr_lookback_years == 5

    async def test_risk_tolerance_aggressive_raises_expected_return_vs_conservative(self):
        """AGGRESSIVE 성향은 CONSERVATIVE 대비 더 높은 기대수익률(더 큰 변동성 감수)로 유도한다.

        n=2에 기본 40% 캡(1/n로 완화되어 50%)을 쓰면 두 비중이 (0.5, 0.5)로 강제되어 버퍼 유무와
        무관하게 결과가 동일해지므로(자유도 0), 종목 3개로 최적화에 실제 자유도를 부여한다.
        """
        random.seed(13)
        returns_map = {
            "A": [random.gauss(0.0002, 0.001) for _ in range(252)],  # 저변동
            "B": [random.gauss(0.0004, 0.006) for _ in range(252)],  # 중변동
            "C": [random.gauss(0.0004, 0.02) for _ in range(252)],  # 고변동
        }
        cagr_map = {
            ("A", "NASDAQ"): {"cagr_pct": 3.0},
            ("B", "NASDAQ"): {"cagr_pct": 6.0},
            ("C", "NASDAQ"): {"cagr_pct": 15.0},
        }

        def make_settings(risk_tolerance: str) -> SimpleNamespace:
            return SimpleNamespace(
                goal_amount=100_000_000.0,
                retirement_target_year=9999,
                monthly_deposit_amount=1_000_000.0,
                annual_deposit_goal=None,
                annual_dividend_goal=None,
                goal_candidate_tickers=[
                    {"ticker": "A", "name": "A Inc", "market": "NASDAQ"},
                    {"ticker": "B", "name": "B Inc", "market": "NASDAQ"},
                    {"ticker": "C", "name": "C Inc", "market": "NASDAQ"},
                ],
                goal_risk_tolerance=risk_tolerance,
            )

        async def run(risk_tolerance: str):
            with (
                patch(
                    "app.services.goal_recommendation_service.solve_required_annual_return_pct",
                    return_value=5.0,
                ),
                patch(
                    "app.services.goal_recommendation_service.get_historical_returns",
                    AsyncMock(return_value=cagr_map),
                ),
                patch(
                    "app.services.goal_recommendation_service._fetch_dividend_yields",
                    AsyncMock(return_value={}),
                ),
                patch(
                    "app.services.goal_recommendation_service.fetch_yf_daily_returns",
                    return_value=returns_map,
                ),
            ):
                return await get_goal_recommendation(None, 10_000_000.0, [], make_settings(risk_tolerance), AsyncMock())

        conservative = await run("CONSERVATIVE")
        aggressive = await run("AGGRESSIVE")

        assert conservative.risk_tolerance == "CONSERVATIVE"
        assert aggressive.risk_tolerance == "AGGRESSIVE"
        assert aggressive.expected_return_pct > conservative.expected_return_pct
        assert aggressive.expected_return_pct >= 7.5 - 0.1

    async def test_max_weight_pct_setting_caps_recommended_weights(self):
        random.seed(17)
        returns_map = {
            "A": [random.gauss(0.0002, 0.001) for _ in range(252)],  # 저변동 → 무제한이면 쏠림
            "B": [random.gauss(0.0004, 0.01) for _ in range(252)],
            "C": [random.gauss(0.0004, 0.01) for _ in range(252)],
            "D": [random.gauss(0.0004, 0.01) for _ in range(252)],
        }
        cagr_map = {(t, "NASDAQ"): {"cagr_pct": 3.0} for t in ("A", "B", "C", "D")}
        settings_row = SimpleNamespace(
            goal_amount=100_000_000.0,
            retirement_target_year=9999,
            monthly_deposit_amount=1_000_000.0,
            annual_deposit_goal=None,
            annual_dividend_goal=None,
            goal_candidate_tickers=[
                {"ticker": t, "name": f"{t} Inc", "market": "NASDAQ"} for t in ("A", "B", "C", "D")
            ],
            goal_max_weight_pct=25.0,
        )

        with (
            patch(
                "app.services.goal_recommendation_service.get_historical_returns",
                AsyncMock(return_value=cagr_map),
            ),
            patch(
                "app.services.goal_recommendation_service._fetch_dividend_yields",
                AsyncMock(return_value={}),
            ),
            patch(
                "app.services.goal_recommendation_service.fetch_yf_daily_returns",
                return_value=returns_map,
            ),
        ):
            result = await get_goal_recommendation(None, 10_000_000.0, [], settings_row, AsyncMock())

        assert result.max_weight_pct == 25.0
        assert result.recommended_items
        assert all(item.weight <= 25.0 + 0.5 for item in result.recommended_items)

    async def test_isa_uniform_tax_type_prefers_overseas_and_augments_with_curated_etfs(self):
        """전체 탭: 활성 계좌가 전부 ISA면 국내 개별주식(삼성전자 등) 대신 큐레이션 해외지수 ETF로 보강된다."""
        settings_row = SimpleNamespace(
            user_id=uuid.uuid4(),
            goal_amount=100_000_000.0,
            retirement_target_year=9999,
            monthly_deposit_amount=1_000_000.0,
            annual_deposit_goal=None,
            annual_dividend_goal=None,
            goal_candidate_tickers=[
                {"ticker": "005930", "name": "삼성전자", "market": "KOSPI", "asset_class": "EQUITY"},
            ],
        )
        cagr_map = {
            ("133690", "KOSPI"): {"cagr_pct": 14.0},
            ("360750", "KOSPI"): {"cagr_pct": 9.0},
            ("458730", "KOSPI"): {"cagr_pct": 7.0},
        }
        random.seed(31)
        returns_map = {
            sym: [random.gauss(0.0005, 0.01) for _ in range(252)] for sym in ["133690.KS", "360750.KS", "458730.KS"]
        }
        get_historical_returns_mock = AsyncMock(return_value=cagr_map)

        with (
            patch(
                "app.services.goal_recommendation_service._active_account_tax_types",
                AsyncMock(return_value=["ISA"]),
            ),
            patch(
                "app.services.goal_recommendation_service.get_historical_returns",
                get_historical_returns_mock,
            ),
            patch(
                "app.services.goal_recommendation_service._fetch_dividend_yields",
                AsyncMock(return_value={}),
            ),
            patch(
                "app.services.goal_recommendation_service.fetch_yf_daily_returns",
                return_value=returns_map,
            ),
        ):
            mock_db = AsyncMock()
            mock_db.scalar = AsyncMock(return_value=settings_row)
            result = await get_goal_recommendation(None, 10_000_000.0, [], settings_row, mock_db)

        queried_tickers = get_historical_returns_mock.call_args.args[0]
        assert set(queried_tickers) == {("133690", "KOSPI"), ("360750", "KOSPI"), ("458730", "KOSPI")}
        assert result.recommended_items
        assert {item.ticker for item in result.recommended_items} <= {"133690", "360750", "458730"}
        assert "005930" not in {item.ticker for item in result.recommended_items}
        assert result.note is not None
        assert "해외지수" in result.note

        # 자동 보강된 큐레이션 ETF가 "후보 ETF 관리" 화면에도 반영되도록 실제로 등록·커밋된다
        saved_tickers = {c["ticker"] for c in settings_row.goal_candidate_tickers}
        assert {"133690", "360750", "458730"} <= saved_tickers
        mock_db.commit.assert_awaited()

    async def test_mixed_tax_types_skips_index_region_preference(self):
        """전체 탭: 활성 계좌 세제유형이 혼재하면(ISA+GENERAL) 지역 선호 필터를 적용하지 않는다."""
        settings_row = SimpleNamespace(
            user_id=uuid.uuid4(),
            goal_amount=100_000_000.0,
            retirement_target_year=9999,
            monthly_deposit_amount=1_000_000.0,
            annual_deposit_goal=None,
            annual_dividend_goal=None,
            goal_candidate_tickers=[
                {"ticker": "005930", "name": "삼성전자", "market": "KOSPI", "asset_class": "EQUITY"},
                {"ticker": "000660", "name": "SK하이닉스", "market": "KOSPI", "asset_class": "EQUITY"},
            ],
        )
        cagr_map = {
            ("005930", "KOSPI"): {"cagr_pct": 7.0},
            ("000660", "KOSPI"): {"cagr_pct": 8.0},
        }
        random.seed(37)
        returns_map = {sym: [random.gauss(0.0004, 0.008) for _ in range(252)] for sym in ["005930.KS", "000660.KS"]}
        get_historical_returns_mock = AsyncMock(return_value=cagr_map)

        with (
            patch(
                "app.services.goal_recommendation_service._active_account_tax_types",
                AsyncMock(return_value=["ISA", "GENERAL"]),
            ),
            patch(
                "app.services.goal_recommendation_service.get_historical_returns",
                get_historical_returns_mock,
            ),
            patch(
                "app.services.goal_recommendation_service._fetch_dividend_yields",
                AsyncMock(return_value={}),
            ),
            patch(
                "app.services.goal_recommendation_service.fetch_yf_daily_returns",
                return_value=returns_map,
            ),
        ):
            result = await get_goal_recommendation(None, 10_000_000.0, [], settings_row, AsyncMock())

        queried_tickers = get_historical_returns_mock.call_args.args[0]
        assert set(queried_tickers) == {("005930", "KOSPI"), ("000660", "KOSPI")}
        assert result.recommended_items

    async def test_does_not_cache_result_with_no_recommended_items(self):
        """서킷브레이커 등으로 시세 데이터를 못 가져와 recommended_items가 비어 있으면 캐시에
        쓰지 않는다 — 그렇지 않으면 일시적 실패가 TTL(10분) 동안 그대로 얼어붙는다."""
        settings_row = SimpleNamespace(
            user_id=uuid.uuid4(),
            goal_amount=100_000_000.0,
            retirement_target_year=9999,
            monthly_deposit_amount=1_000_000.0,
            annual_deposit_goal=None,
            annual_dividend_goal=None,
            goal_candidate_tickers=[
                {"ticker": "SPY", "name": "SPDR S&P 500 ETF", "market": "NYSE"},
                {"ticker": "QQQ", "name": "Invesco QQQ Trust", "market": "NASDAQ"},
            ],
        )
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)

        with (
            patch(
                "app.services.goal_recommendation_service._active_account_tax_types",
                AsyncMock(return_value=[]),
            ),
            patch(
                "app.services.goal_recommendation_service.get_historical_returns",
                AsyncMock(return_value={("SPY", "NYSE"): {"cagr_pct": 10.0}, ("QQQ", "NASDAQ"): {"cagr_pct": 15.0}}),
            ),
            patch(
                "app.services.goal_recommendation_service._fetch_dividend_yields",
                AsyncMock(return_value={}),
            ),
            patch(
                "app.services.goal_recommendation_service.fetch_yf_daily_returns",
                return_value={},  # Yahoo 서킷브레이커 오픈 상황 시뮬레이션 — 일별수익률 조회 실패
            ),
        ):
            result = await get_goal_recommendation(mock_redis, 10_000_000.0, [], settings_row, AsyncMock())

        assert result.recommended_items == []
        mock_redis.setex.assert_not_called()

    async def test_caches_result_with_recommended_items(self):
        """정상적으로 추천이 생성되면 결과를 캐싱한다."""
        settings_row = SimpleNamespace(
            user_id=uuid.uuid4(),
            goal_amount=100_000_000.0,
            retirement_target_year=9999,
            monthly_deposit_amount=1_000_000.0,
            annual_deposit_goal=None,
            annual_dividend_goal=None,
            goal_candidate_tickers=[
                {"ticker": "SPY", "name": "SPDR S&P 500 ETF", "market": "NYSE"},
                {"ticker": "QQQ", "name": "Invesco QQQ Trust", "market": "NASDAQ"},
            ],
        )
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        cagr_map = {("SPY", "NYSE"): {"cagr_pct": 10.0}, ("QQQ", "NASDAQ"): {"cagr_pct": 15.0}}
        returns_map = {"SPY": [0.0005] * 252, "QQQ": [0.0006] * 252}

        with (
            patch(
                "app.services.goal_recommendation_service._active_account_tax_types",
                AsyncMock(return_value=[]),
            ),
            patch(
                "app.services.goal_recommendation_service.get_historical_returns",
                AsyncMock(return_value=cagr_map),
            ),
            patch(
                "app.services.goal_recommendation_service._fetch_dividend_yields",
                AsyncMock(return_value={}),
            ),
            patch(
                "app.services.goal_recommendation_service.fetch_yf_daily_returns",
                return_value=returns_map,
            ),
        ):
            result = await get_goal_recommendation(mock_redis, 10_000_000.0, [], settings_row, AsyncMock())

        assert result.recommended_items
        mock_redis.setex.assert_awaited_once()


def _execute_result(rows: list[tuple]) -> MagicMock:
    result = MagicMock()
    result.all.return_value = rows
    return result


class TestGetHorizonRecommendations:
    """단기/중기/장기 × 세제유형 투자기간별 추천 (목표 역산이 아닌 리스크 성향 + 시장 재배분)."""

    async def test_skips_horizons_without_tagged_accounts(self):
        settings_row = SimpleNamespace(
            goal_candidate_tickers=[
                {"ticker": "SPY", "name": "SPDR S&P 500 ETF", "market": "NYSE", "asset_class": "EQUITY"},
            ],
            goal_max_weight_pct=None,
            goal_cagr_lookback_years=None,
        )
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=_execute_result([]))

        with patch(
            "app.services.goal_recommendation_service.query_latest_position_map",
            AsyncMock(return_value={}),
        ):
            result = await get_horizon_recommendations(None, mock_db, uuid.uuid4(), settings_row)

        assert result.recommendations == []

    async def test_short_term_filters_to_bond_and_cash_candidates(self):
        """단기 추천은 세제유형에 맞는 시장(국내/해외)의 후보만 사용하고(EQUITY 후보라도 시장이
        맞지 않으면 제외), 필요수익률 제약이 무효화되어 순수 최소분산으로 계산된다."""
        settings_row = SimpleNamespace(
            goal_candidate_tickers=[
                {"ticker": "SPY", "name": "SPDR S&P 500 ETF", "market": "NYSE", "asset_class": "EQUITY"},
                {"ticker": "153130", "name": "KODEX 단기채권", "market": "KOSPI", "asset_class": "CASH"},
                {"ticker": "114260", "name": "KODEX 국고채3년", "market": "KOSPI", "asset_class": "BOND"},
            ],
            goal_max_weight_pct=None,
            goal_cagr_lookback_years=None,
        )
        account_id = uuid.uuid4()
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=_execute_result([("SHORT_TERM", "GENERAL", account_id)]))

        cagr_map = {
            ("153130", "KOSPI"): {"cagr_pct": 2.0},
            ("114260", "KOSPI"): {"cagr_pct": 3.0},
        }
        random.seed(3)
        returns_map = {
            "153130.KS": [random.gauss(0.0001, 0.0005) for _ in range(252)],
            "114260.KS": [random.gauss(0.00015, 0.001) for _ in range(252)],
        }
        get_historical_returns_mock = AsyncMock(return_value=cagr_map)

        with (
            patch(
                "app.services.goal_recommendation_service.query_latest_position_map",
                AsyncMock(return_value={}),
            ),
            patch(
                "app.services.goal_recommendation_service.build_portfolio_overview",
                AsyncMock(return_value={"total_assets_krw": 5_000_000.0}),
            ),
            patch(
                "app.services.goal_recommendation_service.get_historical_returns",
                get_historical_returns_mock,
            ),
            patch(
                "app.services.goal_recommendation_service.fetch_yf_daily_returns",
                return_value=returns_map,
            ),
        ):
            result = await get_horizon_recommendations(None, mock_db, uuid.uuid4(), settings_row)

        assert len(result.recommendations) == 1
        rec = result.recommendations[0]
        assert rec.investment_horizon == "SHORT_TERM"
        assert rec.tax_type == "GENERAL"
        assert rec.risk_tolerance == "CONSERVATIVE"
        assert rec.account_count == 1
        assert rec.base_krw == 5_000_000.0
        assert rec.recommended_items
        assert {item.ticker for item in rec.recommended_items} <= {"153130", "114260", "CASH_EQUIVALENT"}
        queried_tickers = get_historical_returns_mock.call_args.args[0]
        assert ("SPY", "NYSE") not in queried_tickers
        assert ("CASH_EQUIVALENT", "CASH") not in queried_tickers

    async def test_short_term_includes_cash_equivalent_alongside_registered_candidates(self):
        """단기 추천은 등록된 BOND/CASH 후보가 있어도 현금성 자산(CMA·파킹통장) 합성 후보를
        함께 옵티마이저에 넣어 실제로 섞인 비중을 계산한다."""
        settings_row = SimpleNamespace(
            goal_candidate_tickers=[
                {"ticker": "153130", "name": "KODEX 단기채권", "market": "KOSPI", "asset_class": "CASH"},
                {"ticker": "114260", "name": "KODEX 국고채3년", "market": "KOSPI", "asset_class": "BOND"},
            ],
            goal_max_weight_pct=None,
            goal_cagr_lookback_years=None,
        )
        account_id = uuid.uuid4()
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=_execute_result([("SHORT_TERM", "GENERAL", account_id)]))

        cagr_map = {
            ("153130", "KOSPI"): {"cagr_pct": 2.0},
            ("114260", "KOSPI"): {"cagr_pct": 3.0},
        }
        random.seed(5)
        returns_map = {
            "153130.KS": [random.gauss(0.0001, 0.0005) for _ in range(252)],
            "114260.KS": [random.gauss(0.00015, 0.001) for _ in range(252)],
        }
        fetch_returns_mock = MagicMock(return_value=returns_map)

        with (
            patch(
                "app.services.goal_recommendation_service.query_latest_position_map",
                AsyncMock(return_value={}),
            ),
            patch(
                "app.services.goal_recommendation_service.build_portfolio_overview",
                AsyncMock(return_value={"total_assets_krw": 5_000_000.0}),
            ),
            patch(
                "app.services.goal_recommendation_service.get_historical_returns",
                AsyncMock(return_value=cagr_map),
            ),
            patch(
                "app.services.goal_recommendation_service.fetch_yf_daily_returns",
                fetch_returns_mock,
            ),
        ):
            result = await get_horizon_recommendations(None, mock_db, uuid.uuid4(), settings_row)

        assert len(result.recommendations) == 1
        rec = result.recommendations[0]
        # CASH_EQUIVALENT는 실제 시세 조회 대상이 아니므로 fetch_yf_daily_returns에 전달되지 않아야 한다.
        queried_symbols = fetch_returns_mock.call_args.args[0]
        assert "CASH_EQUIVALENT" not in queried_symbols
        assert rec.recommended_items
        assert "CASH_EQUIVALENT" in {item.ticker for item in rec.recommended_items}
        assert rec.includes_cash_equivalent is True

    async def test_insufficient_eligible_candidates_falls_back_to_cash_equivalent(self):
        """단기 추천에 적합한(BOND/CASH) 후보가 없으면 옵티마이저 없이 현금성 자산 100% 배분을 반환한다."""
        settings_row = SimpleNamespace(
            goal_candidate_tickers=[
                {"ticker": "SPY", "name": "SPDR S&P 500 ETF", "market": "NYSE", "asset_class": "EQUITY"},
            ],
            goal_max_weight_pct=None,
            goal_cagr_lookback_years=None,
        )
        account_id = uuid.uuid4()
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=_execute_result([("SHORT_TERM", "GENERAL", account_id)]))

        with (
            patch(
                "app.services.goal_recommendation_service.query_latest_position_map",
                AsyncMock(return_value={}),
            ),
            patch(
                "app.services.goal_recommendation_service.build_portfolio_overview",
                AsyncMock(return_value={"total_assets_krw": 1_000_000.0}),
            ),
        ):
            result = await get_horizon_recommendations(None, mock_db, uuid.uuid4(), settings_row)

        assert len(result.recommendations) == 1
        rec = result.recommendations[0]
        assert len(rec.recommended_items) == 1
        assert rec.recommended_items[0].ticker == "CASH_EQUIVALENT"
        assert rec.recommended_items[0].weight == 100.0
        assert rec.includes_cash_equivalent is True
        assert "현금성 자산" in rec.note

    async def test_mid_term_insufficient_candidates_unaffected_by_cash_equivalent_fallback(self):
        """현금성 자산 합성 후보 주입은 SHORT_TERM 전용이며, MID_TERM의 기존 부족 안내 동작은 그대로다."""
        settings_row = SimpleNamespace(
            goal_candidate_tickers=[
                {"ticker": "SPY", "name": "SPDR S&P 500 ETF", "market": "NYSE", "asset_class": "EQUITY"},
            ],
            goal_max_weight_pct=None,
            goal_cagr_lookback_years=None,
        )
        account_id = uuid.uuid4()
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=_execute_result([("MID_TERM", "GENERAL", account_id)]))

        with (
            patch(
                "app.services.goal_recommendation_service.query_latest_position_map",
                AsyncMock(return_value={}),
            ),
            patch(
                "app.services.goal_recommendation_service.build_portfolio_overview",
                AsyncMock(return_value={"total_assets_krw": 1_000_000.0}),
            ),
        ):
            result = await get_horizon_recommendations(None, mock_db, uuid.uuid4(), settings_row)

        assert len(result.recommendations) == 1
        rec = result.recommendations[0]
        assert rec.recommended_items == []
        assert rec.includes_cash_equivalent is False
        assert "채권/현금성" in rec.note

    async def test_short_term_applies_configured_equity_floor(self):
        """등록된 주식(EQUITY) 후보가 있으면 기본 설정(80%)만큼 주식 비중이 강제로 배분된다."""
        settings_row = SimpleNamespace(
            goal_candidate_tickers=[
                {"ticker": "069500", "name": "KODEX 200", "market": "KOSPI", "asset_class": "EQUITY"},
                {"ticker": "153130", "name": "KODEX 단기채권", "market": "KOSPI", "asset_class": "CASH"},
            ],
            goal_max_weight_pct=None,
            goal_cagr_lookback_years=None,
            goal_short_term_equity_floor_pct=None,
        )
        account_id = uuid.uuid4()
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=_execute_result([("SHORT_TERM", "GENERAL", account_id)]))

        cagr_map = {
            ("069500", "KOSPI"): {"cagr_pct": 8.0},
            ("153130", "KOSPI"): {"cagr_pct": 2.0},
        }
        random.seed(11)
        returns_map = {
            "069500.KS": [random.gauss(0.0004, 0.01) for _ in range(252)],
            "153130.KS": [random.gauss(0.0001, 0.0005) for _ in range(252)],
        }

        with (
            patch(
                "app.services.goal_recommendation_service.query_latest_position_map",
                AsyncMock(return_value={}),
            ),
            patch(
                "app.services.goal_recommendation_service.build_portfolio_overview",
                AsyncMock(return_value={"total_assets_krw": 5_000_000.0}),
            ),
            patch(
                "app.services.goal_recommendation_service.get_historical_returns",
                AsyncMock(return_value=cagr_map),
            ),
            patch(
                "app.services.goal_recommendation_service.fetch_yf_daily_returns",
                return_value=returns_map,
            ),
        ):
            result = await get_horizon_recommendations(None, mock_db, uuid.uuid4(), settings_row)

        rec = result.recommendations[0]
        stock_weight = next(i.weight for i in rec.recommended_items if i.ticker == "069500")
        assert stock_weight == pytest.approx(80.0, abs=1.0)
        assert sum(i.weight for i in rec.recommended_items) == pytest.approx(100.0, abs=0.5)
        assert "80%" in (rec.note or "")

    async def test_short_term_equity_floor_respects_custom_setting(self):
        """goal_short_term_equity_floor_pct를 낮게 설정하면 그 값이 실제로 반영된다."""
        settings_row = SimpleNamespace(
            goal_candidate_tickers=[
                {"ticker": "069500", "name": "KODEX 200", "market": "KOSPI", "asset_class": "EQUITY"},
                {"ticker": "153130", "name": "KODEX 단기채권", "market": "KOSPI", "asset_class": "CASH"},
            ],
            goal_max_weight_pct=None,
            goal_cagr_lookback_years=None,
            goal_short_term_equity_floor_pct=50.0,
        )
        account_id = uuid.uuid4()
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=_execute_result([("SHORT_TERM", "GENERAL", account_id)]))

        cagr_map = {
            ("069500", "KOSPI"): {"cagr_pct": 8.0},
            ("153130", "KOSPI"): {"cagr_pct": 2.0},
        }
        random.seed(11)
        returns_map = {
            "069500.KS": [random.gauss(0.0004, 0.01) for _ in range(252)],
            "153130.KS": [random.gauss(0.0001, 0.0005) for _ in range(252)],
        }

        with (
            patch(
                "app.services.goal_recommendation_service.query_latest_position_map",
                AsyncMock(return_value={}),
            ),
            patch(
                "app.services.goal_recommendation_service.build_portfolio_overview",
                AsyncMock(return_value={"total_assets_krw": 5_000_000.0}),
            ),
            patch(
                "app.services.goal_recommendation_service.get_historical_returns",
                AsyncMock(return_value=cagr_map),
            ),
            patch(
                "app.services.goal_recommendation_service.fetch_yf_daily_returns",
                return_value=returns_map,
            ),
        ):
            result = await get_horizon_recommendations(None, mock_db, uuid.uuid4(), settings_row)

        rec = result.recommendations[0]
        stock_weight = next(i.weight for i in rec.recommended_items if i.ticker == "069500")
        assert stock_weight == pytest.approx(50.0, abs=1.0)

    async def test_short_term_equity_floor_zero_disables_constraint(self):
        """goal_short_term_equity_floor_pct=0이면 하한 제약 없이 기존처럼 순수 최소분산으로 계산된다."""
        settings_row = SimpleNamespace(
            goal_candidate_tickers=[
                {"ticker": "069500", "name": "KODEX 200", "market": "KOSPI", "asset_class": "EQUITY"},
                {"ticker": "153130", "name": "KODEX 단기채권", "market": "KOSPI", "asset_class": "CASH"},
            ],
            goal_max_weight_pct=None,
            goal_cagr_lookback_years=None,
            goal_short_term_equity_floor_pct=0.0,
        )
        account_id = uuid.uuid4()
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=_execute_result([("SHORT_TERM", "GENERAL", account_id)]))

        cagr_map = {
            ("069500", "KOSPI"): {"cagr_pct": 8.0},
            ("153130", "KOSPI"): {"cagr_pct": 2.0},
        }
        random.seed(11)
        returns_map = {
            # 주식은 변동성을 크게 줘서 무제약 최소분산이면 비중이 낮게 나오도록 구성
            "069500.KS": [random.gauss(0.0004, 0.03) for _ in range(252)],
            "153130.KS": [random.gauss(0.0001, 0.0005) for _ in range(252)],
        }

        with (
            patch(
                "app.services.goal_recommendation_service.query_latest_position_map",
                AsyncMock(return_value={}),
            ),
            patch(
                "app.services.goal_recommendation_service.build_portfolio_overview",
                AsyncMock(return_value={"total_assets_krw": 5_000_000.0}),
            ),
            patch(
                "app.services.goal_recommendation_service.get_historical_returns",
                AsyncMock(return_value=cagr_map),
            ),
            patch(
                "app.services.goal_recommendation_service.fetch_yf_daily_returns",
                return_value=returns_map,
            ),
        ):
            result = await get_horizon_recommendations(None, mock_db, uuid.uuid4(), settings_row)

        rec = result.recommendations[0]
        stock_item = next((i for i in rec.recommended_items if i.ticker == "069500"), None)
        stock_weight = stock_item.weight if stock_item else 0.0
        assert stock_weight < 40.0
        assert rec.includes_cash_equivalent is True

    async def test_short_term_equity_floor_with_single_equity_candidate_raises_per_ticker_cap(self):
        """주식 후보가 1개뿐이어도(채권/현금성 실후보 없음) 설정된 비율까지 배분되도록 종목당 상한이
        동적으로 완화된다(기본 종목당 최대 비중 40%를 넘어설 수 있음)."""
        settings_row = SimpleNamespace(
            goal_candidate_tickers=[
                {"ticker": "069500", "name": "KODEX 200", "market": "KOSPI", "asset_class": "EQUITY"},
            ],
            goal_max_weight_pct=None,
            goal_cagr_lookback_years=None,
            goal_short_term_equity_floor_pct=None,
        )
        account_id = uuid.uuid4()
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=_execute_result([("SHORT_TERM", "GENERAL", account_id)]))

        cagr_map = {("069500", "KOSPI"): {"cagr_pct": 8.0}}
        random.seed(11)
        returns_map = {"069500.KS": [random.gauss(0.0004, 0.01) for _ in range(252)]}

        with (
            patch(
                "app.services.goal_recommendation_service.query_latest_position_map",
                AsyncMock(return_value={}),
            ),
            patch(
                "app.services.goal_recommendation_service.build_portfolio_overview",
                AsyncMock(return_value={"total_assets_krw": 5_000_000.0}),
            ),
            patch(
                "app.services.goal_recommendation_service.get_historical_returns",
                AsyncMock(return_value=cagr_map),
            ),
            patch(
                "app.services.goal_recommendation_service.fetch_yf_daily_returns",
                return_value=returns_map,
            ),
        ):
            result = await get_horizon_recommendations(None, mock_db, uuid.uuid4(), settings_row)

        rec = result.recommendations[0]
        stock_weight = next(i.weight for i in rec.recommended_items if i.ticker == "069500")
        assert stock_weight == pytest.approx(80.0, abs=1.0)

    async def test_same_horizon_different_tax_types_produce_separate_cards(self):
        """같은 기간(LONG_TERM)에 ISA 계좌와 해외전용 계좌가 함께 태그되면 세제유형별로 카드가 분리되고,
        각 카드는 시장 적합 후보(국내 vs 해외)로만 필터링된다."""
        settings_row = SimpleNamespace(
            goal_candidate_tickers=[
                {"ticker": "069500", "name": "KODEX 200", "market": "KOSPI", "asset_class": "EQUITY"},
                {"ticker": "SPY", "name": "SPDR S&P 500 ETF", "market": "NYSE", "asset_class": "EQUITY"},
            ],
            goal_max_weight_pct=None,
            goal_cagr_lookback_years=None,
        )
        isa_account_id = uuid.uuid4()
        overseas_account_id = uuid.uuid4()
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            return_value=_execute_result(
                [
                    ("LONG_TERM", "ISA", isa_account_id),
                    ("LONG_TERM", "OVERSEAS_DEDICATED", overseas_account_id),
                ]
            )
        )

        cagr_map = {
            ("069500", "KOSPI"): {"cagr_pct": 8.0},
            ("SPY", "NYSE"): {"cagr_pct": 10.0},
        }
        random.seed(9)
        returns_map = {
            "069500.KS": [random.gauss(0.0004, 0.008) for _ in range(252)],
            "SPY": [random.gauss(0.0005, 0.01) for _ in range(252)],
        }

        with (
            patch(
                "app.services.goal_recommendation_service.query_latest_position_map",
                AsyncMock(return_value={}),
            ),
            patch(
                "app.services.goal_recommendation_service.build_portfolio_overview",
                AsyncMock(return_value={"total_assets_krw": 3_000_000.0}),
            ),
            patch(
                "app.services.goal_recommendation_service.get_historical_returns",
                AsyncMock(return_value=cagr_map),
            ),
            patch(
                "app.services.goal_recommendation_service.fetch_yf_daily_returns",
                return_value=returns_map,
            ),
        ):
            result = await get_horizon_recommendations(None, mock_db, uuid.uuid4(), settings_row)

        assert len(result.recommendations) == 2
        by_tax_type = {r.tax_type: r for r in result.recommendations}
        assert set(by_tax_type) == {"ISA", "OVERSEAS_DEDICATED"}

        isa_rec = by_tax_type["ISA"]
        assert isa_rec.investment_horizon == "LONG_TERM"
        assert {item.market for item in isa_rec.recommended_items} <= {"KOSPI", "KOSDAQ", "KRX"}

        overseas_rec = by_tax_type["OVERSEAS_DEDICATED"]
        assert overseas_rec.investment_horizon == "LONG_TERM"
        assert all(item.market not in {"KOSPI", "KOSDAQ", "KRX"} for item in overseas_rec.recommended_items)

    async def test_pension_savings_and_irp_are_restricted_to_domestic_market(self):
        """연금저축펀드/IRP 계좌는 국내 후보만 사용해야 하므로 해외 후보는 옵티마이저에 전달되지 않는다."""
        settings_row = SimpleNamespace(
            goal_candidate_tickers=[
                {"ticker": "069500", "name": "KODEX 200", "market": "KOSPI", "asset_class": "EQUITY"},
                {"ticker": "SPY", "name": "SPDR S&P 500 ETF", "market": "NYSE", "asset_class": "EQUITY"},
            ],
            goal_max_weight_pct=None,
            goal_cagr_lookback_years=None,
        )
        pension_account_id = uuid.uuid4()
        irp_account_id = uuid.uuid4()
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            return_value=_execute_result(
                [
                    ("LONG_TERM", "PENSION_SAVINGS", pension_account_id),
                    ("LONG_TERM", "IRP", irp_account_id),
                ]
            )
        )

        cagr_map = {("069500", "KOSPI"): {"cagr_pct": 8.0}}
        get_historical_returns_mock = AsyncMock(return_value=cagr_map)

        with (
            patch(
                "app.services.goal_recommendation_service.query_latest_position_map",
                AsyncMock(return_value={}),
            ),
            patch(
                "app.services.goal_recommendation_service.build_portfolio_overview",
                AsyncMock(return_value={"total_assets_krw": 2_000_000.0}),
            ),
            patch(
                "app.services.goal_recommendation_service.get_historical_returns",
                get_historical_returns_mock,
            ),
        ):
            result = await get_horizon_recommendations(None, mock_db, uuid.uuid4(), settings_row)

        assert len(result.recommendations) == 2
        for rec in result.recommendations:
            assert rec.tax_type in {"PENSION_SAVINGS", "IRP"}
        for call in get_historical_returns_mock.call_args_list:
            queried_tickers = call.args[0]
            assert ("SPY", "NYSE") not in queried_tickers

    async def test_isa_prefers_overseas_index_tracking_krx_etfs(self):
        """ISA는 국내상장이지만 해외지수를 추종하는 ETF(나스닥100/S&P500/다우존스)를 우선하고,
        국내지수 추종 종목/ETF(KODEX 200/삼성전자)는 후보에서 제외한다.

        선호 후보를 3개로 구성한 것은 n=2일 때 기본 40% 캡이 1/n=50%로 완화되어 비중이
        (0.5, 0.5)로 강제되는 옵티마이저 코너케이스(risk_tolerance 반영 불가 note 발생)를
        피하기 위함 — `test_risk_tolerance_aggressive_raises_expected_return_vs_conservative`와
        동일한 이유.
        """
        settings_row = SimpleNamespace(
            goal_candidate_tickers=[
                {"ticker": "069500", "name": "KODEX 200", "market": "KOSPI", "asset_class": "EQUITY"},
                {"ticker": "005930", "name": "삼성전자", "market": "KOSPI", "asset_class": "EQUITY"},
                {"ticker": "133690", "name": "TIGER 미국나스닥100", "market": "KOSPI", "asset_class": "EQUITY"},
                {"ticker": "360750", "name": "TIGER 미국S&P500", "market": "KOSPI", "asset_class": "EQUITY"},
                {"ticker": "458730", "name": "TIGER 미국배당다우존스", "market": "KOSPI", "asset_class": "EQUITY"},
            ],
            goal_max_weight_pct=None,
            goal_cagr_lookback_years=None,
        )
        account_id = uuid.uuid4()
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=_execute_result([("LONG_TERM", "ISA", account_id)]))

        cagr_map = {
            ("069500", "KOSPI"): {"cagr_pct": 6.0},
            ("005930", "KOSPI"): {"cagr_pct": 7.0},
            ("133690", "KOSPI"): {"cagr_pct": 14.0},
            ("360750", "KOSPI"): {"cagr_pct": 9.0},
            ("458730", "KOSPI"): {"cagr_pct": 5.0},
        }
        random.seed(21)
        returns_map = {
            sym: [random.gauss(0.0005, 0.01) for _ in range(252)]
            for sym in ["069500.KS", "005930.KS", "133690.KS", "360750.KS", "458730.KS"]
        }
        get_historical_returns_mock = AsyncMock(return_value=cagr_map)

        with (
            patch(
                "app.services.goal_recommendation_service.query_latest_position_map",
                AsyncMock(return_value={}),
            ),
            patch(
                "app.services.goal_recommendation_service.build_portfolio_overview",
                AsyncMock(return_value={"total_assets_krw": 2_000_000.0}),
            ),
            patch(
                "app.services.goal_recommendation_service.get_historical_returns",
                get_historical_returns_mock,
            ),
            patch(
                "app.services.goal_recommendation_service.fetch_yf_daily_returns",
                return_value=returns_map,
            ),
        ):
            result = await get_horizon_recommendations(None, mock_db, uuid.uuid4(), settings_row)

        rec = result.recommendations[0]
        assert rec.tax_type == "ISA"
        queried_tickers = get_historical_returns_mock.call_args.args[0]
        assert set(queried_tickers) == {("133690", "KOSPI"), ("360750", "KOSPI"), ("458730", "KOSPI")}
        assert {item.ticker for item in rec.recommended_items} <= {"133690", "360750", "458730"}

    async def test_general_prefers_domestic_index_tracking_candidates(self):
        """일반 계좌는 반대로 국내지수 추종 종목/ETF를 우선하고 해외지수 추종 ETF는 제외한다."""
        settings_row = SimpleNamespace(
            goal_candidate_tickers=[
                {"ticker": "069500", "name": "KODEX 200", "market": "KOSPI", "asset_class": "EQUITY"},
                {"ticker": "005930", "name": "삼성전자", "market": "KOSPI", "asset_class": "EQUITY"},
                {"ticker": "000660", "name": "SK하이닉스", "market": "KOSPI", "asset_class": "EQUITY"},
                {"ticker": "133690", "name": "TIGER 미국나스닥100", "market": "KOSPI", "asset_class": "EQUITY"},
                {"ticker": "360750", "name": "TIGER 미국S&P500", "market": "KOSPI", "asset_class": "EQUITY"},
            ],
            goal_max_weight_pct=None,
            goal_cagr_lookback_years=None,
        )
        account_id = uuid.uuid4()
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=_execute_result([("LONG_TERM", "GENERAL", account_id)]))

        cagr_map = {
            ("069500", "KOSPI"): {"cagr_pct": 6.0},
            ("005930", "KOSPI"): {"cagr_pct": 7.0},
            ("000660", "KOSPI"): {"cagr_pct": 8.0},
            ("133690", "KOSPI"): {"cagr_pct": 14.0},
            ("360750", "KOSPI"): {"cagr_pct": 9.0},
        }
        random.seed(23)
        returns_map = {
            sym: [random.gauss(0.0005, 0.01) for _ in range(252)]
            for sym in ["069500.KS", "005930.KS", "000660.KS", "133690.KS", "360750.KS"]
        }
        get_historical_returns_mock = AsyncMock(return_value=cagr_map)

        with (
            patch(
                "app.services.goal_recommendation_service.query_latest_position_map",
                AsyncMock(return_value={}),
            ),
            patch(
                "app.services.goal_recommendation_service.build_portfolio_overview",
                AsyncMock(return_value={"total_assets_krw": 2_000_000.0}),
            ),
            patch(
                "app.services.goal_recommendation_service.get_historical_returns",
                get_historical_returns_mock,
            ),
            patch(
                "app.services.goal_recommendation_service.fetch_yf_daily_returns",
                return_value=returns_map,
            ),
        ):
            result = await get_horizon_recommendations(None, mock_db, uuid.uuid4(), settings_row)

        rec = result.recommendations[0]
        assert rec.tax_type == "GENERAL"
        queried_tickers = get_historical_returns_mock.call_args.args[0]
        assert set(queried_tickers) == {("069500", "KOSPI"), ("005930", "KOSPI"), ("000660", "KOSPI")}
        assert {item.ticker for item in rec.recommended_items} <= {"069500", "005930", "000660"}

    async def test_isa_auto_augments_with_curated_etfs_when_none_registered(self):
        """ISA인데 등록된 후보 전부 국내지수 추종이면(해외지수 추종 ETF 없음) 국내 개별주식(005930 등)을
        그대로 노출하는 대신 큐레이션 해외지수 추종 ETF로 자동 보강해 추천한다."""
        settings_row = SimpleNamespace(
            goal_candidate_tickers=[
                {"ticker": "069500", "name": "KODEX 200", "market": "KOSPI", "asset_class": "EQUITY"},
                {"ticker": "005930", "name": "삼성전자", "market": "KOSPI", "asset_class": "EQUITY"},
            ],
            goal_max_weight_pct=None,
            goal_cagr_lookback_years=None,
        )
        account_id = uuid.uuid4()
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=_execute_result([("LONG_TERM", "ISA", account_id)]))

        cagr_map = {
            ("133690", "KOSPI"): {"cagr_pct": 14.0},
            ("360750", "KOSPI"): {"cagr_pct": 9.0},
            ("458730", "KOSPI"): {"cagr_pct": 7.0},
        }
        random.seed(29)
        returns_map = {
            sym: [random.gauss(0.0005, 0.01) for _ in range(252)] for sym in ["133690.KS", "360750.KS", "458730.KS"]
        }
        get_historical_returns_mock = AsyncMock(return_value=cagr_map)

        with (
            patch(
                "app.services.goal_recommendation_service.query_latest_position_map",
                AsyncMock(return_value={}),
            ),
            patch(
                "app.services.goal_recommendation_service.build_portfolio_overview",
                AsyncMock(return_value={"total_assets_krw": 2_000_000.0}),
            ),
            patch(
                "app.services.goal_recommendation_service.get_historical_returns",
                get_historical_returns_mock,
            ),
            patch(
                "app.services.goal_recommendation_service.fetch_yf_daily_returns",
                return_value=returns_map,
            ),
        ):
            result = await get_horizon_recommendations(None, mock_db, uuid.uuid4(), settings_row)

        rec = result.recommendations[0]
        assert rec.recommended_items
        queried_tickers = get_historical_returns_mock.call_args.args[0]
        assert set(queried_tickers) == {("133690", "KOSPI"), ("360750", "KOSPI"), ("458730", "KOSPI")}
        assert {item.ticker for item in rec.recommended_items} <= {"133690", "360750", "458730"}
        assert "005930" not in {item.ticker for item in rec.recommended_items}
        assert rec.note is not None
        assert "해외지수" in rec.note
        assert "자동 등록" in rec.note

        # 자동 보강된 큐레이션 ETF가 "후보 ETF 관리" 화면에도 반영되도록 실제로 등록·커밋된다
        saved_tickers = {c["ticker"] for c in settings_row.goal_candidate_tickers}
        assert {"133690", "360750", "458730"} <= saved_tickers
        mock_db.commit.assert_awaited()

    async def test_multiple_combos_preserve_order_after_parallelized_io(self):
        """`_build_horizon_result` 호출을 asyncio.gather로 동시 실행하도록 바꾼 뒤에도, DB 의존
        단계(overview 조회)는 여전히 (InvestmentHorizon, AccountTaxType) enum 순서대로 순차 실행되고
        최종 결과 순서도 그 순서를 유지해야 한다."""
        settings_row = SimpleNamespace(
            goal_candidate_tickers=[
                {"ticker": "153130", "name": "KODEX 단기채권", "market": "KOSPI", "asset_class": "CASH"},
                {"ticker": "114260", "name": "KODEX 국고채3년", "market": "KOSPI", "asset_class": "BOND"},
            ],
            goal_max_weight_pct=None,
            goal_cagr_lookback_years=None,
        )
        mid_account_id = uuid.uuid4()
        short_account_id = uuid.uuid4()
        mock_db = AsyncMock()
        # SHORT_TERM보다 나중인 MID_TERM 조합을 먼저 반환해도, 결과는 InvestmentHorizon enum
        # 순서(SHORT_TERM → MID_TERM)를 따라야 한다.
        mock_db.execute = AsyncMock(
            return_value=_execute_result(
                [
                    ("MID_TERM", "GENERAL", mid_account_id),
                    ("SHORT_TERM", "GENERAL", short_account_id),
                ]
            )
        )

        cagr_map = {
            ("153130", "KOSPI"): {"cagr_pct": 2.0},
            ("114260", "KOSPI"): {"cagr_pct": 3.0},
        }
        random.seed(11)
        returns_map = {
            "153130.KS": [random.gauss(0.0001, 0.0005) for _ in range(252)],
            "114260.KS": [random.gauss(0.00015, 0.001) for _ in range(252)],
        }
        overview_mock = AsyncMock(return_value={"total_assets_krw": 5_000_000.0})

        with (
            patch(
                "app.services.goal_recommendation_service.query_latest_position_map",
                AsyncMock(return_value={}),
            ),
            patch("app.services.goal_recommendation_service.build_portfolio_overview", overview_mock),
            patch(
                "app.services.goal_recommendation_service.get_historical_returns",
                AsyncMock(return_value=cagr_map),
            ),
            patch(
                "app.services.goal_recommendation_service.fetch_yf_daily_returns",
                return_value=returns_map,
            ),
        ):
            result = await get_horizon_recommendations(None, mock_db, uuid.uuid4(), settings_row)

        assert [(r.investment_horizon, r.tax_type) for r in result.recommendations] == [
            ("SHORT_TERM", "GENERAL"),
            ("MID_TERM", "GENERAL"),
        ]
        overview_account_ids = [call.kwargs["account_ids"] for call in overview_mock.call_args_list]
        assert overview_account_ids == [[short_account_id], [mid_account_id]]

    async def test_does_not_cache_when_any_combo_has_no_recommended_items(self):
        """조합 중 하나라도 recommended_items가 비어 있으면(예: Yahoo 서킷브레이커로 해외전용
        조합만 시세 조회 실패) 전체 응답을 캐싱하지 않는다 — 그렇지 않으면 나머지 정상 조합까지
        TTL 동안 이 실패 상태로 함께 얼어붙는다."""
        settings_row = SimpleNamespace(
            goal_candidate_tickers=[
                {"ticker": "SPY", "name": "SPDR S&P 500 ETF", "market": "NYSE", "asset_class": "EQUITY"},
                {"ticker": "QQQ", "name": "Invesco QQQ Trust", "market": "NASDAQ", "asset_class": "EQUITY"},
            ],
            goal_max_weight_pct=None,
            goal_cagr_lookback_years=None,
        )
        account_id = uuid.uuid4()
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=_execute_result([("LONG_TERM", "OVERSEAS_DEDICATED", account_id)]))
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)

        with (
            patch(
                "app.services.goal_recommendation_service.query_latest_position_map",
                AsyncMock(return_value={}),
            ),
            patch(
                "app.services.goal_recommendation_service.build_portfolio_overview",
                AsyncMock(return_value={"total_assets_krw": 5_000_000.0}),
            ),
            patch(
                "app.services.goal_recommendation_service.get_historical_returns",
                AsyncMock(return_value={("SPY", "NYSE"): {"cagr_pct": 10.0}, ("QQQ", "NASDAQ"): {"cagr_pct": 15.0}}),
            ),
            patch(
                "app.services.goal_recommendation_service.fetch_yf_daily_returns",
                return_value={},  # Yahoo 서킷브레이커 오픈 상황 시뮬레이션 — 일별수익률 조회 실패
            ),
        ):
            result = await get_horizon_recommendations(mock_redis, mock_db, uuid.uuid4(), settings_row)

        assert len(result.recommendations) == 1
        assert result.recommendations[0].recommended_items == []
        mock_redis.setex.assert_not_called()

    async def test_caches_when_all_combos_have_recommended_items(self):
        """모든 조합이 정상적으로 추천을 생성하면 응답 전체를 캐싱한다."""
        settings_row = SimpleNamespace(
            goal_candidate_tickers=[
                {"ticker": "SPY", "name": "SPDR S&P 500 ETF", "market": "NYSE", "asset_class": "EQUITY"},
                {"ticker": "QQQ", "name": "Invesco QQQ Trust", "market": "NASDAQ", "asset_class": "EQUITY"},
            ],
            goal_max_weight_pct=None,
            goal_cagr_lookback_years=None,
        )
        account_id = uuid.uuid4()
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=_execute_result([("LONG_TERM", "OVERSEAS_DEDICATED", account_id)]))
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        random.seed(13)
        returns_map = {sym: [random.gauss(0.0005, 0.01) for _ in range(252)] for sym in ["SPY", "QQQ"]}

        with (
            patch(
                "app.services.goal_recommendation_service.query_latest_position_map",
                AsyncMock(return_value={}),
            ),
            patch(
                "app.services.goal_recommendation_service.build_portfolio_overview",
                AsyncMock(return_value={"total_assets_krw": 5_000_000.0}),
            ),
            patch(
                "app.services.goal_recommendation_service.get_historical_returns",
                AsyncMock(return_value={("SPY", "NYSE"): {"cagr_pct": 10.0}, ("QQQ", "NASDAQ"): {"cagr_pct": 15.0}}),
            ),
            patch(
                "app.services.goal_recommendation_service.fetch_yf_daily_returns",
                return_value=returns_map,
            ),
        ):
            result = await get_horizon_recommendations(mock_redis, mock_db, uuid.uuid4(), settings_row)

        assert len(result.recommendations) == 1
        assert result.recommendations[0].recommended_items
        mock_redis.setex.assert_awaited_once()
