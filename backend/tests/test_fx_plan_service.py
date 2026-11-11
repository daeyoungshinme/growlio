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

from app.exceptions import NotFoundError
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


def test_plan_merges_targets_that_floor_to_same_rate():
    # σ=6: 1400 − 3 = 1397 → 1390, 1400 − 6 = 1394 → 1390 → 한 구간으로 합침
    tranches = svc.compute_fx_plan(_pos(sigma=6.0), 1000.0, 1400.0)
    assert [t.target_rate for t in tranches] == [None, 1390.0]
    assert sum(t.usd for t in tranches) == pytest.approx(1000.0, abs=0.02)


def test_plan_target_strictly_below_live_rate():
    # σ≈0이면 floor(1405)=1400 — 현재 환율 1405에서 한 단계 아래인 1400 이하로
    tranches = svc.compute_fx_plan(_pos(sigma=0.0, rate=1405.0), 1000.0, 1405.0)
    assert [t.target_rate for t in tranches[1:]] == [1400.0]
    tranches = svc.compute_fx_plan(_pos(sigma=0.0, rate=1400.0), 1000.0, 1400.0)
    assert [t.target_rate for t in tranches[1:]] == [1390.0]


def test_plan_without_position_single_tranche():
    tranches = svc.compute_fx_plan(None, 500.0, 1400.0)
    assert len(tranches) == 1
    assert tranches[0].target_rate is None
    assert tranches[0].krw_estimate == 700_000


# ── overseas_weight_pct ──────────────────────────────────────


def _item(market, weight, group_key=None, members=()):
    ticker = "QQQ" if market not in ("KOSPI", "KOSDAQ") else "069500"
    return SimpleNamespace(ticker=ticker, market=market, weight=weight, group_key=group_key, members=list(members))


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


def _acct(deposit_usd=None, asset_type="STOCK_OTHER", **kw):
    return SimpleNamespace(
        id=kw.pop("id", uuid.uuid4()),
        name=kw.pop("name", "계좌"),
        asset_type=asset_type,
        deposit_usd=deposit_usd,
        kis_account_no=kw.pop("kis_account_no", None),
        kiwoom_account_no=kw.pop("kiwoom_account_no", None),
        tax_type=kw.pop("tax_type", None),
    )


def _db(portfolios, *, dca_portfolio_id=None, monthly=1_400_000.0, accounts=(), fixed=(), waiting_usd=0.0):
    """execute 순서: 포트폴리오 목록 → 정액 적립 알림 → (필요 시) 브로커 계좌.
    scalar 순서: 적립 자동매수 포트폴리오 → (정액이 없을 때) 월 적립액 → 환전 대기 필요 달러."""
    db = MagicMock()
    portfolios_result = MagicMock()
    portfolios_result.scalars.return_value.all.return_value = portfolios
    fixed_result = MagicMock()
    fixed_result.all.return_value = list(fixed)
    accounts_result = MagicMock()
    accounts_result.scalars.return_value.all.return_value = list(accounts)
    db.execute = AsyncMock(side_effect=[portfolios_result, fixed_result, accounts_result])
    scalars = [dca_portfolio_id] + ([] if fixed else [monthly]) + [waiting_usd]
    db.scalar = AsyncMock(side_effect=scalars)
    return db


async def _plan(db, *, portfolio_id=None, months=3, closes=None, rate=1400.0, rate_is_live=True):
    with (
        patch.object(svc, "get_live_or_cached_usd_krw", new=AsyncMock(return_value=(rate, rate_is_live))),
        patch.object(svc, "fetch_usd_krw_closes", new=AsyncMock(return_value=closes)),
    ):
        return await svc.get_fx_plan(db, None, uuid.uuid4(), portfolio_id, months)


async def test_plan_need_usd_from_deposit_overseas_weight_and_held():
    p = _portfolio()
    db = _db([p], accounts=[_acct(100.0), _acct(None)])
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
    with pytest.raises(NotFoundError):
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
    db = _db([_portfolio()], accounts=[_acct(5000.0)])
    result = await _plan(db)
    assert result["status"] == "SUFFICIENT"
    assert result["need_usd"] == 0
    assert result["tranches"] == []


async def test_plan_degrades_without_history():
    result = await _plan(_db([_portfolio()]), closes=None)
    assert result["position"] is None
    assert len(result["tranches"]) == 1
    assert result["tranches"][0]["target_rate"] is None


async def test_plan_uses_last_close_when_rate_not_live():
    """실시간·캐시 환율이 없으면 설정 fallback(1300) 대신 1년 일봉 마지막 종가 기준 (plans/97 A2)."""
    closes = _closes()
    result = await _plan(_db([_portfolio()]), closes=closes, rate=1300.0, rate_is_live=False)
    assert result["rate_is_live"] is False
    assert result["position"]["rate"] == round(closes[-1], 2)
    assert result["monthly_need_usd"] == round(1_400_000 * 0.6 / closes[-1], 2)


async def test_plan_no_rate_when_neither_live_nor_history():
    """환율도 종가도 없으면 fallback 1300으로 달러를 계산하지 않는다 (plans/99 A6)."""
    result = await _plan(_db([_portfolio()]), closes=None, rate=1300.0, rate_is_live=False)
    assert result["status"] == "NO_RATE"
    assert result["need_usd"] == 0.0
    assert result["tranches"] == []


async def test_plan_rate_is_live_flag_default():
    result = await _plan(_db([_portfolio()]), closes=_closes())
    assert result["rate_is_live"] is True


async def test_held_usd_limited_to_linked_accounts():
    account_id = uuid.uuid4()
    db = _db([_portfolio(linked=[account_id])], accounts=[_acct(10.0)])
    await _plan(db)
    stmt = db.execute.await_args_list[2].args[0]
    assert "asset_accounts.id IN" in str(stmt)
    # 수기 증권 계좌(STOCK_OTHER, 메리츠 등)도 대상이다 — 브로커 API 계좌만 고르면 직접 입력한 달러가 빠진다
    assert "STOCK_OTHER" in str(stmt.compile(compile_kwargs={"literal_binds": True}))


# ── plans/121 B — 정액 적립·실시간 달러·환전 대기 ─────────────


def _fixed_alert(amount):
    return SimpleNamespace(dca_amount_krw=amount)


async def test_plan_uses_fixed_dca_amount_over_monthly_goal():
    acct = _acct(0.0)
    p = _portfolio()  # 해외 60 / 국내 40
    db = _db([p], fixed=[(_fixed_alert(1_000_000), acct)], accounts=[])
    result = await _plan(db)
    assert result["deposit_source"] == "DCA_AMOUNT"
    assert result["monthly_deposit_krw"] == 1_000_000
    # 100만 × 60% / 1400 = 428.57달러 — 월 적립액(140만)이 아니라 정액 금액 기준
    assert result["monthly_need_usd"] == round(1_000_000 * 0.6 / 1400, 2)
    # 월 적립액은 조회하지 않는다(scalar: 적립 포트폴리오 → 환전 대기)
    assert db.scalar.await_count == 2


async def test_plan_fixed_amount_in_tax_deferred_account_has_no_overseas_share():
    isa = _acct(0.0, tax_type="ISA")
    result = await _plan(_db([_portfolio()], fixed=[(_fixed_alert(1_000_000), isa)]))
    assert result["status"] == "NO_OVERSEAS"
    assert result["deposit_source"] == "DCA_AMOUNT"


async def test_plan_monthly_goal_source_without_fixed_alert():
    result = await _plan(_db([_portfolio()]))
    assert result["deposit_source"] == "MONTHLY_GOAL"


async def test_held_usd_reads_live_for_broker_accounts_and_caches(mock_cache):
    from app.core.cache_store import CacheStore

    kis = _acct(10.0, asset_type="STOCK_KIS", kis_account_no="123")
    manual = _acct(0.0)
    cache = CacheStore()
    live = AsyncMock(return_value=250.0)
    with patch.object(svc, "fetch_usd_buying_power", new=live):
        held = await svc._account_usd(MagicMock(), cache, uuid.uuid4(), kis)
        assert (held.usd, held.source) == (250.0, "LIVE")
        # 두 번째 조회는 2분 캐시
        user_id = uuid.uuid4()
        await svc._account_usd(MagicMock(), cache, user_id, kis)
        await svc._account_usd(MagicMock(), cache, user_id, kis)
    assert live.await_count == 2  # 첫 user_id 1회 + 두 번째 user_id 1회(캐시 키가 사용자별)
    held = await svc._account_usd(MagicMock(), cache, uuid.uuid4(), manual)
    assert (held.usd, held.source) == (0.0, "MANUAL")


async def test_held_usd_falls_back_to_synced_when_live_fails():
    kis = _acct(42.0, asset_type="STOCK_KIWOOM", kiwoom_account_no="9")
    with patch.object(svc, "fetch_usd_buying_power", new=AsyncMock(return_value=None)):
        held = await svc._account_usd(MagicMock(), None, uuid.uuid4(), kis)
    assert (held.usd, held.source, held.live_failed) == (42.0, "SYNCED", True)


async def test_held_usd_remembers_live_failure_for_ttl():
    """실패도 2분 기억 — 화면을 열 때마다 증권사 재조회·Sentry 이벤트를 남기지 않는다(plans/122 B4)."""
    from app.core.cache_store import CacheStore

    kis = _acct(42.0, asset_type="STOCK_KIS", kis_account_no="1")
    cache = CacheStore()
    user_id = uuid.uuid4()
    live = AsyncMock(return_value=None)
    with patch.object(svc, "fetch_usd_buying_power", new=live):
        for _ in range(2):
            held = await svc._account_usd(MagicMock(), cache, user_id, kis)
            assert (held.usd, held.source, held.live_failed) == (42.0, "SYNCED", True)
    assert live.await_count == 1


async def test_held_usd_skips_live_for_account_without_number():
    kis = _acct(5.0, asset_type="STOCK_KIS", kis_account_no=None)
    live = AsyncMock()
    with patch.object(svc, "fetch_usd_buying_power", new=live):
        held = await svc._account_usd(MagicMock(), None, uuid.uuid4(), kis)
    assert (held.usd, held.source, held.live_failed) == (5.0, "SYNCED", False)
    live.assert_not_awaited()


async def test_plan_held_usd_live_flag_and_fixed_account_included():
    kis = _acct(0.0, asset_type="STOCK_KIS", kis_account_no="1")
    db = _db([_portfolio()], fixed=[(_fixed_alert(1_400_000), kis)], accounts=[])
    with patch.object(svc, "fetch_usd_buying_power", new=AsyncMock(return_value=300.0)):
        result = await _plan(db)
    # 연결 계좌 조회 결과가 비어도 정액 적립 실행 계좌의 달러는 센다
    assert result["held_usd"] == 300.0
    assert result["held_usd_is_live"] is True


async def test_plan_includes_manual_stock_account_usd_with_breakdown():
    """포트폴리오에 연결된 수기 계좌(메리츠 등)의 직접 입력 달러도 보유 달러에 더하고 계좌별로 보여준다."""
    kis = _acct(0.0, asset_type="STOCK_KIS", kis_account_no="1", name="한국투자")
    meritz = _acct(1200.0, name="메리츠")
    db = _db([_portfolio()], accounts=[kis, meritz])
    with patch.object(svc, "fetch_usd_buying_power", new=AsyncMock(return_value=333.0)):
        result = await _plan(db)
    assert result["held_usd"] == 1533.0
    # 600달러 × 3개월 − 1533
    assert result["need_usd"] == 267.0
    assert result["held_usd_is_live"] is False
    assert [(a["name"], a["usd"], a["source"]) for a in result["held_usd_accounts"]] == [
        ("메리츠", 1200.0, "MANUAL"),
        ("한국투자", 333.0, "LIVE"),
    ]


async def test_plan_live_failure_with_zero_synced_is_not_live():
    """실시간 조회에 실패한 계좌는 동기화 값이 0이어도 '실시간'으로 표시하지 않는다."""
    kis = _acct(0.0, asset_type="STOCK_KIS", kis_account_no="1")
    kiwoom = _acct(0.0, asset_type="STOCK_KIWOOM", kiwoom_account_no="2")
    live = AsyncMock(side_effect=[100.0, None])
    db = _db([_portfolio()], accounts=[kis, kiwoom])
    with patch.object(svc, "fetch_usd_buying_power", new=live):
        result = await _plan(db)
    assert result["held_usd"] == 100.0
    assert result["held_usd_is_live"] is False


async def test_plan_waiting_fx_offset_only_by_executable_account_usd():
    """수기 계좌 달러로는 KIS·키움 대기 매수를 채울 수 없다 — 환전 대기 부족분은 실행 계좌 달러로만 상쇄한다."""
    kis = _acct(0.0, asset_type="STOCK_KIS", kis_account_no="1")
    meritz = _acct(1000.0)
    db = _db([_portfolio()], accounts=[kis, meritz], waiting_usd=450.0)
    with patch.object(svc, "fetch_usd_buying_power", new=AsyncMock(return_value=100.0)):
        result = await _plan(db, months=1, closes=_closes())
    assert result["held_usd"] == 1100.0
    assert result["waiting_fx_usd"] == 350.0
    # 전체 필요(600 − 1100 < 0)보다 대기 부족분이 크다 — 지금 350달러는 환전해야 한다
    assert result["need_usd"] == 350.0


async def test_plan_waiting_fx_forces_now_tranche():
    # 월 600달러 × 1개월 − 보유 100 = 500 필요. 환전 대기 매수 450달러 − 보유 100 = 350은 지금 환전해야 한다
    db = _db([_portfolio()], accounts=[_acct(100.0, asset_type="STOCK_KIS")], waiting_usd=450.0)
    result = await _plan(db, months=1, closes=_closes())
    assert result["waiting_fx_usd"] == 350.0
    now = result["tranches"][0]
    assert now["label"] == "지금"
    assert now["usd"] >= 350.0


async def test_plan_waiting_fx_covered_by_held_dollars():
    db = _db([_portfolio()], accounts=[_acct(500.0, asset_type="STOCK_KIS")], waiting_usd=450.0)
    result = await _plan(db)
    assert result["waiting_fx_usd"] == 0.0


def test_plan_urgent_exceeding_zone_share_takes_whole_need():
    tranches = svc.compute_fx_plan(_pos("EXPENSIVE"), 100.0, 1400.0, urgent_usd=150.0)
    assert [(t.label, t.usd) for t in tranches] == [("지금", 100.0)]


def test_plan_urgent_without_position_splits_now_and_run_day():
    tranches = svc.compute_fx_plan(None, 1000.0, 1400.0, urgent_usd=300.0)
    assert [(t.label, t.usd) for t in tranches] == [("지금", 300.0), ("적립일에 환전", 700.0)]


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
    with patch.object(
        svc, "get_fx_plan", new=AsyncMock(side_effect=NotFoundError(detail="포트폴리오를 찾을 수 없습니다"))
    ):
        res = api.get(f"/api/v1/invest/fx-plan?portfolio_id={uuid.uuid4()}")
    assert res.status_code == 404
    assert res.json() == {"detail": "포트폴리오를 찾을 수 없습니다"}


@pytest.mark.parametrize("months", [0, 13])
def test_api_months_out_of_range_422(api, months):
    res = api.get(f"/api/v1/invest/fx-plan?months={months}")
    assert res.status_code == 422


# ── 계획 알림 동기화 (plans/121) ─────────────────────────────


def _alert(rate, *, source="FX_PLAN", portfolio_id=None, triggered=False, usd=100.0, is_active=True):
    from datetime import UTC, datetime, timedelta

    if triggered is True:
        triggered = datetime.now(UTC)
    elif isinstance(triggered, int) and triggered is not False:
        triggered = datetime.now(UTC) - timedelta(days=triggered)  # 며칠 전 발동
    return SimpleNamespace(
        target_rate=rate,
        source=source,
        portfolio_id=portfolio_id,
        triggered_at=triggered or None,
        planned_usd=usd,
        is_active=is_active,
    )


def _sync_db(alerts, *, owned=True, total=None):
    db = MagicMock()
    db.scalar = AsyncMock(side_effect=[uuid.uuid4() if owned else None, len(alerts) if total is None else total])
    result = MagicMock()
    result.scalars.return_value.all.return_value = alerts
    db.execute = AsyncMock(return_value=result)
    db.delete = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


async def _sync(db, portfolio_id, targets):
    from app.core.cache_store import CacheStore

    return await svc.sync_fx_plan_alerts(db, CacheStore(), uuid.uuid4(), portfolio_id, targets)


async def test_sync_creates_updates_and_removes_plan_alerts():
    pid = uuid.uuid4()
    keep = _alert(1320.0, portfolio_id=pid, usd=50.0)
    old = _alert(1350.0, portfolio_id=pid)
    db = _sync_db([keep, old])

    result = await _sync(db, pid, [(1320.0, 120.0), (1300.0, 130.0)])

    assert result == svc.FxPlanAlertSyncResult(created=1, updated=1, removed=1, skipped_manual=0)
    assert keep.planned_usd == 120.0
    db.delete.assert_awaited_once_with(old)
    created = db.add.call_args.args[0]
    assert (float(created.target_rate), created.direction, created.max_trigger_count) == (1300.0, "BELOW", 1)
    assert (created.source, created.planned_usd, created.portfolio_id) == ("FX_PLAN", 130.0, pid)
    db.commit.assert_awaited_once()


async def test_sync_skips_target_with_manual_alert_and_never_touches_it():
    pid = uuid.uuid4()
    manual = _alert(1300.0, source="MANUAL", usd=None)
    db = _sync_db([manual])

    result = await _sync(db, pid, [(1300.0, 100.0)])

    assert result.skipped_manual == 1
    assert result.created == 0
    db.add.assert_not_called()
    db.delete.assert_not_awaited()
    assert manual.planned_usd is None


async def test_sync_leaves_other_portfolio_and_triggered_plan_alerts():
    pid = uuid.uuid4()
    other = _alert(1310.0, portfolio_id=uuid.uuid4())
    fired = _alert(1290.0, portfolio_id=pid, triggered=True)
    db = _sync_db([other, fired])

    result = await _sync(db, pid, [])

    assert result.removed == 0
    db.delete.assert_not_awaited()


async def test_sync_removes_old_triggered_plan_alerts_only():
    """발동 후 "지금 할 일" 기간이 지난 계획 알림은 지운다 — 쌓이면 알림 상한 409(plans/122 B5)."""
    pid = uuid.uuid4()
    recent = _alert(1300.0, portfolio_id=pid, triggered=1)
    old = _alert(1290.0, portfolio_id=pid, triggered=10)
    other_old = _alert(1280.0, portfolio_id=uuid.uuid4(), triggered=10)
    db = _sync_db([recent, old, other_old])

    result = await _sync(db, pid, [])

    assert result.removed == 1
    db.delete.assert_awaited_once_with(old)


async def test_sync_reuses_paused_plan_alert_instead_of_duplicating():
    """일시정지한 미발동 계획 알림도 같은 목표면 다시 켜서 쓴다 — 같은 환율 알림이 둘 생기지 않게(plans/122 B5)."""
    pid = uuid.uuid4()
    paused = _alert(1320.0, portfolio_id=pid, is_active=False)
    db = _sync_db([paused])

    result = await _sync(db, pid, [(1320.0, 80.0)])

    assert (result.created, result.updated) == (0, 1)
    assert paused.is_active is True
    assert paused.planned_usd == 80.0
    db.add.assert_not_called()


async def test_sync_dedupes_duplicate_plan_alerts_for_same_target():
    pid = uuid.uuid4()
    first, dup = _alert(1320.0, portfolio_id=pid), _alert(1320.0, portfolio_id=pid)
    db = _sync_db([first, dup])

    result = await _sync(db, pid, [(1320.0, 80.0)])

    assert (result.updated, result.removed) == (1, 1)
    db.delete.assert_awaited_once_with(dup)


async def test_sync_rejects_over_alert_cap():
    from app.exceptions import ConflictError

    db = _sync_db([], total=49)
    with pytest.raises(ConflictError):
        await _sync(db, uuid.uuid4(), [(1300.0, 1.0), (1290.0, 1.0)])
    db.add.assert_not_called()
    db.commit.assert_not_awaited()


async def test_sync_not_owned_portfolio_raises():
    db = _sync_db([], owned=False)
    with pytest.raises(NotFoundError):
        await _sync(db, uuid.uuid4(), [(1300.0, 1.0)])
    db.execute.assert_not_awaited()


async def test_sync_conflict_when_lock_held():
    from app.core.cache_store import CacheStore
    from app.exceptions import ConflictError

    cache = CacheStore()
    user_id = uuid.uuid4()
    await cache.set(f"lock:fx_plan_alerts:{user_id}", "other", nx=True, ex=30)
    with pytest.raises(ConflictError):
        await svc.sync_fx_plan_alerts(_sync_db([]), cache, user_id, uuid.uuid4(), [])


def test_api_sync_alerts_returns_counts(api):
    result = svc.FxPlanAlertSyncResult(created=2, updated=0, removed=1, skipped_manual=0)
    with patch.object(svc, "sync_fx_plan_alerts", new=AsyncMock(return_value=result)) as mocked:
        res = api.put(
            "/api/v1/invest/fx-plan/alerts",
            json={"portfolio_id": str(uuid.uuid4()), "targets": [{"target_rate": 1320, "usd": 100.5}]},
        )
    assert res.status_code == 200
    assert res.json() == {"created": 2, "updated": 0, "removed": 1, "skipped_manual": 0}
    assert mocked.await_args.args[4] == [(1320.0, 100.5)]


@pytest.mark.parametrize(
    "targets",
    [
        [{"target_rate": 1320, "usd": 1}, {"target_rate": 1320.0, "usd": 2}],  # 중복 목표
        [{"target_rate": 0, "usd": 1}],
        [{"target_rate": 1300, "usd": -1}],
        [{"target_rate": 1000 + i * 10, "usd": 1} for i in range(6)],  # 6개 초과
    ],
)
def test_api_sync_alerts_validation_422(api, targets):
    res = api.put("/api/v1/invest/fx-plan/alerts", json={"portfolio_id": str(uuid.uuid4()), "targets": targets})
    assert res.status_code == 422


async def test_delete_portfolio_removes_its_fx_plan_alerts():
    """포트폴리오 FK가 SET NULL이라 계획 알림이 계획 없이 계속 발동했다 — 함께 지운다(plans/122 B5)."""
    from sqlalchemy.sql.dml import Delete

    from app.services.portfolio import portfolio_crud_service as crud

    portfolio = SimpleNamespace(id=uuid.uuid4())
    db = MagicMock()
    db.scalar = AsyncMock(return_value=portfolio)
    db.execute = AsyncMock()
    db.delete = AsyncMock()
    db.commit = AsyncMock()
    with patch("app.services.rebalancing.plan_execution.cancel_pending_buy_legs", new=AsyncMock()):
        await crud.delete_portfolio(db, uuid.uuid4(), portfolio.id)

    deletes = [c.args[0] for c in db.execute.await_args_list if isinstance(c.args[0], Delete)]
    assert len(deletes) == 1
    assert deletes[0].table.name == "exchange_rate_alerts"
    sql = str(deletes[0].compile())
    assert "portfolio_id" in sql
    assert "source" in sql
    db.delete.assert_awaited_once_with(portfolio)
