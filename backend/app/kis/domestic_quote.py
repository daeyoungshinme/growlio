import httpx

from app.kis.client import kis_request
from app.kis.constants import DOMESTIC_MARKET_DIV, DOMESTIC_MARKET_DIV_ETF, TR_DOMESTIC_ETF_PRICE, TR_DOMESTIC_PRICE

import structlog

logger = structlog.get_logger()

async def get_domestic_price(
    app_key: str,
    app_secret: str,
    access_token: str,
    ticker: str,
    *,
    is_mock: bool,
) -> float:
    """국내 주식/ETF 현재가 조회."""
    headers = {
        "authorization": f"Bearer {access_token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": TR_DOMESTIC_PRICE,
        "custtype": "P",
    }
    data = await kis_request(
        "GET",
        "/uapi/domestic-stock/v1/quotations/inquire-price",
        is_mock=is_mock,
        headers=headers,
        params={"FID_COND_MRKT_DIV_CODE": DOMESTIC_MARKET_DIV, "FID_INPUT_ISCD": ticker},
    )
    output = data.get("output", {})
    return float(output.get("stck_prpr", 0))


async def get_domestic_dividend_info(
    app_key: str,
    app_secret: str,
    access_token: str,
    ticker: str,
    *,
    is_mock: bool,
) -> dict:
    """국내 주식 배당 정보 조회.

    inquire-price(FHKST01010100) → stck_divi_rate, per_divi_amt 파싱.
    ETF 분배금은 pykrx(_sync_pykrx_etf_dividend_info)가 담당.
    Returns: {"dps": float, "dividend_yield": float} — yield는 decimal (예: 0.0215)
    """
    headers = {
        "authorization": f"Bearer {access_token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": TR_DOMESTIC_PRICE,  # FHKST01010100
        "custtype": "P",
    }

    logger.debug("kis_dividend_request", ticker=ticker, is_mock=is_mock)

    try:
        data = await kis_request(
            "GET",
            "/uapi/domestic-stock/v1/quotations/inquire-price",
            is_mock=is_mock,
            headers=headers,
            params={"FID_COND_MRKT_DIV_CODE": DOMESTIC_MARKET_DIV, "FID_INPUT_ISCD": ticker},
        )
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (400, 404):
            logger.debug("kis_dividend_stock_http_error", ticker=ticker, status=e.response.status_code)
            return {"dps": 0.0, "dividend_yield": 0.0}
        raise

    rt_cd = data.get("rt_cd")
    output = data.get("output", {})

    if rt_cd != "0":
        logger.debug("kis_dividend_stock_api_error", ticker=ticker, rt_cd=rt_cd, msg=data.get("msg1"))
        return {"dps": 0.0, "dividend_yield": 0.0}

    raw_divi_rate = output.get("stck_divi_rate")
    raw_divi_amt = output.get("per_divi_amt")

    logger.info("kis_dividend_raw_output", ticker=ticker, is_mock=is_mock, stck_divi_rate=raw_divi_rate, per_divi_amt=raw_divi_amt)

    try:
        stck_divi_rate_pct = float(raw_divi_rate or 0)
    except (ValueError, TypeError):
        logger.warning("kis_dividend_parse_error", ticker=ticker, field="stck_divi_rate", value=raw_divi_rate)
        stck_divi_rate_pct = 0.0

    try:
        per_divi_amt = float(raw_divi_amt or 0)
    except (ValueError, TypeError):
        logger.warning("kis_dividend_parse_error", ticker=ticker, field="per_divi_amt", value=raw_divi_amt)
        per_divi_amt = 0.0

    yield_decimal = stck_divi_rate_pct / 100 if stck_divi_rate_pct > 0 else 0.0

    logger.info("kis_dividend_parsed", ticker=ticker, is_mock=is_mock, dps=per_divi_amt, dividend_yield=yield_decimal)
    return {"dps": per_divi_amt, "dividend_yield": yield_decimal}


async def get_domestic_etf_dividend_info(
    app_key: str,
    app_secret: str,
    access_token: str,
    ticker: str,
    *,
    is_mock: bool,
) -> dict:
    """국내 ETF/ETN 분배율 조회 (FHPET01010000).

    Returns: {"dps": float, "dividend_yield": float} — yield는 decimal (예: 0.0215)
    """
    headers = {
        "authorization": f"Bearer {access_token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": TR_DOMESTIC_ETF_PRICE,
        "custtype": "P",
    }

    logger.debug("kis_etf_dividend_request", ticker=ticker, is_mock=is_mock)

    try:
        data = await kis_request(
            "GET",
            "/uapi/domestic-stock/v1/quotations/inquire-price",
            is_mock=is_mock,
            headers=headers,
            params={"FID_COND_MRKT_DIV_CODE": DOMESTIC_MARKET_DIV_ETF, "FID_INPUT_ISCD": ticker},
        )
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (400, 404):
            logger.debug("kis_etf_dividend_http_error", ticker=ticker, status=e.response.status_code)
            return {"dps": 0.0, "dividend_yield": 0.0}
        raise

    rt_cd = data.get("rt_cd")
    output = data.get("output", {})

    if rt_cd != "0":
        logger.debug("kis_etf_dividend_api_error", ticker=ticker, rt_cd=rt_cd, msg=data.get("msg1"))
        return {"dps": 0.0, "dividend_yield": 0.0}

    # FHPET01010000 응답 필드: etf_divi_rt(분배율%), etf_divi_amt(분배금)
    # 필드명이 API 버전에 따라 다를 수 있어 stck_divi_rate/per_divi_amt로도 fallback
    raw_divi_rt = output.get("etf_divi_rt") or output.get("stck_divi_rate")
    raw_divi_amt = output.get("etf_divi_amt") or output.get("per_divi_amt")

    logger.info("kis_etf_dividend_raw_output", ticker=ticker, is_mock=is_mock, etf_divi_rt=raw_divi_rt, etf_divi_amt=raw_divi_amt)

    try:
        divi_rt_pct = float(raw_divi_rt or 0)
    except (ValueError, TypeError):
        logger.warning("kis_etf_dividend_parse_error", ticker=ticker, field="etf_divi_rt", value=raw_divi_rt)
        divi_rt_pct = 0.0

    try:
        divi_amt = float(raw_divi_amt or 0)
    except (ValueError, TypeError):
        logger.warning("kis_etf_dividend_parse_error", ticker=ticker, field="etf_divi_amt", value=raw_divi_amt)
        divi_amt = 0.0

    yield_decimal = round(divi_rt_pct / 100, 6) if divi_rt_pct > 0 else 0.0

    logger.info("kis_etf_dividend_parsed", ticker=ticker, is_mock=is_mock, dps=divi_amt, dividend_yield=yield_decimal)
    return {"dps": divi_amt, "dividend_yield": yield_decimal}

