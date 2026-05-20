from typing import Any

from app.kis.client import kis_request
from app.kis.constants import (
    OVERSEAS_MARKET_CODES,
    TR_DOMESTIC_BALANCE_MOCK,
    TR_DOMESTIC_BALANCE_REAL,
    TR_OVERSEAS_BALANCE_MOCK,
    TR_OVERSEAS_BALANCE_REAL,
)


def _auth_headers(app_key: str, app_secret: str, access_token: str, tr_id: str) -> dict[str, str]:
    return {
        "authorization": f"Bearer {access_token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": tr_id,
        "custtype": "P",
        "Content-Type": "application/json; charset=utf-8",
    }


async def get_domestic_balance(
    app_key: str,
    app_secret: str,
    access_token: str,
    account_no: str,
    *,
    is_mock: bool,
) -> dict[str, Any]:
    """국내주식 잔고 조회 — 보유종목 + 평가금액."""
    cano, acnt_prdt_cd = account_no[:8], account_no[8:].lstrip("-") or "01"
    tr_id = TR_DOMESTIC_BALANCE_MOCK if is_mock else TR_DOMESTIC_BALANCE_REAL
    headers = _auth_headers(app_key, app_secret, access_token, tr_id)

    data = await kis_request(
        "GET",
        "/uapi/domestic-stock/v1/trading/inquire-balance",
        is_mock=is_mock,
        headers=headers,
        params={
            "CANO": cano,
            "ACNT_PRDT_CD": acnt_prdt_cd,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "N",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "01",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        },
    )

    positions = []
    for item in data.get("output1", []):
        qty = int(item.get("hldg_qty", 0))
        if qty <= 0:
            continue
        positions.append(
            {
                "ticker": item.get("pdno"),
                "name": item.get("prdt_name"),
                "market": "KOSPI",
                "qty": qty,
                "avg_price": float(item.get("pchs_avg_pric", 0)),
                "current_price": float(item.get("prpr", 0)),
                "value_krw": float(item.get("evlu_amt", 0)),
                "pnl": float(item.get("evlu_pfls_amt", 0)),
                "pnl_pct": float(item.get("evlu_pfls_rt", 0)),
                "currency": "KRW",
            }
        )

    summary = data.get("output2", [{}])[0] if data.get("output2") else {}
    return {
        "positions": positions,
        "total_value_krw": float(summary.get("tot_evlu_amt", 0)),
        "deposit_krw": float(summary.get("dnca_tot_amt", 0)),
        "invested_krw": float(summary.get("pchs_amt_smtl_amt", 0)),
        "pnl_krw": float(summary.get("evlu_pfls_smtl_amt", 0)),
    }


async def get_overseas_balance(
    app_key: str,
    app_secret: str,
    access_token: str,
    account_no: str,
    *,
    is_mock: bool,
) -> dict[str, Any]:
    """해외주식 잔고 조회 — NYSE/NASDAQ/AMEX 전 거래소 합산."""
    cano, acnt_prdt_cd = account_no[:8], account_no[8:].lstrip("-") or "01"
    tr_id = TR_OVERSEAS_BALANCE_MOCK if is_mock else TR_OVERSEAS_BALANCE_REAL
    headers = _auth_headers(app_key, app_secret, access_token, tr_id)

    all_positions: list[dict] = []
    deposit_usd = 0.0

    # KIS 해외잔고 API는 거래소별로 각각 호출해야 한다.
    # "NASD"만 조회하면 NYSE·AMEX 보유 종목이 누락됨.
    for market_name, exchange_code in OVERSEAS_MARKET_CODES.items():
        try:
            data = await kis_request(
                "GET",
                "/uapi/overseas-stock/v1/trading/inquire-balance",
                is_mock=is_mock,
                headers=headers,
                params={
                    "CANO": cano,
                    "ACNT_PRDT_CD": acnt_prdt_cd,
                    "OVRS_EXCG_CD": exchange_code,
                    "TR_CRCY_CD": "USD",
                    "CTX_AREA_FK200": "",
                    "CTX_AREA_NK200": "",
                },
            )
        except Exception:
            continue  # 한 거래소 실패해도 나머지 거래소 조회 계속

        for item in data.get("output1", []):
            qty = int(item.get("ovrs_cblc_qty", 0))
            if qty <= 0:
                continue
            all_positions.append(
                {
                    "ticker": item.get("ovrs_pdno"),
                    "name": item.get("ovrs_item_name"),
                    "market": market_name,
                    "qty": qty,
                    "avg_price": float(item.get("pchs_avg_pric", 0)),
                    "current_price": float(item.get("now_pric2", 0)),
                    "value_usd": float(item.get("ovrs_stck_evlu_amt", 0)),
                    "pnl_usd": float(item.get("frcr_evlu_pfls_amt", 0)),
                    "pnl_pct": float(item.get("evlu_pfls_rt", 0)),
                    "currency": "USD",
                }
            )

        # 외화예수금은 거래소별 응답에 동일하게 포함되므로 첫 번째 값만 사용
        if deposit_usd == 0.0:
            summary = data.get("output2", {}) or {}
            deposit_usd = float(summary.get("frcr_dncl_amt_2", 0))

    return {
        "positions": all_positions,
        "total_value_usd": sum(p["value_usd"] for p in all_positions),
        "deposit_usd": deposit_usd,
    }
