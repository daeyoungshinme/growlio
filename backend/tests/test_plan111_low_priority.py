"""계획 111 E4 — 낮은 순위 보고 건 회귀 테스트."""

from __future__ import annotations

import asyncio
import threading
import time
import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.goal import _goal_dividend_suggestions as gds
from app.services.goal import _goal_recommendation_common as grc
from app.services.goal.goal_recommendation_service import (
    MAX_GOAL_CANDIDATE_TICKERS,
    _resolve_required_return,
    get_goal_recommendation,
)
from app.services.goal.goal_return_solver import build_feasibility_preview, solve_required_annual_return_pct
from app.services.tactical import tactical_allocation_service as tactical


class TestRequiredReturnWhenDepositsSuffice:
    """a — 적립만으로 달성되면 "연 -90% 필요"가 아니라 0%다."""

    def test_deposits_far_exceed_goal(self):
        assert solve_required_annual_return_pct(9_000_000, 5_000_000, 12, 10_000_000) == 0.0

    def test_deposits_barely_exceed_goal(self):
        assert solve_required_annual_return_pct(9_000_000, 100_000, 12, 10_000_000) == 0.0

    def test_positive_requirement_unchanged(self):
        required = solve_required_annual_return_pct(1_000_000, 100_000, 12, 3_000_000)
        assert required is not None
        assert required > 0

    def test_preview_says_deposits_are_enough(self):
        preview = build_feasibility_preview(9_000_000, 10_000_000, 12, 5_000_000)
        assert preview.required_return_pct == 0.0
        assert preview.note is not None
        assert "적립" in preview.note

    def test_optimizer_floor_stays_non_binding(self):
        """0%를 하한으로 넘기면 CAGR이 전부 음수일 때 '목표 수익률 0.0% 달성 어려움'으로 빈 추천이 된다."""
        settings_row = SimpleNamespace(
            goal_amount=10_000_000.0,
            retirement_target_year=9999,
            monthly_deposit_amount=5_000_000.0,
            annual_deposit_goal=None,
        )
        required, floor, early = _resolve_required_return(settings_row, True, 9_000_000.0, None)
        assert early is None
        assert required == 0.0
        assert floor == grc._NON_BINDING_RETURN_FLOOR


class TestDividendCapacityCountsAugmentedCandidates:
    """b — 세제 선호 후보 보강 뒤의 등록 수로 잔여 슬롯을 계산해야 20개 상한을 넘지 않는다."""

    async def test_capacity_after_augmentation(self):
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
        suggest = AsyncMock(return_value=([], None, None))
        db = AsyncMock()
        db.scalar = AsyncMock(return_value=settings_row)
        with (
            patch(
                "app.services.goal.goal_recommendation_service._active_account_tax_types",
                AsyncMock(return_value=["ISA"]),
            ),
            patch(
                "app.services.goal.goal_recommendation_service.get_historical_returns",
                AsyncMock(return_value={}),
            ),
            patch(f"{grc.__name__}._fetch_dividend_yields", AsyncMock(return_value={})),
            patch(f"{gds.__name__}._suggest_for_dividend_goal", suggest),
        ):
            await get_goal_recommendation(None, 10_000_000.0, [], settings_row, db)

        registered = len(settings_row.goal_candidate_tickers)
        assert registered > 1  # 큐레이션 후보가 실제로 보강됐다
        assert suggest.await_args.kwargs["capacity_remaining"] == MAX_GOAL_CANDIDATE_TICKERS - registered


class TestDividendFetchSharesConcurrencyLimit:
    """c — 조합마다 세마포어를 새로 만들면 조합 수만큼 동시 호출이 곱해진다."""

    async def test_concurrent_calls_share_one_limit(self):
        lock = threading.Lock()
        running = 0
        peak = 0

        def _slow(_symbol: str) -> dict[str, float]:
            nonlocal running, peak
            with lock:
                running += 1
                peak = max(peak, running)
            time.sleep(0.02)
            with lock:
                running -= 1
            return {"dividend_yield": 0.01}

        limit = 2
        batches = [[(f"T{batch}{i}", "NYSE") for i in range(limit)] for batch in range(3)]
        with (
            patch.object(grc, "_dividend_fetch_sem", asyncio.Semaphore(limit)),
            patch.object(grc, "sync_yahoo_dividend_info", _slow),
        ):
            await asyncio.gather(*(grc._fetch_dividend_yields(None, b) for b in batches))

        assert peak <= limit


class TestPartialTrendUnknownHoldsRegime:
    """d — 한쪽 시세만 받았을 때 정상 NEUTRAL 관측으로 2일 확정에 쓰이면 안 된다."""

    @pytest.mark.parametrize(
        ("spy", "qqq"),
        [("UP", "UNKNOWN"), ("NEUTRAL", "UNKNOWN"), ("UNKNOWN", "UP"), ("UNKNOWN", "NEUTRAL"), ("UNKNOWN", "DOWN")],
    )
    def test_holds(self, spy, qqq):
        regime, reasons = tactical.classify_regime("GREEN", "LIVE", {"SPY": spy, "QQQ": qqq})
        assert regime is None
        assert "판정" in reasons[-1]

    def test_risk_on_is_not_dropped_by_missing_qqq(self):
        regime, _ = tactical.classify_regime("YELLOW", "LIVE", {"SPY": "UP", "QQQ": "UNKNOWN"}, prev="RISK_ON")
        assert regime is None

    @pytest.mark.parametrize(
        ("macro", "spy", "qqq"),
        [("GREEN", "DOWN", "UNKNOWN"), ("RED", "UP", "UNKNOWN"), ("RED", "UNKNOWN", "UP")],
    )
    def test_confirmed_risk_off_still_applies(self, macro, spy, qqq):
        regime, _ = tactical.classify_regime(macro, "LIVE", {"SPY": spy, "QQQ": qqq})
        assert regime == "RISK_OFF"


class TestWeightsFitStoredPrecision:
    """e — `PortfolioItem.weight`는 Numeric(6,2)라 소수 셋째 자리 이하는 저장 때 잘려 합계가 100이 안 된다."""

    @staticmethod
    def _table(risk_on: dict[str, float]) -> dict[str, dict[str, float]]:
        return {"RISK_ON": risk_on, "NEUTRAL": {"CASH": 100}, "RISK_OFF": {"CASH": 100}}

    @pytest.mark.parametrize(
        "risk_on",
        [
            {"QQQ": 33.333, "SPY": 33.333, "CASH": 33.333},  # 합계 99.999 — ±0.01 통과
            {"QQQ": 50.005, "SPY": 49.995},
        ],
    )
    def test_sum_is_exactly_100_at_two_decimals(self, risk_on):
        weights = tactical.validate_regime_weights(self._table(risk_on))["RISK_ON"]
        stored = [Decimal(str(v)).quantize(Decimal("0.01")) for v in weights.values()]
        assert sum(stored) == Decimal("100.00")
        assert all(Decimal(str(v)) == s for v, s in zip(weights.values(), stored, strict=True))

    def test_clean_values_are_untouched(self):
        weights = tactical.validate_regime_weights(self._table({"QQQ": 50, "SPY": 40, "CASH": 10}))["RISK_ON"]
        assert weights == {"QQQ": 50.0, "SPY": 40.0, "DIA": 0.0, "QLD": 0.0, "SSO": 0.0, "CASH": 10.0}

    def test_stored_fractional_table_is_not_replaced_by_default(self):
        """검증을 거부로 바꾸면 이미 저장된 표가 조용히 기본 비중으로 바뀐다."""
        strategy = SimpleNamespace(id=uuid.uuid4(), regime_weights=self._table({"QQQ": 33.333, "SPY": 66.667}))
        assert tactical.resolve_weights(strategy)["RISK_ON"]["QQQ"] == pytest.approx(33.33)
