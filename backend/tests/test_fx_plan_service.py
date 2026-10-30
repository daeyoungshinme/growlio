"""달러 환전 계획 — 환율 위치·분할 구간 계산(services/fx_plan_service)과 GET /invest/fx-plan.

plans/96.
"""

from __future__ import annotations

import math
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.services import fx_plan_service as svc


def _closes(n=250, start=1300.0, step=0.4):
    """완만히 오르며 위아래로 흔들리는 시계열 — 표준편차가 0이 아니게."""
    return [start + i * step + (5 if i % 2 else -5) for i in range(n)]


# ── compute_fx_position ──────────────────────────────────────


def test_position_none_when_too_few_observations():
    assert svc.compute_fx_position(_closes(n=59), 1400.0) is None
    assert svc.compute_fx_position(_closes(), 0.0) is None


@pytest.mark.parametrize(
    ("live", "zone"),
    [(1290.0, "CHEAP"), (1350.0, "NEUTRAL"), (1500.0, "EXPENSIVE")],
)
def test_position_zone_by_percentile(live, zone):
    pos = svc.compute_fx_position(_closes(), live)
    assert pos is not None
    assert pos.zone == zone


def test_position_percentile_ma_and_sigma():
    closes = _closes()
    live = 1400.0
    pos = svc.compute_fx_position(closes, live)
    assert pos is not None
    assert pos.percentile_1y == pytest.approx(sum(1 for c in closes if c < live) / len(closes) * 100, abs=0.1)
    assert pos.ma20 == pytest.approx(sum(closes[-20:]) / 20, abs=0.01)
    assert pos.ma60 == pytest.approx(sum(closes[-60:]) / 60, abs=0.01)
    assert pos.low_1y == min(closes)
    assert pos.high_1y == max(closes)
    assert pos.sigma_1m > 0
    assert pos.range_1m_low == pytest.approx(live - pos.sigma_1m, abs=0.02)
    assert pos.range_1m_high == pytest.approx(live + pos.sigma_1m, abs=0.02)


def test_position_ignores_non_positive_and_nan():
    closes = [*_closes(), 0.0, math.nan]
    assert svc.compute_fx_position(closes, 1400.0) == svc.compute_fx_position(_closes(), 1400.0)


# ── compute_fx_plan ──────────────────────────────────────────


def _pos(zone="NEUTRAL", sigma=40.0, rate=1400.0):
    return svc.FxPosition(
        rate=rate,
        low_1y=1300,
        high_1y=1500,
        percentile_1y=50,
        ma20=rate,
        ma60=rate,
        deviation_ma20_pct=0,
        deviation_ma60_pct=0,
        sigma_1m=sigma,
        range_1m_low=rate - sigma,
        range_1m_high=rate + sigma,
        zone=zone,
    )


def test_plan_empty_when_nothing_needed():
    assert svc.compute_fx_plan(_pos(), 0.0, 1400.0) == []


@pytest.mark.parametrize(("zone", "now_share"), [("CHEAP", 0.5), ("NEUTRAL", 0.34), ("EXPENSIVE", 0.2)])
def test_plan_now_share_by_zone(zone, now_share):
    tranches = svc.compute_fx_plan(_pos(zone=zone), 1000.0, 1400.0)
    assert [t.target_rate for t in tranches][0] is None
    assert tranches[0].usd == pytest.approx(1000 * now_share)
    assert sum(t.usd for t in tranches) == pytest.approx(1000.0, abs=0.02)
    assert tranches[1].usd == tranches[2].usd


def test_plan_target_rates_floor_to_10_won():
    # 1400 − 0.5×37 = 1381.5 → 1380, 1400 − 37 = 1363 → 1360
    tranches = svc.compute_fx_plan(_pos(sigma=37.0), 900.0, 1400.0)
    assert [t.target_rate for t in tranches[1:]] == [1380.0, 1360.0]
    assert tranches[1].label == "1,380원 이하"
    assert tranches[1].krw_estimate == round(tranches[1].usd * 1380)


def test_plan_without_position_single_tranche():
    tranches = svc.compute_fx_plan(None, 500.0, 1400.0)
    assert len(tranches) == 1
    assert tranches[0].target_rate is None
    assert tranches[0].krw_estimate == 700_000


# ── overseas_weight_pct ──────────────────────────────────────


def _item(market, weight, group_key=None, members=()):
    return SimpleNamespace(market=market, weight=weight, group_key=group_key, members=list(members))


def test_overseas_weight_excludes_domestic_and_cash():
    p = SimpleNamespace(
        tax_type=None,
        items=[_item("KOSPI", 30), _item("NASDAQ", 50), _item("NYSE", 10), _item("CASH", 10)],
    )
    assert svc.overseas_weight_pct(p) == 60


def test_overseas_weight_excludes_domestic_alt_in_tax_deferred_account():
    alt = SimpleNamespace(role="DOMESTIC_ALT", market="KOSPI")
    group = _item("NASDAQ", 70, group_key="nasdaq100", members=[alt])
    p = SimpleNamespace(tax_type="ISA", items=[group, _item("NYSE", 30)])
    assert svc.overseas_weight_pct(p) == 30


# ── fetch_usd_krw_closes ─────────────────────────────────────


async def test_closes_cached_after_fetch(mock_cache):
    closes = _closes()
    with patch("app.services.market_data.yahoo_price.run_yf_bounded", new=AsyncMock(return_value=closes)):
        assert await svc.fetch_usd_krw_closes(mock_cache) == closes
    mock_cache.setex.assert_awaited_once()
    assert mock_cache.setex.await_args.args[1] == svc.TTL_USD_KRW_HISTORY


async def test_closes_not_cached_when_insufficient(mock_cache):
    with patch("app.services.market_data.yahoo_price.run_yf_bounded", new=AsyncMock(return_value=[1400.0] * 10)):
        assert await svc.fetch_usd_krw_closes(mock_cache) is None
    mock_cache.setex.assert_not_awaited()


async def test_closes_none_on_fetch_error(mock_cache):
    with patch("app.services.market_data.yahoo_price.run_yf_bounded", new=AsyncMock(side_effect=RuntimeError("x"))):
        assert await svc.fetch_usd_krw_closes(mock_cache) is None


# ── get_fx_plan ──────────────────────────────────────────────


def _portfolio(name="해외 적립", items=None, linked=(), tax_type=None):
    return SimpleNamespace(
        id=uuid.uuid4(),
        name=name,
        tax_type=tax_type,
        items=items if items is not None else [_item("NASDAQ", 60), _item("KOSPI", 40)],
        linked_accounts=[SimpleNamespace(account_id=a) for a in linked],
    )


def _db(portfolios, *, dca_portfolio_id=None, monthly=1_400_000.0, accounts=()):
    """execute 호출 순서: 포트폴리오 목록 → (필요 시) 브로커 계좌. scalar 순서: 적립 자동매수 포트폴리오 → 월 적립액."""
    db = MagicMock()
    portfolios_result = MagicMock()
    portfolios_result.scalars.return_value.all.return_value = portfolios
    accounts_result = MagicMock()
    accounts_result.scalars.return_value.all.return_value = list(accounts)
    db.execute = AsyncMock(side_effect=[portfolios_result, accounts_result])
    db.scalar = AsyncMock(side_effect=[dca_portfolio_id, monthly])
    return db


async def _plan(db, *, portfolio_id=None, months=3, closes=None, rate=1400.0):
    with (
        patch.object(svc, "get_usd_krw_rate", new=AsyncMock(return_value=rate)),
        patch.object(svc, "fetch_usd_krw_closes", new=AsyncMock(return_value=closes)),
    ):
        return await svc.get_fx_plan(db, None, uuid.uuid4(), portfolio_id, months)


async def test_plan_need_usd_from_deposit_overseas_weight_and_held():
    p = _portfolio()
    db = _db([p], accounts=[SimpleNamespace(deposit_usd=100.0), SimpleNamespace(deposit_usd=None)])
    result = await _plan(db, closes=_closes())
    # 월 140만 × 60% / 1400 = 600달러 × 3개월 − 보유 100
    assert result["status"] == "OK"
    assert result["monthly_need_usd"] == 600.0
    assert result["held_usd"] == 100.0
    assert result["need_usd"] == 1700.0
    assert len(result["tranches"]) == 3
    assert result["position"]["zone"] in {"CHEAP", "NEUTRAL", "EXPENSIVE"}
    assert result["portfolio_options"] == [{"id": p.id, "name": p.name}]


async def test_plan_prefers_dca_auto_buy_portfolio():
    first, dca = _portfolio("먼저"), _portfolio("적립")
    result = await _plan(_db([first, dca], dca_portfolio_id=dca.id))
    assert result["portfolio_id"] == dca.id


async def test_plan_falls_back_to_first_overseas_portfolio():
    domestic = _portfolio("국내", items=[_item("KOSPI", 100)])
    overseas = _portfolio("해외")
    result = await _plan(_db([domestic, overseas]))
    assert result["portfolio_id"] == overseas.id
    assert [o["name"] for o in result["portfolio_options"]] == ["해외"]


async def test_plan_explicit_portfolio_not_owned_raises():
    db = _db([_portfolio()])
    with pytest.raises(svc.PortfolioNotFound):
        await _plan(db, portfolio_id=uuid.uuid4())


async def test_plan_explicit_domestic_portfolio_no_overseas():
    domestic = _portfolio("국내", items=[_item("KOSPI", 100)])
    result = await _plan(_db([domestic]), portfolio_id=domestic.id)
    assert result["status"] == "NO_OVERSEAS"
    assert result["tranches"] == []


async def test_plan_no_portfolio():
    result = await _plan(_db([]), closes=_closes())
    assert result["status"] == "NO_PORTFOLIO"
    assert result["position"] is not None


async def test_plan_no_deposit_goal():
    result = await _plan(_db([_portfolio()], monthly=None))
    assert result["status"] == "NO_DEPOSIT_GOAL"


async def test_plan_sufficient_when_held_covers_need():
    db = _db([_portfolio()], accounts=[SimpleNamespace(deposit_usd=5000.0)])
    result = await _plan(db)
    assert result["status"] == "SUFFICIENT"
    assert result["need_usd"] == 0
    assert result["tranches"] == []


async def test_plan_degrades_without_history():
    result = await _plan(_db([_portfolio()]), closes=None)
    assert result["position"] is None
    assert len(result["tranches"]) == 1
    assert result["tranches"][0]["target_rate"] is None


async def test_held_usd_limited_to_linked_accounts():
    account_id = uuid.uuid4()
    db = _db([_portfolio(linked=[account_id])], accounts=[SimpleNamespace(deposit_usd=10.0)])
    await _plan(db)
    stmt = db.execute.await_args_list[1].args[0]
    assert "asset_accounts.id IN" in str(stmt)


# ── GET /invest/fx-plan ──────────────────────────────────────


def _client(db):
    from app.api.deps import get_current_user
    from app.core.database import get_db
    from app.main import app

    user = SimpleNamespace(id=uuid.uuid4(), email="t@e.com", is_active=True, needs_password_reset=False)

    async def override_auth():
        return user

    async def override_db():
        yield db

    app.dependency_overrides[get_current_user] = override_auth
    app.dependency_overrides[get_db] = override_db
    return app


@pytest.fixture
def api():
    db = MagicMock()
    app = _client(db)
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_api_returns_plan(api):
    payload = {
        "position": None,
        "status": "NO_PORTFOLIO",
        "portfolio_id": None,
        "portfolio_name": None,
        "portfolio_options": [],
        "months": 6,
        "overseas_weight_pct": 0.0,
        "monthly_deposit_krw": None,
        "monthly_need_usd": 0.0,
        "held_usd": 0.0,
        "need_usd": 0.0,
        "tranches": [],
    }
    with patch.object(svc, "get_fx_plan", new=AsyncMock(return_value=payload)) as mocked:
        res = api.get("/api/v1/invest/fx-plan?months=6")
    assert res.status_code == 200
    assert res.json()["status"] == "NO_PORTFOLIO"
    assert mocked.await_args.args[4] == 6


def test_api_not_owned_portfolio_404(api):
    with patch.object(svc, "get_fx_plan", new=AsyncMock(side_effect=svc.PortfolioNotFound)):
        res = api.get(f"/api/v1/invest/fx-plan?portfolio_id={uuid.uuid4()}")
    assert res.status_code == 404


@pytest.mark.parametrize("months", [0, 13])
def test_api_months_out_of_range_422(api, months):
    res = api.get(f"/api/v1/invest/fx-plan?months={months}")
    assert res.status_code == 422
