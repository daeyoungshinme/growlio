"""app/kis/balance.py 단위 테스트 — 국내 예수금 필드 선택(D+2)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.kis.balance import get_domestic_balance


def _balance_response(*, prvs_rcdl_excc_amt="120000", dnca_tot_amt="100000"):
    summary = {"evlu_amt_smtl_amt": "950000", "pchs_amt_smtl_amt": "900000", "evlu_pfls_smtl_amt": "50000"}
    if prvs_rcdl_excc_amt is not None:
        summary["prvs_rcdl_excc_amt"] = prvs_rcdl_excc_amt
    if dnca_tot_amt is not None:
        summary["dnca_tot_amt"] = dnca_tot_amt
    return {"output1": [], "output2": [summary]}


class TestKisDomesticDeposit:
    @pytest.mark.asyncio
    async def test_uses_prvs_rcdl_excc_amt_d2_deposit(self):
        async def _fake(*args, **kwargs):
            return _balance_response()

        with patch("app.kis.balance.kis_request", side_effect=_fake):
            result = await get_domestic_balance("k", "s", "t", "12345678", is_mock=False)

        assert result["deposit_krw"] == 120000.0  # D+2, not dnca_tot_amt(100000)

    @pytest.mark.asyncio
    async def test_falls_back_to_dnca_tot_amt_when_d2_missing(self):
        async def _fake(*args, **kwargs):
            return _balance_response(prvs_rcdl_excc_amt=None)

        with (
            patch("app.kis.balance.kis_request", side_effect=_fake),
            patch("app.kis.balance.logger") as mock_logger,
        ):
            result = await get_domestic_balance("k", "s", "t", "12345678", is_mock=False)

        assert result["deposit_krw"] == 100000.0
        mock_logger.warning.assert_called_once()


def _overseas_response(ticker: str) -> dict:
    return {
        "output1": [
            {
                "ovrs_pdno": ticker,
                "ovrs_item_name": ticker,
                "ovrs_cblc_qty": "3",
                "pchs_avg_pric": "100",
                "now_pric2": "110",
                "ovrs_stck_evlu_amt": "330",
                "frcr_evlu_pfls_amt": "30",
                "evlu_pfls_rt": "10",
            }
        ],
        "output2": {"frcr_dncl_amt_2": "50"},
    }


class TestKisOverseasBalance:
    @pytest.mark.asyncio
    async def test_all_exchanges_ok_returns_merged_positions(self):
        from app.kis.balance import get_overseas_balance

        async def _fake(*args, **kwargs):
            return _overseas_response(kwargs["params"]["OVRS_EXCG_CD"])

        with patch("app.kis.balance.kis_request", side_effect=_fake):
            result = await get_overseas_balance("k", "s", "t", "12345678", is_mock=False)

        assert len(result["positions"]) == 3
        assert result["deposit_usd"] == 50.0

    @pytest.mark.asyncio
    async def test_partial_exchange_failure_raises_instead_of_partial_result(self):
        """한 거래소라도 실패하면 부분 결과를 확정값처럼 반환하지 않고 raise —
        fetch_overseas_cached가 ok=False(미확인)로 처리해 해외 포지션·예수금을 보존하게 한다."""
        from app.kis.balance import get_overseas_balance

        async def _fake(*args, **kwargs):
            if kwargs["params"]["OVRS_EXCG_CD"] == "AMEX":
                raise RuntimeError("boom")
            return _overseas_response(kwargs["params"]["OVRS_EXCG_CD"])

        with (
            patch("app.kis.balance.kis_request", side_effect=_fake),
            pytest.raises(RuntimeError, match="AMEX"),
        ):
            await get_overseas_balance("k", "s", "t", "12345678", is_mock=False)

    @pytest.mark.asyncio
    async def test_token_expired_propagates(self):
        from app.kis.balance import get_overseas_balance
        from app.kis.client import KisTokenExpiredError

        async def _fake(*args, **kwargs):
            raise KisTokenExpiredError("expired")

        with (
            patch("app.kis.balance.kis_request", side_effect=_fake),
            pytest.raises(KisTokenExpiredError),
        ):
            await get_overseas_balance("k", "s", "t", "12345678", is_mock=False)


def _domestic_row(ticker: str) -> dict:
    return {
        "pdno": ticker,
        "prdt_name": ticker,
        "hldg_qty": "1",
        "pchs_avg_pric": "100",
        "prpr": "100",
        "evlu_amt": "100",
        "evlu_pfls_amt": "0",
        "evlu_pfls_rt": "0",
    }


class TestKisBalancePagination:
    """실계좌 미검증 — KIS 문서 규약(응답 헤더 tr_cont F/M=다음 있음, 요청 헤더 tr_cont=N + CTX_AREA 키) 기반."""

    @pytest.mark.asyncio
    async def test_domestic_follows_tr_cont_to_next_page(self):
        calls: list[dict] = []

        async def _fake(*args, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                kwargs["response_headers"]["tr_cont"] = "M"
                return {
                    "output1": [_domestic_row("005930")],
                    "output2": [{"prvs_rcdl_excc_amt": "1"}],
                    "ctx_area_fk100": "FK1",
                    "ctx_area_nk100": "NK1",
                }
            kwargs["response_headers"]["tr_cont"] = "D"
            return {"output1": [_domestic_row("000660")], "output2": [{"prvs_rcdl_excc_amt": "1"}]}

        with patch("app.kis.balance.kis_request", side_effect=_fake):
            result = await get_domestic_balance("k", "s", "t", "12345678", is_mock=False)

        assert [p["ticker"] for p in result["positions"]] == ["005930", "000660"]
        assert calls[1]["headers"]["tr_cont"] == "N"
        assert calls[1]["params"]["CTX_AREA_NK100"] == "NK1"
        assert calls[1]["params"]["CTX_AREA_FK100"] == "FK1"

    @pytest.mark.asyncio
    async def test_domestic_stops_on_last_page_even_with_ctx_key(self):
        """마지막 페이지(tr_cont=D)도 본문에 연속키가 남을 수 있다 — 헤더 기준으로 멈춰야 이중 집계가 없다."""
        calls = 0

        async def _fake(*args, **kwargs):
            nonlocal calls
            calls += 1
            kwargs["response_headers"]["tr_cont"] = "D"
            return {"output1": [_domestic_row("005930")], "output2": [{}], "ctx_area_nk100": "NK1"}

        with patch("app.kis.balance.kis_request", side_effect=_fake):
            result = await get_domestic_balance("k", "s", "t", "12345678", is_mock=False)

        assert calls == 1
        assert len(result["positions"]) == 1

    @pytest.mark.asyncio
    async def test_overseas_follows_tr_cont_per_exchange(self):
        from app.kis.balance import get_overseas_balance

        seen: dict[str, int] = {}

        async def _fake(*args, **kwargs):
            exch = kwargs["params"]["OVRS_EXCG_CD"]
            seen[exch] = seen.get(exch, 0) + 1
            if exch == "NASD" and seen[exch] == 1:
                kwargs["response_headers"]["tr_cont"] = "F"
                return {**_overseas_response("AAPL"), "ctx_area_nk200": "NK"}
            return _overseas_response("MSFT" if exch == "NASD" else exch)

        with patch("app.kis.balance.kis_request", side_effect=_fake):
            result = await get_overseas_balance("k", "s", "t", "12345678", is_mock=False)

        tickers = sorted(p["ticker"] for p in result["positions"])
        assert tickers == ["AAPL", "AMEX", "MSFT", "NYSE"]
