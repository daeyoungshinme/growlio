from app.core.config import settings
from app.kis.client import kis_request
from app.kis.constants import OVERSEAS_QUOTE_EXCD, TR_OVERSEAS_PRICE


async def get_overseas_price(
    app_key: str,
    app_secret: str,
    access_token: str,
    ticker: str,
    market: str,
    *,
    is_mock: bool,
) -> dict[str, float]:
    """해외 주식/ETF 현재가 + USD/KRW 환율 조회."""
    # 시세 EXCD는 주문용 OVRS_EXCG_CD(NASD/NYSE/AMEX)와 다른 3자리 코드(NAS/NYS/AMS)다.
    excd = OVERSEAS_QUOTE_EXCD.get(market.upper(), "NAS")
    headers = {
        "authorization": f"Bearer {access_token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": TR_OVERSEAS_PRICE,
        "custtype": "P",
    }
    data = await kis_request(
        "GET",
        "/uapi/overseas-price/v1/quotations/price",
        is_mock=is_mock,
        headers=headers,
        params={"AUTH": "", "EXCD": excd, "SYMB": ticker},
    )
    output = data.get("output", {})
    return {
        "price_usd": float(output.get("last", 0)),
        "usd_krw_rate": float(output.get("rate", settings.usd_krw_fallback_rate)),
    }
