"""배당 서비스 오케스트레이터.

DB 조회·Redis 캐시·외부 fetch를 조율해 배당금 집계 결과를 생성한다.
순수 계산 로직 → calculator.py
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import date

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.redis_client import get_redis
from app.models.asset import AssetAccount, AssetSnapshot
from app.services._snapshot_queries import latest_snapshot_subquery
from app.services.credential_service import get_kis_user_credentials
from app.services.dividend._dividend_queries import fetch_dart_api_key, load_user_dividend_overrides
from app.services.dividend.calculator import calculate_position_dividend
from app.services.dividend.constants import KNOWN_DIVIDEND_SCHEDULES as KNOWN_DIVIDEND_SCHEDULES
from app.services.dividend.fetcher import fetch_ticker_dividend_info
from app.utils.cache_keys import TTL_DART, TTL_DIVIDEND_INFO, dividend_ticker_summary_key
from app.utils.currency import get_usd_krw_rate

logger = structlog.get_logger()

_DIVIDEND_FETCH_SEM = asyncio.Semaphore(settings.api_semaphore_limit)


async def _collect_positions(user_id: uuid.UUID, db: AsyncSession) -> dict[tuple[str, str], dict]:
    """활성 주식 계좌의 최신 스냅샷에서 (ticker, market) → 포지션 정보 맵 수집."""
    subq = latest_snapshot_subquery(user_id=user_id)
    snap_date_match = (AssetSnapshot.account_id == subq.c.account_id) & (AssetSnapshot.snapshot_date == subq.c.max_date)
    result = await db.execute(
        select(AssetSnapshot, AssetAccount)
        .options(selectinload(AssetSnapshot.position_items))
        .join(subq, snap_date_match)
        .join(AssetAccount, AssetAccount.id == AssetSnapshot.account_id)
        .where(
            AssetAccount.is_active == True,  # noqa: E712
            AssetAccount.asset_type.like("STOCK%"),
        )
    )
    rows = result.all()

    positions_map: dict[tuple[str, str], dict] = {}
    for snap, _acc in rows:
        if not snap.position_items:
            continue
        for p in snap.position_items:
            ticker = p.ticker
            market = (p.market or "KOSPI").upper()
            name = p.name or ticker
            raw_value_krw = p.value_krw
            if raw_value_krw and float(raw_value_krw) > 0:
                value = float(raw_value_krw)
            else:
                qty = float(p.qty or 0)
                price = float(p.current_price or p.avg_price or 0)
                value = qty * price if qty > 0 and price > 0 else 0.0
            invested = float(p.avg_price or 0) * float(p.qty or 0)
            if ticker and value > 0:
                key = (ticker, market)
                if key not in positions_map:
                    positions_map[key] = {
                        "value_krw": 0.0,
                        "name": name,
                        "invested_krw": 0.0,
                        "qty": 0.0,
                    }
                positions_map[key]["value_krw"] += value
                positions_map[key]["invested_krw"] += invested
                positions_map[key]["qty"] += float(p.qty or 0)

    return positions_map


def _build_ticker_output_entry(
    *,
    ticker_key: str,
    est_keys: list[tuple[str, str]],
    estimated_map: dict[tuple[str, str], dict],
    received_map: dict[str, float],
    pos_name: str,
) -> dict:
    """종목별 예상 배당금 집계 결과를 output dict으로 조립한다."""
    if est_keys:
        primary = estimated_map[est_keys[0]]
        combined_annual = sum(estimated_map[k].get("estimated_annual_krw", 0) for k in est_keys)
        combined_monthly = sum(estimated_map[k].get("estimated_monthly_krw", 0) for k in est_keys)
        combined_months = sorted({m for k in est_keys for m in estimated_map[k].get("dividend_months", [])})
        market_val = primary.get("market")
        yield_decimal = primary.get("yield_decimal", 0.0)
        dps = primary.get("dps", 0.0)
        investment_yield = primary.get("investment_yield", 0.0)
        is_manual = primary.get("dividend_months_is_manual", False)
        currency = primary.get("currency", "KRW")
        combined_monthly_usd = (
            round(sum(estimated_map[k].get("estimated_monthly_usd") or 0 for k in est_keys), 2)
            if currency == "USD"
            else None
        )
    else:
        combined_annual = combined_monthly = 0
        combined_months = []
        market_val = None
        yield_decimal = dps = investment_yield = 0.0
        is_manual = False
        currency = "KRW"
        combined_monthly_usd = None

    return {
        "ticker": ticker_key,
        "name": pos_name,
        "market": market_val,
        "received_krw": received_map.get(ticker_key, 0),
        "estimated_annual_krw": combined_annual,
        "estimated_monthly_krw": combined_monthly,
        "dividend_yield": round(yield_decimal * 100, 2),
        "dps": dps,
        "dividend_months": combined_months,
        "dividend_months_is_manual": is_manual,
        "investment_yield": investment_yield,
        "currency": currency,
        "estimated_monthly_usd": combined_monthly_usd,
    }


async def _fetch_received_dividends_by_ticker(db: AsyncSession, user_id: uuid.UUID, year: int) -> dict[str, float]:
    """올해 배당 실수령액을 ticker별로 합산 조회한다 (미분류 거래는 '__unclassified__' 키)."""
    result = await db.execute(
        text("""
            SELECT COALESCE(ticker, '__unclassified__') AS ticker_key, SUM(amount) AS total
            FROM transactions
            WHERE user_id = :uid
              AND transaction_type = 'DIVIDEND'
              AND EXTRACT(year FROM transaction_date) = :yr
            GROUP BY 1
        """),
        {"uid": str(user_id), "yr": year},
    )
    return {row.ticker_key: float(row.total) for row in result}


def _normalize_received_map_by_ticker(
    received_map: dict[str, float], positions: dict[tuple[str, str], dict]
) -> dict[str, float]:
    """거래내역이 종목명으로 기록된 경우 보유 포지션의 ticker 코드로 정규화해 합산한다."""
    name_to_ticker: dict[str, str] = {}
    for (tkr, _mkt), info in positions.items():
        name = info.get("name", "")
        if name and name != tkr:
            name_to_ticker[name] = tkr
    normalized: dict[str, float] = {}
    for key, val in received_map.items():
        normalized_key = name_to_ticker.get(key, key)
        normalized[normalized_key] = normalized.get(normalized_key, 0.0) + val
    return normalized


async def _fetch_estimated_dividend_map(
    positions: dict[tuple[str, str], dict],
    redis,
    kis_creds,
    dart_key,
    overrides: dict,
    usd_krw_rate: float,
) -> dict[tuple[str, str], dict]:
    """보유 포지션별 예상 배당금을 동시 조회해 (ticker, market) → 집계 dict로 병합한다."""

    async def _fetch_estimated(ticker: str, market: str, value_krw: float, invested_krw: float, qty: float) -> dict:
        override_months = overrides.get((ticker, market))
        yield_decimal, dps, months, _ = await fetch_ticker_dividend_info(
            ticker, market, redis, _DIVIDEND_FETCH_SEM, kis_creds, dart_key, overrides
        )
        return calculate_position_dividend(
            ticker=ticker,
            market=market,
            yield_decimal=yield_decimal,
            dps=dps,
            months=months,
            value_krw=value_krw,
            invested_krw=invested_krw,
            qty=qty,
            usd_krw_rate=usd_krw_rate,
            override_months=override_months,
        )

    tasks = [
        _fetch_estimated(ticker, market, info["value_krw"], info["invested_krw"], info.get("qty", 0.0))
        for (ticker, market), info in positions.items()
    ]
    estimated_results = await asyncio.gather(*tasks, return_exceptions=True)

    estimated_map: dict[tuple[str, str], dict] = {}
    for item in estimated_results:
        if isinstance(item, Exception):
            logger.warning("dividend_estimate_fetch_failed", error=str(item))
            continue
        if not isinstance(item, dict):
            continue
        em_key: tuple[str, str] = (item["ticker"], item.get("market", ""))
        if em_key not in estimated_map:
            estimated_map[em_key] = item
        else:
            existing = estimated_map[em_key]
            existing["estimated_annual_krw"] = existing.get("estimated_annual_krw", 0) + item.get(
                "estimated_annual_krw", 0
            )
            existing["estimated_monthly_krw"] = existing.get("estimated_monthly_krw", 0) + item.get(
                "estimated_monthly_krw", 0
            )
            existing["dividend_months"] = sorted(
                set(existing.get("dividend_months", []) + item.get("dividend_months", []))
            )
    return estimated_map


def _assemble_ticker_dividend_output(
    received_map: dict[str, float],
    estimated_map: dict[tuple[str, str], dict],
    positions: dict[tuple[str, str], dict],
) -> list[dict]:
    """실수령/예상 배당금 맵을 종목별 output 리스트로 조립한다 (미분류 항목 포함, 내림차순 정렬)."""
    ticker_to_est_keys: dict[str, list[tuple[str, str]]] = {}
    for tkr, mkt in estimated_map:
        ticker_to_est_keys.setdefault(tkr, []).append((tkr, mkt))

    all_tickers: set[str] = set(received_map.keys()) | set(ticker_to_est_keys.keys())
    output: list[dict] = []

    for ticker_key in all_tickers:
        if ticker_key == "__unclassified__":
            output.append(
                {
                    "ticker": None,
                    "name": "미분류",
                    "market": None,
                    "received_krw": received_map.get("__unclassified__", 0),
                    "estimated_annual_krw": 0,
                    "estimated_monthly_krw": 0,
                    "dividend_yield": 0.0,
                    "dps": 0.0,
                    "dividend_months": [],
                    "dividend_months_is_manual": False,
                    "investment_yield": 0.0,
                    "currency": "KRW",
                    "estimated_monthly_usd": None,
                }
            )
            continue

        pos_entry = next(
            (v for (t, _m), v in positions.items() if t == ticker_key),
            {"name": ticker_key},
        )
        entry = _build_ticker_output_entry(
            ticker_key=ticker_key,
            est_keys=ticker_to_est_keys.get(ticker_key, []),
            estimated_map=estimated_map,
            received_map=received_map,
            pos_name=pos_entry.get("name", ticker_key),
        )
        output.append(entry)

    output.sort(key=lambda x: x["estimated_annual_krw"] + x["received_krw"], reverse=True)
    return output


async def get_ticker_dividend_summary(user_id: uuid.UUID, db: AsyncSession) -> list[dict]:
    """종목별 실수령(올해) + 예상 배당금 통합. Redis 24h 캐시."""
    current_year = date.today().year
    cache_key = dividend_ticker_summary_key(user_id, current_year)

    redis = await get_redis()
    cached = await redis.get(cache_key)
    if cached:
        logger.info("dividend_by_ticker_cache_hit", user_id=str(user_id))
        return json.loads(cached)

    received_map = await _fetch_received_dividends_by_ticker(db, user_id, current_year)
    positions = await _collect_positions(user_id, db)
    received_map = _normalize_received_map_by_ticker(received_map, positions)

    overrides = await load_user_dividend_overrides(user_id, db)
    dart_key = await fetch_dart_api_key(user_id, db)
    kis_creds = await get_kis_user_credentials(user_id, db)
    usd_krw_rate: float = await get_usd_krw_rate(redis)

    estimated_map = await _fetch_estimated_dividend_map(positions, redis, kis_creds, dart_key, overrides, usd_krw_rate)

    output = _assemble_ticker_dividend_output(received_map, estimated_map, positions)

    has_yield = any(item.get("investment_yield", 0) > 0 for item in output)
    ttl = TTL_DIVIDEND_INFO if has_yield else TTL_DART
    await redis.setex(cache_key, ttl, json.dumps(output))
    logger.info("dividend_by_ticker_computed", user_id=str(user_id), count=len(output))
    return output


async def get_position_dividend_yields(user_id: uuid.UUID, db: AsyncSession) -> list[dict]:
    """보유 종목별 배당수익률과 예상 배당금을 반환한다."""
    positions = await _collect_positions(user_id, db)
    overrides = await load_user_dividend_overrides(user_id, db)
    dart_key = await fetch_dart_api_key(user_id, db)
    kis_creds = await get_kis_user_credentials(user_id, db)

    redis = await get_redis()

    async def fetch_one(ticker: str, market: str, value_krw: float, invested_krw: float, qty: float) -> dict:
        override_months = overrides.get((ticker, market))
        yield_decimal, dps, months, ex_dividend_date = await fetch_ticker_dividend_info(
            ticker, market, redis, _DIVIDEND_FETCH_SEM, kis_creds, dart_key, overrides
        )
        return calculate_position_dividend(
            ticker=ticker,
            market=market,
            yield_decimal=yield_decimal,
            dps=dps,
            months=months,
            value_krw=value_krw,
            invested_krw=invested_krw,
            qty=qty,
            override_months=override_months,
            ex_dividend_date=ex_dividend_date,
        )

    tasks = [
        fetch_one(ticker, market, info["value_krw"], info["invested_krw"], info.get("qty", 0.0))
        for (ticker, market), info in positions.items()
    ]
    raw = await asyncio.gather(*tasks, return_exceptions=True)
    results: list[dict] = []
    for item in raw:
        if isinstance(item, Exception):
            logger.warning("position_yield_fetch_failed", error=str(item))
            continue
        if not isinstance(item, dict):
            continue
        results.append(item)
    return results
