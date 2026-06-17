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
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.kis.auth import get_access_token
from app.kis.domestic_quote import get_domestic_dividend_info, get_domestic_etf_dividend_info
from app.models.asset import AssetAccount, AssetSnapshot, UserTickerSettings
from app.models.user import UserSettings
from app.redis_client import get_redis
from app.services._snapshot_queries import latest_snapshot_subquery
from app.services.credential_service import decrypt, get_kis_user_credentials
from app.services.dividend.calculator import calculate_position_dividend
from app.services.dividend_constants import KNOWN_DIVIDEND_SCHEDULES as KNOWN_DIVIDEND_SCHEDULES
from app.services.dividend_fetcher import fetch_ticker_dividend_info
from app.utils.cache_keys import (
    TTL_DART,
    TTL_DIVIDEND_INFO,
    dividend_info_key,
    dividend_months_key,
    dividend_ticker_summary_key,
)
from app.utils.currency import get_usd_krw_rate

logger = structlog.get_logger()


async def _get_dart_key(user_id: uuid.UUID, db: AsyncSession) -> str:
    """user_settings에서 DART API 키 조회 및 복호화. 없으면 config 기본값 사용."""
    row = await db.scalar(select(UserSettings).where(UserSettings.user_id == user_id))
    if row and row.dart_api_key:
        return decrypt(row.dart_api_key)
    return settings.dart_api_key


async def _call_kis_dividend_api(
    ticker: str,
    user_id: uuid.UUID,
    db: AsyncSession,
    fetch_fn,
    log_name: str,
) -> dict | None:
    """KIS 계좌를 통해 배당 API를 호출하는 공통 헬퍼."""
    account = await db.scalar(
        select(AssetAccount).where(
            AssetAccount.user_id == user_id,
            AssetAccount.data_source == "KIS_API",
            AssetAccount.is_active == True,  # noqa: E712
            AssetAccount.kis_app_key != None,  # noqa: E711
        )
    )
    if not account:
        return None

    try:
        redis = await get_redis()
        app_key = decrypt(account.kis_app_key)  # type: ignore[arg-type]
        app_secret = decrypt(account.kis_app_secret)  # type: ignore[arg-type]
        access_token = await get_access_token(
            app_key,
            app_secret,
            is_mock=account.is_mock_mode,
            redis=redis,
            db=db,
            user_id=str(user_id),
            account_id=str(account.id),
        )
        result = await fetch_fn(
            app_key=app_key,
            app_secret=app_secret,
            access_token=access_token,
            ticker=ticker,
            is_mock=account.is_mock_mode,
        )
        if result["dps"] > 0 or result["dividend_yield"] > 0:
            logger.info(f"{log_name}_used", ticker=ticker)
            return result
        return None
    except Exception as e:
        logger.warning(f"{log_name}_failed", ticker=ticker, error=str(e))
        return None


async def _get_kis_dividend_fallback(
    ticker: str,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> dict | None:
    """사용자의 KIS 계좌로 국내 종목 배당 정보 조회. KIS 계좌 없거나 데이터 없으면 None 반환."""
    return await _call_kis_dividend_api(ticker, user_id, db, get_domestic_dividend_info, "kis_dividend_fallback")


async def _get_kis_etf_dividend_fallback(
    ticker: str,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> dict | None:
    """국내 ETF 전용 KIS API로 분배율 조회. 자격증명 없거나 데이터 없으면 None 반환."""
    return await _call_kis_dividend_api(
        ticker, user_id, db, get_domestic_etf_dividend_info, "kis_etf_dividend_fallback"
    )


async def _get_kis_credentials(user_id: uuid.UUID, db: AsyncSession) -> dict | None:
    return await get_kis_user_credentials(user_id, db)


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


async def _load_user_overrides(user_id: uuid.UUID, db: AsyncSession) -> dict[tuple[str, str], list[int]]:
    """사용자 ticker 설정에서 배당월 override map 로드."""
    result = await db.execute(select(UserTickerSettings).where(UserTickerSettings.user_id == user_id))
    rows = result.scalars().all()
    return {(row.ticker, row.market): list(row.dividend_months) for row in rows if row.dividend_months}


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


async def get_ticker_dividend_summary(user_id: uuid.UUID, db: AsyncSession) -> list[dict]:
    """종목별 실수령(올해) + 예상 배당금 통합. Redis 24h 캐시."""
    current_year = date.today().year
    cache_key = dividend_ticker_summary_key(user_id, current_year)

    redis = await get_redis()
    cached = await redis.get(cache_key)
    if cached:
        logger.info("dividend_by_ticker_cache_hit", user_id=str(user_id))
        return json.loads(cached)

    result = await db.execute(
        text("""
            SELECT COALESCE(ticker, '__unclassified__') AS ticker_key, SUM(amount) AS total
            FROM transactions
            WHERE user_id = :uid
              AND transaction_type = 'DIVIDEND'
              AND EXTRACT(year FROM transaction_date) = :yr
            GROUP BY 1
        """),
        {"uid": str(user_id), "yr": current_year},
    )
    received_map: dict[str, float] = {row.ticker_key: float(row.total) for row in result}

    positions = await _collect_positions(user_id, db)

    name_to_ticker: dict[str, str] = {}
    for (tkr, _mkt), info in positions.items():
        name = info.get("name", "")
        if name and name != tkr:
            name_to_ticker[name] = tkr
    normalized: dict[str, float] = {}
    for key, val in received_map.items():
        normalized_key = name_to_ticker.get(key, key)
        normalized[normalized_key] = normalized.get(normalized_key, 0.0) + val
    received_map = normalized

    overrides = await _load_user_overrides(user_id, db)
    dart_key = await _get_dart_key(user_id, db)
    sem = asyncio.Semaphore(5)
    kis_creds = await _get_kis_credentials(user_id, db)
    usd_krw_rate: float = await get_usd_krw_rate(redis)

    async def _fetch_estimated(ticker: str, market: str, value_krw: float, invested_krw: float, qty: float) -> dict:
        override_months = overrides.get((ticker, market))
        yield_decimal, dps, months, _ = await fetch_ticker_dividend_info(
            ticker, market, redis, sem, kis_creds, dart_key, overrides
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
        _fetch_estimated(ticker, market, info["value_krw"], info["invested_krw"], info.get("qty", 0.0))  # noqa: E501
        for (ticker, market), info in positions.items()
    ]
    estimated_results = await asyncio.gather(*tasks, return_exceptions=True)

    estimated_map: dict[tuple[str, str], dict] = {}
    for item in estimated_results:
        if isinstance(item, Exception):
            logger.warning("dividend_estimate_fetch_failed", error=str(item))
            continue
        assert isinstance(item, dict)
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

    has_yield = any(item.get("investment_yield", 0) > 0 for item in output)
    ttl = TTL_DIVIDEND_INFO if has_yield else TTL_DART
    await redis.setex(cache_key, ttl, json.dumps(output))
    logger.info("dividend_by_ticker_computed", user_id=str(user_id), count=len(output))
    return output


async def get_position_dividend_yields(user_id: uuid.UUID, db: AsyncSession) -> list[dict]:
    """보유 종목별 배당수익률과 예상 배당금을 반환한다."""
    positions = await _collect_positions(user_id, db)
    overrides = await _load_user_overrides(user_id, db)
    dart_key = await _get_dart_key(user_id, db)
    kis_creds = await _get_kis_credentials(user_id, db)

    sem = asyncio.Semaphore(5)
    redis = await get_redis()

    async def fetch_one(ticker: str, market: str, value_krw: float, invested_krw: float, qty: float) -> dict:
        override_months = overrides.get((ticker, market))
        yield_decimal, dps, months, ex_dividend_date = await fetch_ticker_dividend_info(
            ticker, market, redis, sem, kis_creds, dart_key, overrides
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
        assert isinstance(item, dict)
        results.append(item)
    return results


# ── ticker 설정 CRUD ───────────────────────────────────────


async def get_ticker_settings(user_id: uuid.UUID, ticker: str, market: str, db: AsyncSession) -> dict | None:
    row = await db.scalar(
        select(UserTickerSettings).where(
            UserTickerSettings.user_id == user_id,
            UserTickerSettings.ticker == ticker,
            UserTickerSettings.market == market,
        )
    )
    if not row:
        return None
    return {
        "ticker": row.ticker,
        "market": row.market,
        "dividend_months": list(row.dividend_months or []),
        "is_manual": True,
    }


async def upsert_ticker_settings(
    user_id: uuid.UUID, ticker: str, market: str, dividend_months: list[int], db: AsyncSession
) -> dict:
    stmt = (
        pg_insert(UserTickerSettings)
        .values(user_id=user_id, ticker=ticker, market=market, dividend_months=dividend_months)
        .on_conflict_do_update(
            constraint="uq_user_ticker_settings",
            set_={"dividend_months": dividend_months, "updated_at": func.now()},
        )
    )
    await db.execute(stmt)
    await db.commit()

    redis = await get_redis()
    current_year = date.today().year
    await redis.delete(dividend_ticker_summary_key(user_id, current_year))
    await redis.delete(dividend_info_key(ticker, market))
    logger.info("ticker_settings_upserted", user_id=str(user_id), ticker=ticker, market=market)

    return {
        "ticker": ticker,
        "market": market,
        "dividend_months": dividend_months,
        "is_manual": True,
    }


async def delete_ticker_settings(user_id: uuid.UUID, ticker: str, market: str, db: AsyncSession) -> bool:
    row = await db.scalar(
        select(UserTickerSettings).where(
            UserTickerSettings.user_id == user_id,
            UserTickerSettings.ticker == ticker,
            UserTickerSettings.market == market,
        )
    )
    if not row:
        return False
    await db.delete(row)
    await db.commit()

    redis = await get_redis()
    current_year = date.today().year
    await redis.delete(dividend_ticker_summary_key(user_id, current_year))
    await redis.delete(dividend_months_key(ticker, market))
    await redis.delete(dividend_info_key(ticker, market))
    logger.info("ticker_settings_deleted", user_id=str(user_id), ticker=ticker, market=market)

    return True
