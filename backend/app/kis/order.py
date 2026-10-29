"""KIS OpenAPI 매수/매도 주문 실행 모듈."""

from typing import Any

from app.exceptions import BrokerOrderRejectedError
from app.kis.client import auth_headers, kis_request, split_account_no
from app.kis.constants import (
    OVERSEAS_MARKET_CODES,
    OVERSEAS_MARKETS,
    TR_DOMESTIC_BUY_MOCK,
    TR_DOMESTIC_BUY_REAL,
    TR_DOMESTIC_CANCEL_MOCK,
    TR_DOMESTIC_CANCEL_REAL,
    TR_DOMESTIC_SELL_MOCK,
    TR_DOMESTIC_SELL_REAL,
    TR_OVERSEAS_BUY_MOCK,
    TR_OVERSEAS_BUY_REAL,
    TR_OVERSEAS_CANCEL_MOCK,
    TR_OVERSEAS_CANCEL_REAL,
    TR_OVERSEAS_SELL_MOCK,
    TR_OVERSEAS_SELL_REAL,
)


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

    cano, acnt_prdt_cd = split_account_no(account_no)
    headers = auth_headers(app_key, app_secret, access_token, tr_id)

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
        retry_on_request_error=False,
        retry_transient_rt_cd=False,
    )

    if data.get("rt_cd") != "0":
        raise BrokerOrderRejectedError(data.get("msg1") or "국내주식 주문 실패")

    output = data.get("output") or {}
    # 조직번호는 국내 정정·취소 요청의 필수값이라 함께 돌려준다(plans/89)
    return {"order_no": output.get("ODNO"), "order_org_no": output.get("KRX_FWDG_ORD_ORGNO"), "raw": output}


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
    cano, acnt_prdt_cd = split_account_no(account_no)
    headers = auth_headers(app_key, app_secret, access_token, tr_id)

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
        retry_on_request_error=False,
        retry_transient_rt_cd=False,
    )

    if data.get("rt_cd") != "0":
        raise BrokerOrderRejectedError(data.get("msg1") or "해외주식 주문 실패")

    output = data.get("output") or {}
    return {"order_no": output.get("ODNO"), "raw": output}


async def cancel_domestic_order(
    app_key: str,
    app_secret: str,
    access_token: str,
    account_no: str,
    *,
    order_org_no: str,
    order_no: str,
    is_mock: bool,
) -> dict[str, Any]:
    """국내주식 미체결 잔량 전부 취소(QTY_ALL_ORD_YN="Y"). 이미 체결된 주문은 증권사가 거부한다."""
    tr_id = TR_DOMESTIC_CANCEL_MOCK if is_mock else TR_DOMESTIC_CANCEL_REAL
    cano, acnt_prdt_cd = split_account_no(account_no)
    headers = auth_headers(app_key, app_secret, access_token, tr_id)

    body: dict[str, Any] = {
        "CANO": cano,
        "ACNT_PRDT_CD": acnt_prdt_cd,
        "KRX_FWDG_ORD_ORGNO": order_org_no,
        "ORGN_ODNO": order_no,
        "ORD_DVSN": "00",
        "RVSE_CNCL_DVSN_CD": "02",  # 02=취소
        "ORD_QTY": "0",
        "ORD_UNPR": "0",
        "QTY_ALL_ORD_YN": "Y",  # 잔량 전부
    }

    data = await kis_request(
        "POST",
        "/uapi/domestic-stock/v1/trading/order-rvsecncl",
        is_mock=is_mock,
        headers=headers,
        json=body,
        retry_on_request_error=False,
        retry_transient_rt_cd=False,
    )

    if data.get("rt_cd") != "0":
        raise BrokerOrderRejectedError(data.get("msg1") or "국내주식 주문 취소 실패")

    output = data.get("output") or {}
    return {"order_no": output.get("ODNO"), "raw": output}


async def cancel_overseas_order(
    app_key: str,
    app_secret: str,
    access_token: str,
    account_no: str,
    *,
    ticker: str,
    market: str,
    order_no: str,
    quantity: int,
    is_mock: bool,
) -> dict[str, Any]:
    """해외주식 미체결 주문 취소. market은 주문 때 쓴(KIS 보정된) 거래소여야 한다."""
    tr_id = TR_OVERSEAS_CANCEL_MOCK if is_mock else TR_OVERSEAS_CANCEL_REAL
    exchange_cd = OVERSEAS_MARKET_CODES.get(market.upper(), "NASD")
    cano, acnt_prdt_cd = split_account_no(account_no)
    headers = auth_headers(app_key, app_secret, access_token, tr_id)

    body: dict[str, Any] = {
        "CANO": cano,
        "ACNT_PRDT_CD": acnt_prdt_cd,
        "OVRS_EXCG_CD": exchange_cd,
        "PDNO": ticker,
        "ORGN_ODNO": order_no,
        "RVSE_CNCL_DVSN_CD": "02",  # 02=취소
        "ORD_QTY": str(quantity),
        "OVRS_ORD_UNPR": "0",
        "ORD_SVR_DVSN_CD": "0",
    }

    data = await kis_request(
        "POST",
        "/uapi/overseas-stock/v1/trading/order-rvsecncl",
        is_mock=is_mock,
        headers=headers,
        json=body,
        retry_on_request_error=False,
        retry_transient_rt_cd=False,
    )

    if data.get("rt_cd") != "0":
        raise BrokerOrderRejectedError(data.get("msg1") or "해외주식 주문 취소 실패")

    output = data.get("output") or {}
    return {"order_no": output.get("ODNO"), "raw": output}
