"""goal_portfolio_optimizer.py 단위 테스트.

배당 달성가능성 사전검증(`_dividend_floor_constraint`)이 `equity_floor`/`equity_ceiling`
그룹 예산을 무시해 실제로는 불가능한 배당 목표를 "달성 가능"으로 오판, SLSQP에 불충족
제약을 넘겨 최적화 전체가 실패(빈 추천)하던 버그의 회귀 테스트.
"""

import random

from app.services.goal_portfolio_optimizer import (
    _dividend_floor_constraint,
    _optimize_goal_portfolio,
)


class TestDividendFloorConstraintGroupBudget:
    """`equity_flags`/`group_budget` 없이 호출하면(기존 동작) 종목당 상한만으로 판정한다."""

    def test_without_group_budget_uses_per_ticker_bounds_only(self):
        bounds = [(0.0, 0.8), (0.0, 0.6)]
        dividends = (2.0, 3.0)
        # 종목당 상한만 보면(그룹 예산 무시) 고배당 종목(0.6)부터 채우고 남는 0.4를 저배당
        # 종목에 배분 -> 0.6*3.0 + 0.4*2.0 = 2.6%까지 달성 가능
        constraint, note = _dividend_floor_constraint(bounds, dividends, 2.6)
        assert constraint is not None
        assert note is None

        constraint2, note2 = _dividend_floor_constraint(bounds, dividends, 2.7)
        assert constraint2 is None
        assert "충족하는 조합을 찾지 못해" in note2

    def test_group_budget_lowers_achievable_ceiling_when_equity_floor_forces_low_yield_stock(self):
        """주식(배당 2.0%) 하나뿐인데 equity_floor로 최소 0.8까지 강제 배분되면, 비주식(배당
        3.0%)에는 0.2만 남아 실제 달성 가능한 최대는 0.8*2.0 + 0.2*3.0 = 2.2%뿐이다.

        `group_budget` 없이 종목당 상한(bounds)만 보면 이 종목이 상한(0.8)까지 배당 3.0%
        종목과 무관하게 자유롭게 움직일 수 있다고 오판해 더 높은 값(예: bounds 상 최댓값)을
        달성 가능하다고 착각할 수 있다 — 아래 테스트가 그 차이를 검증한다.
        """
        bounds = [(0.0, 0.8), (0.0, 0.6)]  # equity_floor로 인해 확장된 주식 종목 상한(0.8)
        dividends = (2.0, 3.0)
        equity_flags = (True, False)
        group_budget = {True: 1.0, False: 0.2}  # 비주식 예산 = 1 - equity_floor(0.8)

        # group_budget 없이는 achievable = 0.8*2.0 + 0.2*3.0 = 2.2%로 동일하게 계산되지만
        # (bounds 자체가 이미 equity_cap=0.8로 좁혀져 있으므로), 아래처럼 종목당 상한이 더
        # 느슨한(equity_floor보다 큰 max_weight) 경우 차이가 드러난다.
        wide_bounds = [(0.0, 0.6), (0.0, 0.6)]  # equity_floor 반영 전 원래 max_weight
        constraint_no_budget, note_no_budget = _dividend_floor_constraint(wide_bounds, dividends, 2.6)
        assert constraint_no_budget is not None  # bounds만 보면 0.6*3.0+0.4*2.0=2.6% 달성 가능으로 오판
        assert note_no_budget is None

        constraint_with_budget, note_with_budget = _dividend_floor_constraint(
            wide_bounds, dividends, 2.6, equity_flags=equity_flags, group_budget=group_budget
        )
        assert constraint_with_budget is None  # 그룹 예산 반영 시 실제로는 2.2%가 한계라 불가능
        assert "충족하는 조합을 찾지 못해" in note_with_budget

        # 실제 한계치(2.2%) 이하는 그룹 예산을 반영해도 여전히 달성 가능
        constraint_ok, note_ok = _dividend_floor_constraint(
            bounds, dividends, 2.2, equity_flags=equity_flags, group_budget=group_budget
        )
        assert constraint_ok is not None
        assert note_ok is None


class TestOptimizeGoalPortfolioDividendEquityFloorInteraction:
    """단기(SHORT_TERM) 추천처럼 `equity_floor`+`required_dividend_yield_pct`가 동시에 걸리는
    시나리오의 회귀 테스트 — 실제 계정 설정(종목당 최대 비중 60%, equity_floor 80%)으로
    재현된 버그를 그대로 축소한 시나리오."""

    def _candidates(self):
        symbols = ["069500.KS", "153130.KS", "114260.KS", "357870.KS"]
        tickers = [
            ("069500", "KODEX 200", "KOSPI"),
            ("153130", "KODEX 단기채권", "KOSPI"),
            ("114260", "KODEX 국고채3년", "KOSPI"),
            ("357870", "TIGER CD금리투자KIS(합성)", "KOSPI"),
        ]
        cagrs = [8.0, 3.0, 3.0, 3.0]
        is_equity = [True, False, False, False]
        dividend_yields = [1.8, 3.3, 3.0, 3.4]
        return symbols, tickers, cagrs, is_equity, dividend_yields

    def test_unachievable_dividend_goal_fails_soft_instead_of_crashing(self):
        """수정 전에는 이 시나리오에서 SLSQP가 전체 실패해 빈 추천을 반환했다 — 그룹 예산을
        반영한 사전검증이 배당 제약만 조용히 드롭하고 정상 추천을 반환해야 한다."""
        random.seed(42)
        symbols, tickers, cagrs, is_equity, dividend_yields = self._candidates()
        returns_map = {s: [random.gauss(0.0003, 0.008) for _ in range(252)] for s in symbols}

        items, expected_return, expected_vol, note = _optimize_goal_portfolio(
            symbols,
            tickers,
            cagrs,
            returns_map,
            -50.0,
            max_weight=0.6,
            risk_tolerance="CONSERVATIVE",
            is_equity=is_equity,
            equity_floor=0.8,
            equity_ceiling=None,
            market_signal_level=None,
            dividend_yields=dividend_yields,
            required_dividend_yield_pct=2.6,
        )

        assert items  # 수정 전에는 [](SLSQP 전체 실패)였음
        assert note is not None
        assert "충족하는 조합을 찾지 못해" in note
        equity_weight = sum(i["weight"] for i in items if i["ticker"] == "069500")
        assert equity_weight >= 79.5  # equity_floor(80%)는 여전히 만족

    def test_achievable_dividend_goal_still_applies_constraint(self):
        """equity_floor와 함께라도 실제 달성 가능한 범위의 배당 목표는 그대로 제약으로 반영된다."""
        random.seed(42)
        symbols, tickers, cagrs, is_equity, dividend_yields = self._candidates()
        returns_map = {s: [random.gauss(0.0003, 0.008) for _ in range(252)] for s in symbols}

        items, expected_return, expected_vol, note = _optimize_goal_portfolio(
            symbols,
            tickers,
            cagrs,
            returns_map,
            -50.0,
            max_weight=0.6,
            risk_tolerance="CONSERVATIVE",
            is_equity=is_equity,
            equity_floor=0.8,
            equity_ceiling=None,
            market_signal_level=None,
            dividend_yields=dividend_yields,
            required_dividend_yield_pct=1.5,
        )

        assert items
        assert note is None
        dividend_by_ticker = dict(zip((t[0] for t in tickers), dividend_yields, strict=False))
        weighted_dividend = sum(i["weight"] / 100 * dividend_by_ticker[i["ticker"]] for i in items)
        assert weighted_dividend >= 1.5 - 0.05

    def test_no_equity_floor_behaves_as_before(self):
        """equity_floor/ceiling이 전혀 없는 경우(전체 자산 기준 경로) 동작은 기존과 동일하다."""
        random.seed(42)
        symbols, tickers, cagrs, is_equity, dividend_yields = self._candidates()
        returns_map = {s: [random.gauss(0.0003, 0.008) for _ in range(252)] for s in symbols}

        items, expected_return, expected_vol, note = _optimize_goal_portfolio(
            symbols,
            tickers,
            cagrs,
            returns_map,
            -50.0,
            max_weight=0.6,
            risk_tolerance="CONSERVATIVE",
            is_equity=is_equity,
            equity_floor=None,
            equity_ceiling=None,
            market_signal_level=None,
            dividend_yields=dividend_yields,
            required_dividend_yield_pct=2.6,
        )

        assert items
        assert note is None


class TestDividendFallbackRetryOnTargetReturnConflict:
    """BALANCED/AGGRESSIVE의 "가중평균 CAGR = target" 등식 제약은 배당 목표 사전검증
    (`_dividend_floor_constraint`)이 전혀 모르는 축이라, 배당 목표 하나만 보면 달성 가능해도
    등식 제약과 동시에는 불가능한 조합이 실제로 있다 — 장기(LONG_TERM=AGGRESSIVE) + 배당목표
    조합에서 실제 재현된 버그(QQQ/QQQM/VOO/SCHD/QLD 실제 데이터로 직접 재현). 수정 후에는
    SLSQP가 실패하면 배당 제약만 뺀 채로 재시도해 fail-soft로 처리해야 한다."""

    def _candidates(self):
        symbols = ["QQQ", "QQQM", "VOO", "SCHD", "QLD"]
        tickers = [
            ("QQQ", "Invesco QQQ Trust", "NASDAQ"),
            ("QQQM", "Invesco NASDAQ 100 ETF", "NASDAQ"),
            ("VOO", "Vanguard S&P 500 ETF", "NYSE"),
            ("SCHD", "Schwab US Dividend Equity ETF", "NYSE"),
            ("QLD", "ProShares Ultra QQQ", "NASDAQ"),
        ]
        cagrs = [18.0, 18.0, 13.0, 11.0, 32.0]
        dividend_yields = [0.6, 0.6, 1.3, 3.5, 0.5]
        return symbols, tickers, cagrs, dividend_yields

    def _returns_map(self):
        random.seed(5)
        return {
            "QQQ": [random.gauss(0.0009, 0.013) for _ in range(252)],
            "QQQM": [random.gauss(0.0009, 0.013) for _ in range(252)],
            "VOO": [random.gauss(0.0006, 0.010) for _ in range(252)],
            "SCHD": [random.gauss(0.0005, 0.009) for _ in range(252)],
            "QLD": [random.gauss(0.0018, 0.026) for _ in range(252)],
        }

    def test_aggressive_with_dividend_goal_falls_back_instead_of_crashing(self):
        """수정 전에는 이 시나리오에서 SLSQP가 전체 실패해 빈 추천을 반환했다(장기 연금저축/IRP/
        해외전용에서 재현된 버그) — 배당 제약만 조용히 드롭하고 정상 추천을 반환해야 한다."""
        symbols, tickers, cagrs, dividend_yields = self._candidates()

        items, expected_return, expected_vol, note = _optimize_goal_portfolio(
            symbols,
            tickers,
            cagrs,
            self._returns_map(),
            -50.0,
            max_weight=0.4,
            risk_tolerance="AGGRESSIVE",
            is_equity=[True] * 5,
            equity_floor=None,
            equity_ceiling=None,
            market_signal_level=None,
            dividend_yields=dividend_yields,
            required_dividend_yield_pct=1.8,
        )

        assert items  # 수정 전에는 [](SLSQP 전체 실패)였음
        assert note is not None
        assert "다른 조건과 함께 만족하는" in note
        dividend_by_ticker = dict(zip((t[0] for t in tickers), dividend_yields, strict=False))
        weighted_dividend = sum(i["weight"] / 100 * dividend_by_ticker[i["ticker"]] for i in items)
        assert weighted_dividend < 1.8  # 배당 제약이 실제로 드롭됐음을 확인

    def test_conservative_with_same_data_still_applies_dividend_constraint(self):
        """등식 제약이 없는 CONSERVATIVE는 동일한 데이터로도 배당 제약이 그대로 반영돼야 한다
        — 재시도 로직이 불필요한 경우까지 배당 제약을 지우면 안 된다."""
        symbols, tickers, cagrs, dividend_yields = self._candidates()

        items, expected_return, expected_vol, note = _optimize_goal_portfolio(
            symbols,
            tickers,
            cagrs,
            self._returns_map(),
            -50.0,
            max_weight=0.4,
            risk_tolerance="CONSERVATIVE",
            is_equity=[True] * 5,
            equity_floor=None,
            equity_ceiling=None,
            market_signal_level=None,
            dividend_yields=dividend_yields,
            required_dividend_yield_pct=1.8,
        )

        assert items
        assert note is None
        dividend_by_ticker = dict(zip((t[0] for t in tickers), dividend_yields, strict=False))
        weighted_dividend = sum(i["weight"] / 100 * dividend_by_ticker[i["ticker"]] for i in items)
        assert weighted_dividend >= 1.8 - 0.05
