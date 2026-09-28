"""목표 역산 추천 characterization(스냅샷) 테스트 — `_compute_*` 분해 리팩터링 안전망.

전체 자산 기준(`get_goal_recommendation`)·연령대별(`get_age_based_recommendation`)·투자기간별
(`get_horizon_recommendations`) 세 진입점과 MVO 엔진(`_optimize_goal_portfolio`)의 **전체 출력**을
시나리오별로 `snapshots/goal_recommendation.json`에 고정한다. 개별 단위 테스트(`test_goal_recommendation.py`)가
속성 몇 개만 검증하는 것과 달리, 노트 문구·비중·배당 제안까지 한 글자라도 바뀌면 실패한다 — 순수 이동/추출
리팩터링이 동작을 바꾸지 않았음을 확인하는 용도다.

외부 I/O(CAGR·일별수익률·배당수익률·시장신호·DB)와 시간 의존(`months_until_year_end`), 큐레이션
유니버스(`RECOMMENDATION_UNIVERSE`)는 전부 이 파일의 고정 데이터로 대체한다 — 유니버스가 실제로
바뀌어도 이 스냅샷은 깨지지 않는다.

**의도적으로 동작을 바꾼 경우에만** 스냅샷을 갱신한다:

    UPDATE_GOAL_SNAPSHOTS=1 uv run pytest tests/test_goal_recommendation_snapshots.py

실수 비교는 `_FLOAT_TOL` 허용오차를 둔다 — SLSQP 결과가 플랫폼(BLAS)마다 마지막 자리에서 달라질 수
있어서다(비중은 0.1% 단위 반올림).
"""

from __future__ import annotations

import asyncio
import importlib
import json
import os
import random
import uuid
import zlib
from collections.abc import Callable
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.goal_age_recommendation_service import get_age_based_recommendation
from app.services.goal_horizon_recommendation_service import get_horizon_recommendations
from app.services.goal_portfolio_optimizer import _optimize_goal_portfolio
from app.services.goal_recommendation_service import get_goal_recommendation

_SNAPSHOT_PATH = Path(__file__).parent / "snapshots" / "goal_recommendation.json"
_UPDATE = os.environ.get("UPDATE_GOAL_SNAPSHOTS") == "1"
_FLOAT_TOL = 0.15

_GRS = "app.services.goal_recommendation_service"
_AGE = "app.services.goal_age_recommendation_service"
_HOR = "app.services.goal_horizon_recommendation_service"
_GRC = "app.services._goal_recommendation_common"
_GCS = "app.services.goal_candidate_service"


def _c(ticker: str, name: str, market: str, asset_class: str = "EQUITY", index_region: str | None = None) -> dict:
    c = {"ticker": ticker, "name": name, "market": market, "asset_class": asset_class}
    if index_region is not None:
        c["index_region"] = index_region
    return c


# ── 고정 데이터 ───────────────────────────────────────────────────────────────

KODEX200 = _c("069500", "KODEX 200", "KOSPI", index_region="DOMESTIC")
TIGER_SP500 = _c("360750", "TIGER 미국S&P500", "KOSPI", index_region="OVERSEAS")
TIGER_NDX = _c("133690", "TIGER 미국나스닥100", "KOSPI", index_region="OVERSEAS")
TIGER_DIV = _c("458730", "TIGER 미국배당다우존스", "KOSPI", index_region="OVERSEAS")
KODEX_SP500 = _c("379800", "KODEX 미국S&P500TR", "KOSPI", index_region="OVERSEAS")
KODEX_BOND = _c("153130", "KODEX 단기채권", "KOSPI", "BOND")
KODEX_BOND2 = _c("114260", "KODEX 국고채3년", "KOSPI", "BOND")
TIGER_CD = _c("357870", "TIGER CD금리투자KIS(합성)", "KOSPI", "CASH")
SAMSUNG = _c("005930", "삼성전자", "KOSPI", index_region="DOMESTIC")
KODEX_LEV = _c("122630", "KODEX 레버리지", "KOSPI", index_region="DOMESTIC")
SPY = _c("SPY", "SPDR S&P 500 ETF", "NYSE", index_region="OVERSEAS")
QQQ = _c("QQQ", "Invesco QQQ Trust", "NASDAQ", index_region="OVERSEAS")
SCHD = _c("SCHD", "Schwab US Dividend Equity ETF", "NYSE", index_region="OVERSEAS")
BND = _c("BND", "Vanguard Total Bond Market ETF", "NASDAQ", "BOND")
JEPI = _c("JEPI", "JPMorgan Equity Premium Income ETF", "NYSE", index_region="OVERSEAS")
JEPQ = _c("JEPQ", "JPMorgan Nasdaq Equity Premium Income ETF", "NASDAQ", index_region="OVERSEAS")
UNKNOWN_A = _c("999990", "데이터없음A", "KOSPI", index_region="DOMESTIC")
UNKNOWN_B = _c("999991", "데이터없음B", "KOSPI", index_region="DOMESTIC")

_UNIVERSE = [KODEX200, TIGER_SP500, TIGER_NDX, TIGER_DIV, KODEX_BOND, TIGER_CD, SPY, QQQ, SCHD, BND, JEPI, JEPQ]

_CAGR: dict[tuple[str, str], float] = {
    ("069500", "KOSPI"): 6.0,
    ("360750", "KOSPI"): 12.0,
    ("133690", "KOSPI"): 16.0,
    ("458730", "KOSPI"): 9.0,
    ("379800", "KOSPI"): 12.5,
    ("153130", "KOSPI"): 3.2,
    ("114260", "KOSPI"): 3.0,
    ("357870", "KOSPI"): 3.4,
    ("005930", "KOSPI"): 11.0,
    ("122630", "KOSPI"): 9.5,
    ("SPY", "NYSE"): 11.0,
    ("QQQ", "NASDAQ"): 17.0,
    ("SCHD", "NYSE"): 10.0,
    ("BND", "NASDAQ"): 2.5,
    ("JEPI", "NYSE"): 7.0,
    ("JEPQ", "NASDAQ"): 9.0,
}
_DIVIDEND: dict[tuple[str, str], float] = {
    ("069500", "KOSPI"): 1.8,
    ("360750", "KOSPI"): 1.1,
    ("133690", "KOSPI"): 0.5,
    ("458730", "KOSPI"): 3.6,
    ("153130", "KOSPI"): 3.3,
    ("114260", "KOSPI"): 3.0,
    ("357870", "KOSPI"): 3.4,
    ("005930", "KOSPI"): 2.1,
    ("SPY", "NYSE"): 1.3,
    ("QQQ", "NASDAQ"): 0.6,
    ("SCHD", "NYSE"): 3.5,
    ("BND", "NASDAQ"): 3.2,
    ("JEPI", "NYSE"): 8.1,
    ("JEPQ", "NASDAQ"): 9.9,
}
_LOW_VOL_SYMBOLS = {"153130.KS", "114260.KS", "357870.KS", "BND"}


def _daily_returns(symbol: str) -> list[float]:
    seed = zlib.crc32(symbol.encode())
    rng = random.Random(seed)
    if symbol in _LOW_VOL_SYMBOLS:
        mean, vol = 0.00012, 0.0008 + (seed % 5) * 0.0001
    else:
        mean, vol = 0.0002 + (seed % 7) * 0.0001, 0.006 + (seed % 11) * 0.001
    return [rng.gauss(mean, vol) for _ in range(252)]


async def _fake_historical_returns(tickers, cache=None, years=10):
    return {tm: {"cagr_pct": round(_CAGR[tm] + (years - 10) * 0.2, 2)} for tm in tickers if tm in _CAGR}


def _fake_daily_returns(symbols):
    return {s: _daily_returns(s) for s in symbols}


async def _fake_dividend_yields(cache, tickers):
    return {tm: _DIVIDEND[tm] for tm in tickers if tm in _DIVIDEND}


def _months_until_year_end(target_year: int) -> int:
    return max(0, (target_year - 2026) * 12)


# ── 비교/저장 ─────────────────────────────────────────────────────────────────


def _normalize(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    if isinstance(value, dict):
        return {k: _normalize(v) for k, v in value.items() if k != "generated_at"}
    if isinstance(value, list | tuple):
        return [_normalize(v) for v in value]
    return value


def _assert_matches(actual: Any, expected: Any, path: str = "$") -> None:
    if isinstance(expected, float) or (isinstance(actual, float) and isinstance(expected, int)):
        assert isinstance(actual, int | float), f"{path}: {actual!r} != {expected!r}"
        assert actual == pytest.approx(expected, abs=_FLOAT_TOL), f"{path}: {actual!r} != {expected!r}"
        return
    if isinstance(expected, dict):
        assert isinstance(actual, dict), f"{path}: {actual!r} != {expected!r}"
        assert actual.keys() == expected.keys(), f"{path}: keys {sorted(actual)} != {sorted(expected)}"
        for k in expected:
            _assert_matches(actual[k], expected[k], f"{path}.{k}")
        return
    if isinstance(expected, list):
        assert isinstance(actual, list), f"{path}: {actual!r} != {expected!r}"
        assert len(actual) == len(expected), f"{path}: len {len(actual)} != {len(expected)}\n{actual!r}"
        for i, (a, e) in enumerate(zip(actual, expected, strict=True)):
            _assert_matches(a, e, f"{path}[{i}]")
        return
    assert actual == expected, f"{path}: {actual!r} != {expected!r}"


def _load_snapshots() -> dict[str, Any]:
    if not _SNAPSHOT_PATH.exists():
        return {}
    return json.loads(_SNAPSHOT_PATH.read_text(encoding="utf-8"))


_UPDATED: dict[str, Any] = {}


@pytest.fixture(scope="module", autouse=True)
def _write_updated_snapshots():
    yield
    if _UPDATE and _UPDATED:
        merged = {**_load_snapshots(), **_UPDATED}
        _SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        _SNAPSHOT_PATH.write_text(
            json.dumps(merged, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )


def _check_snapshot(name: str, result: Any) -> None:
    actual = _normalize(result)
    if _UPDATE:
        _UPDATED[name] = actual
        return
    snapshots = _load_snapshots()
    assert name in snapshots, f"스냅샷 '{name}' 없음 — UPDATE_GOAL_SNAPSHOTS=1로 생성"
    _assert_matches(actual, snapshots[name])


# ── 공통 patch ────────────────────────────────────────────────────────────────


@pytest.fixture
def market_signal_level():
    return {"level": "GREEN"}


@pytest.fixture(autouse=True)
def _fresh_yfinance_semaphore():
    """모듈 전역 `_yfinance_sem`은 처음 대기가 걸린 이벤트 루프에 묶인다 — 투자기간별 조합이 5개를 넘어
    실제로 대기하면 다음 테스트(새 루프)에서 RuntimeError가 나므로 테스트마다 새 세마포어로 바꾼다."""
    with ExitStack() as stack:
        for module_path in (_GRS, _AGE, _HOR, _GRC):
            module = importlib.import_module(module_path)
            if hasattr(module, "_yfinance_sem"):
                stack.enter_context(patch.object(module, "_yfinance_sem", asyncio.Semaphore(5)))
        yield


@pytest.fixture(autouse=True)
def _fixed_environment(market_signal_level):
    async def _signal(cache):
        return {"composite_level": market_signal_level["level"], "data_freshness": "LIVE"}

    with (
        patch(f"{_GCS}.RECOMMENDATION_UNIVERSE", _UNIVERSE),
        patch(f"{_GRC}.RECOMMENDATION_UNIVERSE", _UNIVERSE),
        patch(f"{_GRC}.get_market_signal", AsyncMock(side_effect=_signal)),
        patch(f"{_GRC}._fetch_dividend_yields", AsyncMock(side_effect=_fake_dividend_yields)),
        patch(f"{_GRS}.months_until_year_end", side_effect=_months_until_year_end),
        patch(f"{_GRS}.get_historical_returns", AsyncMock(side_effect=_fake_historical_returns)),
        patch(f"{_GRS}.fetch_yf_daily_returns", side_effect=_fake_daily_returns),
        patch(f"{_AGE}.get_historical_returns", AsyncMock(side_effect=_fake_historical_returns)),
        patch(f"{_AGE}.fetch_yf_daily_returns", side_effect=_fake_daily_returns),
        patch(f"{_HOR}.get_historical_returns", AsyncMock(side_effect=_fake_historical_returns)),
        patch(f"{_HOR}.fetch_yf_daily_returns", side_effect=_fake_daily_returns),
    ):
        yield


def _db(execute_rows: list[tuple] | None = None) -> AsyncMock:
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=None)
    result = MagicMock()
    result.all.return_value = execute_rows or []
    db.execute = AsyncMock(return_value=result)
    return db


# ── 전체 자산 기준 ────────────────────────────────────────────────────────────


def _overall_settings(**overrides: Any) -> SimpleNamespace:
    base: dict[str, Any] = {
        "user_id": None,
        "goal_amount": 200_000_000.0,
        "retirement_target_year": 2036,
        "monthly_deposit_amount": 1_000_000.0,
        "annual_deposit_goal": None,
        "annual_dividend_goal": None,
        "goal_candidate_tickers": [KODEX200, TIGER_SP500, TIGER_NDX, TIGER_DIV, KODEX_BOND, TIGER_CD],
        "goal_max_weight_pct": None,
        "goal_risk_tolerance": None,
        "goal_cagr_lookback_years": None,
        "goal_bond_ceiling_pct": None,
        "goal_cash_ceiling_pct": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


_OVERALL_SCENARIOS: dict[str, dict[str, Any]] = {
    "overall_conservative_asset_goal": {"settings": {}},
    "overall_balanced_ceilings_yellow_general": {
        "settings": {
            "user_id": "u",
            "goal_risk_tolerance": "BALANCED",
            "goal_max_weight_pct": 30.0,
            "goal_bond_ceiling_pct": 20.0,
            "goal_cash_ceiling_pct": 10.0,
            "goal_cagr_lookback_years": 5,
            "annual_dividend_goal": 600_000.0,
            "goal_candidate_tickers": [KODEX200, SAMSUNG, TIGER_SP500, TIGER_NDX, KODEX_BOND, TIGER_CD],
        },
        "tax_types": ["GENERAL", None],
        "signal": "YELLOW",
    },
    "overall_aggressive_dividend_only_red": {
        "settings": {
            "user_id": "u",
            "goal_amount": None,
            "retirement_target_year": None,
            "annual_dividend_goal": 900_000.0,
            "goal_risk_tolerance": "AGGRESSIVE",
            "goal_candidate_tickers": [SPY, QQQ, SCHD, BND],
        },
        "tax_types": ["GENERAL", "ISA"],
        "signal": "RED",
    },
    "overall_pension_single_tax_type": {
        "settings": {
            "user_id": "u",
            "goal_risk_tolerance": "BALANCED",
            "annual_dividend_goal": 450_000.0,
            "goal_candidate_tickers": [SAMSUNG, KODEX_LEV, KODEX200, TIGER_SP500, TIGER_NDX, KODEX_SP500, KODEX_BOND],
        },
        "tax_types": ["PENSION_SAVINGS"],
        "existing": [("360750", "TIGER 미국S&P500", "KOSPI")],
    },
    "overall_isa_curated_fallback": {
        "settings": {"user_id": "u", "goal_candidate_tickers": [KODEX200, SAMSUNG, KODEX_BOND]},
        "tax_types": ["ISA"],
    },
    "overall_unreachable_dividend": {
        "settings": {"user_id": "u", "annual_dividend_goal": 3_000_000.0, "goal_max_weight_pct": 40.0},
        "tax_types": ["GENERAL", "ISA"],
    },
    "overall_insufficient_cagr_with_suggestions": {
        "settings": {
            "user_id": "u",
            "annual_dividend_goal": 1_500_000.0,
            "goal_candidate_tickers": [KODEX200, UNKNOWN_A, UNKNOWN_B],
        },
        "tax_types": ["GENERAL", "ISA"],
    },
    "overall_not_configured": {"settings": {"goal_amount": None, "retirement_target_year": None}},
    "overall_target_year_passed": {"settings": {"retirement_target_year": 2020}},
    "overall_already_achieved": {"settings": {"goal_amount": 10_000_000.0, "annual_dividend_goal": 300_000.0}},
    "overall_required_return_unsolvable": {
        "settings": {"goal_amount": 900_000_000_000.0, "retirement_target_year": 2027, "monthly_deposit_amount": 0}
    },
    "overall_no_candidates": {"settings": {"goal_candidate_tickers": []}},
}


@pytest.mark.parametrize("name", sorted(_OVERALL_SCENARIOS))
async def test_overall_snapshot(name, market_signal_level):
    scenario = _OVERALL_SCENARIOS[name]
    settings_kwargs = dict(scenario["settings"])
    if settings_kwargs.get("user_id") == "u":
        settings_kwargs["user_id"] = uuid.UUID(int=1)
    settings_row = _overall_settings(**settings_kwargs)
    market_signal_level["level"] = scenario.get("signal", "GREEN")

    with patch(f"{_GRS}._active_account_tax_types", AsyncMock(return_value=scenario.get("tax_types", []))):
        result = await get_goal_recommendation(None, 30_000_000.0, scenario.get("existing", []), settings_row, _db())

    payload = {"result": result, "persisted_candidates": settings_row.goal_candidate_tickers}
    _check_snapshot(name, payload)


# ── 연령대별 ──────────────────────────────────────────────────────────────────


_AGE_SCENARIOS: dict[str, dict[str, Any]] = {
    "age_twenties_equity_only_cash_equivalent": {
        "age_group": "TWENTIES",
        "candidates": [KODEX200, TIGER_SP500, TIGER_NDX],
    },
    "age_forties_default_dividend_floor": {
        "age_group": "FORTIES",
        "candidates": [KODEX200, TIGER_SP500, TIGER_DIV, KODEX_BOND, TIGER_CD],
        "signal": "YELLOW",
    },
    "age_fifties_explicit_dividend_goal": {
        "age_group": "FIFTIES",
        "candidates": [TIGER_SP500, TIGER_NDX, TIGER_DIV, KODEX_BOND, KODEX_BOND2],
        "annual_dividend_goal": 600_000.0,
        "max_weight_pct": 50.0,
    },
    "age_sixties_unreachable_dividend_suggests": {
        "age_group": "SIXTIES_PLUS",
        "candidates": [SPY, QQQ, BND],
        "annual_dividend_goal": 1_800_000.0,
        "lookback": 3,
    },
    "age_insufficient_data": {"age_group": "THIRTIES", "candidates": [KODEX200, UNKNOWN_A]},
    "age_no_candidates": {"age_group": "FORTIES", "candidates": []},
    "age_not_configured": {"age_group": None, "candidates": [KODEX200]},
}


@pytest.mark.parametrize("name", sorted(_AGE_SCENARIOS))
async def test_age_snapshot(name, market_signal_level):
    scenario = _AGE_SCENARIOS[name]
    market_signal_level["level"] = scenario.get("signal", "GREEN")
    settings_row = SimpleNamespace(
        age_group=scenario["age_group"],
        annual_dividend_goal=scenario.get("annual_dividend_goal"),
        goal_max_weight_pct=scenario.get("max_weight_pct"),
        goal_cagr_lookback_years=scenario.get("lookback"),
        goal_candidate_tickers=list(scenario["candidates"]),
    )
    positions = {"p1": {"ticker": "379800", "name": "KODEX 미국S&P500TR", "market": "KOSPI"}}

    with (
        patch(f"{_AGE}.query_latest_position_map", AsyncMock(return_value=positions)),
        patch(f"{_AGE}.build_portfolio_overview", AsyncMock(return_value={"total_assets_krw": 30_000_000.0})),
    ):
        result = await get_age_based_recommendation(None, _db(), uuid.UUID(int=2), settings_row)

    _check_snapshot(name, result)


# ── 투자기간별 ────────────────────────────────────────────────────────────────


_ACCOUNT_VALUES = {
    uuid.UUID(int=101): 8_000_000.0,
    uuid.UUID(int=102): 12_000_000.0,
    uuid.UUID(int=103): 6_000_000.0,
    uuid.UUID(int=104): 15_000_000.0,
    uuid.UUID(int=105): 9_000_000.0,
    uuid.UUID(int=106): 4_000_000.0,
    uuid.UUID(int=107): 7_000_000.0,
    uuid.UUID(int=108): 5_000_000.0,
    uuid.UUID(int=109): 3_000_000.0,
}

_ALL_COMBO_ROWS = [
    ("SHORT_TERM", "GENERAL", uuid.UUID(int=101)),
    ("MID_TERM", "ISA", uuid.UUID(int=102)),
    ("LONG_TERM", "IRP", uuid.UUID(int=103)),
    ("LONG_TERM", "OVERSEAS_DEDICATED", uuid.UUID(int=104)),
    ("MID_TERM", "PENSION_SAVINGS", uuid.UUID(int=105)),
    ("SHORT_TERM", "IRP", uuid.UUID(int=106)),
    ("MID_TERM", "OVERSEAS_DEDICATED", uuid.UUID(int=107)),
    ("LONG_TERM", None, uuid.UUID(int=108)),
    ("LONG_TERM", "GENERAL", uuid.UUID(int=109)),
]

_FULL_CANDIDATES = [
    KODEX200,
    TIGER_SP500,
    TIGER_NDX,
    TIGER_DIV,
    KODEX_BOND,
    TIGER_CD,
    SAMSUNG,
    KODEX_LEV,
    SPY,
    QQQ,
    SCHD,
    BND,
]

_HORIZON_SCENARIOS: dict[str, dict[str, Any]] = {
    "horizon_all_combos_with_dividend_goal": {
        "rows": _ALL_COMBO_ROWS,
        "candidates": _FULL_CANDIDATES,
        "annual_dividend_goal": 1_200_000.0,
    },
    "horizon_all_combos_custom_options_yellow": {
        "rows": _ALL_COMBO_ROWS,
        "candidates": _FULL_CANDIDATES,
        "max_weight_pct": 50.0,
        "short_term_floor_pct": 70.0,
        "lookback": 5,
        "signal": "YELLOW",
    },
    "horizon_sparse_candidates": {
        "rows": [
            ("SHORT_TERM", "GENERAL", uuid.UUID(int=101)),
            ("LONG_TERM", "GENERAL", uuid.UUID(int=109)),
            ("MID_TERM", "OVERSEAS_DEDICATED", uuid.UUID(int=107)),
            ("SHORT_TERM", "IRP", uuid.UUID(int=106)),
        ],
        "candidates": [SPY, UNKNOWN_A],
        "annual_dividend_goal": 600_000.0,
    },
    "horizon_no_tagged_accounts": {"rows": [], "candidates": [KODEX200, SPY]},
}


@pytest.mark.parametrize("name", sorted(_HORIZON_SCENARIOS))
async def test_horizon_snapshot(name, market_signal_level):
    scenario = _HORIZON_SCENARIOS[name]
    market_signal_level["level"] = scenario.get("signal", "GREEN")
    settings_row = SimpleNamespace(
        goal_candidate_tickers=list(scenario["candidates"]),
        goal_max_weight_pct=scenario.get("max_weight_pct"),
        goal_cagr_lookback_years=scenario.get("lookback"),
        goal_short_term_equity_floor_pct=scenario.get("short_term_floor_pct"),
        annual_dividend_goal=scenario.get("annual_dividend_goal"),
    )
    accounts_by_id = {acc_id: SimpleNamespace(id=acc_id) for acc_id in _ACCOUNT_VALUES}
    positions = {"p1": {"ticker": "379800", "name": "KODEX 미국S&P500TR", "market": "KOSPI"}}

    def _total_assets(accounts, *_args):
        return sum(_ACCOUNT_VALUES[a.id] for a in accounts)

    with (
        patch(f"{_HOR}.query_latest_position_map", AsyncMock(return_value=positions)),
        patch(
            f"{_HOR}.prefetch_accounts_snapshot_positions",
            AsyncMock(return_value=(accounts_by_id, {}, {}, {})),
        ),
        patch(f"{_HOR}.compute_total_assets_krw", side_effect=_total_assets),
        patch(f"{_HOR}.build_portfolio_overview", AsyncMock(return_value={"total_assets_krw": 60_000_000.0})),
    ):
        result = await get_horizon_recommendations(None, _db(scenario["rows"]), uuid.UUID(int=3), settings_row)

    _check_snapshot(name, {"result": result, "persisted_candidates": settings_row.goal_candidate_tickers})


# ── MVO 엔진 ─────────────────────────────────────────────────────────────────


def _optimizer_inputs(cands: list[dict]) -> tuple[list[str], list[tuple[str, str, str]], list[float], list[float]]:
    from app.services.yahoo_price import to_yf_symbol

    symbols = [to_yf_symbol(c["ticker"], c["market"]) for c in cands]
    tickers = [(c["ticker"], c["name"], c["market"]) for c in cands]
    cagrs = [_CAGR[(c["ticker"], c["market"])] for c in cands]
    dividends = [_DIVIDEND.get((c["ticker"], c["market"]), 0.0) for c in cands]
    return symbols, tickers, cagrs, dividends


_MIXED = [KODEX200, TIGER_SP500, TIGER_NDX, TIGER_DIV, KODEX_BOND, TIGER_CD]
_US = [SPY, QQQ, SCHD, JEPQ]


def _classes(cands: list[dict]) -> list[str]:
    return [c["asset_class"] for c in cands]


_OPTIMIZER_SCENARIOS: dict[str, Callable[[], dict[str, Any]]] = {
    "opt_conservative_basic": lambda: {"cands": _MIXED, "required": 7.0},
    "opt_balanced_equity_floor": lambda: {
        "cands": _MIXED,
        "required": 5.0,
        "risk_tolerance": "BALANCED",
        "classes": True,
        "class_bounds": {"EQUITY": (0.8, 1.0)},
    },
    "opt_aggressive_ceiling_dividend": lambda: {
        "cands": _MIXED,
        "required": -50.0,
        "risk_tolerance": "AGGRESSIVE",
        "classes": True,
        "class_bounds": {"EQUITY": (0.0, 0.7)},
        "dividend": 2.5,
    },
    "opt_bond_cash_ceilings_red": lambda: {
        "cands": _MIXED,
        "required": 6.0,
        "risk_tolerance": "AGGRESSIVE",
        "classes": True,
        "class_bounds": {"BOND": (0.0, 0.2), "CASH": (0.0, 0.1)},
        "signal": "RED",
    },
    "opt_aggressive_dividend_fallback": lambda: {
        "cands": _US,
        "required": -50.0,
        "risk_tolerance": "AGGRESSIVE",
        "dividend": 5.0,
        "max_weight": 0.4,
    },
    "opt_no_spread_balanced": lambda: {
        "cands": _MIXED,
        "required": -50.0,
        "risk_tolerance": "BALANCED",
        "cagr_override": 8.0,
    },
    "opt_unreachable_return": lambda: {"cands": _MIXED, "required": 40.0},
    "opt_unreachable_dividend": lambda: {"cands": _MIXED, "required": -50.0, "dividend": 12.0},
    "opt_insufficient_returns": lambda: {"cands": _MIXED, "required": 5.0, "drop_returns": True},
}


@pytest.mark.parametrize("name", sorted(_OPTIMIZER_SCENARIOS))
def test_optimizer_snapshot(name):
    s = _OPTIMIZER_SCENARIOS[name]()
    symbols, tickers, cagrs, dividends = _optimizer_inputs(s["cands"])
    if "cagr_override" in s:
        cagrs = [s["cagr_override"]] * len(cagrs)
    returns_map = {} if s.get("drop_returns") else {sym: _daily_returns(sym) for sym in symbols}
    result = _optimize_goal_portfolio(
        symbols,
        tickers,
        cagrs,
        returns_map,
        s["required"],
        max_weight=s.get("max_weight", 0.4),
        risk_tolerance=s.get("risk_tolerance", "CONSERVATIVE"),
        asset_classes=_classes(s["cands"]) if s.get("classes") else None,
        class_bounds=s.get("class_bounds"),
        market_signal_level=s.get("signal"),
        dividend_yields=dividends if "dividend" in s else None,
        required_dividend_yield_pct=s.get("dividend"),
    )
    _check_snapshot(name, list(result))


# 스냅샷 파일에 테스트에서 더 이상 쓰지 않는 키가 남아 있으면(시나리오 삭제·개명) 알려준다.
def test_no_orphan_snapshots():
    if _UPDATE:
        pytest.skip("스냅샷 갱신 모드")
    expected = set(_OVERALL_SCENARIOS) | set(_AGE_SCENARIOS) | set(_HORIZON_SCENARIOS) | set(_OPTIMIZER_SCENARIOS)
    assert set(_load_snapshots()) == expected
