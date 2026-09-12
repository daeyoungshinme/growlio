"""app/kiwoom/balance.py 단위 테스트."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.kiwoom.balance import get_domestic_balance, get_overseas_balance


def _ust21070_item(stk_cd="QQQ", name="Invesco QQQ Trust", qty="000000005"):
    """ust21070(미국주식 원장잔고확인) result_list 항목 — 실측 결과 stex_nm은 항상 "미국"
    (국가명)만 반환되어 거래소 구분에 못 쓴다. market은 provider의 enrich_overseas_positions()
    이 Yahoo Finance 조회로 별도 판별하므로, balance.py는 "US" 센티널만 채운다."""
    return {
        "stex_nm": "미국",
        "crnc_code": "USD",
        "stk_cd": stk_cd,
        "frgn_stk_nm": name,
        "poss_qty": qty,
        "frgn_stk_book_uv": "000350.00",
        "now_pric": "-00400.00",  # 전일대비 하락 부호 — 실제 가격은 절대값
        "evlt_amt": "000002000.00",
        "pl_amt": "+00000250.00",
        "pl_rt": "+14.28",
    }


def _ust21110_response(fc_entra="000000500.00"):
    """ust21110(해외주식 예수금) 응답 — result_list 통화별 외화예수금(fc_entra)."""
    return {
        "return_code": 0,
        "krw_entra": "0",
        "result_list": [
            {"crnc_code": "USD", "crnc_nm": "미국달러", "fc_entra": fc_entra},
        ],
    }


def _make_dispatch(bulk_items, *, deposit_fc_entra="000000500.00"):
    """ust21070(빈 body)은 bulk_items 전체를, ust21110은 예수금 응답을 반환한다.
    거래소 프로빙(stex_tp+stk_cd 조합 호출)은 폐기됐으므로 json이 있는 호출은 오지 않는다."""

    async def _dispatch(method, path, *, is_mock, headers, json=None, **kwargs):
        assert path == "/api/us/acnt"
        if headers["api-id"] == "ust21110":
            return _ust21110_response(fc_entra=deposit_fc_entra)
        assert headers["api-id"] == "ust21070"
        assert not json, "거래소 프로빙은 폐기됨 — stex_tp/stk_cd 지정 호출이 없어야 한다"
        return {"result_list": bulk_items}

    return _dispatch


class TestGetOverseasBalance:
    @pytest.mark.asyncio
    async def test_positions_carry_unresolved_market_sentinel(self):
        """balance.py는 거래소를 판별하지 않고 "US" 센티널만 채운다 — 실제 NASDAQ/NYSE/AMEX
        확정은 provider의 enrich_overseas_positions()가 담당한다. 프로빙 호출은 없어야 한다."""
        bulk_items = [_ust21070_item(stk_cd="QQQ"), _ust21070_item(stk_cd="SPY")]

        with patch("app.kiwoom.balance.kiwoom_request", side_effect=_make_dispatch(bulk_items)) as req:
            result = await get_overseas_balance("token", "1234567890", is_mock=True)

        assert {p["ticker"]: p["market"] for p in result["positions"]} == {"QQQ": "US", "SPY": "US"}
        assert result["deposit_usd"] == 500.0
        # ust21070 1회(빈 body) + ust21110 1회 = 2콜, 종목 수와 무관
        assert req.call_count == 2

    @pytest.mark.asyncio
    async def test_zero_qty_positions_excluded(self):
        bulk_items = [_ust21070_item(stk_cd="QQQ", qty="0")]

        with patch("app.kiwoom.balance.kiwoom_request", side_effect=_make_dispatch(bulk_items)):
            result = await get_overseas_balance("token", "1234567890", is_mock=True)

        assert result["positions"] == []
        assert result["total_value_usd"] == 0.0

    @pytest.mark.asyncio
    async def test_parses_position_fields_and_deposit(self):
        bulk_items = [_ust21070_item()]

        with patch("app.kiwoom.balance.kiwoom_request", side_effect=_make_dispatch(bulk_items)):
            result = await get_overseas_balance("token", "1234567890", is_mock=True)

        assert len(result["positions"]) == 1
        pos = result["positions"][0]
        assert pos["ticker"] == "QQQ"
        assert pos["market"] == "US"
        assert pos["qty"] == 5
        assert pos["avg_price"] == 350.0
        assert pos["current_price"] == 400.0  # 부호 제거된 절대값
        assert pos["pnl_usd"] == 250.0
        assert pos["pnl_pct"] == 14.28

        assert result["total_value_usd"] == 2000.0
        assert result["deposit_usd"] == 500.0

    @pytest.mark.asyncio
    async def test_no_usd_deposit_row_returns_zero(self):
        async def _no_deposit_row(method, path, *, is_mock, headers, json=None, **kwargs):
            if headers["api-id"] == "ust21110":
                return {"result_list": []}
            return {"result_list": []}

        with patch("app.kiwoom.balance.kiwoom_request", side_effect=_no_deposit_row):
            result = await get_overseas_balance("token", "1234567890", is_mock=True)

        assert result == {"positions": [], "total_value_usd": 0.0, "deposit_usd": 0.0}


def _evaluation_response():
    """kt00018 응답 — 실측 필드명(acnt_evlt_remn_indv_tot 등) + 숫자 0-padding/부호 접두."""
    return {
        "return_code": 0,
        "tot_pur_amt": "000000900000",
        "tot_evlt_amt": "000000950000",
        "tot_evlt_pl": "+00000050000",
        "acnt_evlt_remn_indv_tot": [
            {
                "stk_cd": "A005930",  # 거래소 접두 A
                "stk_nm": "삼성전자",
                "rmnd_qty": "000000010",
                "pur_pric": "000090000",
                "cur_prc": "-00095000",  # 전일대비 하락 부호 — 실제 가격은 절대값
                "evlt_amt": "000000950000",
                "evltv_prft": "+00000050000",
                "prft_rt": "+5.56",
            },
            {
                # 수량 0 → 제외되어야 함
                "stk_cd": "000660",
                "stk_nm": "SK하이닉스",
                "rmnd_qty": "0",
                "pur_pric": "0",
                "cur_prc": "0",
                "evlt_amt": "0",
                "evltv_prft": "0",
                "prft_rt": "0",
            },
        ],
    }


def _deposit_response(entr="000000100000", d2_entra="000000120000", ord_alow="000000110000"):
    """kt00001(예수금상세현황요청) 응답 — 예수금은 d2_entra(D+2 추정예수금)를 쓴다."""
    return {
        "return_code": 0,
        "entr": entr,
        "d2_entra": d2_entra,
        "ord_alow_amt": ord_alow,
        "100stk_ord_alow_amt": ord_alow,
    }


class TestGetDomesticBalance:
    @pytest.mark.asyncio
    async def test_parses_positions_and_merges_deposit(self):
        """kt00018(평가잔고) + kt00001(예수금)을 api-id로 구분해 병렬 조회·병합해야 한다."""

        async def _fake_request(method, path, *, is_mock, headers, json=None, **kwargs):
            if headers["api-id"] == "kt00018":
                assert json == {"qry_tp": "1", "dmst_stex_tp": "KRX"}
                assert "acnt_no" not in json
                return _evaluation_response()
            assert headers["api-id"] == "kt00001"
            assert json == {"qry_tp": "3"}  # dmst_stex_tp는 kt00001 스키마에 없음
            return _deposit_response()

        with patch("app.kiwoom.balance.kiwoom_request", side_effect=_fake_request):
            result = await get_domestic_balance("token", "1234567890", is_mock=True)

        assert len(result["positions"]) == 1
        pos = result["positions"][0]
        assert pos["ticker"] == "005930"  # A 접두 제거
        assert pos["qty"] == 10
        assert pos["avg_price"] == 90000.0
        assert pos["current_price"] == 95000.0  # 부호 제거된 절대값
        assert pos["pnl"] == 50000.0
        assert pos["pnl_pct"] == 5.56

        assert result["total_value_krw"] == 950000.0
        assert result["invested_krw"] == 900000.0
        assert result["pnl_krw"] == 50000.0
        assert result["deposit_krw"] == 120000.0  # d2_entra (D+2 추정예수금)
        assert result["orderable_krw"] == 110000.0  # 100stk_ord_alow_amt

    @pytest.mark.asyncio
    async def test_deposit_uses_d2_entra_over_entr(self):
        async def _fake_request(method, path, *, is_mock, headers, json=None, **kwargs):
            if headers["api-id"] == "kt00018":
                return _evaluation_response()
            return _deposit_response(entr="000000100000", d2_entra="000000200000")

        with patch("app.kiwoom.balance.kiwoom_request", side_effect=_fake_request):
            result = await get_domestic_balance("token", "1234567890", is_mock=True)

        assert result["deposit_krw"] == 200000.0

    @pytest.mark.asyncio
    async def test_deposit_d2_entra_zero_is_respected(self):
        """d2_entra 키가 있으면 값이 0이어도 신뢰 — entr로 폴백하지 않는다."""

        async def _fake_request(method, path, *, is_mock, headers, json=None, **kwargs):
            if headers["api-id"] == "kt00018":
                return _evaluation_response()
            return {"return_code": 0, "entr": "000000100000", "d2_entra": "0"}

        with patch("app.kiwoom.balance.kiwoom_request", side_effect=_fake_request):
            result = await get_domestic_balance("token", "1234567890", is_mock=True)

        assert result["deposit_krw"] == 0.0

    @pytest.mark.asyncio
    async def test_deposit_falls_back_to_entr_when_d2_missing(self):
        async def _fake_request(method, path, *, is_mock, headers, json=None, **kwargs):
            if headers["api-id"] == "kt00018":
                return _evaluation_response()
            return {"return_code": 0, "entr": "000000100000"}  # d2_entra 없음

        with (
            patch("app.kiwoom.balance.kiwoom_request", side_effect=_fake_request),
            patch("app.kiwoom.balance.logger") as mock_logger,
        ):
            result = await get_domestic_balance("token", "1234567890", is_mock=True)

        assert result["deposit_krw"] == 100000.0
        mock_logger.warning.assert_called_once_with("kiwoom_deposit_d2_missing_fallback_entr", entr="000000100000")

    @pytest.mark.asyncio
    async def test_orderable_krw_fallback_chain(self):
        """100stk_ord_alow_amt → ord_alow_amt → deposit_krw 순 폴백."""

        async def _no_100stk(method, path, *, is_mock, headers, json=None, **kwargs):
            if headers["api-id"] == "kt00018":
                return _evaluation_response()
            return {"return_code": 0, "d2_entra": "000000120000", "ord_alow_amt": "000000105000"}

        with patch("app.kiwoom.balance.kiwoom_request", side_effect=_no_100stk):
            result = await get_domestic_balance("token", "1234567890", is_mock=True)
        assert result["orderable_krw"] == 105000.0

        async def _no_orderable(method, path, *, is_mock, headers, json=None, **kwargs):
            if headers["api-id"] == "kt00018":
                return _evaluation_response()
            return {"return_code": 0, "d2_entra": "000000120000"}

        with patch("app.kiwoom.balance.kiwoom_request", side_effect=_no_orderable):
            result = await get_domestic_balance("token", "1234567890", is_mock=True)
        assert result["orderable_krw"] == 120000.0  # deposit_krw 폴백

    @pytest.mark.asyncio
    async def test_missing_entr_field_logs_warning_and_returns_zero(self):
        """kt00001 응답에 entr 필드가 없으면(비정상 응답) 조용히 0을 반환하지 말고
        경고 로그를 남겨야 한다 — 리밸런싱 실행 화면 예수금 0원 버그의 재발 감지용."""

        async def _fake_request(method, path, *, is_mock, headers, json=None, **kwargs):
            if headers["api-id"] == "kt00018":
                return _evaluation_response()
            assert headers["api-id"] == "kt00001"
            return {"return_code": 0}  # entr 필드 없는 비정상 응답

        with (
            patch("app.kiwoom.balance.kiwoom_request", side_effect=_fake_request),
            patch("app.kiwoom.balance.logger") as mock_logger,
        ):
            result = await get_domestic_balance("token", "1234567890", is_mock=True)

        assert result["deposit_krw"] == 0.0
        mock_logger.warning.assert_called_once_with("kiwoom_deposit_field_missing", response_keys=["return_code"])
