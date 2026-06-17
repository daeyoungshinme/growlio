"""키움증권 REST API 매수/매도 주문 실행 모듈.

경로 및 파라미터: openapi.kiwoom.com/guide/apiguide (kt10000/kt10001) 기준.
"""

from typing import Any

from app.kiwoom.client import kiwoom_request
from app.kiwoom.constants import (
    API_ID_DOMESTIC_BUY,
    API_ID_DOMESTIC_SELL,
)


def _auth_headers(access_token: str, api_id: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json;charset=UTF-8",
        "authorization": f"Bearer {access_token}",
        "api-id": api_id,
    }


async def place_domestic_order(
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
    """국내주식 매수·매도 주문 (kt10000/kt10001).

    side: "BUY" | "SELL"
    키움 trde_tp: "0"=보통(지정가), "3"=시장가
    """
    api_id = API_ID_DOMESTIC_BUY if side == "BUY" else API_ID_DOMESTIC_SELL
    headers = _auth_headers(access_token, api_id)

    if order_type == "LIMIT" and limit_price is not None:
        trde_tp = "0"  # 보통(지정가)
        ord_uv = str(int(limit_price))
    else:
        trde_tp = "3"  # 시장가
        ord_uv = "0"

    body: dict[str, Any] = {
        "acnt_no": account_no,
        "dmst_stex_tp": "KRX",  # 거래소: KRX / NXT / SOR
        "stk_cd": ticker,  # 종목코드
        "ord_qty": str(quantity),  # 주문수량
        "ord_uv": ord_uv,
        "trde_tp": trde_tp,
    }

    data = await kiwoom_request(
        "POST",
        "/api/dostk/ordr",
        is_mock=is_mock,
        headers=headers,
        json=body,
    )

    if str(data.get("return_code", "0")) != "0":
        raise RuntimeError(data.get("return_msg") or "키움 국내주식 주문 실패")

    return {"order_no": data.get("ord_no"), "raw": data}
