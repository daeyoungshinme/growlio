"""해외주식 기간손익 조회 (TTTS3039R, /uapi/overseas-stock/v1/trading/inquire-period-profit).

양도세 250만원 공제 잔여 계산용 — 올해 실제로 매도해 확정된 해외 실현손익을 원화 기준(WCRC_FRCR_DVSN_CD=02)으로
받는다. 원화 환산은 KIS가 매입/매도 시점 환율로 계산한 값이라 국세청 신고 기준(취득·양도일 기준환율)과 가깝지만
완전히 같지는 않다(참고용). 모의투자 서버는 이 TR을 지원하지 않아 실전 계좌에서만 호출한다.

필드 출처: koreainvestment/open-trading-api examples_llm/overseas_stock/inquire_period_profit.
응답 구조(output1=종목·매매일별 행, output2=기간 합계)는 문서마다 표기가 엇갈려, 리스트/딕셔너리 형태로 판별한다.
"""

from __future__ import annotations

from datetime import date
from typing import Any, TypedDict

import structlog

from app.kis.client import auth_headers, kis_request, split_account_no
from app.kis.constants import TR_OVERSEAS_PERIOD_PROFIT_REAL

logger = structlog.get_logger()

_PATH = "/uapi/overseas-stock/v1/trading/inquire-period-profit"
_MAX_PAGES = 10  # 연속조회 상한 — 1년치 체결이 이보다 많으면 합계(output2)를 우선 신뢰


class RealizedTrade(TypedDict):
    trade_date: str
    ticker: str
    qty: float
    realized_krw: float


class OverseasRealizedPnl(TypedDict):
    total_krw: float
    trades: list[RealizedTrade]


def _to_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _split_output(data: dict[str, Any]) -> tuple[list[dict], dict | None]:
    rows: list[dict] = []
    summary: dict | None = None
    for key in ("output1", "output2"):
        value = data.get(key)
        if isinstance(value, list):
            rows.extend(v for v in value if isinstance(v, dict))
        elif isinstance(value, dict) and value:
            summary = value
    return rows, summary


async def get_overseas_realized_pnl(
    app_key: str,
    app_secret: str,
    access_token: str,
    account_no: str,
    start: date,
    end: date,
) -> OverseasRealizedPnl:
    """기간 내 해외주식 실현손익(원화). 전 거래소·전 통화 합산."""
    cano, acnt_prdt_cd = split_account_no(account_no)
    headers = auth_headers(app_key, app_secret, access_token, TR_OVERSEAS_PERIOD_PROFIT_REAL)

    trades: list[RealizedTrade] = []
    summary_total: float | None = None
    fk200 = nk200 = ""
    for page in range(_MAX_PAGES):
        page_headers = {**headers, "tr_cont": "N"} if page > 0 else headers
        data = await kis_request(
            "GET",
            _PATH,
            is_mock=False,
            headers=page_headers,
            params={
                "CANO": cano,
                "ACNT_PRDT_CD": acnt_prdt_cd,
                "OVRS_EXCG_CD": "",
                "NATN_CD": "",
                "CRCY_CD": "",
                "PDNO": "",
                "INQR_STRT_DT": start.strftime("%Y%m%d"),
                "INQR_END_DT": end.strftime("%Y%m%d"),
                "WCRC_FRCR_DVSN_CD": "02",  # 원화
                "CTX_AREA_FK200": fk200,
                "CTX_AREA_NK200": nk200,
            },
        )
        rows, summary = _split_output(data)
        if summary is not None and summary_total is None and "ovrs_rlzt_pfls_tot_amt" in summary:
            summary_total = _to_float(summary.get("ovrs_rlzt_pfls_tot_amt"))
        for row in rows:
            if not row.get("ovrs_pdno"):
                continue
            trades.append(
                {
                    "trade_date": str(row.get("trad_day") or ""),
                    "ticker": str(row["ovrs_pdno"]),
                    "qty": _to_float(row.get("slcl_qty")),
                    "realized_krw": _to_float(row.get("ovrs_rlzt_pfls_amt")),
                }
            )

        next_nk = str(data.get("ctx_area_nk200") or "").strip()
        next_fk = str(data.get("ctx_area_fk200") or "").strip()
        if not rows or not next_nk or next_nk == nk200:
            break
        fk200, nk200 = next_fk, next_nk
    else:
        logger.warning("kis_period_profit_page_limit", pages=_MAX_PAGES, trades=len(trades))

    total = summary_total if summary_total is not None else sum(t["realized_krw"] for t in trades)
    return {"total_krw": total, "trades": trades}
