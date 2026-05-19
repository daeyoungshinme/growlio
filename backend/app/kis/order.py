"""KIS OpenAPI 매수/매도 주문 실행 모듈."""
from typing import Any

from app.kis.client import kis_request
from app.kis.constants import (
    OVERSEAS_MARKET_CODES,
    TR_DOMESTIC_BUY_MOCK,
    TR_DOMESTIC_BUY_REAL,
    TR_DOMESTIC_SELL_MOCK,
    TR_DOMESTIC_SELL_REAL,
    TR_OVERSEAS_BUY_MOCK,
    TR_OVERSEAS_BUY_REAL,
    TR_OVERSEAS_SELL_MOCK,
    TR_OVERSEAS_SELL_REAL,
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


def _split_account_no(account_no: str) -> tuple[str, str]:
    """계좌번호를 CANO(8자리)와 ACNT_PRDT_CD로 분리."""
    return account_no[:8], account_no[8:].lstrip("-") or "01"


OVERSEAS_MARKETS = set(OVERSEAS_MARKET_CODES.keys())  # {"NYSE", "NASDAQ", "AMEX"}


def is_overseas_market(market: str) -> bool:
    return market.upper() in OVERSEAS_MARKETS


async def place_domestic_order(
    app_key: str,
    app_secret: str,
    access_token: str,
    account_no: str,
    *,
    side: str,
    ticker: str,
    quantity: int,
    is_mock: bool,
) -> dict[str, Any]:
    """국내주식/ETF 시장가 매수·매도 주문."""
    if side == "BUY":
        tr_id = TR_DOMESTIC_BUY_MOCK if is_mock else TR_DOMESTIC_BUY_REAL
    else:
        tr_id = TR_DOMESTIC_SELL_MOCK if is_mock else TR_DOMESTIC_SELL_REAL

    cano, acnt_prdt_cd = _split_account_no(account_no)
    headers = _auth_headers(app_key, app_secret, access_token, tr_id)

    body: dict[str, Any] = {
        "CANO": cano,
        "ACNT_PRDT_CD": acnt_prdt_cd,
        "PDNO": ticker,
        "ORD_DVSN": "00",       # 시장가
        "ORD_QTY": str(quantity),
        "ORD_UNPR": "0",
    }
    if side == "SELL":
        body["SLL_TYPE"] = "01"

    data = await kis_request(
        "POST",
        "/uapi/domestic-stock/v1/trading/order-cash",
        is_mock=is_mock,
        headers=headers,
        json=body,
    )

    if data.get("rt_cd") != "0":
        raise RuntimeError(data.get("msg1") or "국내주식 주문 실패")

    output = data.get("output") or {}
    return {"order_no": output.get("ODNO"), "raw": output}


async def place_overseas_order(
    app_key: str,
    app_secret: str,
    access_token: str,
    account_no: str,
    *,
    side: str,
    ticker: str,
    market: str,
    quantity: int,
    is_mock: bool,
) -> dict[str, Any]:
    """해외주식 시장가 매수·매도 주문."""
    if side == "BUY":
        tr_id = TR_OVERSEAS_BUY_MOCK if is_mock else TR_OVERSEAS_BUY_REAL
    else:
        tr_id = TR_OVERSEAS_SELL_MOCK if is_mock else TR_OVERSEAS_SELL_REAL

    exchange_cd = OVERSEAS_MARKET_CODES.get(market.upper(), "NASD")
    cano, acnt_prdt_cd = _split_account_no(account_no)
    headers = _auth_headers(app_key, app_secret, access_token, tr_id)

    body: dict[str, Any] = {
        "CANO": cano,
        "ACNT_PRDT_CD": acnt_prdt_cd,
        "OVRS_EXCG_CD": exchange_cd,
        "PDNO": ticker,
        "ORD_DVSN": "00",
        "ORD_QTY": str(quantity),
        "OVRS_ORD_UNPR": "0",
        "ORD_SVR_DVSN_CD": "0",
    }
    if side == "SELL":
        body["SLL_TYPE"] = "00"

    data = await kis_request(
        "POST",
        "/uapi/overseas-stock/v1/trading/order",
        is_mock=is_mock,
        headers=headers,
        json=body,
    )

    if data.get("rt_cd") != "0":
        raise RuntimeError(data.get("msg1") or "해외주식 주문 실패")

    output = data.get("output") or {}
    return {"order_no": output.get("ODNO"), "raw": output}
