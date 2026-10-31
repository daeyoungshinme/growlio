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
    TR_OVERSEAS_UNFILLED_REAL,
)

_UNFILLED_MAX_PAGES = 5  # 당일 미체결 목록 연속조회 상한 — 넘으면 확인 실패로 본다(0을 돌려주면 "이미 체결"로 오판)
_TR_CONT_MORE = {"F", "M"}  # 응답 헤더 tr_cont: F/M=다음 페이지 있음, D/E=마지막 (balance.py와 같은 규칙)


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


async def get_overseas_unfilled_qty(
    app_key: str,
    app_secret: str,
    access_token: str,
    account_no: str,
    *,
    market: str,
    order_no: str,
    is_mock: bool,
) -> int | None:
    """해외주식 미체결 잔량(TTTS3018R). 미체결 목록에 없으면 0, 모의투자(TR 미지원)면 None.

    해외 취소 TR은 국내와 달리 "잔량 전부" 플래그가 없어 수량을 직접 보내야 한다 — 부분 체결된 주문에
    원주문수량을 보내면 거부될 수 있어 취소 직전에 남은 수량을 확인한다(plans/100 B).
    """
    if is_mock:
        return None
    exchange_cd = OVERSEAS_MARKET_CODES.get(market.upper(), "NASD")
    cano, acnt_prdt_cd = split_account_no(account_no)
    headers = auth_headers(app_key, app_secret, access_token, TR_OVERSEAS_UNFILLED_REAL)
    target = order_no.lstrip("0")

    # 다음 페이지 여부는 응답 헤더 tr_cont로 판정한다 — 본문 연속키는 마지막 페이지에도 채워져 올 수 있다
    fk200 = nk200 = ""
    for page in range(_UNFILLED_MAX_PAGES):
        resp_headers: dict[str, str] = {}
        data = await kis_request(
            "GET",
            "/uapi/overseas-stock/v1/trading/inquire-nccs",
            is_mock=False,
            headers={**headers, "tr_cont": "N"} if page > 0 else headers,
            params={
                "CANO": cano,
                "ACNT_PRDT_CD": acnt_prdt_cd,
                "OVRS_EXCG_CD": exchange_cd,
                "SORT_SQN": "DS",
                "CTX_AREA_FK200": fk200,
                "CTX_AREA_NK200": nk200,
            },
            response_headers=resp_headers,
        )
        for row in data.get("output") or []:
            if str(row.get("odno") or "").lstrip("0") == target:
                return int(float(row.get("nccs_qty") or 0))
        if resp_headers.get("tr_cont") not in _TR_CONT_MORE:
            return 0
        prev = (fk200, nk200)
        fk200 = str(data.get("ctx_area_fk200") or "").strip()
        nk200 = str(data.get("ctx_area_nk200") or "").strip()
        if not nk200 or (fk200, nk200) == prev:
            break
    # 목록을 끝까지 보지 못했다 — 0(이미 체결)으로 단정하지 않고 취소 실패로 남겨 재시도·증권사 앱 확인을 유도한다
    raise BrokerOrderRejectedError("미체결 목록을 끝까지 확인하지 못했습니다. 증권사 앱에서 주문 상태를 확인하세요.")
