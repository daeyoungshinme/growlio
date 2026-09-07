"""토스증권 Open API 잔고·보유종목 조회.

토스는 국내(KR)+미국(US) 보유종목이 `GET /api/v1/holdings` 한 번에 통합되어 오므로
KIS/키움처럼 국내/해외를 분리 호출하지 않는다. 예수금은 holdings에 없어
`GET /api/v1/buying-power`(통화별)를 별도 호출한다.

계좌/자산 계열 호출에는 `X-Tossinvest-Account: {accountSeq}` 헤더가 필요하다 —
accountSeq는 `GET /api/v1/accounts`로 얻으며, 사실상 불변이라 계좌 단위로 캐시한다.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from app.exceptions import ProviderCredentialError
from app.toss.client import TossApiError, toss_request
from app.toss.constants import (
    ACCOUNT_HEADER,
    TOSS_ACCOUNTS_PATH,
    TOSS_ACCTSEQ_CACHE_KEY,
    TOSS_ACCTSEQ_CACHE_TTL,
    TOSS_BUYING_POWER_PATH,
    TOSS_HOLDINGS_PATH,
)

logger = structlog.get_logger()

_BROKERAGE_TYPE = "BROKERAGE"


def _digits(s: str | None) -> str:
    return "".join(c for c in (s or "") if c.isdigit())


def _auth_headers(access_token: str, account_seq: str | int | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {access_token}"}
    if account_seq is not None:
        headers[ACCOUNT_HEADER] = str(account_seq)
    return headers


async def resolve_account_seq(access_token: str, *, account_id: str, account_no: str, cache) -> str:
    """토스 accountSeq를 조회한다 — 캐시 → GET /api/v1/accounts.

    account_no(사용자 입력)와 자릿수가 일치하는 계좌를 우선하고, 없으면 BROKERAGE 계좌가
    정확히 1개일 때만 그것을 사용한다(여러 개면 판별 불가 → ProviderCredentialError).
    """
    cache_key = TOSS_ACCTSEQ_CACHE_KEY.format(account_id=account_id)
    cached = await cache.get(cache_key)
    if cached:
        return cached

    resp = await toss_request("GET", TOSS_ACCOUNTS_PATH, headers=_auth_headers(access_token))
    accounts = resp.get("result") or []
    if not accounts:
        raise ProviderCredentialError("토스 계좌를 찾을 수 없습니다. Open API 신청 상태를 확인하세요.")

    want = _digits(account_no)
    match = next((a for a in accounts if want and _digits(a.get("accountNo")) == want), None)
    if match is None:
        brokerage = [a for a in accounts if a.get("accountType") == _BROKERAGE_TYPE]
        if len(brokerage) == 1:
            match = brokerage[0]
        elif len(brokerage) > 1:
            raise ProviderCredentialError("토스 계좌가 여러 개입니다. 계좌번호를 정확히 입력하세요.")
        else:
            match = accounts[0] if len(accounts) == 1 else None
    if match is None:
        raise ProviderCredentialError("입력한 계좌번호와 일치하는 토스 계좌가 없습니다.")

    account_seq = str(match["accountSeq"])
    await cache.setex(cache_key, TOSS_ACCTSEQ_CACHE_TTL, account_seq)
    return account_seq


def _price_components(price: dict[str, Any] | None) -> dict[str, float]:
    price = price or {}
    return {"krw": float(price.get("krw") or 0), "usd": float(price.get("usd") or 0)}


async def _get_buying_power(access_token: str, account_seq: str, currency: str) -> float:
    """통화별 현금 매수가능금액(예수금). 해당 통화 계좌가 없어 실패하면 0으로 폴백한다."""
    try:
        resp = await toss_request(
            "GET",
            TOSS_BUYING_POWER_PATH,
            headers=_auth_headers(access_token, account_seq),
            params={"currency": currency},
        )
    except TossApiError as e:
        logger.info("toss_buying_power_unavailable", currency=currency, code=e.code)
        return 0.0
    result = resp.get("result") or {}
    return float(result.get("cashBuyingPower") or 0)


async def get_balance(access_token: str, *, account_id: str, account_no: str, cache) -> dict[str, Any]:
    """토스 계좌의 보유종목·평가금액·예수금을 조회한다.

    반환 dict(통화 환산 전 — provider가 usd_krw_rate로 KRW 환산):
      positions: [{ticker, name, market, qty, avg_price, current_price, currency}]
      invested / market_value: {"krw": float, "usd": float}
      deposit_krw / deposit_usd: float
    """
    account_seq = await resolve_account_seq(access_token, account_id=account_id, account_no=account_no, cache=cache)
    headers = _auth_headers(access_token, account_seq)

    holdings_resp, deposit_krw, deposit_usd = await asyncio.gather(
        toss_request("GET", TOSS_HOLDINGS_PATH, headers=headers),
        _get_buying_power(access_token, account_seq, "KRW"),
        _get_buying_power(access_token, account_seq, "USD"),
    )

    overview = holdings_resp.get("result") or {}
    positions: list[dict[str, Any]] = []
    for item in overview.get("items") or []:
        qty = float(item.get("quantity") or 0)
        if qty <= 0:
            continue
        positions.append(
            {
                "ticker": item.get("symbol"),
                "name": item.get("name"),
                # 토스 holdings는 미국 하위 거래소(NASDAQ/NYSE/AMEX)를 구분해 주지 않는다 —
                # "US" 센티널로 두고 provider가 enrich_overseas_positions()로 확정한다.
                "market": "KOSPI" if item.get("marketCountry") == "KR" else "US",
                "qty": int(qty),
                "avg_price": float(item.get("averagePurchasePrice") or 0),
                "current_price": float(item.get("lastPrice") or 0),
                "currency": item.get("currency") or "KRW",
            }
        )

    market_value = _price_components((overview.get("marketValue") or {}).get("amount"))
    invested = _price_components(overview.get("totalPurchaseAmount"))

    return {
        "positions": positions,
        "invested": invested,
        "market_value": market_value,
        "deposit_krw": deposit_krw,
        "deposit_usd": deposit_usd,
    }
