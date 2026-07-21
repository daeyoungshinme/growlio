"""키움증권 REST API 잔고 조회 모듈.

국내(kt00018/kt00001, /api/dostk/acnt): 실계좌 실측 기준(2026-07, 커뮤니티 MCP 서버
ChunSam/kiwoom-mcp-server 교차검증)으로 요청/응답 필드명을 확정. acnt_no/acnt_prdt_cd는
요청 body에 받지 않는다 — app_key/app_secret 자체가 계좌 단위 자격증명이라 호출 계좌가 이미
특정된다. 예수금은 kt00018에 포함되지 않아 kt00001(예수금상세현황요청)을 별도 호출해 합산한다.

해외(ust21070/ust21110, /api/us/acnt): openapi.kiwoom.com 공식 가이드(미국주식>계좌)로 확정.
국내와 경로 자체가 다르다.
"""

import asyncio
from typing import Any

import structlog

from app.kiwoom.client import KiwoomApiError, kiwoom_request
from app.kiwoom.constants import (
    API_ID_DOMESTIC_BALANCE,
    API_ID_DOMESTIC_DEPOSIT,
    API_ID_OVERSEAS_BALANCE,
    API_ID_OVERSEAS_DEPOSIT,
)

logger = structlog.get_logger()

_OVERSEAS_ACCOUNT_PATH = "/api/us/acnt"
# ust21070의 stex_tp/stk_cd는 실측 결과 "둘 다 비움" 또는 "둘 다 지정"만 허용된다 —
# 하나만 지정하면 1517(파라미터 누락) 오류, 지정한 거래소가 해당 종목의 실제 상장
# 거래소가 아니면 1903("종목 정보가 없습니다") 오류가 난다. 즉 "거래소별 필터 조회"
# 자체가 안 되고, stex_nm(응답 거래소명)도 실측 결과 항상 "미국"만 반환해 거래소
# 구분에 못 쓴다. 그래서 (1) 먼저 비운 채로 호출해 보유종목 전체를 얻고, (2) 종목별로
# ND/NY/NA를 각각 stk_cd와 함께 넣어 어느 조합이 성공하는지로 실제 상장 거래소를 판별한다.
_STEX_TP_MARKETS: dict[str, str] = {"ND": "NASDAQ", "NY": "NYSE", "NA": "AMEX"}


def _auth_headers(access_token: str, api_id: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json;charset=UTF-8",
        "authorization": f"Bearer {access_token}",
        "api-id": api_id,
    }


def _parse_num(raw: Any) -> float:
    """키움 숫자 필드는 0-padding("000061300")·부호 접두("+61300"/"-00013000")·쉼표
    천단위 구분("20,190")으로 응답되며, 드물게 부호가 중복("--23722054")될 수 있다."""
    if raw is None:
        return 0.0
    text = str(raw).strip().replace(",", "")
    if not text:
        return 0.0
    i = 0
    sign = ""
    while i < len(text) and text[i] in "+-":
        sign = text[i]
        i += 1
    try:
        return float(sign + text[i:]) if text[i:] else 0.0
    except ValueError:
        return 0.0


def _parse_price(raw: Any) -> float:
    """가격류 필드는 전일 대비 등락 부호가 값 자체에 붙어 올 수 있어 절대값을 취한다."""
    return abs(_parse_num(raw))


def _strip_ticker_prefix(stk_cd: str) -> str:
    """국내 종목코드가 'A005930'처럼 거래소 접두 A가 붙어 올 수 있어 제거한다."""
    if len(stk_cd) == 7 and stk_cd[0] == "A" and stk_cd[1:].isdigit():
        return stk_cd[1:]
    return stk_cd


async def _get_deposit_krw(access_token: str, *, is_mock: bool) -> float:
    """예수금상세현황요청 (kt00001) — 국내 현금 예수금(entr)."""
    headers = _auth_headers(access_token, API_ID_DOMESTIC_DEPOSIT)
    data = await kiwoom_request(
        "POST",
        "/api/dostk/acnt",
        is_mock=is_mock,
        headers=headers,
        json={"qry_tp": "3"},  # 3: 추정조회
    )
    return _parse_num(data.get("entr"))


async def get_domestic_balance(
    access_token: str,
    account_no: str,
    *,
    is_mock: bool,
) -> dict[str, Any]:
    """국내주식 잔고 조회 — 보유종목·평가금액(kt00018) + 예수금(kt00001) 병렬 조회.

    account_no는 사용하지 않는다 — 호출 인터페이스 일관성을 위해서만 유지.
    """
    headers = _auth_headers(access_token, API_ID_DOMESTIC_BALANCE)

    data, deposit_krw = await asyncio.gather(
        kiwoom_request(
            "POST",
            "/api/dostk/acnt",
            is_mock=is_mock,
            headers=headers,
            json={"qry_tp": "1", "dmst_stex_tp": "KRX"},  # qry_tp 1: 합산
        ),
        _get_deposit_krw(access_token, is_mock=is_mock),
    )

    positions = []
    for item in data.get("acnt_evlt_remn_indv_tot", []):
        qty = int(_parse_num(item.get("rmnd_qty")))
        if qty <= 0:
            continue
        positions.append(
            {
                "ticker": _strip_ticker_prefix(item.get("stk_cd", "")),
                "name": item.get("stk_nm"),
                "market": "KOSPI",
                "qty": qty,
                "avg_price": _parse_price(item.get("pur_pric")),
                "current_price": _parse_price(item.get("cur_prc")),
                "value_krw": _parse_num(item.get("evlt_amt")),
                "pnl": _parse_num(item.get("evltv_prft")),
                "pnl_pct": _parse_num(item.get("prft_rt")),
                "currency": "KRW",
            }
        )

    return {
        "positions": positions,
        "total_value_krw": _parse_num(data.get("tot_evlt_amt")),
        "deposit_krw": deposit_krw,
        "invested_krw": _parse_num(data.get("tot_pur_amt")),
        "pnl_krw": _parse_num(data.get("tot_evlt_pl")),
    }


async def _fetch_overseas_all(access_token: str, *, is_mock: bool) -> list[dict[str, Any]]:
    """ust21070을 stex_tp/stk_cd 없이 호출 — 보유종목 전체(수량·가격 포함)를 한 번에 받는다.
    이 응답의 stex_nm은 항상 "미국"만 반환되어 거래소 구분에는 쓸 수 없다."""
    headers = _auth_headers(access_token, API_ID_OVERSEAS_BALANCE)
    data = await kiwoom_request(
        "POST",
        _OVERSEAS_ACCOUNT_PATH,
        is_mock=is_mock,
        headers=headers,
        json={},
    )
    return data.get("result_list", [])


async def _resolve_overseas_market(access_token: str, stk_cd: str, *, is_mock: bool) -> str:
    """stex_tp(ND/NY/NA)를 stk_cd와 함께 각각 넣어 실제 성공하는 조합으로 상장 거래소를 판별한다.

    이 프로빙은 본질적으로 최선 노력(best-effort) 호출이므로 1903(거래소 불일치,
    KiwoomApiError) 뿐 아니라 rate limit 소진(MaxRetriesExceededError) 등 임의의 예외도
    전부 "매칭 안 됨"으로 삼킨다 — 여기서 예외가 전파되면 get_overseas_balance()의
    바깥쪽 gather 전체가 실패해 해외 잔고 전체가 EMPTY_OVERSEAS로 치환되고 기존에 저장된
    해외 Position까지 삭제되는 결과로 이어지므로(asset_service.sync_account 참고),
    종목 하나의 프로빙 실패가 다른 종목/조합에 영향을 주지 않도록 격리한다.
    셋 다 실패(보유는 되어있는데 조회가 전부 안 되는 이례적인 경우)하면 가장 흔한
    NASDAQ으로 폴백한다.
    """
    headers = _auth_headers(access_token, API_ID_OVERSEAS_BALANCE)

    async def _try(stex_tp: str) -> str | None:
        try:
            await kiwoom_request(
                "POST",
                _OVERSEAS_ACCOUNT_PATH,
                is_mock=is_mock,
                headers=headers,
                json={"stex_tp": stex_tp, "stk_cd": stk_cd},
                quiet=True,  # 1903(거래소 불일치)은 프로빙의 정상 결과이지 오류가 아님
            )
            return stex_tp
        except Exception as e:
            if not isinstance(e, KiwoomApiError):
                logger.warning("kiwoom_overseas_market_probe_failed", stk_cd=stk_cd, stex_tp=stex_tp, error=str(e))
            return None

    results = await asyncio.gather(*(_try(stex_tp) for stex_tp in _STEX_TP_MARKETS))
    matched = next((tp for tp in results if tp), None)
    if matched is None:
        logger.warning("kiwoom_overseas_market_unresolved", stk_cd=stk_cd)
    return _STEX_TP_MARKETS.get(matched or "", "NASDAQ")


async def get_overseas_balance(
    access_token: str,
    account_no: str,
    *,
    is_mock: bool,
) -> dict[str, Any]:
    """미국주식 잔고 조회 — 원장잔고(ust21070) + 예수금(ust21110), /api/us/acnt.

    국내(/api/dostk/acnt)와 경로 자체가 다르다. ust21070 응답의 stex_nm(거래소명)은 실측
    결과 항상 "미국"(국가명)만 반환되어 거래소 구분에 쓸 수 없었다 — NASDAQ/NYSE/AMEX
    보유가 전부 market="미국"으로 저장되어 수동입력/타 계좌의 동일 종목(예: QQQ-NASDAQ)과
    ticker-market 키가 어긋나 리밸런싱 진단 등에서 별개 종목으로 취급되는 버그가 있었다.
    stex_tp로 필터링해서 한 번에 거래소별 조회하는 것도 안 된다(stex_tp만 지정하면 1517
    오류) — 그래서 전체 조회 후 종목별로 _resolve_overseas_market()을 호출해 market을
    판별한다. account_no는 인터페이스 일관성을 위해서만 유지.
    """
    deposit_headers = _auth_headers(access_token, API_ID_OVERSEAS_DEPOSIT)

    items, deposit_data = await asyncio.gather(
        _fetch_overseas_all(access_token, is_mock=is_mock),
        kiwoom_request(
            "POST",
            _OVERSEAS_ACCOUNT_PATH,
            is_mock=is_mock,
            headers=deposit_headers,
            json={},
        ),
    )

    held_items = [item for item in items if int(_parse_num(item.get("poss_qty"))) > 0]
    markets = await asyncio.gather(
        *(_resolve_overseas_market(access_token, item.get("stk_cd", ""), is_mock=is_mock) for item in held_items)
    )

    positions = []
    for item, market in zip(held_items, markets, strict=True):
        crnc_code = item.get("crnc_code") or "USD"
        positions.append(
            {
                "ticker": item.get("stk_cd"),
                "name": item.get("frgn_stk_nm"),
                "market": market,
                "qty": int(_parse_num(item.get("poss_qty"))),
                "avg_price": _parse_price(item.get("frgn_stk_book_uv")),
                "current_price": _parse_price(item.get("now_pric")),
                "value_usd": _parse_num(item.get("evlt_amt")),
                "pnl_usd": _parse_num(item.get("pl_amt")),
                "pnl_pct": _parse_num(item.get("pl_rt")),
                "currency": crnc_code,
            }
        )

    deposit_usd = 0.0
    for row in deposit_data.get("result_list", []):
        if row.get("crnc_code") == "USD":
            deposit_usd = _parse_num(row.get("fc_entra"))
            break

    return {
        "positions": positions,
        "total_value_usd": sum(p["value_usd"] for p in positions),
        "deposit_usd": deposit_usd,
    }
