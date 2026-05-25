"""KIS OpenAPI 매수/매도 주문 실행 모듈."""
from typing import Any

from app.kis.client import kis_request
from app.kis.constants import (
    OVERSEAS_MARKET_CODES,
    OVERSEAS_MARKETS,
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
    order_type: str = "MARKET",
    limit_price: float | None = None,
) -> dict[str, Any]:
    """국내주식/ETF 매수·매도 주문.

    KIS OpenAPI 스펙: ORD_DVSN "00"=지정가, "01"=시장가.
    """
    if side == "BUY":
        tr_id = TR_DOMESTIC_BUY_MOCK if is_mock else TR_DOMESTIC_BUY_REAL
    else:
        tr_id = TR_DOMESTIC_SELL_MOCK if is_mock else TR_DOMESTIC_SELL_REAL

    cano, acnt_prdt_cd = _split_account_no(account_no)
    headers = _auth_headers(app_key, app_secret, access_token, tr_id)

    if order_type == "LIMIT" and limit_price is not None:
        ord_dvsn = "00"  # 지정가
        ord_unpr = str(int(limit_price))
    else:
        ord_dvsn = "01"  # 시장가
        ord_unpr = "0"

    body: dict[str, Any] = {
        "CANO": cano,
        "ACNT_PRDT_CD": acnt_prdt_cd,
        "PDNO": ticker,
        "ORD_DVSN": ord_dvsn,
        "ORD_QTY": str(quantity),
        "ORD_UNPR": ord_unpr,
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
    order_type: str = "MARKET",
    limit_price: float | None = None,
) -> dict[str, Any]:
    """해외주식 매수·매도 주문.

    해외 시장가(ORD_DVSN="00", price="0")는 mock 모드에서만 안정 동작.
    실계좌 시장가 코드는 거래소별로 상이하므로 limit_price 사용 권장.
    """
    if side == "BUY":
        tr_id = TR_OVERSEAS_BUY_MOCK if is_mock else TR_OVERSEAS_BUY_REAL
    else:
        tr_id = TR_OVERSEAS_SELL_MOCK if is_mock else TR_OVERSEAS_SELL_REAL

    exchange_cd = OVERSEAS_MARKET_CODES.get(market.upper(), "NASD")
    cano, acnt_prdt_cd = _split_account_no(account_no)
    headers = _auth_headers(app_key, app_secret, access_token, tr_id)

    if order_type == "LIMIT" and limit_price is not None:
        ord_dvsn = "00"  # 지정가 (해외 KIS: "00"=지정가)
        ovrs_ord_unpr = f"{limit_price:.2f}"
    else:
        ord_dvsn = "00"  # 해외 시장가는 거래소별 코드가 달라 mock 호환 "00" 유지
        ovrs_ord_unpr = "0"

    body: dict[str, Any] = {
        "CANO": cano,
        "ACNT_PRDT_CD": acnt_prdt_cd,
        "OVRS_EXCG_CD": exchange_cd,
        "PDNO": ticker,
        "ORD_DVSN": ord_dvsn,
        "ORD_QTY": str(quantity),
        "OVRS_ORD_UNPR": ovrs_ord_unpr,
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
