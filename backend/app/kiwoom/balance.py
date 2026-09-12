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

from app.kiwoom.client import kiwoom_request
from app.kiwoom.constants import (
    API_ID_DOMESTIC_BALANCE,
    API_ID_DOMESTIC_DEPOSIT,
    API_ID_OVERSEAS_BALANCE,
    API_ID_OVERSEAS_DEPOSIT,
)

logger = structlog.get_logger()

_OVERSEAS_ACCOUNT_PATH = "/api/us/acnt"
# ust21070은 상장 거래소를 신뢰성 있게 주지 않는다 — stex_tp 단독 필터는 1517 오류,
# 응답 stex_nm은 항상 "미국"(국가명) 고정값. 그래서 market은 여기서 판별하지 않고 "US"
# 센티널로 두고, provider가 enrich_overseas_positions()(Yahoo Finance 조회 + 7일 캐시)로
# NASDAQ/NYSE/AMEX를 확정한다. providers._overseas_name_enrichment.UNRESOLVED_MARKET와 동일 값.
_UNRESOLVED_MARKET = "US"


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


def _pick_deposit_krw(data: dict[str, Any]) -> tuple[float, str]:
    """예수금 표시값을 고른다 — d2_entra(D+2 추정예수금) 우선, 키 부재 시에만 entr(D+0) 폴백.

    entr는 당일 결제기준 현금이라 매도대금(T+2 결제)·미결제 매수분이 빠져 매매 직후 며칠간
    실제 자금과 벌어진다. 키움 MTS/앱이 "예수금"으로 보여주는 값은 d2_entra다.

    `_parse_num()`이 None·빈문자열·파싱실패를 모두 0.0으로 뭉개므로 "키 부재"와 "값 0"을
    구분하려면 raw dict 접근이 필요하다. d2_entra 키가 있으면 값이 "0"·음수(미수/신용)여도
    그대로 신뢰한다 — 미결제 매수분이 D+2 현금을 소진한 실제 상태다. "d2가 0이면 entr로
    폴백"은 하지 않는다: 더 큰 entr로 되돌아가 과대표시되고, d2가 실제 0이면 entr도 사실상 0이다.
    """
    if data.get("d2_entra") is not None:
        return _parse_num(data["d2_entra"]), "d2_entra"
    if data.get("entr") is not None:
        return _parse_num(data["entr"]), "entr"
    return 0.0, "none"


async def _get_deposit_info(access_token: str, *, is_mock: bool) -> dict[str, float]:
    """예수금상세현황요청 (kt00001) — 국내 현금 예수금(D+2) + 주문가능 현금.

    요청 body는 qry_tp만 보낸다(키움 공식 예제 get_domestic_deposit_detail.py 기준) —
    qry_tp="3"(추정조회)이라야 d2_entra가 채워진다. dmst_stex_tp는 kt00001 스키마에 없어
    보내지 않는다(kt00018과 달리).

    - deposit_krw: d2_entra(D+2 추정예수금, 앱 표시값). 없으면 entr 폴백
    - orderable_krw: 100stk_ord_alow_amt(미수 없는 현금 매수여력) → ord_alow_amt(주문가능금액)
      → deposit_krw 폴백. 리밸런싱 FULL 매수 예산 clamp 전용, KIS nrcvb_buy_amt와 대칭
    """
    headers = _auth_headers(access_token, API_ID_DOMESTIC_DEPOSIT)
    data = await kiwoom_request(
        "POST",
        "/api/dostk/acnt",
        is_mock=is_mock,
        headers=headers,
        json={"qry_tp": "3"},  # 3: 추정조회 (d2_entra는 이 모드에서만 채워짐)
    )

    deposit_krw, src = _pick_deposit_krw(data)
    if src == "none":
        logger.warning("kiwoom_deposit_field_missing", response_keys=list(data.keys()))
    elif src == "entr":
        logger.warning("kiwoom_deposit_d2_missing_fallback_entr", entr=data.get("entr"))
    else:
        logger.debug(
            "kiwoom_deposit_raw",
            d2_entra=data.get("d2_entra"),
            entr=data.get("entr"),
            ord_alow_amt=data.get("ord_alow_amt"),
        )

    orderable_krw = _parse_num(data.get("100stk_ord_alow_amt"))
    if orderable_krw <= 0:
        orderable_krw = _parse_num(data.get("ord_alow_amt"))
    if orderable_krw <= 0:
        orderable_krw = deposit_krw

    return {"deposit_krw": deposit_krw, "orderable_krw": orderable_krw}


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

    data, deposit_info = await asyncio.gather(
        kiwoom_request(
            "POST",
            "/api/dostk/acnt",
            is_mock=is_mock,
            headers=headers,
            json={"qry_tp": "1", "dmst_stex_tp": "KRX"},  # qry_tp 1: 합산
        ),
        _get_deposit_info(access_token, is_mock=is_mock),
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
        "deposit_krw": deposit_info["deposit_krw"],
        "orderable_krw": deposit_info["orderable_krw"],
        "invested_krw": _parse_num(data.get("tot_pur_amt")),
        "pnl_krw": _parse_num(data.get("tot_evlt_pl")),
    }


async def _fetch_overseas_all(access_token: str, *, is_mock: bool) -> list[dict[str, Any]]:
    """ust21070을 stex_tp/stk_cd 없이 호출 — 보유종목 전체(수량·가격 포함)를 한 번에 받는다.
    이 응답의 stex_nm은 항상 "미국"만 반환되어 거래소 구분에는 쓸 수 없다(market은 provider의
    enrich_overseas_positions()가 별도로 판별)."""
    headers = _auth_headers(access_token, API_ID_OVERSEAS_BALANCE)
    data = await kiwoom_request(
        "POST",
        _OVERSEAS_ACCOUNT_PATH,
        is_mock=is_mock,
        headers=headers,
        json={},
    )
    return data.get("result_list", [])


async def get_overseas_balance(
    access_token: str,
    account_no: str,
    *,
    is_mock: bool,
) -> dict[str, Any]:
    """미국주식 잔고 조회 — 원장잔고(ust21070) + 예수금(ust21110), /api/us/acnt.

    국내(/api/dostk/acnt)와 경로 자체가 다르다. ust21070 응답의 stex_nm(거래소명)은 실측
    결과 항상 "미국"(국가명)만 반환되고, stex_tp 필터 조회도 안 되므로(stex_tp만 지정하면
    1517, 거래소 불일치면 1903) 여기서는 상장 거래소를 판별하지 않는다 — market을 "US"
    센티널로 두고 KiwoomProvider가 enrich_overseas_positions()(Yahoo Finance 조회 + 티커당
    7일 캐시)로 NASDAQ/NYSE/AMEX를 확정한다. 과거에는 종목별로 ND/NY/NA를 각각 프로빙했으나
    (보유 종목당 3콜, 2콜 이상은 반드시 1903 실패) NYSE Arca 상장 ETF(SPY 등)를 판별하지
    못하고 로그를 오염시켜 폐기했다. account_no는 인터페이스 일관성을 위해서만 유지.
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

    positions = []
    for item in held_items:
        crnc_code = item.get("crnc_code") or "USD"
        positions.append(
            {
                "ticker": item.get("stk_cd"),
                "name": item.get("frgn_stk_nm"),
                "market": _UNRESOLVED_MARKET,
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
