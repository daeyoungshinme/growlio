"""계획 110 배치 C — 목표 추천·적립 분석이 제약과 실제 수익률 의미를 벗어나던 경로."""

from __future__ import annotations

import random
import uuid
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from app.services import dca_cash_shortfall_service as shortfall
from app.services.dca_service import _calc_goal_timeline, _calc_months_to_goal, _elapsed_months
from app.services.goal import _goal_recommendation_common as grc
from app.services.goal.goal_portfolio_optimizer import _optimize_goal_portfolio
from app.services.goal.goal_portfolio_weights import (
    _annualized_covariance,
    _class_bounds_violated,
    _weights_to_items,
    compute_weighted_expected_metrics,
)
from app.services.goal.goal_return_solver import (
    monthly_rate,
    months_until_year_end,
    solve_required_annual_return_pct,
)

_SOLVER = "app.services.goal.goal_return_solver"


def _noise(seed: int, n: int = 252, mean: float = 0.0004, vol: float = 0.01) -> list[float]:
    rng = random.Random(seed)
    return [rng.gauss(mean, vol) for _ in range(n)]


class TestCovarianceAlignment:
    """C1 — 길이가 다른 시계열은 최근 구간끼리 맞춰야 같은 날짜를 비교한다."""

    def test_new_etf_correlation_uses_recent_window(self):
        old = _noise(1, n=252)
        new = old[-60:]  # 상장 60일 된 ETF — 같은 기간엔 오래된 ETF와 똑같이 움직인다
        cov = _annualized_covariance(("OLD", "NEW"), {"OLD": old, "NEW": new})
        corr = cov[0, 1] / np.sqrt(cov[0, 0] * cov[1, 1])
        assert corr > 0.9


class TestEquityBoundCannotBeDropped:
    """C2 — 지킬 수 없는 상한을 조용히 버리지 않는다."""

    def _optimize(self, classes, bounds):
        symbols = [f"S{i}" for i in range(len(classes))]
        return _optimize_goal_portfolio(
            symbols=symbols,
            tickers=[(s, s, "KOSPI") for s in symbols],
            cagr_pct=[6.0 + i for i in range(len(classes))],
            returns_map={s: _noise(i, vol=0.005 + 0.002 * i) for i, s in enumerate(symbols)},
            required_return_pct=-50.0,
            asset_classes=list(classes),
            class_bounds=bounds,
        )

    def test_all_equity_with_ceiling_returns_no_recommendation(self):
        items, *_rest, note = self._optimize(["EQUITY"] * 4, {"EQUITY": (0.0, 0.35)})
        assert items == []
        assert note is not None
        assert "상한" in note

    def test_all_equity_with_floor_is_fine(self):
        items, *_ = self._optimize(["EQUITY"] * 4, {"EQUITY": (0.7, 1.0)})
        assert items

    def test_ceiling_is_kept_when_safe_asset_exists(self):
        items, *_ = self._optimize(["EQUITY", "EQUITY", "EQUITY", "OTHER"], {"EQUITY": (0.0, 0.35)})
        equity = sum(i["weight"] for i in items if i["ticker"] != "S3")
        assert equity <= 35.05

    def test_ensure_safe_asset_adds_cash_when_bond_lost_daily_returns(self):
        """IRP 채권이 CAGR은 있는데 일별수익률이 모자라면 옵티마이저에서 빠진다 — 그 전에 현금성을 넣는다."""
        bond = grc._GoalCandidate("BOND.KS", ("BOND", "채권", "KOSPI"), 3.0, "OTHER", 0.0)
        equity = grc._GoalCandidate("EQ.KS", ("EQ", "주식", "KOSPI"), 8.0, "EQUITY", 0.0)
        candidates = [bond, equity]
        returns_map = {"BOND.KS": _noise(1, n=10), "EQ.KS": _noise(2)}

        assert grc._ensure_safe_asset(candidates, returns_map) is True
        assert any(c.symbol == grc._CASH_EQUIVALENT_TICKER for c in candidates)
        assert grc._CASH_EQUIVALENT_TICKER in returns_map

    def test_ensure_safe_asset_keeps_real_bond(self):
        bond = grc._GoalCandidate("BOND.KS", ("BOND", "채권", "KOSPI"), 3.0, "OTHER", 0.0)
        candidates = [bond]
        assert grc._ensure_safe_asset(candidates, {"BOND.KS": _noise(1)}) is False
        assert candidates == [bond]


class TestRoundingKeepsBounds:
    """C3 — 반올림 오차가 자산군·종목 상한을 넘기지 않는다."""

    tks = (("A", "A", "K"), ("B", "B", "K"), ("C", "C", "K"), ("D", "D", "K"))

    def test_dropped_weight_does_not_land_on_capped_class(self):
        items = _weights_to_items(
            self.tks,
            [0.40, 0.30, 0.296, 0.004],
            ("EQUITY", "OTHER", "OTHER", "OTHER"),
            {"EQUITY": (0.0, 0.40)},
            [0.40, 0.40, 0.40, 0.40],
        )
        assert round(sum(i["weight"] for i in items), 1) == 100.0
        assert next(i for i in items if i["ticker"] == "A")["weight"] == 40.0

    def test_rounding_up_over_ceiling_is_repaired(self):
        tks = self.tks[:3]
        items = _weights_to_items(
            tks, [0.35049, 0.35049, 0.29902], ("EQUITY", "EQUITY", "OTHER"), {"EQUITY": (0.0, 0.70)}, [1.0, 1.0, 1.0]
        )
        assert sum(i["weight"] for i in items if i["_class"] == "EQUITY") <= 70.0 + 1e-9
        assert round(sum(i["weight"] for i in items), 1) == 100.0

    def test_no_bounds_total_is_100(self):
        items = _weights_to_items(self.tks, [0.3333, 0.3333, 0.3333, 0.0001])
        assert round(sum(i["weight"] for i in items), 1) == 100.0

    @pytest.mark.parametrize("seed", range(40))
    def test_random_weights_stay_in_bounds(self, seed):
        rng = random.Random(seed)
        raw = np.array([rng.random() for _ in range(4)])
        equity = raw[:2] / raw[:2].sum() * 0.7
        other = raw[2:] / raw[2:].sum() * 0.3
        bounds = {"EQUITY": (0.0, 0.7)}
        items = _weights_to_items(
            self.tks, [*equity, *other], ("EQUITY", "EQUITY", "OTHER", "OTHER"), bounds, [1.0] * 4
        )
        assert not _class_bounds_violated(items, bounds)
        assert round(sum(i["weight"] for i in items), 1) == 100.0


class TestDividendFailureIsNotCached:
    """C4 — 조회 실패를 "배당 0%"로 전역 캐시하면 하루 동안 모든 유저의 배당 목표가 틀어진다."""

    async def _fetch(self, info):
        with (
            patch.object(grc, "sync_yahoo_dividend_info", return_value=info),
            patch.object(grc, "get_cached_json", new=AsyncMock(return_value=None)),
            patch.object(grc, "set_cached_json", new=AsyncMock()) as save,
        ):
            result = await grc._fetch_dividend_yields(MagicMock(), [("SCHD", "NYSE")])
        return result, save

    async def test_failure_is_not_cached(self):
        result, save = await self._fetch({"dps": 0.0, "dividend_yield": 0.0, "fetch_failed": True})
        assert result == {}
        save.assert_not_awaited()

    async def test_real_zero_is_cached(self):
        result, save = await self._fetch({"dps": 0.0, "dividend_yield": 0.0})
        assert result == {}
        save.assert_awaited_once()

    async def test_circuit_open_is_marked_failed(self):
        from app.services.dividend import sync_sources

        with patch.object(sync_sources.yahoo_circuit, "is_available", return_value=False):
            assert sync_sources.sync_yahoo_dividend_info("SCHD")["fetch_failed"] is True


class TestIncompleteRecommendationCache:
    """C4 — 일부 후보가 빠진 결과는 짧게만 저장하고 stale 키에는 넣지 않는다."""

    async def _run(self, result):
        from app.schemas.rebalancing import GoalRecommendation

        async def _single_flight(_cache, _key, _read, fetch):
            return await fetch()

        save = AsyncMock()
        with (
            patch.object(grc, "read_cached_model", new=AsyncMock(return_value=None)),
            patch.object(grc, "set_cached_json", new=save),
            patch.object(grc, "single_flight_fetch", new=_single_flight),
        ):
            await grc.cached_recommendation(
                MagicMock(),
                "key",
                "stale",
                GoalRecommendation,
                AsyncMock(return_value=result),
                lambda _r: True,
                lambda r: r.data_incomplete,
            )
        return save

    def _rec(self, *, incomplete):
        from app.schemas.rebalancing import GoalRecommendation

        return GoalRecommendation(generated_at="now", is_configured=True, data_incomplete=incomplete)

    async def test_incomplete_gets_short_ttl_and_no_stale(self):
        save = await self._run(self._rec(incomplete=True))
        assert [(c.args[1], c.args[3]) for c in save.await_args_list] == [
            ("key", grc.TTL_GOAL_RECOMMENDATION_INCOMPLETE)
        ]

    async def test_complete_uses_normal_keys(self):
        save = await self._run(self._rec(incomplete=False))
        assert [c.args[1] for c in save.await_args_list] == ["key", "stale"]

    def test_flag_is_not_in_response(self):
        assert "data_incomplete" not in self._rec(incomplete=True).model_dump()

    def test_missing_count_ignores_synthetic_cash(self):
        cash = grc._cash_equivalent_candidate()
        real = grc._GoalCandidate("EQ.KS", ("EQ", "주식", "KOSPI"), 8.0, "EQUITY", 0.0)
        returns = {"EQ.KS": _noise(1), grc._CASH_EQUIVALENT_TICKER: _noise(2)}
        assert grc._missing_candidate_count(3, [real, cash], returns) == 2
        assert grc._missing_candidate_count(1, [real, cash], returns) == 0


class TestRequiredReturnMeaning:
    """C5 — 필요 수익률은 CAGR과 비교되므로 연 복리 기준이어야 한다."""

    def test_monthly_rate_compounds_to_annual(self):
        assert (1 + monthly_rate(0.07)) ** 12 == pytest.approx(1.07)

    def test_solved_return_reaches_goal_at_that_cagr(self):
        solved = solve_required_annual_return_pct(10_000_000.0, 0.0, 120, 20_000_000.0)
        assert solved is not None
        assert 10_000_000.0 * (1 + solved / 100) ** 10 == pytest.approx(20_000_000.0, rel=1e-3)
        assert solved == pytest.approx(7.18, abs=0.01)

    def test_unsolvable_far_future_returns_none(self):
        """pv·pmt 0이면 어떤 수익률로도 목표에 못 간다 — 예외로 500이 나면 안 된다."""
        assert solve_required_annual_return_pct(0.0, 0.0, 2_000, 1_000_000.0) is None


class TestMonthsUntilYearEnd:
    """C6 — 12월에도 올해 목표는 지난 게 아니다."""

    @pytest.mark.parametrize(
        ("today", "year", "expected"),
        [
            (date(2026, 12, 1), 2026, 1),
            (date(2026, 12, 31), 2026, 1),
            (date(2026, 11, 5), 2026, 1),
            (date(2026, 1, 1), 2026, 11),
            (date(2026, 12, 1), 2025, -11),
            (date(2026, 12, 1), 2027, 12),
        ],
    )
    def test_cases(self, today, year, expected):
        with patch(f"{_SOLVER}.today_kst", return_value=today):
            assert months_until_year_end(year) == expected


class TestDcaBoundaries:
    """C7 — 0값·이미 달성·미래 시작일."""

    def test_reached_goal_is_zero_months(self):
        assert _calc_months_to_goal(100.0, 1.0, 0.01, 100.0) == 0

    def test_future_start_elapsed_is_zero(self):
        assert _elapsed_months(date(2027, 2, 1), date(2026, 11, 5)) == 0

    def _timeline(self, *, initial, current, start, goal=100_000_000.0, months=None):
        r = monthly_rate(0.07)
        return _calc_goal_timeline(
            initial, 1_000_000.0, r, goal, current, start, months if months is not None else 60, 7.0
        )

    def test_future_start_is_not_on_track(self):
        with patch("app.services.dca_service.today_kst", return_value=date(2026, 11, 5)):
            result = self._timeline(initial=10_000_000.0, current=10_000_000.0, start=date(2027, 2, 1))
        assert result["on_track"] is None
        assert result["lead_lag_months"] is None

    def test_already_reached_reports_this_month(self):
        today = date(2026, 11, 5)
        with patch("app.services.dca_service.today_kst", return_value=today):
            result = self._timeline(initial=200_000_000.0, current=200_000_000.0, start=date(2026, 1, 1), months=0)
        assert result["actual_expected_goal_date"] == "2026-11"
        assert result["expected_goal_date"] == "2026-01"


class TestRedSignalKeepsRecommendation:
    """C9 — 시장 신호로 낮아진 목표가 자산군 하한으로 도달할 수 없어 빈 추천이 나오던 경로."""

    @pytest.mark.parametrize("seed", range(60))
    def test_floor_with_red_signal_is_not_empty(self, seed):
        rng = random.Random(seed)
        symbols = ["E1", "E2", "E3", "B1", "B2"]
        classes = ["EQUITY", "EQUITY", "EQUITY", "OTHER", "OTHER"]
        vols = [0.012, 0.015, 0.018, 0.002, 0.003]
        items, *_ = _optimize_goal_portfolio(
            symbols=symbols,
            tickers=[(s, s, "KOSPI") for s in symbols],
            cagr_pct=[rng.uniform(4, 15), rng.uniform(4, 15), rng.uniform(4, 15), 3.0, 3.5],
            returns_map={s: _noise(seed * 7 + i, vol=vols[i]) for i, s in enumerate(symbols)},
            required_return_pct=-50.0,
            risk_tolerance="BALANCED",
            asset_classes=classes,
            class_bounds={"EQUITY": (0.8, 1.0)},
            market_signal_level="RED",
        )
        assert items
        assert sum(i["weight"] for i in items if i["ticker"].startswith("E")) >= 79.95


class TestPreviewMetrics:
    """C9 — 적용 전 미리보기의 "현재 포트폴리오" 수치."""

    def test_holding_without_cagr_is_excluded_not_zero(self):
        ret, _div, _vol = compute_weighted_expected_metrics(
            ["A", "B"], [50.0, 50.0], {"A": 10.0}, {}, {"A": _noise(1), "B": _noise(2)}
        )
        assert ret == 10.0

    async def test_cash_share_is_not_scaled_up(self):
        from app.services.goal import goal_recommendation_service as service

        with (
            patch.object(
                service, "get_historical_returns", new=AsyncMock(return_value={("A", "KOSPI"): {"cagr_pct": 10.0}})
            ),
            patch.object(service._grc, "_fetch_dividend_yields", new=AsyncMock(return_value={})),
            patch.object(service, "to_yf_symbol", return_value="A"),
            patch.object(service, "run_yf_bounded", new=AsyncMock(return_value={"A": _noise(1)})),
        ):
            result = await service.compute_portfolio_expected_metrics(
                MagicMock(), [("A", "KOSPI", "A", 50.0)], non_tradable_weight_pct=50.0
            )
        expected = 10.0 * 0.5 + grc._CASH_EQUIVALENT_CAGR_PCT * 0.5
        assert result.expected_return_pct == pytest.approx(expected, abs=0.01)


class TestTaxTypeFilter:
    """C9 — 은행 계좌가 세제유형 판정을 "혼합"으로 만들면 안 된다."""

    async def test_query_limits_to_stock_accounts(self):
        from app.services.goal.goal_candidate_service import _active_account_tax_types

        result = MagicMock()
        result.scalars.return_value.all.return_value = ["IRP"]
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result)

        assert await _active_account_tax_types(db, uuid.uuid4()) == ["IRP"]
        assert "asset_type" in str(db.execute.await_args.args[0])


def _sf(account_id, cash, *, expected=1_000_000.0, days=3, user_id=None):
    return shortfall.DcaShortfall(
        SimpleNamespace(id=uuid.uuid4()),
        SimpleNamespace(),
        SimpleNamespace(id=account_id),
        SimpleNamespace(id=user_id or uuid.uuid4()),
        None,
        date(2026, 11, 25) + timedelta(days=days),
        days,
        cash,
        expected,
    )


class TestShortfallPerUser:
    """C8 — 월 적립액은 사용자 단위 값이다."""

    def test_split_across_accounts_is_enough(self):
        """60만·40만으로 나눠 사면 합계로 충분하다 — 예전에는 둘 다 부족으로 나왔다."""
        assert shortfall._shortfalls_for_user([_sf("a", 600_000.0), _sf("b", 400_000.0)], None) == []

    def test_shared_account_cash_counts_once(self):
        """한 계좌를 두 포트폴리오가 쓰면 예수금을 두 번 세지 않는다 — 합계가 모자라면 한 건만 알린다."""
        result = shortfall._shortfalls_for_user([_sf("a", 500_000.0), _sf("a", 500_000.0)], None)
        assert len(result) == 1
        assert result[0].cash_krw == 500_000.0

    def test_cash_outside_notice_window_still_counts(self):
        """창 밖 계좌를 빼고 판정하면 거짓 부족이 나온다."""
        near, far = _sf("a", 500_000.0, days=2), _sf("b", 600_000.0, days=20)
        assert shortfall._shortfalls_for_user([near, far], (1, 3)) == []

    def test_only_in_window_alert_is_reported(self):
        near, far = _sf("a", 100_000.0, days=2), _sf("b", 100_000.0, days=20)
        (result,) = shortfall._shortfalls_for_user([near, far], (1, 3))
        assert result.days_until == 2
        assert result.cash_krw == 200_000.0

    def test_without_monthly_amount_checks_each_account(self):
        result = shortfall._shortfalls_for_user([_sf("a", 0.0, expected=None), _sf("b", 9e9, expected=None)], None)
        assert [s.account.id for s in result] == ["a"]


class TestShortfallUnknownCash:
    """C8 — 모르는 것을 "부족"으로 단정하지 않는다."""

    portfolio = SimpleNamespace(items=[SimpleNamespace(market="NASDAQ")])

    def _account(self, krw, usd):
        return SimpleNamespace(deposit_krw=krw, deposit_usd=usd)

    def test_never_synced_is_unknown(self):
        assert shortfall._cash_is_unknown(self._account(None, None), self.portfolio, 1400.0) is True

    def test_usd_without_real_rate_is_unknown(self):
        assert shortfall._cash_is_unknown(self._account(0.0, 1000.0), self.portfolio, 0.0) is True

    def test_real_zero_is_known(self):
        assert shortfall._cash_is_unknown(self._account(0.0, None), self.portfolio, None) is False

    def test_usd_irrelevant_for_domestic_portfolio(self):
        domestic = SimpleNamespace(items=[SimpleNamespace(market="KOSPI")])
        assert shortfall._cash_is_unknown(self._account(0.0, 1000.0), domestic, 0.0) is False

    def test_run_day_is_today_until_fired(self):
        alert = SimpleNamespace(
            schedule_type="MONTHLY",
            schedule_day_of_month=5,
            schedule_day_of_week=None,
            trigger_condition="SCHEDULE_ONLY",
            last_triggered_at=None,
        )
        today = date(2026, 11, 5)
        with patch("app.services.alerts.calculator.today_kst", return_value=today):
            assert shortfall._upcoming_run_date(alert, today) == today
