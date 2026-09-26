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
        with patch("app.services.overseas_realized_service.today_kst", return_value=TODAY):
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


def test_resolve_source():
    covered = [{"account_id": "a", "account_name": "A", "realized_krw": 0.0}]
    uncovered = [{"account_id": "b", "account_name": "B", "reason": "x"}]
    assert resolve_source([], uncovered) == "NONE"
    assert resolve_source(covered, []) == "BROKER"
    assert resolve_source(covered, uncovered) == "PARTIAL"
