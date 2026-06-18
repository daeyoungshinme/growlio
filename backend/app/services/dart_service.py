"""금융감독원 DART OpenAPI 클라이언트 — 국내 주식 배당 데이터 조회."""

from __future__ import annotations

import asyncio
import io
import zipfile
from datetime import datetime

import defusedxml.ElementTree as ET
import httpx
import structlog

from app.config import settings

logger = structlog.get_logger()

DART_BASE = "https://opendart.fss.or.kr/api"

# ── 종목코드 → corp_code 캐시 ───────────────────────────
_corp_code_map: dict[str, str] = {}  # "005930" → "00126380"
_corp_code_loaded_at: datetime | None = None
_corp_code_lock = asyncio.Lock()
_CORP_CODE_TTL_HOURS = 24


async def _fetch_corp_code_map(api_key: str) -> dict[str, str]:
    """DART corp_code ZIP 다운로드 → {stock_code: corp_code} 반환."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{DART_BASE}/corpCode.xml",
                params={"crtfc_key": api_key},
            )
            resp.raise_for_status()
            zip_bytes = resp.content

        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            xml_bytes = zf.read("CORPCODE.xml")

        root = ET.fromstring(xml_bytes)
        result: dict[str, str] = {}
        for item in root.findall(".//list"):
            stock_code = (item.findtext("stock_code") or "").strip()
            corp_code = (item.findtext("corp_code") or "").strip()
            if stock_code and corp_code:
                result[stock_code] = corp_code

        logger.info("dart_corp_code_loaded", count=len(result))
        return result
    except Exception as e:
        logger.warning("dart_corp_code_fetch_failed", error=str(e))
        return {}


async def _ensure_corp_code_map(api_key: str) -> dict[str, str]:
    """TTL 기반 캐시. 초기 또는 24시간 경과 시 재조회."""
    global _corp_code_map, _corp_code_loaded_at

    def _is_fresh() -> bool:
        if not _corp_code_map or _corp_code_loaded_at is None:
            return False
        age = (datetime.utcnow() - _corp_code_loaded_at).total_seconds()
        return age < _CORP_CODE_TTL_HOURS * 3600

    if _is_fresh():
        return _corp_code_map

    async with _corp_code_lock:
        if _is_fresh():
            return _corp_code_map

        new_map = await _fetch_corp_code_map(api_key)
        if new_map:
            _corp_code_map = new_map
            _corp_code_loaded_at = datetime.utcnow()
        else:
            logger.warning("dart_corp_code_refresh_failed", stale_count=len(_corp_code_map))

        return _corp_code_map


async def _lookup_corp_code(ticker: str, api_key: str) -> str | None:
    """6자리 종목코드 → DART corp_code. 미등록이면 None."""
    code_map = await _ensure_corp_code_map(api_key)
    return code_map.get(ticker.zfill(6))


async def fetch_dart_dividend(ticker: str, api_key: str, year: int | None = None) -> dict | None:
    """DART stockDiv.json 조회 → {dividend_yield: float(decimal), dps: float} | None.

    - year 미지정 시 현재연도 조회. 미공시(status 013)이면 전년도 재시도.
    - 실패/데이터 없음 시 None 반환 (예외 전파 없음).
    """
    if not api_key:
        return None

    corp_code = await _lookup_corp_code(ticker, api_key)
    if not corp_code:
        logger.debug("dart_corp_code_not_found", ticker=ticker)
        return None

    bsns_year = str(year or datetime.utcnow().year)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{DART_BASE}/stockDiv.json",
                params={
                    "crtfc_key": api_key,
                    "corp_code": corp_code,
                    "bsns_year": bsns_year,
                    "reprt_code": "11011",  # 사업보고서
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.warning("dart_dividend_failed", ticker=ticker, year=bsns_year, error=str(e))
        return None

    status = data.get("status", "")
    if status != "000":
        # 당해연도 미공시 → 전년도 재시도 1회
        if year is None and status == "013":
            return await fetch_dart_dividend(ticker, api_key, datetime.utcnow().year - 1)
        logger.debug("dart_dividend_no_data", ticker=ticker, status=status, year=bsns_year)
        return None

    # 우선주 여부 판단 (한국 우선주 코드: 6자리이며 마지막 자리가 '5')
    is_preferred = len(ticker) == 6 and ticker[-1] == "5"

    pref_items: list[dict] = []
    common_items: list[dict] = []
    other_items: list[dict] = []
    for item in data.get("list", []):
        se = (item.get("se") or item.get("stock_kind") or "").strip()
        if "우선" in se:
            pref_items.append(item)
        elif "보통" in se or se == "":
            common_items.append(item)
        else:
            other_items.append(item)  # 합계·소계 행 등

    # 해당 종목 타입에 맞는 행 우선 선택, 없으면 순차 폴백
    candidate_items = (pref_items if is_preferred else common_items) or common_items or pref_items or other_items

    for item in candidate_items:
        raw_yield = (item.get("cash_dwnd_rate") or "").replace(",", "").strip()
        raw_dps = (item.get("per_sto_dvdn_amt") or "").replace(",", "").strip()
        try:
            yld = float(raw_yield) / 100  # DART는 % 형식 ("2.15" → 0.0215)
            dps = float(raw_dps) if raw_dps else 0.0

            # DPS 합리성 검증: 주당 배당금이 100만원 초과이면 합계/총액 행으로 판단하고 스킵
            if dps > 1_000_000:
                logger.warning("dart_dps_abnormal_skipped", ticker=ticker, dps=dps, se=item.get("se"))
                continue

            if yld > 0:
                logger.info(
                    "dart_dividend_fetched",
                    ticker=ticker,
                    year=bsns_year,
                    yield_pct=round(yld * 100, 2),
                    dps=dps,
                    se=item.get("se"),
                    is_preferred=is_preferred,
                )
                return {"dividend_yield": yld, "dps": dps}
        except ValueError:
            continue

    return None


# ── 공시 목록 조회 ─────────────────────────────────────────────
_DART_DISCLOSURE_SEM = asyncio.Semaphore(settings.api_semaphore_limit)


async def fetch_disclosures_for_tickers(
    tickers: list[str],
    api_key: str,
    days: int = 30,
) -> list[dict]:
    """보유 국내 종목의 DART 공시 목록 조회.

    tickers: KOSPI/KOSDAQ 6자리 종목코드 목록
    returns: rcept_dt 내림차순 정렬된 공시 항목 목록
    """
    if not api_key or not tickers:
        return []

    from datetime import timedelta

    corp_map = await _ensure_corp_code_map(api_key)

    bgn_de = (datetime.utcnow() - timedelta(days=days)).strftime("%Y%m%d")
    end_de = datetime.utcnow().strftime("%Y%m%d")

    ticker_corp_pairs: list[tuple[str, str]] = []
    for ticker in tickers:
        corp_code = corp_map.get(ticker.zfill(6))
        if corp_code:
            ticker_corp_pairs.append((ticker, corp_code))

    if not ticker_corp_pairs:
        return []

    async def _fetch_one(ticker: str, corp_code: str) -> list[dict]:
        async with _DART_DISCLOSURE_SEM:
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.get(
                        f"{DART_BASE}/list.json",
                        params={
                            "crtfc_key": api_key,
                            "corp_code": corp_code,
                            "bgn_de": bgn_de,
                            "end_de": end_de,
                            "page_count": 20,
                            "sort": "date",
                            "sort_mth": "desc",
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()
            except Exception as e:
                logger.warning("dart_disclosures_fetch_failed", ticker=ticker, error=str(e))
                return []

            if data.get("status") != "000":
                return []

            items = []
            for item in data.get("list", []):
                rcept_no = item.get("rcept_no", "")
                items.append(
                    {
                        "rcept_no": rcept_no,
                        "corp_name": item.get("corp_name", ""),
                        "ticker": ticker,
                        "report_nm": item.get("report_nm", ""),
                        "rcept_dt": item.get("rcept_dt", ""),
                        "rm": item.get("rm", ""),
                        "dart_url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}",
                    }
                )
            return items

    tasks = [_fetch_one(ticker, corp_code) for ticker, corp_code in ticker_corp_pairs]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_items: list[dict] = []
    for r in results:
        if isinstance(r, list):
            all_items.extend(r)

    all_items.sort(key=lambda x: x.get("rcept_dt", ""), reverse=True)
    logger.info("dart_disclosures_fetched", ticker_count=len(ticker_corp_pairs), total=len(all_items))
    return all_items
