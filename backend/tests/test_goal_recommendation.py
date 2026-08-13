"""goal_return_solver.py / goal_recommendation_service.py 단위 테스트."""

from __future__ import annotations

import json
import random
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.goal_age_recommendation_service import (
    _AGE_GROUP_PROFILE,
    age_group_from_birth_year,
    get_age_based_recommendation,
)
from app.services.goal_candidate_service import _seed_candidate_tickers, detect_duplicate_tracking_index_note
from app.services.goal_portfolio_optimizer import compute_weighted_expected_metrics
from app.services.goal_recommendation_service import (
    _apply_index_region_preference,
    _compute_overall_class_bounds,
    _fetch_dividend_yields,
    _matches_index_region_preference,
    _optimize_goal_portfolio,
    _persist_added_candidates,
    _suggest_for_dividend_goal,
    compute_portfolio_expected_metrics,
    compute_recommendation_drift,
    existing_items_from_positions,
    get_goal_recommendation,
    get_horizon_recommendations,
)
from app.services.goal_return_solver import (
    months_until_year_end,
    solve_required_annual_return_pct,
    solve_required_monthly_deposit,
)
from app.services.recommendation_universe import (
    MAX_GOAL_CANDIDATE_TICKERS,
    RECOMMENDATION_UNIVERSE,
    guess_asset_class,
    guess_tracking_index,
    resolve_index_region,
    resolve_tracking_index,
)


@pytest.fixture(autouse=True)
def _mock_market_signal():
    """`get_market_signal`을 GREEN/LIVE로 고정해 실제 외부 API(FRED 등) 호출을 막는다.

    GREEN은 `_SIGNAL_FRONTIER_DAMPENING`에 없어 감쇠 배율 1.0(기존 동작과 동일)이므로 이 파일의
    다른 모든 기존 테스트 결과에 영향을 주지 않는다. 시장 신호 반영 자체를 검증하는 테스트는
    이 fixture 범위 안에서 `patch(...)`로 개별 재정의한다.
    """
    with patch(
        "app.services.goal_recommendation_service.get_market_signal",
        AsyncMock(return_value={"composite_level": "GREEN", "data_freshness": "LIVE"}),
    ):
        yield


@pytest.fixture(autouse=True)
def _mock_dividend_yields():
    """`_fetch_dividend_yields`를 빈 dict로 고정해 실제 외부 API(Naver/Yahoo) 호출을 막는다.

    배당 목표(A1)를 검증하는 `TestGetGoalRecommendation`의 일부 테스트와 기간별 배당 반영(Part 3)을
    검증하는 테스트는 이 fixture 범위 안에서 `patch(...)`로 개별 재정의한다.

    `goal_age_recommendation_service.py`(연령대별 추천, 2026-08-13 분리)가 이 심볼을
    `goal_recommendation_service`에서 import해 자기 모듈 네임스페이스에 별도로 바인딩하므로,
    호출 시점 룩업 대상인 두 경로 모두 patch해야 한다 — 하나만 patch하면 나머지 경로가 실제
    Naver/Yahoo API를 호출한다.
    """
    with (
        patch(
            "app.services.goal_recommendation_service._fetch_dividend_yields",
            AsyncMock(return_value={}),
        ),
        patch(
            "app.services.goal_age_recommendation_service._fetch_dividend_yields",
            AsyncMock(return_value={}),
        ),
    ):
        yield


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


class TestSolveRequiredMonthlyDeposit:
    def test_known_case_matches_fv_formula(self):
        pv, annual_return_pct, n = 10_000_000.0, 6.0, 120
        r_m = annual_return_pct / 100 / 12
        pmt = 500_000.0
        goal_amount = pv * (1 + r_m) ** n + pmt * (((1 + r_m) ** n - 1) / r_m)

        solved = solve_required_monthly_deposit(pv, annual_return_pct, n, goal_amount)

        assert solved == pytest.approx(pmt, abs=1.0)

    def test_zero_return_matches_linear_formula(self):
        pv, n, goal_amount = 10_000_000.0, 60, 40_000_000.0
        solved = solve_required_monthly_deposit(pv, 0.0, n, goal_amount)
        assert solved == pytest.approx((goal_amount - pv) / n, abs=0.01)

    def test_already_sufficient_returns_zero(self):
        solved = solve_required_monthly_deposit(
            pv=200_000_000.0, annual_return_pct=6.0, n_months=12, goal_amount=100_000_000.0
        )
        assert solved == 0.0

    def test_higher_assumed_return_lowers_required_deposit(self):
        low = solve_required_monthly_deposit(pv=0.0, annual_return_pct=4.0, n_months=120, goal_amount=100_000_000.0)
        high = solve_required_monthly_deposit(pv=0.0, annual_return_pct=10.0, n_months=120, goal_amount=100_000_000.0)
        assert high < low


class TestMonthsUntilYearEnd:
    def test_future_year_is_positive(self):
        from datetime import date

        assert months_until_year_end(date.today().year + 5) > 0

    def test_past_year_is_non_positive(self):
        from datetime import date

        assert months_until_year_end(date.today().year - 5) <= 0


class TestComputeOverallClassBounds:
    """`_compute_overall_class_bounds()` — 전체 자산 기준 추천 전용 채권/현금성 비중 상한
    (`UserSettings.goal_bond_ceiling_pct`/`goal_cash_ceiling_pct`) → `class_bounds` 변환."""

    def test_no_ceilings_set_returns_none(self):
        settings_row = SimpleNamespace(goal_bond_ceiling_pct=None, goal_cash_ceiling_pct=None)
        assert _compute_overall_class_bounds(settings_row) is None

    def test_bond_ceiling_only(self):
        settings_row = SimpleNamespace(goal_bond_ceiling_pct=30.0, goal_cash_ceiling_pct=None)
        assert _compute_overall_class_bounds(settings_row) == {"BOND": (0.0, 0.3)}

    def test_both_ceilings_set(self):
        settings_row = SimpleNamespace(goal_bond_ceiling_pct=30.0, goal_cash_ceiling_pct=20.0)
        assert _compute_overall_class_bounds(settings_row) == {"BOND": (0.0, 0.3), "CASH": (0.0, 0.2)}

    def test_none_settings_row_returns_none(self):
        assert _compute_overall_class_bounds(None) is None


class TestOptimizeGoalPortfolio:
    def test_insufficient_candidates_returns_note(self):
        items, expected, _, note = _optimize_goal_portfolio(
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
        items, expected, _, note = _optimize_goal_portfolio(
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

        items, expected, _, note = _optimize_goal_portfolio(
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

        items, _, _, note = _optimize_goal_portfolio(
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

    def test_dividend_floor_shifts_weight_toward_high_yield_candidate(self):
        """dividend_yields+required_dividend_yield_pct를 주면 가중평균 배당수익률이 목표 이상이 되도록
        고배당 종목 비중이 강제된다 — 배당 목표를 최적화 입력으로 반영하는지 검증하는 핵심 테스트."""
        random.seed(9)
        returns_map = {
            "GROWTH": [random.gauss(0.0006, 0.01) for _ in range(252)],
            "DIVIDEND": [random.gauss(0.0003, 0.01) for _ in range(252)],
        }
        tickers = [("GROWTH", "성장주 ETF", "NASDAQ"), ("DIVIDEND", "고배당 ETF", "NASDAQ")]

        items, _, _, note = _optimize_goal_portfolio(
            symbols=["GROWTH", "DIVIDEND"],
            tickers=tickers,
            cagr_pct=[8.0, 6.0],
            returns_map=returns_map,
            required_return_pct=-50.0,
            max_weight=1.0,
            dividend_yields=[0.5, 6.0],
            required_dividend_yield_pct=4.0,
        )

        assert note is None
        dividend_weight = next(i["weight"] for i in items if i["ticker"] == "DIVIDEND")
        # 4%를 채우려면 최소 (4-0.5)/(6-0.5) ≈ 63.6% 이상이 DIVIDEND에 배분돼야 한다
        assert dividend_weight >= 63.0

    def test_dividend_floor_unreachable_falls_back_with_note_but_still_recommends(self):
        """큐레이션 후보만으로 배당 목표를 달성할 수 없으면 제약을 적용하지 않고(fail-soft) note로
        안내하되, 자산 목표 기준 추천 자체는 계속 반환한다."""
        random.seed(10)
        returns_map = {
            "A": [random.gauss(0.0004, 0.01) for _ in range(252)],
            "B": [random.gauss(0.0003, 0.01) for _ in range(252)],
        }
        tickers = [("A", "A", "NASDAQ"), ("B", "B", "NASDAQ")]

        items, expected, _, note = _optimize_goal_portfolio(
            symbols=["A", "B"],
            tickers=tickers,
            cagr_pct=[8.0, 6.0],
            returns_map=returns_map,
            required_return_pct=-50.0,
            dividend_yields=[1.0, 1.5],
            required_dividend_yield_pct=10.0,  # 후보 중 최대 배당수익률(1.5%)보다 훨씬 높아 달성 불가
        )

        assert items
        assert expected is not None
        assert note is not None
        assert "배당 목표" in note

    def test_dividend_floor_not_applied_when_required_pct_none(self):
        """required_dividend_yield_pct가 None이면(배당 목표 미설정) dividend_yields가 주어져도
        제약을 적용하지 않는다 — 기존 동작(배당 목표 미반영) 그대로 유지."""
        random.seed(11)
        returns_map = {
            "A": [random.gauss(0.0004, 0.01) for _ in range(252)],
            "B": [random.gauss(0.0003, 0.01) for _ in range(252)],
        }
        tickers = [("A", "A", "NASDAQ"), ("B", "B", "NASDAQ")]

        items, _, _, note = _optimize_goal_portfolio(
            symbols=["A", "B"],
            tickers=tickers,
            cagr_pct=[8.0, 6.0],
            returns_map=returns_map,
            required_return_pct=-50.0,
            dividend_yields=[1.0, 8.0],
            required_dividend_yield_pct=None,
        )

        assert items
        assert note is None

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

        conservative_items, conservative_expected, _, conservative_note = _optimize_goal_portfolio(
            symbols=["A", "B", "C"],
            tickers=tickers,
            cagr_pct=cagr_pct,
            returns_map=returns_map,
            required_return_pct=5.0,
            risk_tolerance="CONSERVATIVE",
        )
        balanced_items, balanced_expected, _, balanced_note = _optimize_goal_portfolio(
            symbols=["A", "B", "C"],
            tickers=tickers,
            cagr_pct=cagr_pct,
            returns_map=returns_map,
            required_return_pct=5.0,
            risk_tolerance="BALANCED",
        )
        aggressive_items, aggressive_expected, _, aggressive_note = _optimize_goal_portfolio(
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

    def test_market_signal_level_dampens_frontier_target(self):
        """시장 위험 신호가 YELLOW/RED이면 frontier_frac이 감쇠되어 GREEN/None보다 보수적인
        (기대수익률이 더 낮은) 추천으로 수렴해야 한다 — RED가 YELLOW보다 더 보수적이어야 한다."""
        random.seed(4)
        returns_map = {
            "A": [random.gauss(0.0003, 0.001) for _ in range(252)],
            "B": [random.gauss(0.0006, 0.006) for _ in range(252)],
            "C": [random.gauss(0.0006, 0.02) for _ in range(252)],
        }
        tickers = [("A", "A", "NASDAQ"), ("B", "B", "NASDAQ"), ("C", "C", "NASDAQ")]
        cagr_pct = [3.0, 6.0, 15.0]

        def _run(market_signal_level: str | None) -> tuple[float, str | None]:
            _, expected, _, note = _optimize_goal_portfolio(
                symbols=["A", "B", "C"],
                tickers=tickers,
                cagr_pct=cagr_pct,
                returns_map=returns_map,
                required_return_pct=5.0,
                risk_tolerance="AGGRESSIVE",
                market_signal_level=market_signal_level,
            )
            return expected, note

        green_expected, green_note = _run(None)
        yellow_expected, yellow_note = _run("YELLOW")
        red_expected, red_note = _run("RED")

        assert red_expected < yellow_expected < green_expected
        assert green_note is None
        assert yellow_note is not None
        assert "시장 위험 신호(YELLOW)" in yellow_note
        assert red_note is not None
        assert "시장 위험 신호(RED)" in red_note

    def test_market_signal_level_no_effect_on_conservative(self):
        """CONSERVATIVE는 frontier_frac이 이미 0이라 시장 신호 감쇠와 무관하게 결과가 동일해야 한다."""
        random.seed(4)
        returns_map = {
            "A": [random.gauss(0.0003, 0.001) for _ in range(252)],
            "B": [random.gauss(0.0006, 0.006) for _ in range(252)],
        }
        tickers = [("A", "A", "NASDAQ"), ("B", "B", "NASDAQ")]
        cagr_pct = [3.0, 6.0]

        no_signal_items, no_signal_expected, _, no_signal_note = _optimize_goal_portfolio(
            symbols=["A", "B"],
            tickers=tickers,
            cagr_pct=cagr_pct,
            returns_map=returns_map,
            required_return_pct=2.0,
            risk_tolerance="CONSERVATIVE",
        )
        red_items, red_expected, _, red_note = _optimize_goal_portfolio(
            symbols=["A", "B"],
            tickers=tickers,
            cagr_pct=cagr_pct,
            returns_map=returns_map,
            required_return_pct=2.0,
            risk_tolerance="CONSERVATIVE",
            market_signal_level="RED",
        )

        assert no_signal_expected == pytest.approx(red_expected)
        assert no_signal_items == red_items
        assert no_signal_note == red_note

    def test_risk_tolerance_no_spread_returns_note(self):
        """후보 종목의 CAGR이 전부 동일하면 리스크 성향을 바꿔도 반영할 여지가 없으므로,
        note로 안내하고(크래시/실패 없이) 여전히 추천을 반환해야 한다."""
        random.seed(5)
        returns_map = {
            "A": [random.gauss(0.0003, 0.006) for _ in range(252)],
            "B": [random.gauss(0.0006, 0.02) for _ in range(252)],
        }
        tickers = [("A", "A", "NASDAQ"), ("B", "B", "NASDAQ")]

        items, expected, _, note = _optimize_goal_portfolio(
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

        items, _, _, note = _optimize_goal_portfolio(
            symbols=["SAFE", "STOCK"],
            tickers=tickers,
            cagr_pct=[3.0, 8.0],
            returns_map=returns_map,
            required_return_pct=-50.0,
            asset_classes=["OTHER", "EQUITY"],
            class_bounds={"EQUITY": (0.8, 1.0)},
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

        items, _, _, note = _optimize_goal_portfolio(
            symbols=["A", "B"],
            tickers=tickers,
            cagr_pct=[3.0, 8.0],
            returns_map=returns_map,
            required_return_pct=-50.0,
            asset_classes=["EQUITY", "EQUITY"],
            class_bounds={"EQUITY": (0.8, 1.0)},
        )

        assert note is None
        assert sum(i["weight"] for i in items) == pytest.approx(100.0, abs=0.1)

    def test_equity_ceiling_forces_maximum_equity_weight(self):
        """is_equity+equity_ceiling을 주면(IRP 안전자산 하한 전용) 저변동 주식 쏠림이 상한으로
        억제되고 안전자산이 그만큼 채워진다 — equity_floor와 대칭.

        후보를 3개(주식 2개 + 안전자산 1개)로 구성한 것은 n=2일 때 기본 40% 상한이 1/n=50%로
        완화되어 주식 종목당 상한이 equity_ceiling(70%)보다 낮아지는 코너케이스를 피하기 위함 —
        `test_equity_floor_zero_disables_constraint`와 동일한 이유.
        """
        random.seed(29)
        returns_map = {
            "STOCK1": [random.gauss(0.0001, 0.0005) for _ in range(252)],  # 매우 저변동 — 무제한이면 쏠림
            "STOCK2": [random.gauss(0.00012, 0.0006) for _ in range(252)],
            "SAFE": [random.gauss(0.0004, 0.01) for _ in range(252)],
        }
        tickers = [("STOCK1", "주식1", "KOSPI"), ("STOCK2", "주식2", "KOSPI"), ("SAFE", "안전자산", "KOSPI")]

        items, _, _, note = _optimize_goal_portfolio(
            symbols=["STOCK1", "STOCK2", "SAFE"],
            tickers=tickers,
            cagr_pct=[8.0, 8.0, 3.0],
            returns_map=returns_map,
            required_return_pct=-50.0,
            asset_classes=["EQUITY", "EQUITY", "OTHER"],
            class_bounds={"EQUITY": (0.0, 0.7)},
        )

        assert note is None
        equity_weight = sum(i["weight"] for i in items if i["ticker"] in {"STOCK1", "STOCK2"})
        assert equity_weight == pytest.approx(70.0, abs=1.0)

    def test_equity_ceiling_ignored_when_all_candidates_are_equity(self):
        """후보가 전부 주식이면 비교 대상이 없어 제약이 무의미하므로 무시되고 일반 최소분산으로 계산된다."""
        random.seed(31)
        returns_map = {
            "A": [random.gauss(0.0002, 0.002) for _ in range(252)],
            "B": [random.gauss(0.0004, 0.01) for _ in range(252)],
        }
        tickers = [("A", "A", "KOSPI"), ("B", "B", "KOSPI")]

        items, _, _, note = _optimize_goal_portfolio(
            symbols=["A", "B"],
            tickers=tickers,
            cagr_pct=[3.0, 8.0],
            returns_map=returns_map,
            required_return_pct=-50.0,
            asset_classes=["EQUITY", "EQUITY"],
            class_bounds={"EQUITY": (0.0, 0.7)},
        )

        assert note is None
        assert sum(i["weight"] for i in items) == pytest.approx(100.0, abs=0.1)

    def test_equity_ceiling_one_disables_constraint(self):
        """equity_ceiling=1.0이면 상한이 사실상 없는 것과 같아(안전자산 하한 0%) 일반 최소분산
        결과와 동일해야 한다 — equity_floor=0의 대칭 케이스."""
        random.seed(6)
        returns_map = {
            "SAFE1": [random.gauss(0.0001, 0.0005) for _ in range(252)],
            "SAFE2": [random.gauss(0.00012, 0.0006) for _ in range(252)],
            "STOCK": [random.gauss(0.0004, 0.01) for _ in range(252)],
        }
        tickers = [("SAFE1", "안전자산1", "KOSPI"), ("SAFE2", "안전자산2", "KOSPI"), ("STOCK", "주식", "KOSPI")]

        items, _, _, note = _optimize_goal_portfolio(
            symbols=["SAFE1", "SAFE2", "STOCK"],
            tickers=tickers,
            cagr_pct=[3.0, 3.0, 8.0],
            returns_map=returns_map,
            required_return_pct=-50.0,
            asset_classes=["OTHER", "OTHER", "EQUITY"],
            class_bounds={"EQUITY": (0.0, 1.0)},
        )

        assert note is None
        stock_weight = next(i["weight"] for i in items if i["ticker"] == "STOCK")
        assert stock_weight < 40.0  # 고변동 STOCK 쪽 비중이 억제되어야 함 (상한 제약 없음)

    def test_equity_ceiling_with_single_non_equity_candidate_raises_per_ticker_cap(self):
        """안전자산 하한(1-equity_ceiling)이 기본 종목당 최대 비중(40%)보다 크면, 안전자산 후보가
        1개뿐이어도 그 하한을 채울 수 있도록 종목당 상한이 동적으로 완화된다 — equity_floor의
        equity_cap 완화 로직과 대칭."""
        random.seed(37)
        returns_map = {
            "STOCK1": [random.gauss(0.0004, 0.01) for _ in range(252)],
            "STOCK2": [random.gauss(0.0004, 0.01) for _ in range(252)],
            "SAFE": [random.gauss(0.0001, 0.0005) for _ in range(252)],
        }
        tickers = [("STOCK1", "주식1", "KOSPI"), ("STOCK2", "주식2", "KOSPI"), ("SAFE", "안전자산", "KOSPI")]

        items, _, _, note = _optimize_goal_portfolio(
            symbols=["STOCK1", "STOCK2", "SAFE"],
            tickers=tickers,
            cagr_pct=[8.0, 8.0, 3.0],
            returns_map=returns_map,
            required_return_pct=-50.0,
            asset_classes=["EQUITY", "EQUITY", "OTHER"],
            class_bounds={"EQUITY": (0.0, 0.5)},  # 안전자산 하한 50% > 기본 종목당 상한 40%
        )

        assert note is None
        safe_weight = next(i["weight"] for i in items if i["ticker"] == "SAFE")
        assert safe_weight == pytest.approx(50.0, abs=1.0)

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

        items, _, _, note = _optimize_goal_portfolio(
            symbols=["SAFE1", "SAFE2", "STOCK"],
            tickers=tickers,
            cagr_pct=[3.0, 3.0, 8.0],
            returns_map=returns_map,
            required_return_pct=-50.0,
            asset_classes=["OTHER", "OTHER", "EQUITY"],
            class_bounds={"EQUITY": (0.0, 1.0)},
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

    def test_bond_mixed_fund_with_country_prefix_detected(self):
        """'미국채'처럼 국가명+채권 축약형이 붙은 채권혼합형 펀드명도 BOND로 잡혀야 한다
        (IRP 안전자산 30% 하한 계산에서 실보유 채권혼합 ETF가 위험자산으로 오분류되는 것을 방지)."""
        assert guess_asset_class("ACE 미국나스닥100미국채혼합50액티브") == "BOND"

    def test_cash_keyword_detected(self):
        assert guess_asset_class("KODEX 단기채권") == "CASH"
        assert guess_asset_class("TIGER CD금리투자KIS(합성)") == "CASH"


class TestMatchesIndexRegionPreference:
    """`_apply_index_region_preference`(등록 후보 필터링)와 `_suggest_for_dividend_goal`
    (배당목표 미달성 시 제안)이 공유하는 지역선호 판별 헬퍼 — 한쪽만 지역선호를 지키고 다른
    쪽은 무시하는 비일관성(실제 프로덕션에서 재현된 버그: GENERAL 계좌에 배당목표 미달성 시
    해외지수 추종 ETF가 "후보에 추가" 제안으로 새어 들어감)을 막기 위한 공용 규칙."""

    def test_general_rejects_overseas_tracking_equity_even_if_krx_listed(self):
        c = {"ticker": "360750", "name": "TIGER 미국S&P500", "market": "KOSPI", "asset_class": "EQUITY"}
        assert _matches_index_region_preference(c, "GENERAL") is False

    def test_general_accepts_domestic_tracking_equity(self):
        c = {"ticker": "069500", "name": "KODEX 200", "market": "KOSPI", "asset_class": "EQUITY"}
        assert _matches_index_region_preference(c, "GENERAL") is True

    def test_isa_accepts_overseas_tracking_equity(self):
        c = {"ticker": "360750", "name": "TIGER 미국S&P500", "market": "KOSPI", "asset_class": "EQUITY"}
        assert _matches_index_region_preference(c, "ISA") is True

    def test_overseas_dedicated_rejects_krx_listed_even_if_overseas_tracking(self):
        c = {
            "ticker": "360750",
            "name": "TIGER 미국S&P500",
            "market": "KOSPI",
            "asset_class": "EQUITY",
            "index_region": "OVERSEAS",
        }
        assert _matches_index_region_preference(c, "OVERSEAS_DEDICATED") is False

    def test_non_equity_always_matches_regardless_of_region(self):
        c = {"ticker": "360750", "name": "TIGER 미국S&P500", "market": "KOSPI", "asset_class": "CASH"}
        assert _matches_index_region_preference(c, "GENERAL") is True
        assert _matches_index_region_preference(c, "ISA") is True


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
        assert tickers >= {"133690", "360750", "458730", "446720"}  # 큐레이션 해외지수 추종 ETF로 보강됨
        assert "153130" in tickers  # CASH 후보는 영향받지 않고 그대로 유지
        assert note is not None
        assert "자동 등록" in note
        assert {c["ticker"] for c in added} == {"133690", "360750", "458730", "446720"}

    def test_fallback_gives_up_augmenting_when_not_enough_capacity(self):
        """보강 후보 수가 capacity_remaining을 넘으면(등록 한도 초과) 보강을 포기하되, 선호
        지역에 맞지 않는 EQUITY(069500, 국내지수)는 여전히 제외해야 한다 — 원본을 그대로
        반환하면 ISA 계좌에 국내지수 추종 종목이 새어 들어가는 버그가 된다."""
        candidates = [
            {"ticker": "069500", "name": "KODEX 200", "market": "KOSPI", "asset_class": "EQUITY"},
        ]
        # 큐레이션 해외지수 추종 EQUITY는 3개(133690/360750/458730)인데 잔여 슬롯은 2개뿐 — 전부 아니면 전무
        filtered, note, added = _apply_index_region_preference(candidates, "ISA", capacity_remaining=2)
        assert filtered == []  # non_equity가 없으므로 069500은 제외되고 빈 리스트만 남는다
        assert added == []
        assert note is not None
        assert "해외지수" in note
        assert "자동 등록" not in note

    def test_fallback_to_full_candidates_when_curated_universe_has_no_match(self):
        """큐레이션 유니버스에서도 선호 지역 후보를 찾지 못해 보강이 불가능해도, 선호 지역에
        맞지 않는 EQUITY(069500)는 여전히 제외해야 한다 — 안전장치가 필터링 자체를 무력화하면
        안 된다(원본을 그대로 반환하던 이전 동작이 실제 프로덕션 버그였다)."""
        candidates = [
            {"ticker": "069500", "name": "KODEX 200", "market": "KOSPI", "asset_class": "EQUITY"},
        ]
        with patch("app.services.goal_candidate_service.RECOMMENDATION_UNIVERSE", []):
            filtered, note, added = _apply_index_region_preference(candidates, "ISA", capacity_remaining=20)
        assert filtered == []
        assert added == []
        assert note is not None
        assert "해외지수" in note
        assert "자동 등록" not in note

    def test_general_excludes_overseas_tracking_etf_when_capacity_exhausted_regression(self):
        """실제 프로덕션 버그 재현: GENERAL(국내지수 선호) 계좌에 국내지수 추종 EQUITY가 하나도
        없고(TIGER 미국S&P500만 등록) 등록 후보가 이미 한도에 도달해(capacity_remaining=0)
        큐레이션 보강도 불가능하면, 이전에는 안전장치가 원본을 그대로 반환해 해외지수 추종
        ETF(360750)가 국내전용 계좌 추천에 새어 들어갔다 — 이제는 non_equity만 남고 제외돼야
        한다."""
        candidates = [
            {"ticker": "360750", "name": "TIGER 미국S&P500", "market": "KOSPI", "asset_class": "EQUITY"},
            {"ticker": "153130", "name": "KODEX 단기채권", "market": "KOSPI", "asset_class": "CASH"},
        ]
        filtered, note, added = _apply_index_region_preference(candidates, "GENERAL", capacity_remaining=0)
        tickers = {c["ticker"] for c in filtered}
        assert "360750" not in tickers  # 해외지수 추종 EQUITY는 더 이상 새지 않는다
        assert tickers == {"153130"}  # CASH 후보는 영향받지 않고 그대로 유지
        assert added == []
        assert note is not None
        assert "국내지수" in note
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


class TestResolveTrackingIndex:
    """동일 지수 중복 추천 버그(ACE 미국S&P500 보유 중인데 TIGER 미국S&P500도 추천됨) 수정을
    위한 추종지수 판별 헬퍼."""

    def test_guess_tracking_index_matches_sp500_name_variants(self):
        assert guess_tracking_index("ACE 미국S&P500") == "US_SP500"
        assert guess_tracking_index("KODEX 미국S&P500TR") == "US_SP500"

    def test_guess_tracking_index_returns_none_for_unrecognized_name(self):
        """매칭되는 패턴이 없으면 None — dedup 효과가 없을 뿐 추천 자체를 막지 않는다(fail-soft)."""
        assert guess_tracking_index("삼성전자") is None

    def test_guess_tracking_index_prefers_dow_dividend_over_generic_high_dividend(self):
        """이름에 "배당"과 "다우존스"가 함께 들어가는 경우 더 구체적인 다우존스 배당 지수로
        분류돼야 한다(고배당 패턴에 앞서 검사)."""
        assert guess_tracking_index("TIGER 미국배당다우존스") == "US_DIV_DOWJONES100"

    def test_resolve_tracking_index_prefers_explicit_tag(self):
        assert resolve_tracking_index("999999", "KOSPI", "아무이름", "CUSTOM_LABEL") == "CUSTOM_LABEL"

    def test_resolve_tracking_index_looks_up_curated_universe_by_ticker_and_market(self):
        assert resolve_tracking_index("360750", "KOSPI", "TIGER 미국S&P500", None) == "US_SP500"

    def test_resolve_tracking_index_falls_back_to_name_heuristic_outside_universe(self):
        """큐레이션 유니버스 밖의 보유 종목(예: ACE 360200)은 이름 휴리스틱으로 추정된다."""
        assert resolve_tracking_index("360200", "KOSPI", "ACE 미국S&P500", None) == "US_SP500"


class TestSeedCandidateTickersDedup:
    """`_seed_candidate_tickers`의 큐레이션 보강 단계가 보유 종목과 동일 지수를 추종하는
    ETF를 중복으로 추가하지 않는지 검증 — 버그 재현(ACE 보유 + TIGER 자동추천) → 수정 확인."""

    def test_curated_etf_tracking_same_index_as_held_position_is_not_seeded(self):
        existing_items = [("360200", "ACE 미국S&P500", "KOSPI")]
        seed = _seed_candidate_tickers(existing_items)
        tickers = {c["ticker"] for c in seed}
        assert "360200" in tickers
        assert "360750" not in tickers  # TIGER 미국S&P500 — ACE와 동일 지수라 제외됨
        assert "VOO" not in tickers  # Vanguard S&P500 — 마찬가지로 동일 지수라 제외됨
        assert "SPY" not in tickers  # SPDR S&P500 — 마찬가지
        # 무관한 지수를 추종하는 큐레이션 ETF는 정상적으로 함께 시딩된다
        assert "069500" in tickers  # KODEX 200 (KOSPI200)
        assert "QQQ" in tickers  # 나스닥100

    def test_no_held_positions_seeds_curated_universe_unfiltered(self):
        """보유 종목이 없으면(회귀 없음) 큐레이션 유니버스가 그대로(중복 포함) 시딩된다 —
        SPY/VOO/360750처럼 계좌 유형에 따라 의도적으로 병존하는 조합은 여기서 걸러지지 않는다."""
        seed = _seed_candidate_tickers([])
        tickers = {c["ticker"] for c in seed}
        assert {"SPY", "VOO", "360750"} <= tickers

    def test_dow_dividend_monthly_and_quarterly_pair_both_seeded_when_not_held(self):
        """458730(분기배당)/446720(월배당)은 동일 지수를 추종하지만 배당주기가 달라 의도적으로
        함께 큐레이션돼 있다 — 보유 종목과 무관하면 dedup 대상이 아니므로 둘 다 시딩돼야 한다."""
        seed = _seed_candidate_tickers([("069500", "KODEX 200", "KOSPI")])
        tickers = {c["ticker"] for c in seed}
        assert {"458730", "446720"} <= tickers

    def test_holding_quarterly_variant_still_blocks_curated_same_index_dividend_etf(self):
        """458730(분기배당)을 이미 보유 중이면, held_indexes는 배당주기를 구분하지 않으므로
        큐레이션 보강 단계의 458730/446720 둘 다 이미 (ticker, market) 완전일치로 걸러지거나
        seen 처리되는지와 무관하게, 동일 지수의 SCHD도 중복으로 추가되지 않아야 한다."""
        seed = _seed_candidate_tickers([("458730", "TIGER 미국배당다우존스", "KOSPI")])
        tickers = {c["ticker"] for c in seed}
        assert "SCHD" not in tickers


class TestDetectDuplicateTrackingIndexNote:
    """이미 저장된 후보 목록에 보유 종목과 동일 지수를 추종하는 다른 티커가 남아있을 때
    정리를 권유하는 안내문(`detect_duplicate_tracking_index_note`) 검증 — 후보 목록 자체는
    건드리지 않는다(자동 수정 없음)."""

    def test_returns_note_when_registered_candidate_duplicates_held_position_index(self):
        existing_items = [("360200", "ACE 미국S&P500", "KOSPI")]
        candidates = [
            {"ticker": "360200", "name": "ACE 미국S&P500", "market": "KOSPI", "asset_class": "EQUITY"},
            {"ticker": "360750", "name": "TIGER 미국S&P500", "market": "KOSPI", "asset_class": "EQUITY"},
        ]
        note = detect_duplicate_tracking_index_note(candidates, existing_items)
        assert note is not None
        assert "360750" in note
        assert "360200" in note

    def test_no_note_when_no_held_positions(self):
        """등록 후보끼리(큐레이션 유니버스가 계좌 유형별로 의도적으로 병존시키는 조합 포함)는
        비교 대상이 아니다 — 실제 보유 종목이 없으면 항상 None."""
        candidates = [
            {"ticker": "SPY", "name": "SPDR S&P 500 ETF", "market": "NYSE", "asset_class": "EQUITY"},
            {"ticker": "VOO", "name": "Vanguard S&P 500 ETF", "market": "NYSE", "asset_class": "EQUITY"},
        ]
        assert detect_duplicate_tracking_index_note(candidates, []) is None

    def test_no_note_when_registered_candidate_is_the_held_ticker_itself(self):
        existing_items = [("360200", "ACE 미국S&P500", "KOSPI")]
        candidates = [{"ticker": "360200", "name": "ACE 미국S&P500", "market": "KOSPI", "asset_class": "EQUITY"}]
        assert detect_duplicate_tracking_index_note(candidates, existing_items) is None

    def test_no_note_for_dividend_frequency_differentiated_companion(self):
        """458730(분기배당)을 보유 중이어도, 배당주기가 다른 446720(월배당)은 실질적으로
        다른 선택지이므로 중복 안내 대상이 아니다."""
        existing_items = [("458730", "TIGER 미국배당다우존스", "KOSPI")]
        candidates = [
            {
                "ticker": "446720",
                "name": "SOL 미국배당다우존스",
                "market": "KOSPI",
                "asset_class": "EQUITY",
                "distribution_frequency": "MONTHLY",
            },
        ]
        assert detect_duplicate_tracking_index_note(candidates, existing_items) is None


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


class TestSuggestForDividendGoal:
    """등록된 후보만으로 배당 목표를 달성할 수 없을 때 큐레이션 유니버스에서 고배당 후보를
    제안만 하는 `_suggest_for_dividend_goal()` — 저장은 사용자가 추천 카드의 "후보에 추가"
    버튼으로 승인해야만 이뤄지므로, 이 함수는 DB에 쓰지 않고 제안 목록만 반환한다."""

    _DIVIDEND_YIELDS = {
        ("SCHD", "NYSE"): 3.5,
        ("VYM", "NYSE"): 2.9,
        ("JEPI", "NYSE"): 8.1,
        ("JEPQ", "NASDAQ"): 9.95,
        ("446720", "KOSPI"): 2.88,
        ("SPY", "NYSE"): 1.3,
    }

    def _dividend_side_effect(self, cache, tickers):
        return {tm: self._DIVIDEND_YIELDS[tm] for tm in tickers if tm in self._DIVIDEND_YIELDS}

    def _mock_fetch_dividend_yields(self):
        return AsyncMock(side_effect=self._dividend_side_effect)

    async def test_noop_when_no_dividend_goal(self):
        candidates = [{"ticker": "SPY", "name": "SPDR S&P 500 ETF", "market": "NYSE", "asset_class": "EQUITY"}]

        suggested, note, status = await _suggest_for_dividend_goal(None, candidates, None, None, 0.4, 10)

        assert suggested == []
        assert note is None
        assert status is None

    async def test_noop_when_already_achievable_and_no_meaningfully_better_candidate(self):
        candidates = [
            {"ticker": "SCHD", "name": "Schwab US Dividend Equity ETF", "market": "NYSE", "asset_class": "EQUITY"},
            {"ticker": "SPY", "name": "SPDR S&P 500 ETF", "market": "NYSE", "asset_class": "EQUITY"},
        ]
        # max_weight=0.4 -> 등록 후보만으로 최대 0.4*3.5 + 0.4*1.3 = 1.92%까지 달성 가능.
        # 이미 달성(expected=1.2 >= required=1.0)했고, 개선 목표(1.2+0.5=1.7%)도 등록 후보만으로
        # 이미 달성 가능한 범위(<=1.92%)라 미등록 후보를 제안할 필요가 없다.
        with patch(
            "app.services.goal_recommendation_service._fetch_dividend_yields",
            self._mock_fetch_dividend_yields(),
        ):
            suggested, note, status = await _suggest_for_dividend_goal(
                None, candidates, 1.0, 1.2, 0.4, capacity_remaining=10
            )

        assert suggested == []
        assert note is None
        assert status == "optimal"

    async def test_suggests_when_achievable_but_meaningfully_higher_yield_exists(self):
        """이미 배당 목표(연 1.0%)를 달성했어도(expected=1.3%), 등록 후보만으로는 개선 목표
        (1.3+0.5=1.8%)에 못 미쳐 큐레이션 유니버스에서 더 높은 배당 후보(JEPQ)를 제안한다."""
        candidates = [{"ticker": "SPY", "name": "SPDR S&P 500 ETF", "market": "NYSE", "asset_class": "EQUITY"}]

        with patch(
            "app.services.goal_recommendation_service._fetch_dividend_yields",
            self._mock_fetch_dividend_yields(),
        ):
            suggested, note, status = await _suggest_for_dividend_goal(
                None, candidates, 1.0, 1.3, 0.4, capacity_remaining=10
            )

        tickers = [c["ticker"] for c in suggested]
        assert tickers[0] == "JEPQ"
        assert status == "improvable"
        assert note is not None
        assert "이미 배당 목표를 달성했지만" in note

    async def test_suggests_highest_yield_unregistered_candidates_when_unachievable(self):
        """등록 후보(SPY, 배당 1.3%)만으로는 목표(연 5%)를 달성할 수 없어 큐레이션 유니버스의
        고배당 후보를 수익률 내림차순(JEPQ 9.95% > JEPI 8.1%)으로 제안한다 — 등록 목록에는
        반영하지 않는다."""
        candidates = [{"ticker": "SPY", "name": "SPDR S&P 500 ETF", "market": "NYSE", "asset_class": "EQUITY"}]

        with patch(
            "app.services.goal_recommendation_service._fetch_dividend_yields",
            self._mock_fetch_dividend_yields(),
        ):
            suggested, note, status = await _suggest_for_dividend_goal(
                None, candidates, 5.0, 1.3, 0.4, capacity_remaining=10
            )

        tickers = [c["ticker"] for c in suggested]
        assert "SPY" not in tickers  # 이미 등록된 후보는 제안 목록에 포함되지 않음
        assert tickers[0] == "JEPQ"  # 가장 배당수익률이 높은 후보부터 제안
        assert suggested[0]["dividend_yield_pct"] == 9.95
        assert status == "unreachable"
        assert note is not None
        assert "아래 고배당 후보를 추가하면 도움이 됩니다" in note
        assert "자동 등록" not in note

    async def test_excludes_candidates_below_minimum_suggestable_yield(self):
        """등록된 후보(SCHD/JEPI/JEPQ/VYM/446720)가 fixture상 2.5% 이상인 종목을 전부 차지해
        남은 큐레이션 풀에는 2.5% 미만 종목(SPY 1.3%, 나머지는 fixture에 값이 없어 0%로 취급)만
        남으면, 목표를 채우기에 부족해도 저배당 종목을 "고배당 후보"로 제안하지 않는다
        (unreachable 유지, 빈 제안)."""
        candidates = [
            {"ticker": "SCHD", "name": "Schwab US Dividend Equity ETF", "market": "NYSE", "asset_class": "EQUITY"},
            {"ticker": "JEPI", "name": "JPMorgan Equity Premium Income ETF", "market": "NYSE", "asset_class": "EQUITY"},
            {
                "ticker": "JEPQ",
                "name": "JPMorgan Nasdaq Equity Premium Income ETF",
                "market": "NASDAQ",
                "asset_class": "EQUITY",
            },
            {"ticker": "VYM", "name": "Vanguard High Dividend Yield ETF", "market": "NYSE", "asset_class": "EQUITY"},
            {
                "ticker": "446720",
                "name": "SOL 미국배당다우존스",
                "market": "KOSPI",
                "asset_class": "EQUITY",
            },
        ]

        with patch(
            "app.services.goal_recommendation_service._fetch_dividend_yields",
            self._mock_fetch_dividend_yields(),
        ):
            suggested, note, status = await _suggest_for_dividend_goal(
                None, candidates, 20.0, 5.0, 0.4, capacity_remaining=10
            )

        assert suggested == []
        assert note is None
        assert status == "unreachable"

    async def test_status_unreachable_when_expected_is_none(self):
        """옵티마이저가 아직 실행되지 않았거나 실패해 `expected_dividend_yield_pct=None`이면
        무조건 미달성(unreachable)으로 취급한다(조기 반환 지점에서 호출되는 경우)."""
        candidates = [{"ticker": "SPY", "name": "SPDR S&P 500 ETF", "market": "NYSE", "asset_class": "EQUITY"}]

        with patch(
            "app.services.goal_recommendation_service._fetch_dividend_yields",
            self._mock_fetch_dividend_yields(),
        ):
            suggested, note, status = await _suggest_for_dividend_goal(
                None, candidates, 5.0, None, 0.4, capacity_remaining=10
            )

        assert status == "unreachable"
        assert len(suggested) > 0

    async def test_respects_capacity_remaining(self):
        """등록 가능 잔여 슬롯이 0이면 달성 불가능해도 제안하지 않는다."""
        candidates = [{"ticker": "SPY", "name": "SPDR S&P 500 ETF", "market": "NYSE", "asset_class": "EQUITY"}]

        with patch(
            "app.services.goal_recommendation_service._fetch_dividend_yields",
            self._mock_fetch_dividend_yields(),
        ):
            suggested, note, status = await _suggest_for_dividend_goal(
                None, candidates, 5.0, 1.3, 0.4, capacity_remaining=0
            )

        assert suggested == []
        assert note is None
        assert status == "unreachable"

    async def test_market_filter_excludes_overseas_listed_candidates(self):
        """일반(GENERAL) 계좌처럼 국내상장 후보만 허용하는 시장 필터를 넘기면, 미국 상장인
        JEPI/JEPQ는 후보 풀에서 제외되고 국내상장 446720만 제안 대상이 된다."""
        candidates = [{"ticker": "069500", "name": "KODEX 200", "market": "KOSPI", "asset_class": "EQUITY"}]

        def _domestic_only(c: dict[str, str]) -> bool:
            return c["market"].upper() in {"KOSPI", "KOSDAQ"}

        # 446720의 배당수익률을 3.5%로 오버라이드 — 시장 필터 동작 자체를 검증하는 테스트라,
        # 클래스 공용 fixture의 2.88%(최소 제안 하한 3.0% 미만)를 그대로 쓰면 제안 자체가
        # 걸러져 이 테스트의 의도(시장 필터 검증)와 무관하게 실패한다.
        yields = {**self._DIVIDEND_YIELDS, ("446720", "KOSPI"): 3.5}

        async def _dividend_side_effect(cache, tickers):
            return {tm: yields[tm] for tm in tickers if tm in yields}

        with patch(
            "app.services.goal_recommendation_service._fetch_dividend_yields",
            AsyncMock(side_effect=_dividend_side_effect),
        ):
            suggested, note, status = await _suggest_for_dividend_goal(
                None, candidates, 2.5, 0.0, 0.4, capacity_remaining=10, market_filter=_domestic_only
            )

        tickers = {c["ticker"] for c in suggested}
        assert "JEPI" not in tickers
        assert "JEPQ" not in tickers
        assert "446720" in tickers
        assert status == "unreachable"
        assert note is not None

    async def test_gives_up_gracefully_when_universe_cannot_achieve_target(self):
        """유니버스 전체를 더해도 목표를 달성할 수 없으면(비현실적으로 높은 목표), 도움이 되는
        후보는 모두 제안하되 조용히 종료한다 — 최종 fail-soft 판정은 옵티마이저 몫이다."""
        candidates = [{"ticker": "SPY", "name": "SPDR S&P 500 ETF", "market": "NYSE", "asset_class": "EQUITY"}]

        with patch(
            "app.services.goal_recommendation_service._fetch_dividend_yields",
            self._mock_fetch_dividend_yields(),
        ):
            suggested, note, status = await _suggest_for_dividend_goal(
                None, candidates, 100.0, 1.3, 0.4, capacity_remaining=10
            )

        assert len(suggested) > 0
        assert note is not None
        assert status == "unreachable"


class TestFetchDividendYields:
    """`_fetch_dividend_yields()`의 ticker+market 전역 캐시(TTL_GOAL_CANDIDATE_DIVIDEND_YIELD) —
    캐시 히트 시 Naver/Yahoo 실시간 스크래핑을 건너뛰고, 배당수익률이 0인 종목도 재조회 방지를
    위해 그대로 캐싱한다(반환 dict에는 기존과 동일하게 포함하지 않음)."""

    async def test_cache_miss_fetches_and_stores_result(self, mock_cache):
        with patch(
            "app.services.goal_recommendation_service.sync_yahoo_dividend_info",
            return_value={"dividend_yield": 0.032},
        ) as mock_yahoo:
            result = await _fetch_dividend_yields(mock_cache, [("SPY", "NYSE")])

        assert result[("SPY", "NYSE")] == pytest.approx(3.2)
        mock_yahoo.assert_called_once()
        mock_cache.setex.assert_awaited_once()
        cache_key = mock_cache.setex.await_args.args[0]
        assert "SPY" in cache_key
        assert "NYSE" in cache_key

    async def test_cache_hit_skips_external_fetch(self, mock_cache):
        mock_cache.get = AsyncMock(return_value=json.dumps({"yield_pct": 3.2}))

        with patch(
            "app.services.goal_recommendation_service.sync_yahoo_dividend_info",
        ) as mock_yahoo:
            result = await _fetch_dividend_yields(mock_cache, [("SPY", "NYSE")])

        assert result[("SPY", "NYSE")] == 3.2
        mock_yahoo.assert_not_called()
        mock_cache.setex.assert_not_awaited()

    async def test_zero_yield_is_cached_but_excluded_from_result(self, mock_cache):
        with patch(
            "app.services.goal_recommendation_service.sync_yahoo_dividend_info",
            return_value={"dividend_yield": 0.0},
        ):
            result = await _fetch_dividend_yields(mock_cache, [("QQQ", "NASDAQ")])

        assert result == {}
        mock_cache.setex.assert_awaited_once()


@pytest.mark.asyncio
class TestGetGoalRecommendation:
    async def test_not_configured_without_goal_amount(self):
        settings_row = SimpleNamespace(goal_amount=None, retirement_target_year=None, annual_dividend_goal=None)

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
        # autouse _mock_market_signal이 GREEN을 반환하므로 그대로 echo된다
        assert result.market_signal_level == "GREEN"

    async def test_achievable_dividend_goal_shifts_weight_to_high_yield_candidates(self):
        """배당 목표가 달성 가능한 범위면 required_dividend_yield_pct가 실제 비중 계산에 반영되어
        고배당 후보(SCHD/VYM) 비중이 함께 높아진다 — A1(배당목표 MVO 미반영) 수정 검증."""
        settings_row = SimpleNamespace(
            goal_amount=100_000_000.0,
            retirement_target_year=9999,
            monthly_deposit_amount=1_000_000.0,
            annual_deposit_goal=None,
            annual_dividend_goal=300_000.0,  # base_krw 10,000,000 대비 required_dividend_yield_pct = 3.0%
            goal_candidate_tickers=None,
            goal_max_weight_pct=100.0,  # 종목당 상한을 풀어 배당 제약이 실제로 비중을 좌우하게 함
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

        assert result.required_dividend_yield_pct == pytest.approx(3.0)
        high_yield_weight = sum(i.weight for i in result.recommended_items if i.ticker in ("SCHD", "VYM"))
        # 배당 후보 중 SCHD 하나만으로도 3%를 채울 수 있어(비중상한 100%) 제약이 비구속적일 수 있지만,
        # 배당수익률이 0인 나머지 8개 후보만으로는 목표를 채울 수 없으므로 고배당 후보 비중이 0일 수는 없다.
        assert high_yield_weight > 0.0
        assert result.note is None or "배당 목표" not in result.note
        # 배당 제약은 포트폴리오 전체 가중평균에만 걸리므로, 저배당(dividend_map에 없는) 종목도
        # 분산 목적으로 함께 포함될 수 있다 — 화면에서 이를 구분할 수 있도록 종목별 배당수익률이
        # dividend_map과 정확히 일치해야 한다(없으면 None).
        for item in result.recommended_items:
            assert item.dividend_yield_pct == dividend_map.get((item.ticker, item.market))
        assert any(i.dividend_yield_pct is None for i in result.recommended_items)

    async def test_dividend_goal_only_without_asset_goal_returns_configured_recommendation(self):
        """자산목표(goal_amount·retirement_target_year)를 설정하지 않아도 배당목표
        (annual_dividend_goal)만 있으면 "배당 계획" 탭 전용 진입점으로 동작해야 한다.
        required_return_pct는 화면에 노출하지 않고(None), 옵티마이저에는 비구속적 하한만
        전달돼 배당수익률 제약만으로 최소분산 포트폴리오가 계산된다."""
        settings_row = SimpleNamespace(
            goal_amount=None,
            retirement_target_year=None,
            monthly_deposit_amount=None,
            annual_deposit_goal=None,
            annual_dividend_goal=300_000.0,  # base_krw 10,000,000 대비 required_dividend_yield_pct = 3.0%
            goal_candidate_tickers=None,
            goal_max_weight_pct=100.0,
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
        assert result.required_return_pct is None
        assert result.required_dividend_yield_pct == pytest.approx(3.0)
        assert result.recommended_items

    async def test_market_signal_level_propagates_to_result(self):
        """시장 위험 신호(RED)가 결과의 market_signal_level에 그대로 반영되어야 한다."""
        settings_row = SimpleNamespace(
            goal_amount=100_000_000.0,
            retirement_target_year=9999,
            monthly_deposit_amount=1_000_000.0,
            annual_deposit_goal=None,
            annual_dividend_goal=None,
            goal_candidate_tickers=None,
            goal_risk_tolerance="AGGRESSIVE",
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
            patch(
                "app.services.goal_recommendation_service.get_market_signal",
                AsyncMock(return_value={"composite_level": "RED", "data_freshness": "LIVE"}),
            ),
        ):
            mock_db = AsyncMock()
            result = await get_goal_recommendation(None, 10_000_000.0, [], settings_row, mock_db)

        assert result.market_signal_level == "RED"
        assert result.note is not None
        assert "시장 위험 신호(RED)" in result.note

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
        assert {
            "ticker": "SPY",
            "name": "SPDR S&P 500 ETF",
            "market": "NYSE",
            "asset_class": "EQUITY",
        } in settings_row.goal_candidate_tickers
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
        assert set(queried_tickers) == {
            ("133690", "KOSPI"),
            ("360750", "KOSPI"),
            ("458730", "KOSPI"),
            ("446720", "KOSPI"),
        }
        assert result.recommended_items
        assert {item.ticker for item in result.recommended_items} <= {"133690", "360750", "458730", "446720"}
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
        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value=None)

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
            result = await get_goal_recommendation(mock_cache, 10_000_000.0, [], settings_row, AsyncMock())

        assert result.recommended_items == []
        mock_cache.setex.assert_not_called()

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
        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value=None)
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
            result = await get_goal_recommendation(mock_cache, 10_000_000.0, [], settings_row, AsyncMock())

        assert result.recommended_items
        mock_cache.setex.assert_awaited_once()


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
                "app.services.goal_recommendation_service.prefetch_accounts_snapshot_positions",
                AsyncMock(return_value=({account_id: object()}, {}, {}, {})),
            ),
            patch(
                "app.services.goal_recommendation_service.compute_total_assets_krw",
                return_value=5_000_000.0,
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

    async def test_short_term_general_excludes_overseas_tracking_etf_when_candidate_slots_full(self):
        """실제 프로덕션 버그 재현: 등록 후보가 MAX_GOAL_CANDIDATE_TICKERS(20개)에 도달해
        `_apply_index_region_preference`의 큐레이션 보강이 불가능해지면, 이전에는 안전장치가
        선호 지역 필터링 자체를 포기해 GENERAL(국내지수 선호) 계좌에도 해외지수 추종
        EQUITY(TIGER 미국S&P500, 360750)가 그대로 추천됐다 — 수정 후에는 여전히 제외돼야 한다."""
        candidate_tickers = [
            {"ticker": "360750", "name": "TIGER 미국S&P500", "market": "KOSPI", "asset_class": "EQUITY"},
            {"ticker": "153130", "name": "KODEX 단기채권", "market": "KOSPI", "asset_class": "CASH"},
            {"ticker": "357870", "name": "TIGER CD금리투자KIS(합성)", "market": "KOSPI", "asset_class": "CASH"},
        ] + [
            {"ticker": f"PAD{i:03d}", "name": f"패딩종목{i}", "market": "KOSPI", "asset_class": "CASH"}
            for i in range(17)
        ]
        assert len(candidate_tickers) == MAX_GOAL_CANDIDATE_TICKERS  # capacity_remaining=0을 만들기 위한 전제
        settings_row = SimpleNamespace(
            goal_candidate_tickers=candidate_tickers,
            goal_max_weight_pct=None,
            goal_cagr_lookback_years=None,
        )
        account_id = uuid.uuid4()
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=_execute_result([("SHORT_TERM", "GENERAL", account_id)]))

        cagr_map = {
            ("153130", "KOSPI"): {"cagr_pct": 2.0},
            ("357870", "KOSPI"): {"cagr_pct": 2.5},
        }
        random.seed(11)
        returns_map = {
            "153130.KS": [random.gauss(0.0001, 0.0005) for _ in range(252)],
            "357870.KS": [random.gauss(0.00012, 0.0006) for _ in range(252)],
        }

        with (
            patch(
                "app.services.goal_recommendation_service.query_latest_position_map",
                AsyncMock(return_value={}),
            ),
            patch(
                "app.services.goal_recommendation_service.prefetch_accounts_snapshot_positions",
                AsyncMock(return_value=({account_id: object()}, {}, {}, {})),
            ),
            patch(
                "app.services.goal_recommendation_service.compute_total_assets_krw",
                return_value=5_000_000.0,
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

        assert len(result.recommendations) == 1
        rec = result.recommendations[0]
        recommended_tickers = {item.ticker for item in rec.recommended_items}
        assert "360750" not in recommended_tickers  # 해외지수 추종 EQUITY는 더 이상 새지 않는다
        assert recommended_tickers <= {"153130", "357870", "CASH_EQUIVALENT"}
        assert rec.note is not None
        assert "국내지수" in rec.note

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

    async def test_short_term_with_equity_floor_and_dividend_goal_does_not_crash(self):
        """실제 계정에서 재현된 회귀 시나리오: 단기(equity_floor=80%) + 배당목표(연 2.4%,
        equity_floor를 반영하면 실제로는 달성 불가능한 수준) 조합에서 예전에는 배당
        달성가능성 사전검증이 equity_floor 그룹 예산을 무시해 "달성 가능"으로 오판, SLSQP
        전체가 실패(빈 추천)했다. 수정 후에는 배당 제약만 fail-soft로 드롭하고 정상 추천을
        반환해야 한다."""
        settings_row = SimpleNamespace(
            goal_candidate_tickers=[
                {"ticker": "069500", "name": "KODEX 200", "market": "KOSPI", "asset_class": "EQUITY"},
                {"ticker": "153130", "name": "KODEX 단기채권", "market": "KOSPI", "asset_class": "CASH"},
                {"ticker": "114260", "name": "KODEX 국고채3년", "market": "KOSPI", "asset_class": "BOND"},
                {"ticker": "357870", "name": "TIGER CD금리투자KIS(합성)", "market": "KOSPI", "asset_class": "CASH"},
            ],
            goal_max_weight_pct=60.0,
            goal_cagr_lookback_years=None,
            annual_dividend_goal=240_000.0,  # total_assets_krw 10,000,000 대비 required_dividend_yield_pct = 2.4%
        )
        account_id = uuid.uuid4()
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=_execute_result([("SHORT_TERM", "GENERAL", account_id)]))

        cagr_map = {
            ("069500", "KOSPI"): {"cagr_pct": 8.0},
            ("153130", "KOSPI"): {"cagr_pct": 3.0},
            ("114260", "KOSPI"): {"cagr_pct": 3.0},
            ("357870", "KOSPI"): {"cagr_pct": 3.0},
        }
        dividend_map = {
            ("069500", "KOSPI"): 1.8,
            ("153130", "KOSPI"): 3.3,
            ("114260", "KOSPI"): 3.0,
            ("357870", "KOSPI"): 3.4,
        }
        random.seed(42)
        returns_map = {
            sym: [random.gauss(0.0003, 0.008) for _ in range(252)]
            for sym in ["069500.KS", "153130.KS", "114260.KS", "357870.KS"]
        }

        with (
            patch(
                "app.services.goal_recommendation_service.query_latest_position_map",
                AsyncMock(return_value={}),
            ),
            patch(
                "app.services.goal_recommendation_service.prefetch_accounts_snapshot_positions",
                AsyncMock(return_value=({account_id: object()}, {}, {}, {})),
            ),
            patch(
                "app.services.goal_recommendation_service.compute_total_assets_krw",
                return_value=5_000_000.0,
            ),
            patch(
                "app.services.goal_recommendation_service.build_portfolio_overview",
                AsyncMock(return_value={"total_assets_krw": 10_000_000.0}),
            ),
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
            result = await get_horizon_recommendations(None, mock_db, uuid.uuid4(), settings_row)

        assert len(result.recommendations) == 1
        rec = result.recommendations[0]
        # 수정 전에는 이 시나리오에서 빈 추천 + "제약 조건을 만족하는 포트폴리오를 찾지
        # 못했습니다" 노트가 반환됐다.
        assert rec.recommended_items
        equity_weight = sum(i.weight for i in rec.recommended_items if i.ticker == "069500")
        assert equity_weight >= 79.5  # equity_floor(80%)는 여전히 만족
        assert rec.required_dividend_yield_pct == pytest.approx(2.4)

    async def test_long_term_overseas_dedicated_with_dividend_goal_does_not_crash(self):
        """실제 계정에서 재현된 회귀 시나리오: 장기(LONG_TERM, risk_tolerance=AGGRESSIVE 고정) +
        해외전용 계좌에 배당목표(연 1.8%)가 걸리면, AGGRESSIVE의 "가중평균 CAGR=target" 등식
        제약과 배당 제약이 동시에는 충족 불가능해 예전에는 SLSQP가 전체 실패(빈 추천 + "제약
        조건을 만족하는 포트폴리오를 찾지 못했습니다")했다. 수정 후에는 배당 제약만 fail-soft로
        드롭하고 정상 추천을 반환해야 한다."""
        settings_row = SimpleNamespace(
            goal_candidate_tickers=[
                {"ticker": "QQQ", "name": "Invesco QQQ Trust", "market": "NASDAQ", "asset_class": "EQUITY"},
                {"ticker": "QQQM", "name": "Invesco NASDAQ 100 ETF", "market": "NASDAQ", "asset_class": "EQUITY"},
                {"ticker": "VOO", "name": "Vanguard S&P 500 ETF", "market": "NYSE", "asset_class": "EQUITY"},
                {"ticker": "SCHD", "name": "Schwab US Dividend Equity ETF", "market": "NYSE", "asset_class": "EQUITY"},
                {"ticker": "QLD", "name": "ProShares Ultra QQQ", "market": "NASDAQ", "asset_class": "EQUITY"},
            ],
            goal_max_weight_pct=40.0,
            goal_cagr_lookback_years=None,
            annual_dividend_goal=180_000.0,  # total_assets_krw 10,000,000 대비 required_dividend_yield_pct = 1.8%
        )
        account_id = uuid.uuid4()
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=_execute_result([("LONG_TERM", "OVERSEAS_DEDICATED", account_id)]))

        cagr_map = {
            ("QQQ", "NASDAQ"): {"cagr_pct": 18.0},
            ("QQQM", "NASDAQ"): {"cagr_pct": 18.0},
            ("VOO", "NYSE"): {"cagr_pct": 13.0},
            ("SCHD", "NYSE"): {"cagr_pct": 11.0},
            ("QLD", "NASDAQ"): {"cagr_pct": 32.0},
        }
        dividend_map = {
            ("QQQ", "NASDAQ"): 0.6,
            ("QQQM", "NASDAQ"): 0.6,
            ("VOO", "NYSE"): 1.3,
            ("SCHD", "NYSE"): 3.5,
            ("QLD", "NASDAQ"): 0.5,
        }
        random.seed(5)
        returns_map = {
            "QQQ": [random.gauss(0.0009, 0.013) for _ in range(252)],
            "QQQM": [random.gauss(0.0009, 0.013) for _ in range(252)],
            "VOO": [random.gauss(0.0006, 0.010) for _ in range(252)],
            "SCHD": [random.gauss(0.0005, 0.009) for _ in range(252)],
            "QLD": [random.gauss(0.0018, 0.026) for _ in range(252)],
        }

        with (
            patch(
                "app.services.goal_recommendation_service.query_latest_position_map",
                AsyncMock(return_value={}),
            ),
            patch(
                "app.services.goal_recommendation_service.prefetch_accounts_snapshot_positions",
                AsyncMock(return_value=({account_id: object()}, {}, {}, {})),
            ),
            patch(
                "app.services.goal_recommendation_service.compute_total_assets_krw",
                return_value=5_000_000.0,
            ),
            patch(
                "app.services.goal_recommendation_service.build_portfolio_overview",
                AsyncMock(return_value={"total_assets_krw": 10_000_000.0}),
            ),
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
            result = await get_horizon_recommendations(None, mock_db, uuid.uuid4(), settings_row)

        assert len(result.recommendations) == 1
        rec = result.recommendations[0]
        # 수정 전에는 이 시나리오에서 빈 추천 + "제약 조건을 만족하는 포트폴리오를 찾지
        # 못했습니다" 노트가 반환됐다.
        assert rec.recommended_items
        assert rec.risk_tolerance == "AGGRESSIVE"
        assert rec.note is not None
        assert "다른 조건과 함께 만족하는" in rec.note

    async def test_each_combo_gets_its_own_dividend_suggestions_not_persisted_or_merged(self):
        """LONG_TERM 내 GENERAL(국내전용)·OVERSEAS_DEDICATED(해외전용) 두 조합이 동시에 배당
        목표를 달성하지 못할 때, 조합별로 서로 다른(시장 필터가 적용된) 제안 목록이 정확히
        매칭돼 부착되는지 검증한다 — `combos`를 7-튜플로 확장하고 `asyncio.gather` 이후
        `zip`으로 매핑하는 배선(제안이 엉뚱한 조합에 붙는 회귀를 방지). 또한 제안된 후보는
        어느 조합의 `recommended_items`에도 나타나지 않고(승인 전 비중 계산 미반영),
        `goal_candidate_tickers`도 변경되지 않아야 한다."""
        settings_row = SimpleNamespace(
            goal_candidate_tickers=[
                # 005930/000660은 개별 종목이라 index_region이 자동으로 DOMESTIC 판정되므로
                # GENERAL의 지역 선호 필터를 통과한다 — 큐레이션 유니버스에서 진짜 국내지수
                # 추종 EQUITY는 069500 하나뿐이라, 069500을 등록하지 않고 남겨둬야 제안 풀에서
                # 실제로 제안 대상이 된다(제안도 `_apply_index_region_preference`와 동일하게
                # 지역 선호를 지켜야 한다는 회귀 방지).
                {"ticker": "005930", "name": "삼성전자", "market": "KOSPI", "asset_class": "EQUITY"},
                {"ticker": "000660", "name": "SK하이닉스", "market": "KOSPI", "asset_class": "EQUITY"},
                {"ticker": "SPY", "name": "SPDR S&P 500 ETF", "market": "NYSE", "asset_class": "EQUITY"},
                {"ticker": "VOO", "name": "Vanguard S&P 500 ETF", "market": "NYSE", "asset_class": "EQUITY"},
            ],
            goal_max_weight_pct=None,
            goal_cagr_lookback_years=None,
            annual_dividend_goal=300_000.0,  # total_assets_krw 10,000,000 대비 required_dividend_yield_pct = 3.0%
        )
        general_account_id = uuid.uuid4()
        overseas_account_id = uuid.uuid4()
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            return_value=_execute_result(
                [
                    ("LONG_TERM", "GENERAL", general_account_id),
                    ("LONG_TERM", "OVERSEAS_DEDICATED", overseas_account_id),
                ]
            )
        )

        cagr_map = {
            ("005930", "KOSPI"): {"cagr_pct": 9.0},
            ("000660", "KOSPI"): {"cagr_pct": 7.0},
            ("SPY", "NYSE"): {"cagr_pct": 10.0},
            ("VOO", "NYSE"): {"cagr_pct": 9.5},
        }
        dividend_by_ticker = {
            # 등록된 후보 (전부 배당수익률이 낮아 3.0% 목표를 등록 후보만으로 달성 불가)
            ("005930", "KOSPI"): 1.0,
            ("000660", "KOSPI"): 0.6,
            ("SPY", "NYSE"): 1.3,
            ("VOO", "NYSE"): 1.2,
            # 국내(GENERAL) 큐레이션 풀 — 진짜 국내지수 추종 EQUITY는 069500 하나뿐이다. 최소
            # 제안 하한(3.0%)을 넘기도록 3.5%로 설정해(그것만 더해도 3.0% 목표에는 못 미치지만
            # 여전히 제안은 되어야 함) 제안 자체는 그대로 나오는지 검증한다.
            # 360750/133690/458730/446720(해외지수 추종·KRX 상장)은 GENERAL 지역 선호에 안 맞아
            # 제안 풀에서 제외돼야 한다 — 이게 이 테스트가 검증하는 회귀 방지 포인트.
            ("069500", "KOSPI"): 3.5,
            # 해외(OVERSEAS_DEDICATED) 큐레이션 풀 — JEPQ 하나만 추가해도 목표 달성 가능
            ("JEPQ", "NASDAQ"): 9.95,
            ("JEPI", "NYSE"): 8.1,
            ("SCHD", "NYSE"): 3.5,
            ("VYM", "NYSE"): 2.9,
            ("VTI", "NYSE"): 1.3,
            ("QQQ", "NASDAQ"): 0.6,
        }

        async def _dividend_side_effect(cache, tickers):
            return {tm: dividend_by_ticker[tm] for tm in tickers if tm in dividend_by_ticker}

        random.seed(7)
        returns_map = {
            sym: [random.gauss(0.0004, 0.008) for _ in range(252)] for sym in ["005930.KS", "000660.KS", "SPY", "VOO"]
        }

        with (
            patch(
                "app.services.goal_recommendation_service.query_latest_position_map",
                AsyncMock(return_value={}),
            ),
            patch(
                "app.services.goal_recommendation_service.prefetch_accounts_snapshot_positions",
                AsyncMock(return_value=({general_account_id: object(), overseas_account_id: object()}, {}, {}, {})),
            ),
            patch(
                "app.services.goal_recommendation_service.compute_total_assets_krw",
                return_value=5_000_000.0,
            ),
            patch(
                "app.services.goal_recommendation_service.build_portfolio_overview",
                AsyncMock(return_value={"total_assets_krw": 10_000_000.0}),
            ),
            patch(
                "app.services.goal_recommendation_service.get_historical_returns",
                AsyncMock(return_value=cagr_map),
            ),
            patch(
                "app.services.goal_recommendation_service._fetch_dividend_yields",
                AsyncMock(side_effect=_dividend_side_effect),
            ),
            patch(
                "app.services.goal_recommendation_service.fetch_yf_daily_returns",
                return_value=returns_map,
            ),
        ):
            result = await get_horizon_recommendations(None, mock_db, uuid.uuid4(), settings_row)

        assert len(result.recommendations) == 2
        by_tax_type = {r.tax_type: r for r in result.recommendations}

        general_rec = by_tax_type["GENERAL"]
        general_suggested = {c.ticker for c in general_rec.suggested_candidates}
        assert general_suggested == {"069500"}  # 진짜 국내지수 추종 EQUITY만 제안됨
        general_recommended = {i.ticker for i in general_rec.recommended_items}
        assert general_recommended == {"005930", "000660"}  # 제안된 종목은 비중 계산에 반영 안 됨

        overseas_rec = by_tax_type["OVERSEAS_DEDICATED"]
        overseas_suggested = {c.ticker for c in overseas_rec.suggested_candidates}
        assert overseas_suggested == {"JEPQ"}
        jepq = next(c for c in overseas_rec.suggested_candidates if c.ticker == "JEPQ")
        assert jepq.dividend_yield_pct == 9.95
        overseas_recommended = {i.ticker for i in overseas_rec.recommended_items}
        assert overseas_recommended == {"SPY", "VOO"}

        mock_db.commit.assert_not_awaited()
        assert len(settings_row.goal_candidate_tickers) == 4

    async def test_combo_already_achieving_dividend_goal_suggests_better_candidate(self):
        """등록 후보(QQQ/VOO/SCHD)만으로 배당 목표(연 1.74%)를 이미 달성했어도(CONSERVATIVE는
        배당 하한을 딱 그 값에서 충족하도록 최소분산 해를 찾음), 등록 후보만으로는 개선 목표
        (1.74+0.5=2.24%)에 못 미쳐 큐레이션 유니버스의 JEPQ(9.95%)가 "더 나은 옵션"으로
        제안돼야 한다 — 판정 시점을 최적화 이후로 옮긴 리팩터링의 핵심 시나리오."""
        settings_row = SimpleNamespace(
            goal_candidate_tickers=[
                {"ticker": "QQQ", "name": "Invesco QQQ Trust", "market": "NASDAQ", "asset_class": "EQUITY"},
                {"ticker": "VOO", "name": "Vanguard S&P 500 ETF", "market": "NYSE", "asset_class": "EQUITY"},
                {"ticker": "SCHD", "name": "Schwab US Dividend Equity ETF", "market": "NYSE", "asset_class": "EQUITY"},
            ],
            goal_max_weight_pct=40.0,
            goal_cagr_lookback_years=None,
            annual_dividend_goal=174_000.0,  # total_assets_krw 10,000,000 대비 required_dividend_yield_pct = 1.74%
        )
        account_id = uuid.uuid4()
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=_execute_result([("LONG_TERM", "OVERSEAS_DEDICATED", account_id)]))

        cagr_map = {
            ("QQQ", "NASDAQ"): {"cagr_pct": 18.0},
            ("VOO", "NYSE"): {"cagr_pct": 13.0},
            ("SCHD", "NYSE"): {"cagr_pct": 11.0},
        }
        dividend_map = {
            ("QQQ", "NASDAQ"): 0.6,
            ("VOO", "NYSE"): 1.3,
            ("SCHD", "NYSE"): 3.5,
            ("JEPQ", "NASDAQ"): 9.95,
            ("JEPI", "NYSE"): 8.1,
        }
        random.seed(5)
        returns_map = {
            "QQQ": [random.gauss(0.0009, 0.013) for _ in range(252)],
            "VOO": [random.gauss(0.0006, 0.010) for _ in range(252)],
            "SCHD": [random.gauss(0.0005, 0.009) for _ in range(252)],
        }

        async def _dividend_side_effect(cache, tickers):
            return {tm: dividend_map[tm] for tm in tickers if tm in dividend_map}

        with (
            patch(
                "app.services.goal_recommendation_service.query_latest_position_map",
                AsyncMock(return_value={}),
            ),
            patch(
                "app.services.goal_recommendation_service.prefetch_accounts_snapshot_positions",
                AsyncMock(return_value=({account_id: object()}, {}, {}, {})),
            ),
            patch(
                "app.services.goal_recommendation_service.compute_total_assets_krw",
                return_value=5_000_000.0,
            ),
            patch(
                "app.services.goal_recommendation_service.build_portfolio_overview",
                AsyncMock(return_value={"total_assets_krw": 10_000_000.0}),
            ),
            patch(
                "app.services.goal_recommendation_service.get_historical_returns",
                AsyncMock(return_value=cagr_map),
            ),
            patch(
                "app.services.goal_recommendation_service._fetch_dividend_yields",
                AsyncMock(side_effect=_dividend_side_effect),
            ),
            patch(
                "app.services.goal_recommendation_service.fetch_yf_daily_returns",
                return_value=returns_map,
            ),
        ):
            result = await get_horizon_recommendations(None, mock_db, uuid.uuid4(), settings_row)

        rec = result.recommendations[0]
        assert rec.required_dividend_yield_pct == pytest.approx(1.74)
        assert rec.expected_dividend_yield_pct >= 1.74  # 등록 후보만으로 이미 목표 달성
        assert rec.dividend_goal_status == "improvable"
        suggested_tickers = {c.ticker for c in rec.suggested_candidates}
        assert suggested_tickers == {"JEPQ"}
        assert "이미 배당 목표를 달성했지만" in rec.note
        # 제안된 후보는 이번 계산의 recommended_items(비중 계산)에는 반영되지 않는다.
        assert "JEPQ" not in {i.ticker for i in rec.recommended_items}

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
                {"ticker": "133690", "name": "TIGER 미국나스닥100", "market": "KOSPI", "asset_class": "EQUITY"},
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
        """연금저축펀드/IRP 계좌는 국내 후보만 사용해야 하므로 해외 후보는 옵티마이저에 전달되지 않는다.

        IRP는 추가로 퇴직연금 규정상 안전자산(현금성) 최소 30% 하한이 투자기간과 무관하게
        적용되므로, LONG_TERM(원래 EQUITY만 허용)이어도 합성 현금성 자산 후보가 항상 함께
        분석에 포함된다 — PENSION_SAVINGS는 이 규칙 대상이 아니므로 등록된 주식 후보만으로
        기존처럼(안전자산 제약 없이) 계산된다.
        """
        settings_row = SimpleNamespace(
            goal_candidate_tickers=[
                {"ticker": "133690", "name": "TIGER 미국나스닥100", "market": "KOSPI", "asset_class": "EQUITY"},
                {"ticker": "360750", "name": "TIGER 미국S&P500", "market": "KOSPI", "asset_class": "EQUITY"},
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

        cagr_map = {
            ("133690", "KOSPI"): {"cagr_pct": 8.0},
            ("360750", "KOSPI"): {"cagr_pct": 7.0},
        }
        get_historical_returns_mock = AsyncMock(return_value=cagr_map)
        random.seed(19)
        returns_map = {
            "133690.KS": [random.gauss(0.0004, 0.01) for _ in range(252)],
            "360750.KS": [random.gauss(0.0004, 0.01) for _ in range(252)],
        }

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

        assert len(result.recommendations) == 2
        for rec in result.recommendations:
            assert rec.tax_type in {"PENSION_SAVINGS", "IRP"}
        for call in get_historical_returns_mock.call_args_list:
            queried_tickers = call.args[0]
            assert ("SPY", "NYSE") not in queried_tickers

        pension_rec = next(r for r in result.recommendations if r.tax_type == "PENSION_SAVINGS")
        irp_rec = next(r for r in result.recommendations if r.tax_type == "IRP")

        # PENSION_SAVINGS는 IRP 안전자산 규칙 대상이 아니므로 현금성 자산 없이 등록된 주식만으로 계산된다.
        assert pension_rec.includes_cash_equivalent is False
        assert sum(i.weight for i in pension_rec.recommended_items) == pytest.approx(100.0, abs=0.5)

        # IRP는 안전자산 30% 하한(equity_ceiling=70%)이 적용되어 주식(133690+360750) 합산 비중이 제한된다.
        irp_equity_weight = sum(i.weight for i in irp_rec.recommended_items if i.ticker != "CASH_EQUIVALENT")
        assert irp_equity_weight <= 70.0 + 0.5
        assert irp_rec.includes_cash_equivalent is True

    async def test_irp_short_term_uses_safe_asset_floor_instead_of_equity_floor(self):
        """IRP는 단기 태그여도 기존 주식 최소 80% 규칙이 아니라 퇴직연금 규정상 안전자산
        최소 30% 하한(equity_ceiling=70%)이 우선 적용된다."""
        settings_row = SimpleNamespace(
            goal_candidate_tickers=[
                {"ticker": "133690", "name": "TIGER 미국나스닥100", "market": "KOSPI", "asset_class": "EQUITY"},
                {"ticker": "153130", "name": "KODEX 단기채권", "market": "KOSPI", "asset_class": "CASH"},
            ],
            goal_max_weight_pct=None,
            goal_cagr_lookback_years=None,
            goal_short_term_equity_floor_pct=None,
        )
        account_id = uuid.uuid4()
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=_execute_result([("SHORT_TERM", "IRP", account_id)]))

        cagr_map = {
            ("133690", "KOSPI"): {"cagr_pct": 8.0},
            ("153130", "KOSPI"): {"cagr_pct": 2.0},
        }
        random.seed(11)
        returns_map = {
            "133690.KS": [random.gauss(0.0004, 0.01) for _ in range(252)],
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
        stock_weight = next(i.weight for i in rec.recommended_items if i.ticker == "133690")
        assert stock_weight <= 70.0 + 0.5  # 단기 주식 최소 80% 하한이 적용됐다면 이 검증은 실패한다
        assert sum(i.weight for i in rec.recommended_items) == pytest.approx(100.0, abs=0.5)
        assert "IRP" in (rec.note or "")

    async def test_irp_mid_term_enforces_safe_asset_floor(self):
        """IRP+MID_TERM 조합도 안전자산 최소 30% 하한이 투자기간과 무관하게 적용된다."""
        settings_row = SimpleNamespace(
            goal_candidate_tickers=[
                {"ticker": "133690", "name": "TIGER 미국나스닥100", "market": "KOSPI", "asset_class": "EQUITY"},
                {"ticker": "114260", "name": "KODEX 국고채3년", "market": "KOSPI", "asset_class": "BOND"},
            ],
            goal_max_weight_pct=None,
            goal_cagr_lookback_years=None,
        )
        account_id = uuid.uuid4()
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=_execute_result([("MID_TERM", "IRP", account_id)]))

        cagr_map = {
            ("133690", "KOSPI"): {"cagr_pct": 8.0},
            ("114260", "KOSPI"): {"cagr_pct": 3.0},
        }
        random.seed(23)
        returns_map = {
            "133690.KS": [random.gauss(0.0004, 0.01) for _ in range(252)],
            "114260.KS": [random.gauss(0.00015, 0.001) for _ in range(252)],
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
        stock_weight = next(i.weight for i in rec.recommended_items if i.ticker == "133690")
        assert stock_weight <= 70.0 + 0.5
        safe_weight = sum(i.weight for i in rec.recommended_items if i.ticker != "133690")
        assert safe_weight >= 30.0 - 0.5

    async def test_irp_long_term_uses_real_bond_candidate_instead_of_cash_equivalent(self):
        """IRP+LONG_TERM(원래 EQUITY만 허용)에서 실보유 BOND 후보가 등록되어 있으면, 안전자산
        30% 하한을 합성 CASH_EQUIVALENT가 아니라 그 실보유 후보로 채워야 한다.

        회귀 대상 버그: 합성 CASH_EQUIVALENT는 분산·공분산이 0으로 가정되어 있어, 실제 변동성을
        가진 진짜 채권형 ETF를 등록해도 MVO 목적함수(순수 분산 최소화) 상 항상 그 합성 자산이
        우위를 점해 안전자산 몫 전체를 가져가 버리는 문제가 있었다 — 실보유 후보를 BOND로 정확히
        태깅해도 절대 의미 있는 비중을 받지 못했다."""
        settings_row = SimpleNamespace(
            goal_candidate_tickers=[
                {"ticker": "133690", "name": "TIGER 미국나스닥100", "market": "KOSPI", "asset_class": "EQUITY"},
                {
                    "ticker": "438100",
                    "name": "ACE 미국나스닥100미국채혼합50액티브",
                    "market": "KOSPI",
                    "asset_class": "BOND",
                },
            ],
            goal_max_weight_pct=None,
            goal_cagr_lookback_years=None,
        )
        account_id = uuid.uuid4()
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=_execute_result([("LONG_TERM", "IRP", account_id)]))

        cagr_map = {
            ("133690", "KOSPI"): {"cagr_pct": 12.0},
            ("438100", "KOSPI"): {"cagr_pct": 5.0},
        }
        random.seed(23)
        returns_map = {
            "133690.KS": [random.gauss(0.0004, 0.01) for _ in range(252)],
            # 채권혼합형이라도 실제로는 변동성이 0이 아니다 — 이 값이 0에 가까우면 합성 자산과
            # 사실상 구분이 안 돼 이 회귀 테스트의 취지(0-분산 합성 자산과의 경쟁)가 무의미해진다.
            "438100.KS": [random.gauss(0.00015, 0.004) for _ in range(252)],
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
        assert rec.includes_cash_equivalent is False
        bond_weight = next((i.weight for i in rec.recommended_items if i.ticker == "438100"), 0.0)
        assert bond_weight >= 20.0

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

    async def test_market_signal_level_propagates_to_horizon_result(self):
        """LONG_TERM(risk_tolerance=AGGRESSIVE)에서 시장 위험 신호(RED)가 결과에 반영되어야 한다."""
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
                AsyncMock(return_value=cagr_map),
            ),
            patch(
                "app.services.goal_recommendation_service.fetch_yf_daily_returns",
                return_value=returns_map,
            ),
            patch(
                "app.services.goal_recommendation_service.get_market_signal",
                AsyncMock(return_value={"composite_level": "RED", "data_freshness": "LIVE"}),
            ),
        ):
            result = await get_horizon_recommendations(None, mock_db, uuid.uuid4(), settings_row)

        rec = result.recommendations[0]
        assert rec.market_signal_level == "RED"
        assert rec.note is not None
        assert "시장 위험 신호(RED)" in rec.note

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
        assert set(queried_tickers) == {
            ("133690", "KOSPI"),
            ("360750", "KOSPI"),
            ("458730", "KOSPI"),
            ("446720", "KOSPI"),
        }
        assert {item.ticker for item in rec.recommended_items} <= {"133690", "360750", "458730", "446720"}
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
        단계(계좌당 base_krw 계산)는 여전히 (InvestmentHorizon, AccountTaxType) enum 순서대로
        순차 실행되고 최종 결과 순서도 그 순서를 유지해야 한다."""
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
        accounts_by_id = {short_account_id: object(), mid_account_id: object()}
        compute_total_assets_mock = MagicMock(return_value=5_000_000.0)

        with (
            patch(
                "app.services.goal_recommendation_service.query_latest_position_map",
                AsyncMock(return_value={}),
            ),
            patch(
                "app.services.goal_recommendation_service.prefetch_accounts_snapshot_positions",
                AsyncMock(return_value=(accounts_by_id, {}, {}, {})),
            ),
            patch(
                "app.services.goal_recommendation_service.compute_total_assets_krw",
                compute_total_assets_mock,
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

        assert [(r.investment_horizon, r.tax_type) for r in result.recommendations] == [
            ("SHORT_TERM", "GENERAL"),
            ("MID_TERM", "GENERAL"),
        ]
        combo_accounts_seen = [call.args[0] for call in compute_total_assets_mock.call_args_list]
        assert combo_accounts_seen == [[accounts_by_id[short_account_id]], [accounts_by_id[mid_account_id]]]

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
        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value=None)

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
            result = await get_horizon_recommendations(mock_cache, mock_db, uuid.uuid4(), settings_row)

        assert len(result.recommendations) == 1
        assert result.recommendations[0].recommended_items == []
        mock_cache.setex.assert_not_called()

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
        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value=None)
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
            result = await get_horizon_recommendations(mock_cache, mock_db, uuid.uuid4(), settings_row)

        assert len(result.recommendations) == 1
        assert result.recommendations[0].recommended_items
        mock_cache.setex.assert_awaited_once()


class TestAgeGroupProfile:
    """연령대(`UserSettings.age_group`) → (구간 라벨, risk_tolerance, equity_floor, equity_ceiling,
    기본 배당수익률 하한%) 매핑."""

    def test_twenties_gets_aggressive_equity_floor(self):
        label, risk_tolerance, equity_floor, equity_ceiling, dividend_floor = _AGE_GROUP_PROFILE["TWENTIES"]
        assert label == "20대"
        assert risk_tolerance == "AGGRESSIVE"
        assert equity_floor == 0.8
        assert equity_ceiling is None
        assert dividend_floor == 0.0

    def test_thirties_gets_aggressive_equity_floor(self):
        label, risk_tolerance, equity_floor, equity_ceiling, dividend_floor = _AGE_GROUP_PROFILE["THIRTIES"]
        assert label == "30대"
        assert risk_tolerance == "AGGRESSIVE"
        assert equity_floor == 0.7
        assert equity_ceiling is None
        assert dividend_floor == 0.0

    def test_forties_gets_balanced_equity_floor(self):
        label, risk_tolerance, equity_floor, equity_ceiling, dividend_floor = _AGE_GROUP_PROFILE["FORTIES"]
        assert label == "40대"
        assert risk_tolerance == "BALANCED"
        assert equity_floor == 0.55
        assert equity_ceiling is None
        assert dividend_floor == 1.5

    def test_fifties_gets_balanced_equity_ceiling(self):
        label, risk_tolerance, equity_floor, equity_ceiling, dividend_floor = _AGE_GROUP_PROFILE["FIFTIES"]
        assert label == "50대"
        assert risk_tolerance == "BALANCED"
        assert equity_floor is None
        assert equity_ceiling == 0.6
        assert dividend_floor == 2.5

    def test_sixties_plus_gets_conservative_equity_ceiling(self):
        label, risk_tolerance, equity_floor, equity_ceiling, dividend_floor = _AGE_GROUP_PROFILE["SIXTIES_PLUS"]
        assert label == "60대 이상"
        assert risk_tolerance == "CONSERVATIVE"
        assert equity_floor is None
        assert equity_ceiling == 0.35
        assert dividend_floor == 3.5

    def test_dividend_floor_increases_monotonically_with_age(self):
        """ "나이가 많을수록 배당목표에 초점" 요구사항 — 연령대 순서대로 배당수익률 하한이
        감소하지 않아야 한다."""
        order = ["TWENTIES", "THIRTIES", "FORTIES", "FIFTIES", "SIXTIES_PLUS"]
        floors = [_AGE_GROUP_PROFILE[key][4] for key in order]
        assert floors == sorted(floors)


class TestAgeGroupFromBirthYear:
    """출생연도 → `_AGE_GROUP_PROFILE` 조회용 연령대 파생(`age_group_from_birth_year`) — 온보딩에서
    실제 나이를 입력받아 기존 연령대 버킷 로직에 매핑하는 헬퍼."""

    def _current_year(self) -> int:
        from datetime import UTC, datetime

        return datetime.now(UTC).year

    def test_twenties(self):
        year = self._current_year()
        assert age_group_from_birth_year(year - 25).value == "TWENTIES"

    def test_thirties(self):
        year = self._current_year()
        assert age_group_from_birth_year(year - 35).value == "THIRTIES"

    def test_forties(self):
        year = self._current_year()
        assert age_group_from_birth_year(year - 45).value == "FORTIES"

    def test_fifties(self):
        year = self._current_year()
        assert age_group_from_birth_year(year - 55).value == "FIFTIES"

    def test_sixties_plus(self):
        year = self._current_year()
        assert age_group_from_birth_year(year - 65).value == "SIXTIES_PLUS"

    def test_boundary_ages_snap_to_next_bucket(self):
        year = self._current_year()
        assert age_group_from_birth_year(year - 30).value == "THIRTIES"
        assert age_group_from_birth_year(year - 40).value == "FORTIES"
        assert age_group_from_birth_year(year - 50).value == "FIFTIES"
        assert age_group_from_birth_year(year - 60).value == "SIXTIES_PLUS"

    def test_under_twenty_clamps_to_twenties(self):
        year = self._current_year()
        assert age_group_from_birth_year(year - 10).value == "TWENTIES"


class TestGetAgeBasedRecommendation:
    """사용자가 직접 선택한 연령대(`UserSettings.age_group`) 기반 추천 — 목표 역산 없이 연령대의
    risk_tolerance + 주식비중 상/하한만으로 비중을 계산한다."""

    async def test_age_group_not_configured_returns_not_configured(self):
        settings_row = SimpleNamespace(age_group=None)

        result = await get_age_based_recommendation(None, AsyncMock(), uuid.uuid4(), settings_row)

        assert result.is_configured is False
        assert "연령대" in result.note
        assert result.recommended_items == []

    async def test_no_candidates_registered(self):
        settings_row = SimpleNamespace(
            age_group="TWENTIES",
            goal_candidate_tickers=[],
            goal_max_weight_pct=None,
            goal_cagr_lookback_years=None,
        )

        with patch(
            "app.services.goal_age_recommendation_service.query_latest_position_map",
            AsyncMock(return_value={}),
        ):
            result = await get_age_based_recommendation(None, AsyncMock(), uuid.uuid4(), settings_row)

        assert result.age_bracket == "20대"
        assert result.recommended_items == []
        assert "후보 ETF" in result.note

    async def test_twenties_applies_equity_floor_with_cash_equivalent_fallback(self):
        """20대는 AGGRESSIVE + equity_floor 80% — 등록된 안전자산 후보가 하나도 없으면 합성
        현금성 자산(CASH_EQUIVALENT)으로 나머지를 채운다."""
        settings_row = SimpleNamespace(
            age_group="TWENTIES",
            goal_candidate_tickers=[
                {"ticker": "SPY", "name": "SPDR S&P 500 ETF", "market": "NYSE", "asset_class": "EQUITY"},
                {"ticker": "QQQ", "name": "Invesco QQQ Trust", "market": "NASDAQ", "asset_class": "EQUITY"},
                {"ticker": "VOO", "name": "Vanguard S&P 500 ETF", "market": "NYSE", "asset_class": "EQUITY"},
            ],
            goal_max_weight_pct=None,
            goal_cagr_lookback_years=None,
        )
        random.seed(11)
        returns_map = {
            "SPY": [random.gauss(0.0005, 0.01) for _ in range(252)],
            "QQQ": [random.gauss(0.0006, 0.012) for _ in range(252)],
            "VOO": [random.gauss(0.00055, 0.0105) for _ in range(252)],
        }

        with (
            patch(
                "app.services.goal_age_recommendation_service.query_latest_position_map",
                AsyncMock(return_value={}),
            ),
            patch(
                "app.services.goal_age_recommendation_service.get_historical_returns",
                AsyncMock(
                    return_value={
                        ("SPY", "NYSE"): {"cagr_pct": 10.0},
                        ("QQQ", "NASDAQ"): {"cagr_pct": 12.0},
                        ("VOO", "NYSE"): {"cagr_pct": 10.5},
                    }
                ),
            ),
            patch(
                "app.services.goal_age_recommendation_service.fetch_yf_daily_returns",
                return_value=returns_map,
            ),
        ):
            result = await get_age_based_recommendation(None, AsyncMock(), uuid.uuid4(), settings_row)

        assert result.age_bracket == "20대"
        assert result.risk_tolerance == "AGGRESSIVE"
        assert result.includes_cash_equivalent is True
        tickers = {item.ticker for item in result.recommended_items}
        assert "CASH_EQUIVALENT" in tickers
        equity_weight = sum(item.weight for item in result.recommended_items if item.ticker in {"SPY", "QQQ", "VOO"})
        assert equity_weight >= 75.0
        # 20대는 배당수익률 하한이 0이라 annual_dividend_goal 미설정 시 배당 제약을 전혀 걸지 않는다
        assert result.required_dividend_yield_pct is None

    async def test_sixties_plus_applies_equity_ceiling(self):
        """60대 이상은 CONSERVATIVE + equity_ceiling 35% — 주식 비중이 상한을 크게 넘지 않는다."""
        settings_row = SimpleNamespace(
            age_group="SIXTIES_PLUS",
            goal_candidate_tickers=[
                {"ticker": "SPY", "name": "SPDR S&P 500 ETF", "market": "NYSE", "asset_class": "EQUITY"},
                {"ticker": "114260", "name": "KODEX 국고채3년", "market": "KOSPI", "asset_class": "BOND"},
            ],
            goal_max_weight_pct=None,
            goal_cagr_lookback_years=None,
        )
        random.seed(13)
        returns_map = {
            "SPY": [random.gauss(0.0006, 0.012) for _ in range(252)],
            "114260.KS": [random.gauss(0.0001, 0.001) for _ in range(252)],
        }

        with (
            patch(
                "app.services.goal_age_recommendation_service.query_latest_position_map",
                AsyncMock(return_value={}),
            ),
            patch(
                "app.services.goal_age_recommendation_service.get_historical_returns",
                AsyncMock(return_value={("SPY", "NYSE"): {"cagr_pct": 10.0}, ("114260", "KOSPI"): {"cagr_pct": 3.0}}),
            ),
            patch(
                "app.services.goal_age_recommendation_service.fetch_yf_daily_returns",
                return_value=returns_map,
            ),
        ):
            result = await get_age_based_recommendation(None, AsyncMock(), uuid.uuid4(), settings_row)

        assert result.age_bracket == "60대 이상"
        assert result.risk_tolerance == "CONSERVATIVE"
        assert result.includes_cash_equivalent is False
        spy_weight = next((item.weight for item in result.recommended_items if item.ticker == "SPY"), 0.0)
        assert spy_weight <= 35.5

    async def test_caches_result_when_recommendation_produced(self):
        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value=None)
        settings_row = SimpleNamespace(
            age_group="FORTIES",
            goal_candidate_tickers=[
                {"ticker": "SPY", "name": "SPDR S&P 500 ETF", "market": "NYSE", "asset_class": "EQUITY"},
                {"ticker": "QQQ", "name": "Invesco QQQ Trust", "market": "NASDAQ", "asset_class": "EQUITY"},
                {"ticker": "114260", "name": "KODEX 국고채3년", "market": "KOSPI", "asset_class": "BOND"},
            ],
            goal_max_weight_pct=None,
            goal_cagr_lookback_years=None,
        )
        random.seed(17)
        returns_map = {
            "SPY": [random.gauss(0.0006, 0.012) for _ in range(252)],
            "QQQ": [random.gauss(0.0007, 0.014) for _ in range(252)],
            "114260.KS": [random.gauss(0.0001, 0.001) for _ in range(252)],
        }

        with (
            patch(
                "app.services.goal_age_recommendation_service.query_latest_position_map",
                AsyncMock(return_value={}),
            ),
            patch(
                "app.services.goal_age_recommendation_service.get_historical_returns",
                AsyncMock(
                    return_value={
                        ("SPY", "NYSE"): {"cagr_pct": 10.0},
                        ("QQQ", "NASDAQ"): {"cagr_pct": 12.0},
                        ("114260", "KOSPI"): {"cagr_pct": 3.0},
                    }
                ),
            ),
            patch(
                "app.services.goal_age_recommendation_service.fetch_yf_daily_returns",
                return_value=returns_map,
            ),
        ):
            result = await get_age_based_recommendation(mock_cache, AsyncMock(), uuid.uuid4(), settings_row)

        assert result.recommended_items
        mock_cache.setex.assert_awaited_once()

    async def test_age_default_dividend_floor_shifts_weight_to_high_yield_candidate(self):
        """annual_dividend_goal 미설정 + 40대 → 연령대 기본 배당수익률 하한(1.5%)이
        required_dividend_yield_pct로 반영되고, note에 안내 문구가 포함되며, 고배당 후보(SCHD)
        비중이 늘어 목표 배당수익률을 충족한다."""
        settings_row = SimpleNamespace(
            age_group="FORTIES",
            annual_dividend_goal=None,
            goal_candidate_tickers=[
                {"ticker": "SPY", "name": "SPDR S&P 500 ETF", "market": "NYSE", "asset_class": "EQUITY"},
                {"ticker": "SCHD", "name": "Schwab US Dividend Equity ETF", "market": "NYSE", "asset_class": "EQUITY"},
            ],
            goal_max_weight_pct=100.0,  # 종목당 상한을 풀어 배당 제약이 실제로 비중을 좌우하게 함
            goal_cagr_lookback_years=None,
        )
        random.seed(19)
        returns_map = {
            "SPY": [random.gauss(0.0005, 0.01) for _ in range(252)],
            "SCHD": [random.gauss(0.0004, 0.009) for _ in range(252)],
        }
        dividend_map = {("SPY", "NYSE"): 0.0, ("SCHD", "NYSE"): 3.5}

        with (
            patch(
                "app.services.goal_age_recommendation_service.query_latest_position_map",
                AsyncMock(return_value={}),
            ),
            patch(
                "app.services.goal_age_recommendation_service.get_historical_returns",
                AsyncMock(return_value={("SPY", "NYSE"): {"cagr_pct": 10.0}, ("SCHD", "NYSE"): {"cagr_pct": 8.0}}),
            ),
            patch(
                "app.services.goal_age_recommendation_service._fetch_dividend_yields",
                AsyncMock(return_value=dividend_map),
            ),
            patch(
                "app.services.goal_age_recommendation_service.fetch_yf_daily_returns",
                return_value=returns_map,
            ),
        ):
            result = await get_age_based_recommendation(None, AsyncMock(), uuid.uuid4(), settings_row)

        assert result.age_bracket == "40대"
        assert result.required_dividend_yield_pct == 1.5
        assert "40대" in result.note
        assert "1.5" in result.note
        assert result.expected_dividend_yield_pct is not None
        assert result.expected_dividend_yield_pct >= 1.4  # 반올림 오차 허용
        # SPY(저배당, dividend_map=0.0)도 분산 목적으로 포함될 수 있는데, 종목별 배당수익률이
        # dividend_map과 일치해야 화면에서 "이건 배당 목적이 아니다"를 구분할 수 있다.
        for item in result.recommended_items:
            assert item.dividend_yield_pct == dividend_map.get((item.ticker, item.market))

    async def test_explicit_dividend_goal_overrides_age_default(self):
        """annual_dividend_goal이 설정돼 있으면 연령대 기본값(40대=1.5%) 대신 명시적 목표에서
        계산된 값이 우선 반영된다."""
        settings_row = SimpleNamespace(
            age_group="FORTIES",
            annual_dividend_goal=1_000_000.0,
            goal_candidate_tickers=[
                {"ticker": "SPY", "name": "SPDR S&P 500 ETF", "market": "NYSE", "asset_class": "EQUITY"},
                {"ticker": "SCHD", "name": "Schwab US Dividend Equity ETF", "market": "NYSE", "asset_class": "EQUITY"},
            ],
            goal_max_weight_pct=100.0,
            goal_cagr_lookback_years=None,
        )
        random.seed(23)
        returns_map = {
            "SPY": [random.gauss(0.0005, 0.01) for _ in range(252)],
            "SCHD": [random.gauss(0.0004, 0.009) for _ in range(252)],
        }
        dividend_map = {("SPY", "NYSE"): 0.0, ("SCHD", "NYSE"): 3.5}

        with (
            patch(
                "app.services.goal_age_recommendation_service.query_latest_position_map",
                AsyncMock(return_value={}),
            ),
            patch(
                "app.services.goal_age_recommendation_service.build_portfolio_overview",
                AsyncMock(return_value={"total_assets_krw": 10_000_000.0}),
            ),
            patch(
                "app.services.goal_age_recommendation_service.get_historical_returns",
                AsyncMock(return_value={("SPY", "NYSE"): {"cagr_pct": 10.0}, ("SCHD", "NYSE"): {"cagr_pct": 8.0}}),
            ),
            patch(
                "app.services.goal_age_recommendation_service._fetch_dividend_yields",
                AsyncMock(return_value=dividend_map),
            ),
            patch(
                "app.services.goal_age_recommendation_service.fetch_yf_daily_returns",
                return_value=returns_map,
            ),
        ):
            result = await get_age_based_recommendation(None, AsyncMock(), uuid.uuid4(), settings_row)

        # 1,000,000 / 10,000,000 * 100 = 10.0% — 40대 기본값(1.5%)보다 훨씬 큼
        assert result.required_dividend_yield_pct == 10.0
        # 큐레이션 후보(최대 3.5%)로는 10% 목표를 달성할 수 없어 fail-soft로 무시된다
        assert "충족하는 조합을 찾지 못해" in result.note
        # 명시적 목표를 쓴 경우이므로 연령대 기본값 안내 문구는 붙지 않는다
        assert "연령대 기본" not in result.note
        assert result.recommended_items

    async def test_unachievable_age_default_dividend_goal_falls_back_gracefully(self):
        """연령대 기본 배당목표가 큐레이션 후보로 달성 불가능하면 제약을 조용히 무시하고(fail-soft)
        note로 안내하되, 추천 자체는 정상적으로 반환된다."""
        settings_row = SimpleNamespace(
            age_group="SIXTIES_PLUS",
            annual_dividend_goal=None,
            goal_candidate_tickers=[
                {"ticker": "SPY", "name": "SPDR S&P 500 ETF", "market": "NYSE", "asset_class": "EQUITY"},
                {"ticker": "114260", "name": "KODEX 국고채3년", "market": "KOSPI", "asset_class": "BOND"},
            ],
            goal_max_weight_pct=None,
            goal_cagr_lookback_years=None,
        )
        random.seed(29)
        returns_map = {
            "SPY": [random.gauss(0.0006, 0.012) for _ in range(252)],
            "114260.KS": [random.gauss(0.0001, 0.001) for _ in range(252)],
        }
        # 두 후보 모두 배당수익률 0% — 60대 이상 기본 하한(3.5%)은 절대 달성 불가능
        dividend_map = {("SPY", "NYSE"): 0.0, ("114260", "KOSPI"): 0.0}

        with (
            patch(
                "app.services.goal_age_recommendation_service.query_latest_position_map",
                AsyncMock(return_value={}),
            ),
            patch(
                "app.services.goal_age_recommendation_service.get_historical_returns",
                AsyncMock(return_value={("SPY", "NYSE"): {"cagr_pct": 10.0}, ("114260", "KOSPI"): {"cagr_pct": 3.0}}),
            ),
            patch(
                "app.services.goal_age_recommendation_service._fetch_dividend_yields",
                AsyncMock(return_value=dividend_map),
            ),
            patch(
                "app.services.goal_age_recommendation_service.fetch_yf_daily_returns",
                return_value=returns_map,
            ),
        ):
            result = await get_age_based_recommendation(None, AsyncMock(), uuid.uuid4(), settings_row)

        assert result.required_dividend_yield_pct == 3.5
        assert "60대 이상 연령대 기본 배당목표" in result.note
        assert "충족하는 조합을 찾지 못해" in result.note
        assert result.recommended_items

    async def test_age_default_dividend_goal_suggests_curated_high_yield_candidate(self):
        """등록된 후보(SPY 1.0%, 114260 국고채 0%)만으로는 60대 이상 기본 배당목표(3.5%)를
        달성할 수 없을 때, 큐레이션 유니버스의 고배당 후보(JEPQ)를 `suggested_candidates`로
        제안한다 — 사용자가 승인하기 전까지는 비중 계산(`recommended_items`)에 반영되지
        않고, 등록 목록(`goal_candidate_tickers`)도 그대로 유지된다."""
        settings_row = SimpleNamespace(
            age_group="SIXTIES_PLUS",
            annual_dividend_goal=None,
            goal_candidate_tickers=[
                {"ticker": "SPY", "name": "SPDR S&P 500 ETF", "market": "NYSE", "asset_class": "EQUITY"},
                {"ticker": "114260", "name": "KODEX 국고채3년", "market": "KOSPI", "asset_class": "BOND"},
            ],
            goal_max_weight_pct=None,
            goal_cagr_lookback_years=None,
        )
        random.seed(31)
        returns_map = {
            "SPY": [random.gauss(0.0006, 0.012) for _ in range(252)],
            "114260.KS": [random.gauss(0.0001, 0.001) for _ in range(252)],
            "JEPQ": [random.gauss(0.0003, 0.009) for _ in range(252)],
        }
        cagr_map = {
            ("SPY", "NYSE"): {"cagr_pct": 10.0},
            ("114260", "KOSPI"): {"cagr_pct": 3.0},
            ("JEPQ", "NASDAQ"): {"cagr_pct": 6.0},
        }
        dividend_by_ticker = {
            ("SPY", "NYSE"): 1.0,
            ("114260", "KOSPI"): 0.0,
            ("JEPQ", "NASDAQ"): 9.95,
            ("JEPI", "NYSE"): 8.1,
            ("SCHD", "NYSE"): 3.5,
            ("VYM", "NYSE"): 2.9,
            ("458730", "KOSPI"): 2.81,
            ("446720", "KOSPI"): 2.88,
        }

        async def _dividend_side_effect(cache, tickers):
            return {tm: dividend_by_ticker[tm] for tm in tickers if tm in dividend_by_ticker}

        user_id = uuid.uuid4()
        mock_db = AsyncMock()

        with (
            patch(
                "app.services.goal_age_recommendation_service.query_latest_position_map",
                AsyncMock(return_value={}),
            ),
            patch(
                "app.services.goal_age_recommendation_service.get_historical_returns",
                AsyncMock(return_value=cagr_map),
            ),
            patch(
                "app.services.goal_age_recommendation_service._fetch_dividend_yields",
                AsyncMock(side_effect=_dividend_side_effect),
            ),
            patch(
                "app.services.goal_recommendation_service._fetch_dividend_yields",
                AsyncMock(side_effect=_dividend_side_effect),
            ),
            patch(
                "app.services.goal_age_recommendation_service.fetch_yf_daily_returns",
                return_value=returns_map,
            ),
        ):
            result = await get_age_based_recommendation(None, mock_db, user_id, settings_row)

        recommended_tickers = {item.ticker for item in result.recommended_items}
        assert "JEPQ" not in recommended_tickers  # 승인 전에는 비중 계산에 반영되지 않음

        suggested_tickers = {c.ticker for c in result.suggested_candidates}
        assert "JEPQ" in suggested_tickers  # 가장 배당수익률이 높은 미등록 후보가 제안됨
        jepq = next(c for c in result.suggested_candidates if c.ticker == "JEPQ")
        assert jepq.dividend_yield_pct == 9.95

        assert "60대 이상 연령대 기본 배당목표" in result.note
        assert "아래 고배당 후보를 추가하면 도움이 됩니다" in result.note
        assert "자동 등록" not in result.note
        mock_db.commit.assert_not_awaited()
        assert result.risk_tolerance == "CONSERVATIVE"
        # 승인 전이므로 등록 목록(goal_candidate_tickers)은 변경되지 않아야 한다.
        assert len(settings_row.goal_candidate_tickers) == 2

    async def test_age_based_already_achieving_dividend_goal_suggests_better_candidate(self):
        """등록 후보(QQQ/VOO/SCHD)만으로 명시적 배당목표(연 1.74%)를 이미 달성했어도, 등록
        후보만으로는 개선 목표(1.74+0.5=2.24%)에 못 미쳐 큐레이션 유니버스의 JEPQ(9.95%)가
        "더 나은 옵션"으로 제안돼야 한다 — overall/by-horizon과 동일한 사후 판정 배선을
        연령대별 경로에서도 검증."""
        settings_row = SimpleNamespace(
            age_group="FORTIES",
            annual_dividend_goal=174_000.0,  # total_assets_krw 10,000,000 대비 1.74%
            goal_candidate_tickers=[
                {"ticker": "QQQ", "name": "Invesco QQQ Trust", "market": "NASDAQ", "asset_class": "EQUITY"},
                {"ticker": "VOO", "name": "Vanguard S&P 500 ETF", "market": "NYSE", "asset_class": "EQUITY"},
                {"ticker": "SCHD", "name": "Schwab US Dividend Equity ETF", "market": "NYSE", "asset_class": "EQUITY"},
            ],
            goal_max_weight_pct=40.0,
            goal_cagr_lookback_years=None,
        )
        cagr_map = {
            ("QQQ", "NASDAQ"): {"cagr_pct": 18.0},
            ("VOO", "NYSE"): {"cagr_pct": 13.0},
            ("SCHD", "NYSE"): {"cagr_pct": 11.0},
        }
        dividend_map = {
            ("QQQ", "NASDAQ"): 0.6,
            ("VOO", "NYSE"): 1.3,
            ("SCHD", "NYSE"): 3.5,
            ("JEPQ", "NASDAQ"): 9.95,
            ("JEPI", "NYSE"): 8.1,
        }
        random.seed(5)
        returns_map = {
            "QQQ": [random.gauss(0.0009, 0.013) for _ in range(252)],
            "VOO": [random.gauss(0.0006, 0.010) for _ in range(252)],
            "SCHD": [random.gauss(0.0005, 0.009) for _ in range(252)],
        }

        async def _dividend_side_effect(cache, tickers):
            return {tm: dividend_map[tm] for tm in tickers if tm in dividend_map}

        with (
            patch(
                "app.services.goal_age_recommendation_service.query_latest_position_map",
                AsyncMock(return_value={}),
            ),
            patch(
                "app.services.goal_age_recommendation_service.build_portfolio_overview",
                AsyncMock(return_value={"total_assets_krw": 10_000_000.0}),
            ),
            patch(
                "app.services.goal_age_recommendation_service.get_historical_returns",
                AsyncMock(return_value=cagr_map),
            ),
            patch(
                "app.services.goal_age_recommendation_service._fetch_dividend_yields",
                AsyncMock(side_effect=_dividend_side_effect),
            ),
            patch(
                "app.services.goal_recommendation_service._fetch_dividend_yields",
                AsyncMock(side_effect=_dividend_side_effect),
            ),
            patch(
                "app.services.goal_age_recommendation_service.fetch_yf_daily_returns",
                return_value=returns_map,
            ),
        ):
            result = await get_age_based_recommendation(None, AsyncMock(), uuid.uuid4(), settings_row)

        assert result.expected_dividend_yield_pct >= 1.74  # 등록 후보만으로 이미 목표 달성
        assert result.dividend_goal_status == "improvable"
        suggested_tickers = {c.ticker for c in result.suggested_candidates}
        assert suggested_tickers == {"JEPQ"}
        assert "이미 배당 목표를 달성했지만" in result.note
        assert "JEPQ" not in {i.ticker for i in result.recommended_items}


class TestComputeWeightedExpectedMetrics:
    """`compute_weighted_expected_metrics()` — 이미 정해진 비중에 대한 기대수익률/배당수익률/변동성 계산."""

    def test_empty_symbols_returns_all_none(self):
        result = compute_weighted_expected_metrics([], [], {}, {}, {})
        assert result == (None, None, None)

    def test_no_matching_returns_data_returns_all_none(self):
        result = compute_weighted_expected_metrics(["SPY"], [100.0], {"SPY": 10.0}, {"SPY": 2.0}, {})
        assert result == (None, None, None)

    def test_single_symbol_weighted_average_equals_its_own_values(self):
        random.seed(1)
        returns_map = {"SPY": [random.gauss(0.0005, 0.01) for _ in range(252)]}
        expected_return, expected_dividend, expected_volatility = compute_weighted_expected_metrics(
            ["SPY"], [100.0], {"SPY": 10.0}, {"SPY": 2.0}, returns_map
        )
        assert expected_return == 10.0
        assert expected_dividend == 2.0
        assert expected_volatility is not None
        assert expected_volatility > 0

    def test_two_symbols_weighted_average(self):
        random.seed(2)
        returns_map = {
            "SPY": [random.gauss(0.0005, 0.01) for _ in range(252)],
            "QQQ": [random.gauss(0.0007, 0.015) for _ in range(252)],
        }
        expected_return, expected_dividend, _ = compute_weighted_expected_metrics(
            ["SPY", "QQQ"],
            [50.0, 50.0],
            {"SPY": 10.0, "QQQ": 20.0},
            {"SPY": 2.0, "QQQ": 0.5},
            returns_map,
        )
        assert expected_return == 15.0  # (10+20)/2
        assert expected_dividend == 1.25  # (2.0+0.5)/2

    def test_missing_return_data_excluded_and_renormalized(self):
        """시세 데이터 없는 종목은 제외되고 나머지 비중으로 재정규화된다."""
        random.seed(3)
        returns_map = {"SPY": [random.gauss(0.0005, 0.01) for _ in range(252)]}
        expected_return, _, _ = compute_weighted_expected_metrics(
            ["SPY", "MISSING"],
            [50.0, 50.0],
            {"SPY": 10.0, "MISSING": 999.0},
            {"SPY": 2.0, "MISSING": 999.0},
            returns_map,
        )
        assert expected_return == 10.0  # MISSING 제외 후 SPY 100%로 재정규화


class TestComputePortfolioExpectedMetrics:
    """`compute_portfolio_expected_metrics()` — 포트폴리오의 현재 목표 비중에 대한 지표 계산(적용 전 비교 미리보기)."""

    @pytest.mark.asyncio
    async def test_empty_items_returns_empty_metrics(self):
        result = await compute_portfolio_expected_metrics(None, [])
        assert result.expected_return_pct is None
        assert result.expected_dividend_yield_pct is None
        assert result.expected_volatility_pct is None

    @pytest.mark.asyncio
    async def test_computes_metrics_from_items(self):
        random.seed(4)
        returns_map = {"SPY": [random.gauss(0.0005, 0.01) for _ in range(252)]}

        with (
            patch(
                "app.services.goal_recommendation_service.get_historical_returns",
                AsyncMock(return_value={("SPY", "NYSE"): {"cagr_pct": 10.0}}),
            ),
            patch(
                "app.services.goal_recommendation_service._fetch_dividend_yields",
                AsyncMock(return_value={("SPY", "NYSE"): 2.0}),
            ),
            patch(
                "app.services.goal_recommendation_service.fetch_yf_daily_returns",
                return_value=returns_map,
            ),
        ):
            result = await compute_portfolio_expected_metrics(None, [("SPY", "NYSE", "SPDR S&P 500", 100.0)])

        assert result.expected_return_pct == 10.0
        assert result.expected_dividend_yield_pct == 2.0
        assert result.expected_volatility_pct is not None


class TestComputeRecommendationDrift:
    """`compute_recommendation_drift()` — 프론트 `recommendationDrift.ts`와 동일한 로직의 백엔드 포팅."""

    def test_no_drift_when_weights_match(self):
        recommended = [("SPY", "NYSE", 100.0)]
        current = [("SPY", "NYSE", 100.0)]
        assert compute_recommendation_drift(recommended, current) == (0.0, 0)

    def test_max_delta_pct_reflects_largest_difference(self):
        recommended = [("SPY", "NYSE", 80.0), ("QQQ", "NASDAQ", 20.0)]
        current = [("SPY", "NYSE", 50.0), ("QQQ", "NASDAQ", 50.0)]
        max_delta_pct, new_candidate_count = compute_recommendation_drift(recommended, current)
        assert max_delta_pct == 30.0
        assert new_candidate_count == 0

    def test_new_candidate_not_in_current_counted(self):
        recommended = [("SPY", "NYSE", 50.0), ("SCHD", "NYSE", 50.0)]
        current = [("SPY", "NYSE", 50.0)]
        max_delta_pct, new_candidate_count = compute_recommendation_drift(recommended, current)
        assert max_delta_pct == 0.0
        assert new_candidate_count == 1

    def test_ticker_matches_only_on_same_market(self):
        """같은 티커라도 market이 다르면 다른 종목으로 취급 — 신규 후보로 카운트된다."""
        recommended = [("069500", "KOSPI", 100.0)]
        current = [("069500", "KOSDAQ", 100.0)]
        max_delta_pct, new_candidate_count = compute_recommendation_drift(recommended, current)
        assert new_candidate_count == 1
