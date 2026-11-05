import httpx
import structlog

from app.kis.client import kis_request
from app.kis.constants import (
    DOMESTIC_MARKET_DIV,
    DOMESTIC_MARKET_DIV_ETF,
    TR_DOMESTIC_ETF_PRICE,
    TR_DOMESTIC_PRICE,
)

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


def _parse_amount(raw: object, ticker: str, field: str, event_prefix: str) -> float:
    try:
        return float(raw or 0)  # type: ignore[arg-type]
    except (ValueError, TypeError):
        logger.warning(f"{event_prefix}_parse_error", ticker=ticker, field=field, value=raw)
        return 0.0


async def _fetch_dividend_fields(
    app_key: str,
    app_secret: str,
    access_token: str,
    ticker: str,
    *,
    is_mock: bool,
    tr_id: str,
    market_div: str,
    event_prefix: str,
    rate_fields: tuple[str, ...],
    amount_fields: tuple[str, ...],
) -> tuple[float, float]:
    """inquire-price 응답에서 (배당률 %, 주당 배당금)을 읽는다. 조회 불가·오류 응답은 (0, 0).

    필드명이 API 버전에 따라 다를 수 있어 앞쪽 필드부터 값이 있는 것을 쓴다.
    """
    headers = {
        "authorization": f"Bearer {access_token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": tr_id,
        "custtype": "P",
    }
    logger.debug(f"{event_prefix}_request", ticker=ticker, is_mock=is_mock)

    try:
        data = await kis_request(
            "GET",
            "/uapi/domestic-stock/v1/quotations/inquire-price",
            is_mock=is_mock,
            headers=headers,
            params={"FID_COND_MRKT_DIV_CODE": market_div, "FID_INPUT_ISCD": ticker},
        )
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (400, 404):
            logger.debug(f"{event_prefix}_http_error", ticker=ticker, status=e.response.status_code)
            return 0.0, 0.0
        raise

    rt_cd = data.get("rt_cd")
    if rt_cd != "0":
        logger.debug(f"{event_prefix}_api_error", ticker=ticker, rt_cd=rt_cd, msg=data.get("msg1"))
        return 0.0, 0.0

    output = data.get("output", {})
    raw_rate = next((output[f] for f in rate_fields if output.get(f)), None)
    raw_amount = next((output[f] for f in amount_fields if output.get(f)), None)
    logger.info(f"{event_prefix}_raw_output", ticker=ticker, is_mock=is_mock, rate=raw_rate, amount=raw_amount)
    return (
        _parse_amount(raw_rate, ticker, rate_fields[0], event_prefix),
        _parse_amount(raw_amount, ticker, amount_fields[0], event_prefix),
    )


async def get_domestic_dividend_info(
    app_key: str,
    app_secret: str,
    access_token: str,
    ticker: str,
    *,
    is_mock: bool,
) -> dict:
    """국내 주식 배당 정보 조회 (FHKST01010100).

    ETF 분배금은 KIS ETF 시세·FDR 폴백(`dividend/fetcher.py`)이 담당.
    Returns: {"dps": float, "dividend_yield": float} — yield는 decimal (예: 0.0215)
    """
    rate_pct, dps = await _fetch_dividend_fields(
        app_key,
        app_secret,
        access_token,
        ticker,
        is_mock=is_mock,
        tr_id=TR_DOMESTIC_PRICE,
        market_div=DOMESTIC_MARKET_DIV,
        event_prefix="kis_dividend",
        rate_fields=("stck_divi_rate",),
        amount_fields=("per_divi_amt",),
    )
    yield_decimal = rate_pct / 100 if rate_pct > 0 else 0.0
    logger.info("kis_dividend_parsed", ticker=ticker, is_mock=is_mock, dps=dps, dividend_yield=yield_decimal)
    return {"dps": dps, "dividend_yield": yield_decimal}


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
    rate_pct, dps = await _fetch_dividend_fields(
        app_key,
        app_secret,
        access_token,
        ticker,
        is_mock=is_mock,
        tr_id=TR_DOMESTIC_ETF_PRICE,
        market_div=DOMESTIC_MARKET_DIV_ETF,
        event_prefix="kis_etf_dividend",
        rate_fields=("etf_divi_rt", "stck_divi_rate"),
        amount_fields=("etf_divi_amt", "per_divi_amt"),
    )
    yield_decimal = round(rate_pct / 100, 6) if rate_pct > 0 else 0.0
    logger.info("kis_etf_dividend_parsed", ticker=ticker, is_mock=is_mock, dps=dps, dividend_yield=yield_decimal)
    return {"dps": dps, "dividend_yield": yield_decimal}
