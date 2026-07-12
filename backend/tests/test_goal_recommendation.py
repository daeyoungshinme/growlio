"""goal_return_solver.py / goal_recommendation_service.py 단위 테스트."""

from __future__ import annotations

import random
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.goal_recommendation_service import (
    _months_until_year_end,
    _optimize_goal_portfolio,
    existing_items_from_positions,
    get_goal_recommendation,
)
from app.services.goal_return_solver import solve_required_annual_return_pct


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
        assert len(settings_row.goal_candidate_tickers) <= 10
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
