"""보유 종목 → 추종 지수 분류 (지수별 비중 합산용, 순수 함수).

SPY(미국상장)와 TIGER 미국S&P500(국내상장)처럼 상장시장·운용사가 달라도 같은 지수를 추종하는 ETF를 한
그룹으로 묶기 위한 분류기다. 지수 키 판별은 `etf_overlap_service.resolve_index_key`와 같은 우선순위
(해외 ticker 맵·큐레이션 유니버스 > Naver 기초지수명 > 종목명 > 해외 정식명칭)를 따르되, 비중 집계에 맞게
다음 규칙을 더한다.

- 레버리지·인버스: 기초지수와 무관하게 `LEVERAGED` 묶음(배수 노출은 반영하지 않는다).
- 커버드콜: 원 지수와 별도 그룹. 나스닥100/S&P500 외 기초지수는 `COVERED_CALL:<기초지수 키>`,
  기초지수를 모르면 `COVERED_CALL_OTHER`.
- 환헤지(H)·합성·선물형: 원 지수에 합산하고 `hedged` 플래그만 남긴다.
- 지수를 모르는 ETF는 `OTHER_ETF`, ETF가 아니면 `STOCK`(개별주).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Literal

from app.constants import DOMESTIC_MARKETS
from app.services.etf_profile_service import EtfProfile
from app.services.goal_candidate_service import LEVERAGED_INVERSE_RE, looks_like_korean_etf
from app.services.recommendation_universe import (
    COVERED_CALL_RE,
    guess_tracking_index,
    resolve_tracking_index,
)

HoldingKind = Literal["INDEX", "LEVERAGED", "OTHER_ETF", "STOCK"]
Region = Literal["DOMESTIC", "OVERSEAS"]

INDEX_LABELS: dict[str, str] = {
    "US_SP500": "S&P 500",
    "US_NASDAQ100": "나스닥 100",
    "US_TOTAL_MARKET": "미국 전체시장",
    "US_DJIA": "다우존스 산업평균",
    "US_DIV_DOWJONES100": "미국배당다우존스",
    "US_HIGH_DIVIDEND": "미국 고배당",
    "US_COVERED_CALL_SP500": "S&P 500 커버드콜",
    "US_COVERED_CALL_NASDAQ100": "나스닥 100 커버드콜",
    "US_PHLX_SEMI": "필라델피아 반도체",
    "US_TOTAL_BOND": "미국 종합채권",
    "US_TREASURY_SHORT": "미국 단기국채",
    "KR_KOSPI200": "코스피 200",
    "KR_KOSDAQ150": "코스닥 150",
    "KR_TREASURY_3Y": "국고채 3년",
    "KR_CD_RATE": "CD금리",
    "KR_SHORT_BOND": "국내 단기채권",
    "COVERED_CALL_OTHER": "기타 커버드콜",
}

_COVERED_CALL_PREFIX = "COVERED_CALL:"
_RAW_PREFIX = "RAW:"

_US_LEVERAGED_TICKERS: frozenset[str] = frozenset(
    {
        "TQQQ", "SQQQ", "QLD", "QID", "PSQ", "UPRO", "SPXU", "SPXL", "SPXS", "SSO", "SDS", "SH",
        "SOXL", "SOXS", "TECL", "TECS", "FNGU", "FNGD", "TNA", "TZA", "UDOW", "SDOW", "DDM", "DXD",
        "DOG", "LABU", "LABD", "FAS", "FAZ", "TMF", "TMV", "TBT", "UBT", "YINN", "YANG", "NVDL",
        "NVDU", "TSLL", "TSLQ", "CONL", "BITX", "USD", "SSG", "NAIL", "DPST", "WEBL",
    }
)  # fmt: skip
"""해외 레버리지·인버스 ETF ticker — 정식명칭("ProShares UltraPro QQQ")에 한글 패턴이 없어 따로 둔다."""

_US_LEVERAGED_NAME_RE = re.compile(
    r"\bUltra(Pro|Short)?\b|\bInverse\b|\bBear\b|\bBull\s*[23]X\b|\b[23]X\b|\bProShares\s+Short\b|Daily\s+.*\b[23]X\b",
    re.IGNORECASE,
)

_OVERSEAS_NAME_RE = re.compile(
    r"미국|나스닥|NASDAQ|S&P|다우|필라델피아|글로벌|선진국|신흥국|차이나|중국|항셍|홍콩|일본|니케이|토픽스|인도|베트남|"
    r"유로|유럽|독일|대만|브라질|라틴|MSCI\s*(ACWI|World|EM)|해외|WORLD|FANG|빅테크|테슬라|엔비디아|애플|"
    r"마이크로소프트|아마존|알파벳|매그니피센트|TOP\s*7",
    re.IGNORECASE,
)
"""국내상장 ETF 종목명/기초지수명의 해외 노출 키워드 — 국내 키워드보다 먼저 검사("KODEX 미국S&P500" 대비)."""

_DOMESTIC_NAME_RE = re.compile(
    r"코스피|KOSPI|코스닥|KOSDAQ|KRX|국고채|통안|CD금리|KOFR|단기채|머니마켓|종합채권|회사채|금융채|한국|국내|"
    r"(?<!\d)200(?!\d)",
    re.IGNORECASE,
)

_HEDGED_RE = re.compile(r"\(\s*(합성\s*)?H\s*\)|환헤지|Hedged", re.IGNORECASE)


@dataclass(frozen=True)
class IndexClass:
    kind: HoldingKind
    index_key: str | None = None
    label: str | None = None
    hedged: bool = False
    region: Region | None = None  # 실제 투자지역(상장시장과 다름 — TIGER 미국S&P500은 OVERSEAS). 판별 불가면 None


def is_domestic_listed(market: str) -> bool:
    return market.upper() in DOMESTIC_MARKETS


def _normalize_index_name(raw: str) -> str:
    return re.sub(r"[\s\-_.()]", "", raw).upper()


def index_label(key: str, base_index: str | None = None) -> str:
    """지수 키 → 표시 라벨. RAW 키는 원문 기초지수명, 커버드콜 파생 키는 "<기초지수> 커버드콜"."""
    if key in INDEX_LABELS:
        return INDEX_LABELS[key]
    if key.startswith(_COVERED_CALL_PREFIX):
        return f"{index_label(key[len(_COVERED_CALL_PREFIX) :])} 커버드콜"
    if key.startswith(_RAW_PREFIX):
        return base_index or key[len(_RAW_PREFIX) :]
    return key


def _is_leveraged(ticker: str, market: str, name: str, long_name: str | None) -> bool:
    if LEVERAGED_INVERSE_RE.search(name.upper()):
        return True
    if is_domestic_listed(market):
        return False
    if ticker.upper() in _US_LEVERAGED_TICKERS:
        return True
    return any(_US_LEVERAGED_NAME_RE.search(n) for n in (name, long_name) if n)


def _covered_call_key(names: list[str]) -> str:
    """커버드콜 상품의 그룹 키. 나스닥100/S&P500은 기존 라벨, 그 외는 커버드콜 문구를 지운 이름으로 기초지수 추정."""
    for n in names:
        guessed = guess_tracking_index(n)
        if guessed and guessed.startswith("US_COVERED_CALL"):
            return guessed
    for n in names:
        base = guess_tracking_index(COVERED_CALL_RE.sub(" ", n))
        if base:
            return f"{_COVERED_CALL_PREFIX}{base}"
    return "COVERED_CALL_OTHER"


def _resolve_index_key(ticker: str, market: str, name: str, profile: EtfProfile | None) -> str | None:
    base_index = profile.get("base_index") if profile else None
    long_name = profile.get("long_name") if profile else None
    names = [n for n in (name, base_index, long_name) if n]

    known = resolve_tracking_index(ticker, market, "", None)
    if known:
        return known
    if any(COVERED_CALL_RE.search(n) for n in names):
        return _covered_call_key(names)
    if base_index:
        return guess_tracking_index(base_index) or f"{_RAW_PREFIX}{_normalize_index_name(base_index)}"
    for n in (name, long_name):
        if n:
            guessed = guess_tracking_index(n)
            if guessed:
                return guessed
    return None


def _looks_like_etf(ticker: str, market: str, name: str, profile: EtfProfile | None) -> bool:
    if profile is not None:
        return True
    if is_domestic_listed(market):
        return looks_like_korean_etf({"ticker": ticker, "name": name, "market": market})
    return False


def _region_from_names(*names: str | None) -> Region | None:
    texts = [n for n in names if n]
    if any(_OVERSEAS_NAME_RE.search(n) for n in texts):
        return "OVERSEAS"
    if any(_DOMESTIC_NAME_RE.search(n) for n in texts):
        return "DOMESTIC"
    return None


def exposure_region(market: str, name: str, cls: IndexClass, profile: EtfProfile | None = None) -> Region | None:
    """실제 투자지역. 해외상장은 해외, 국내 개별주는 국내, 국내상장 ETF는 지수 키 접두어 → 이름 키워드 순으로 판별."""
    if not is_domestic_listed(market):
        return "OVERSEAS"
    if cls.kind == "STOCK":
        return "DOMESTIC"
    key = cls.index_key or ""
    if key.startswith(_COVERED_CALL_PREFIX):
        key = key[len(_COVERED_CALL_PREFIX) :]
    if key.startswith("US_"):
        return "OVERSEAS"
    if key.startswith("KR_"):
        return "DOMESTIC"
    base_index = profile.get("base_index") if profile else None
    region = _region_from_names(name, base_index)
    if region is None and cls.kind == "LEVERAGED":
        return "DOMESTIC"  # 지역 키워드 없는 국내 레버리지·인버스("KODEX 레버리지")는 코스피200 추종이 대부분
    return region


def classify_holding(ticker: str, market: str, name: str, profile: EtfProfile | None) -> IndexClass:
    """보유 종목 1건을 분류한다. `profile`은 `get_etf_profiles` 결과(ETF가 아니거나 조회 실패면 None)."""
    long_name = profile.get("long_name") if profile else None
    hedged = bool(_HEDGED_RE.search(name))

    if _is_leveraged(ticker, market, name, long_name):
        cls = IndexClass(kind="LEVERAGED", hedged=hedged)
    elif key := _resolve_index_key(ticker, market, name, profile):
        base_index = profile.get("base_index") if profile else None
        cls = IndexClass(kind="INDEX", index_key=key, label=index_label(key, base_index), hedged=hedged)
    elif _looks_like_etf(ticker, market, name, profile):
        cls = IndexClass(kind="OTHER_ETF", hedged=hedged)
    else:
        cls = IndexClass(kind="STOCK")
    return replace(cls, region=exposure_region(market, name, cls, profile))
