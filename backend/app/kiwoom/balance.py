"""키움증권 REST API 잔고 조회 모듈.

경로 및 응답 필드명: openapi.kiwoom.com/guide/apiguide (kt00018 계좌평가잔고내역요청) 기준.
잔고조회 응답 필드명은 공식 문서 확인 후 수정 필요할 수 있음.
"""

from typing import Any

from app.kiwoom.client import kiwoom_request
from app.kiwoom.constants import API_ID_DOMESTIC_BALANCE


def _auth_headers(access_token: str, api_id: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json;charset=UTF-8",
        "authorization": f"Bearer {access_token}",
        "api-id": api_id,
    }


async def get_domestic_balance(
    access_token: str,
    account_no: str,
    *,
    is_mock: bool,
) -> dict[str, Any]:
    """국내주식 잔고 조회 — 보유종목 + 평가금액 (kt00018).

    반환 구조는 asset_service와 호환 유지.
    응답 필드명은 openapi.kiwoom.com/guide/apiguide kt00018 명세 기준.
    실제 필드명이 다를 경우 아래 파싱 부분만 수정할 것.
    """
    headers = _auth_headers(access_token, API_ID_DOMESTIC_BALANCE)

    data = await kiwoom_request(
        "POST",
        "/api/dostk/acnt",
        is_mock=is_mock,
        headers=headers,
        json={
            "acnt_no": account_no,
            "acnt_prdt_cd": "01",
            "inqr_dvsn_1": "1",  # 1: 잔고
            "inqr_dvsn_2": "0",
        },
    )

    # 키움 잔고조회 응답 파싱 (kt00018)
    # 보유종목 목록: data["acnt_eval_remn_base_amt_list"] 또는 유사 필드
    # 아래 필드명은 공식 문서 기준이며, 실제 응답과 다를 경우 수정 필요
    positions = []
    for item in data.get("acnt_eval_remn_base_amt_list", []):
        qty = int(item.get("hldg_qty", 0))
        if qty <= 0:
            continue
        positions.append(
            {
                "ticker": item.get("stk_cd"),
                "name": item.get("stk_nm"),
                "market": "KOSPI",
                "qty": qty,
                "avg_price": float(item.get("pchs_avg_pric", 0)),
                "current_price": float(item.get("cur_prc", 0)),
                "value_krw": float(item.get("eval_amt", 0)),
                "pnl": float(item.get("eval_pfls_amt", 0)),
                "pnl_pct": float(item.get("eval_pfls_rt", 0)),
                "currency": "KRW",
            }
        )

    return {
        "positions": positions,
        "total_value_krw": float(data.get("tot_eval_amt", 0)),
        "deposit_krw": float(data.get("dnca_tot_amt", 0)),
        "invested_krw": float(data.get("pchs_amt_smtl", 0)),
        "pnl_krw": float(data.get("eval_pfls_smtl_amt", 0)),
    }
