"""app/kiwoom/balance.py 단위 테스트."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.kiwoom.balance import get_domestic_balance, get_overseas_balance
from app.kiwoom.client import KiwoomApiError
from app.providers.http_client import MaxRetriesExceededError


def _ust21070_item(stk_cd="QQQ", name="Invesco QQQ Trust", qty="000000005"):
    """ust21070(미국주식 원장잔고확인) result_list 항목 — 실측 결과 stex_nm은 항상 "미국"
    (국가명)만 반환되어 거래소 구분에 못 쓴다. market은 별도로 종목별 stex_tp+stk_cd 조합을
    시도해 성공하는 거래소로 판별한다(_resolve_overseas_market)."""
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


def _make_dispatch(bulk_items, exchange_by_ticker, *, deposit_fc_entra="000000500.00"):
    """실측 동작을 흉내내는 mock — ust21070은 (1) 빈 body 호출 시 bulk_items 전체를,
    (2) stex_tp+stk_cd 조합 호출 시 exchange_by_ticker[stk_cd]와 일치할 때만 성공,
    불일치하면 KiwoomApiError(1903)를 던진다. ust21110은 예수금 응답을 반환한다."""

    async def _dispatch(method, path, *, is_mock, headers, json=None, **kwargs):
        assert path == "/api/us/acnt"
        if headers["api-id"] == "ust21110":
            return _ust21110_response(fc_entra=deposit_fc_entra)
        assert headers["api-id"] == "ust21070"
        if not json:
            return {"result_list": bulk_items}
        stk_cd, stex_tp = json["stk_cd"], json["stex_tp"]
        if exchange_by_ticker.get(stk_cd) == stex_tp:
            return {"result_list": [{"stk_cd": stk_cd}]}
        raise KiwoomApiError("7", "종목 정보가 없습니다")

    return _dispatch


class TestGetOverseasBalance:
    @pytest.mark.asyncio
    async def test_market_resolved_via_per_ticker_exchange_probe(self):
        """ust21070은 stex_tp 단독 필터링이 안 되므로(1517 오류) 전체 조회 후 종목별로
        stex_tp+stk_cd 조합을 시도해 성공하는 거래소로 market을 판별해야 한다 —
        응답의 stex_nm("미국" 고정값)에 의존하면 안 된다."""
        bulk_items = [_ust21070_item(stk_cd="QQQ"), _ust21070_item(stk_cd="DBC")]
        dispatch = _make_dispatch(bulk_items, {"QQQ": "ND", "DBC": "NY"})

        with patch("app.kiwoom.balance.kiwoom_request", side_effect=dispatch):
            result = await get_overseas_balance("token", "1234567890", is_mock=True)

        by_ticker = {p["ticker"]: p for p in result["positions"]}
        assert by_ticker["QQQ"]["market"] == "NASDAQ"
        assert by_ticker["DBC"]["market"] == "NYSE"
        assert result["deposit_usd"] == 500.0

    @pytest.mark.asyncio
    async def test_all_exchange_probes_fail_falls_back_to_nasdaq(self):
        """세 거래소 조합이 전부 실패하는 이례적 상황에서도 예외 없이 NASDAQ으로 폴백하고,
        (프로빙 도중의 기대된 실패와 구분되는) 명시적 경고 로그를 1회 남겨야 한다."""
        bulk_items = [_ust21070_item(stk_cd="QQQ")]
        dispatch = _make_dispatch(bulk_items, {})  # 어떤 조합도 매칭 안 됨 → 전부 KiwoomApiError

        with (
            patch("app.kiwoom.balance.kiwoom_request", side_effect=dispatch),
            patch("app.kiwoom.balance.logger") as mock_logger,
        ):
            result = await get_overseas_balance("token", "1234567890", is_mock=True)

        assert result["positions"][0]["market"] == "NASDAQ"
        mock_logger.warning.assert_called_once_with("kiwoom_overseas_market_unresolved", stk_cd="QQQ")

    @pytest.mark.asyncio
    async def test_single_probe_failure_isolated_from_other_combos_and_tickers(self):
        """한 거래소 조합 프로빙이 KiwoomApiError(1903)가 아닌 다른 예외(예: rate limit
        소진으로 인한 MaxRetriesExceededError)를 던져도, 나머지 조합/다른 종목 결과는
        영향받지 않고 get_overseas_balance() 전체가 실패하지 않아야 한다 — 이 예외가
        전파되면 해외 잔고 전체가 EMPTY_OVERSEAS로 치환되고 기존 Position까지 삭제되는
        상위 버그(asset_service.sync_account)로 이어짐."""
        bulk_items = [_ust21070_item(stk_cd="QQQ"), _ust21070_item(stk_cd="DBC")]

        async def dispatch(method, path, *, is_mock, headers, json=None, **kwargs):
            assert path == "/api/us/acnt"
            if headers["api-id"] == "ust21110":
                return _ust21110_response()
            if not json:
                return {"result_list": bulk_items}
            stk_cd, stex_tp = json["stk_cd"], json["stex_tp"]
            if stk_cd == "QQQ" and stex_tp == "ND":
                raise MaxRetriesExceededError("kiwoom API 속도 제한 초과 (재시도 3회)")
            if stk_cd == "QQQ" and stex_tp == "NA":
                return {"result_list": [{"stk_cd": stk_cd}]}
            if stk_cd == "DBC" and stex_tp == "ND":
                return {"result_list": [{"stk_cd": stk_cd}]}
            raise KiwoomApiError("7", "종목 정보가 없습니다")

        with patch("app.kiwoom.balance.kiwoom_request", side_effect=dispatch):
            result = await get_overseas_balance("token", "1234567890", is_mock=True)

        by_ticker = {p["ticker"]: p for p in result["positions"]}
        assert by_ticker["QQQ"]["market"] == "AMEX"
        assert by_ticker["DBC"]["market"] == "NASDAQ"

    @pytest.mark.asyncio
    async def test_zero_qty_positions_excluded_before_exchange_probe(self):
        """수량 0인 종목은 거래소 판별 호출 자체를 하지 않고 제외해야 한다."""
        bulk_items = [_ust21070_item(stk_cd="QQQ", qty="0")]
        dispatch = _make_dispatch(bulk_items, {"QQQ": "ND"})

        with patch("app.kiwoom.balance.kiwoom_request", side_effect=dispatch):
            result = await get_overseas_balance("token", "1234567890", is_mock=True)

        assert result["positions"] == []
        assert result["total_value_usd"] == 0.0

    @pytest.mark.asyncio
    async def test_parses_position_fields_and_deposit(self):
        bulk_items = [_ust21070_item()]
        dispatch = _make_dispatch(bulk_items, {"QQQ": "ND"})

        with patch("app.kiwoom.balance.kiwoom_request", side_effect=dispatch):
            result = await get_overseas_balance("token", "1234567890", is_mock=True)

        assert len(result["positions"]) == 1
        pos = result["positions"][0]
        assert pos["ticker"] == "QQQ"
        assert pos["market"] == "NASDAQ"
        assert pos["qty"] == 5
        assert pos["avg_price"] == 350.0
        assert pos["current_price"] == 400.0  # 부호 제거된 절대값
        assert pos["pnl_usd"] == 250.0
        assert pos["pnl_pct"] == 14.28

        assert result["total_value_usd"] == 2000.0
        assert result["deposit_usd"] == 500.0

    @pytest.mark.asyncio
    async def test_no_usd_deposit_row_returns_zero(self):
        dispatch = _make_dispatch([], {})

        async def _no_deposit_row(method, path, *, is_mock, headers, json=None, **kwargs):
            if headers["api-id"] == "ust21110":
                return {"result_list": []}
            return await dispatch(method, path, is_mock=is_mock, headers=headers, json=json)

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


def _deposit_response(entr="000000100000"):
    return {"return_code": 0, "entr": entr}


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
        assert result["deposit_krw"] == 100000.0
