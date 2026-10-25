"""E6 해외주식 실현손익 자동 집계 — KIS 기간손익 클라이언트 + overseas_realized_service 테스트."""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.kis.realized import get_overseas_realized_pnl
from app.services.overseas_realized_service import get_overseas_realized_summary, resolve_source

TODAY = date(2026, 9, 26)


def _row(ticker: str, pnl: float, day: str = "20260310") -> dict:
    return {"trad_day": day, "ovrs_pdno": ticker, "slcl_qty": "3", "ovrs_rlzt_pfls_amt": str(pnl)}


class TestGetOverseasRealizedPnl:
    @pytest.mark.asyncio
    async def test_prefers_summary_total_and_sends_krw_params(self):
        req = AsyncMock(
            return_value={
                "output1": [_row("AAPL", 1_200_000), _row("TSLA", -300_000)],
                "output2": {"ovrs_rlzt_pfls_tot_amt": "900000"},
                "ctx_area_nk200": "",
            }
        )
        with patch("app.kis.realized.kis_request", new=req):
            result = await get_overseas_realized_pnl("k", "s", "t", "12345678-01", date(2026, 1, 1), TODAY)

        assert result["total_krw"] == 900_000
        assert [t["ticker"] for t in result["trades"]] == ["AAPL", "TSLA"]
        params = req.call_args.kwargs["params"]
        assert params["WCRC_FRCR_DVSN_CD"] == "02"
        assert params["INQR_STRT_DT"] == "20260101"
        assert params["INQR_END_DT"] == "20260926"
        assert params["CANO"] == "12345678"
        assert req.call_args.kwargs["headers"]["tr_id"] == "TTTS3039R"
        assert req.call_args.kwargs["is_mock"] is False

    @pytest.mark.asyncio
    async def test_paginates_and_sums_rows_without_summary(self):
        req = AsyncMock(
            side_effect=[
                {"output1": [_row("AAPL", 500_000)], "ctx_area_nk200": "NEXT1", "ctx_area_fk200": "FK1"},
                {"output1": [_row("MSFT", 250_000)], "ctx_area_nk200": ""},
            ]
        )
        with patch("app.kis.realized.kis_request", new=req):
            result = await get_overseas_realized_pnl("k", "s", "t", "1234567801", date(2026, 1, 1), TODAY)

        assert result["total_krw"] == 750_000
        assert req.await_count == 2
        second = req.call_args_list[1].kwargs
        assert second["params"]["CTX_AREA_NK200"] == "NEXT1"
        assert second["headers"]["tr_cont"] == "N"

    @pytest.mark.asyncio
    async def test_stops_when_continuation_key_repeats(self):
        page = {"output1": [_row("AAPL", 100_000)], "ctx_area_nk200": "SAME"}
        req = AsyncMock(return_value=page)
        with patch("app.kis.realized.kis_request", new=req):
            result = await get_overseas_realized_pnl("k", "s", "t", "1234567801", date(2026, 1, 1), TODAY)

        assert req.await_count == 2  # 두 번째 응답의 키가 요청 키와 같아 중단
        assert result["total_krw"] == 200_000

    @pytest.mark.asyncio
    async def test_empty_response(self):
        with patch("app.kis.realized.kis_request", new=AsyncMock(return_value={"output1": [], "output2": {}})):
            result = await get_overseas_realized_pnl("k", "s", "t", "1234567801", date(2026, 1, 1), TODAY)
        assert result == {"total_krw": 0, "trades": []}


def _acc(make_account, name: str, **kw):
    kw.setdefault("is_mock_mode", False)
    kw.setdefault("kis_app_key", "enc-key")
    kw.setdefault("kis_app_secret", "enc-secret")
    return make_account(account_id=uuid.uuid4(), name=name, **kw)


def _db_with_accounts(accounts: list) -> MagicMock:
    db = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = accounts
    db.execute = AsyncMock(return_value=result)
    return db


class TestGetOverseasRealizedSummary:
    @pytest.fixture(autouse=True)
    def _today(self):
        # 수기 매매 기록 집계는 TestTradeRecordRealized가 따로 검증 — 여기선 기록 없음으로 고정
        with (
            patch("app.services.overseas_realized_service.today_kst", return_value=TODAY),
            patch(
                "app.services.overseas_realized_service.load_trade_record_realized",
                new=AsyncMock(return_value={}),
            ) as self.load_records,
        ):
            yield

    @pytest.mark.asyncio
    async def test_kis_real_accounts_covered_and_unsupported_holders_listed(self, make_account, mock_cache):
        kis = _acc(make_account, "KIS 일반")
        kis_mock = _acc(make_account, "KIS 모의", is_mock_mode=True)
        kiwoom = _acc(make_account, "키움", asset_type="STOCK_KIWOOM")
        toss_no_overseas = _acc(make_account, "토스", asset_type="STOCK_TOSS")
        isa = _acc(make_account, "KIS ISA", tax_type="ISA")
        db = _db_with_accounts([kis, kis_mock, kiwoom, toss_no_overseas, isa])
        positions = [{"account_id": str(kis_mock.id)}, {"account_id": str(kiwoom.id)}]

        fetch = AsyncMock(return_value=1_300_000.0)
        with (
            patch("app.services.overseas_realized_service._fetch_kis_realized", new=fetch),
            patch(
                "app.services.overseas_realized_service.get_overseas_positions_detail",
                new=AsyncMock(return_value=positions),
            ),
        ):
            summary = await get_overseas_realized_summary(uuid.uuid4(), 2026, db, cache=mock_cache)

        assert fetch.await_count == 1
        assert fetch.call_args.args[1:3] == (date(2026, 1, 1), TODAY)  # 올해는 오늘까지
        assert summary["realized_gain_krw"] == 1_300_000
        assert summary["source"] == "PARTIAL"
        assert [a["account_name"] for a in summary["covered_accounts"]] == ["KIS 일반"]
        uncovered = {a["account_name"]: a["reason"] for a in summary["uncovered_accounts"]}
        assert set(uncovered) == {"KIS 모의", "키움"}  # 해외 미보유 토스·과세이연 ISA는 제외
        assert "모의투자" in uncovered["KIS 모의"]
        assert "키움" in uncovered["키움"]
        mock_cache.setex.assert_awaited()

    @pytest.mark.asyncio
    async def test_fetch_failure_is_isolated_and_not_cached(self, make_account, mock_cache):
        ok = _acc(make_account, "A 계좌")
        broken = _acc(make_account, "B 계좌")
        db = _db_with_accounts([ok, broken])
        fetch = AsyncMock(side_effect=[500_000.0, RuntimeError("boom")])
        with (
            patch("app.services.overseas_realized_service._fetch_kis_realized", new=fetch),
            patch(
                "app.services.overseas_realized_service.get_overseas_positions_detail",
                new=AsyncMock(return_value=[]),
            ),
        ):
            summary = await get_overseas_realized_summary(uuid.uuid4(), 2026, db, cache=mock_cache)

        assert summary["realized_gain_krw"] == 500_000
        assert summary["uncovered_accounts"] == [
            {"account_id": str(broken.id), "account_name": "B 계좌", "reason": "조회 실패"}
        ]
        mock_cache.setex.assert_not_awaited()
        mock_cache.set.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_supported_accounts_returns_none(self, make_account, mock_cache):
        db = _db_with_accounts([_acc(make_account, "수기", asset_type="STOCK_OTHER")])
        with patch(
            "app.services.overseas_realized_service.get_overseas_positions_detail",
            new=AsyncMock(return_value=[]),
        ):
            summary = await get_overseas_realized_summary(uuid.uuid4(), 2025, db, cache=mock_cache)

        assert summary["realized_gain_krw"] is None
        assert summary["source"] == "NONE"
        assert summary["uncovered_accounts"] == []

    @pytest.mark.asyncio
    async def test_returns_cached_value(self, mock_cache):
        cached = {"year": 2026, "realized_gain_krw": 1.0, "source": "BROKER"}
        with patch("app.services.overseas_realized_service.get_cached_json", new=AsyncMock(return_value=cached)):
            db = MagicMock()
            db.execute = AsyncMock()
            summary = await get_overseas_realized_summary(uuid.uuid4(), 2026, db, cache=mock_cache)
        assert summary == cached
        db.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_fetch_kis_realized_refreshes_expired_token(self, make_account, mock_cache):
        from app.kis.client import KisTokenExpiredError
        from app.services.overseas_realized_service import _fetch_kis_realized

        acc = _acc(make_account, "KIS")
        token = AsyncMock(side_effect=["old", "new"])
        pnl = AsyncMock(side_effect=[KisTokenExpiredError(), {"total_krw": 42.0, "trades": []}])
        with (
            patch("app.services.overseas_realized_service.decrypt_kis_credentials", return_value=("k", "s")),
            patch("app.services.overseas_realized_service.get_access_token", new=token),
            patch("app.services.overseas_realized_service.get_overseas_realized_pnl", new=pnl),
        ):
            total = await _fetch_kis_realized(acc, date(2026, 1, 1), TODAY, MagicMock(), mock_cache)

        assert total == 42.0
        assert token.call_args_list[1].kwargs["force_refresh"] is True
        assert pnl.call_args_list[1].args[2] == "new"

    @pytest.mark.asyncio
    async def test_fetch_timeout_does_not_cancel_token_issuance(self, make_account, mock_cache):
        """토큰 발급(내부 commit)은 타임아웃 대상이 아니다 — 조회 HTTP에만 wait_for가 걸린다."""
        import asyncio

        from app.services.overseas_realized_service import _fetch_kis_realized

        acc = _acc(make_account, "KIS")

        async def slow_token(*args, **kwargs):
            await asyncio.sleep(0.05)
            return "tok"

        async def slow_pnl(*args, **kwargs):
            await asyncio.sleep(1)
            return {"total_krw": 1.0, "trades": []}

        with (
            patch("app.services.overseas_realized_service.decrypt_kis_credentials", return_value=("k", "s")),
            patch("app.services.overseas_realized_service._FETCH_TIMEOUT_SECONDS", 0.01),
            patch("app.services.overseas_realized_service.get_access_token", new=slow_token),
        ):
            fast_pnl = AsyncMock(return_value={"total_krw": 7.0, "trades": []})
            with patch("app.services.overseas_realized_service.get_overseas_realized_pnl", new=fast_pnl):
                assert await _fetch_kis_realized(acc, date(2026, 1, 1), TODAY, MagicMock(), mock_cache) == 7.0
            with (
                patch("app.services.overseas_realized_service.get_overseas_realized_pnl", new=slow_pnl),
                pytest.raises(TimeoutError),
            ):
                await _fetch_kis_realized(acc, date(2026, 1, 1), TODAY, MagicMock(), mock_cache)


def test_resolve_source():
    covered = [{"account_id": "a", "account_name": "A", "realized_krw": 0.0}]
    uncovered = [{"account_id": "b", "account_name": "B", "reason": "x"}]
    assert resolve_source([], uncovered) == "NONE"
    assert resolve_source(covered, []) == "BROKER"
    assert resolve_source(covered, uncovered) == "PARTIAL"


def _trade(
    side: str, qty: float, price: float, day: date, *, ticker="AAPL", market="NASDAQ", fee=None, account_id=None
):
    from types import SimpleNamespace

    return SimpleNamespace(
        id=uuid.uuid4(),
        account_id=account_id,
        side=side,
        ticker=ticker,
        market=market,
        qty=qty,
        price_krw=price,
        fee=fee,
        trade_date=day,
    )


def _pos(snapshot_id, account_id, avg_price, qty=1, ticker="AAPL", market="NASDAQ"):
    from types import SimpleNamespace

    return SimpleNamespace(
        snapshot_id=snapshot_id, account_id=account_id, ticker=ticker, market=market, qty=qty, avg_price=avg_price
    )


START, END = date(2026, 1, 1), TODAY


class TestComputeTradeRealized:
    def test_uses_buy_record_cost_and_fee(self):
        from app.services.overseas_realized_service import compute_trade_realized

        trades = [
            _trade("SELL", 4, 150_000, date(2026, 3, 1), fee=1_000),
            _trade("BUY", 10, 100_000, date(2025, 12, 1)),
        ]
        r = compute_trade_realized(trades, START, END, lambda t: None)
        assert r.realized_krw == pytest.approx(4 * 150_000 - 1_000 - 4 * 100_000)
        assert (r.sell_count, r.missing_basis_count, r.estimated) == (1, 0, False)

    def test_falls_back_to_snapshot_avg_when_buys_do_not_cover(self):
        from app.services.overseas_realized_service import compute_trade_realized

        trades = [_trade("BUY", 1, 90_000, date(2026, 2, 1)), _trade("SELL", 3, 150_000, date(2026, 3, 1))]
        r = compute_trade_realized(trades, START, END, lambda t: 120_000.0)
        assert r.realized_krw == pytest.approx(3 * 150_000 - 3 * 120_000)
        assert r.estimated is True

    def test_missing_basis_is_excluded(self):
        from app.services.overseas_realized_service import compute_trade_realized

        r = compute_trade_realized([_trade("SELL", 3, 150_000, date(2026, 3, 1))], START, END, lambda t: None)
        assert (r.realized_krw, r.sell_count, r.missing_basis_count) == (0.0, 0, 1)

    def test_prior_year_sell_consumes_lot_and_future_sell_ignored(self):
        from app.services.overseas_realized_service import compute_trade_realized

        trades = [
            _trade("BUY", 10, 100_000, date(2025, 6, 1)),
            _trade("SELL", 5, 200_000, date(2025, 11, 1)),  # 작년 매도 — lot만 줄인다
            _trade("SELL", 5, 110_000, date(2026, 2, 1)),
            _trade("SELL", 5, 300_000, date(2026, 12, 1)),  # 오늘 이후 — 무시
        ]
        r = compute_trade_realized(trades, START, END, lambda t: None)
        assert r.realized_krw == pytest.approx(5 * 110_000 - 5 * 100_000)
        assert r.sell_count == 1

    def test_tickers_have_separate_lots(self):
        from app.services.overseas_realized_service import compute_trade_realized

        trades = [
            _trade("BUY", 1, 100_000, date(2026, 1, 5), ticker="AAPL"),
            _trade("BUY", 1, 500_000, date(2026, 1, 5), ticker="MSFT"),
            _trade("SELL", 1, 50_000, date(2026, 2, 5), ticker="MSFT"),
        ]
        r = compute_trade_realized(trades, START, END, lambda t: None)
        assert r.realized_krw == pytest.approx(-450_000)


def _result(*, scalars=None, rows=None) -> MagicMock:
    res = MagicMock()
    res.scalars.return_value.all.return_value = scalars or []
    res.all.return_value = rows or []
    return res


class TestLoadTradeRecordRealized:
    @pytest.mark.asyncio
    async def test_filters_domestic_and_uses_snapshot_before_sell_date(self, make_account):
        from app.services.overseas_realized_service import load_trade_record_realized

        acc = make_account(account_id=uuid.uuid4(), asset_type="STOCK_KIWOOM")
        sell_day = date(2026, 3, 10)
        trades = [
            _trade("SELL", 2, 150_000, sell_day, account_id=acc.id),
            _trade("SELL", 1, 70_000, sell_day, ticker="005930", market="KOSPI", account_id=acc.id),
        ]
        before_id, same_day_id = uuid.uuid4(), uuid.uuid4()
        snaps = [(before_id, acc.id, date(2026, 3, 9)), (same_day_id, acc.id, sell_day)]
        positions = [
            _pos(before_id, acc.id, 100_000, qty=4),
            _pos(same_day_id, acc.id, 999_999, qty=2),  # 매도 당일 스냅샷은 쓰지 않는다
            _pos(None, acc.id, 888_888, qty=2),
        ]
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[_result(scalars=trades), _result(rows=snaps), _result(scalars=positions)])

        out = await load_trade_record_realized(uuid.uuid4(), [acc], START, END, db)

        r = out[str(acc.id)]
        assert r.realized_krw == pytest.approx(2 * 150_000 - 2 * 100_000)  # 국내 매도 제외, 직전 스냅샷 평단
        assert (r.sell_count, r.estimated) == (1, True)

    @pytest.mark.asyncio
    async def test_current_position_fallback_and_no_sells(self, make_account):
        from app.services.overseas_realized_service import load_trade_record_realized

        acc = make_account(account_id=uuid.uuid4(), asset_type="STOCK_TOSS")
        trades = [_trade("SELL", 1, 150_000, date(2026, 3, 10), account_id=acc.id)]
        current = [_pos(None, acc.id, 130_000, market="US")]
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[_result(scalars=trades), _result(rows=[]), _result(scalars=current)])
        out = await load_trade_record_realized(uuid.uuid4(), [acc], START, END, db)
        assert out[str(acc.id)].realized_krw == pytest.approx(20_000)

        buy_only = [_trade("BUY", 1, 1, date(2026, 3, 1), account_id=acc.id)]
        db.execute = AsyncMock(return_value=_result(scalars=buy_only))
        assert await load_trade_record_realized(uuid.uuid4(), [acc], START, END, db) == {}
        assert db.execute.await_count == 1  # SELL이 없으면 스냅샷·포지션을 읽지 않는다

        assert await load_trade_record_realized(uuid.uuid4(), [], START, END, db) == {}


class TestSummaryWithTradeRecords:
    @pytest.mark.asyncio
    async def test_records_cover_unsupported_accounts_without_double_counting_kis(self, make_account, mock_cache):
        from app.services.overseas_realized_service import TradeRealized

        kis = _acc(make_account, "KIS 일반")
        kiwoom = _acc(make_account, "키움", asset_type="STOCK_KIWOOM")
        toss_sold_out = _acc(make_account, "토스", asset_type="STOCK_TOSS")
        manual_no_basis = _acc(make_account, "수기", asset_type="STOCK_OTHER")
        db = _db_with_accounts([kis, kiwoom, toss_sold_out, manual_no_basis])
        records = {
            str(kiwoom.id): TradeRealized(realized_krw=1_000_000, sell_count=2),
            str(toss_sold_out.id): TradeRealized(realized_krw=-200_000, sell_count=1, estimated=True),
            str(manual_no_basis.id): TradeRealized(sell_count=0, missing_basis_count=1),
        }
        load = AsyncMock(return_value=records)
        with (
            patch("app.services.overseas_realized_service.today_kst", return_value=TODAY),
            patch("app.services.overseas_realized_service.load_trade_record_realized", new=load),
            patch("app.services.overseas_realized_service._fetch_kis_realized", new=AsyncMock(return_value=500_000.0)),
            patch(
                "app.services.overseas_realized_service.get_overseas_positions_detail",
                new=AsyncMock(return_value=[{"account_id": str(kiwoom.id)}]),
            ),
        ):
            summary = await get_overseas_realized_summary(uuid.uuid4(), 2026, db, cache=mock_cache)

        assert kis not in load.call_args.args[1]  # KIS 자동 집계 계좌는 기록을 쓰지 않는다(이중 집계 방지)
        assert summary["realized_gain_krw"] == 1_300_000
        methods = {a["account_name"]: (a["method"], a["estimated"]) for a in summary["covered_accounts"]}
        assert methods == {
            "KIS 일반": ("BROKER", False),
            "키움": ("TRADE_RECORD", False),
            "토스": ("TRADE_RECORD", True),  # 전량 매도로 현재 보유가 없어도 집계
        }
        assert summary["uncovered_accounts"] == [
            {
                "account_id": str(manual_no_basis.id),
                "account_name": "수기",
                "reason": "매도 기록의 취득가를 알 수 없어요",
            }
        ]
        assert summary["source"] == "PARTIAL"
