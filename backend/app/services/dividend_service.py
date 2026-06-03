"""배당금 예상 조회 및 종목별 배당 데이터 서비스.

트랜잭션 기반 집계(수령액) → dividend_aggregator.py
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
from app.services.credential_service import decrypt, get_kis_user_credentials
from app.services.dividend_constants import KNOWN_DIVIDEND_SCHEDULES as KNOWN_DIVIDEND_SCHEDULES, is_korean_etf
from app.services.dividend_fetcher import fetch_ticker_dividend_info
from app.utils.cache_keys import dividend_ticker_summary_key
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
        app_key = decrypt(account.kis_app_key)
        app_secret = decrypt(account.kis_app_secret)
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
    return await _call_kis_dividend_api(
        ticker, user_id, db, get_domestic_dividend_info, "kis_dividend_fallback"
    )


async def _get_kis_etf_dividend_fallback(
    ticker: str,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> dict | None:
    """국내 ETF 전용 KIS API(FHPET01010000)로 분배율 조회. 자격증명 없거나 데이터 없으면 None 반환."""
    return await _call_kis_dividend_api(
        ticker, user_id, db, get_domestic_etf_dividend_info, "kis_etf_dividend_fallback"
    )


async def _get_kis_credentials(user_id: uuid.UUID, db: AsyncSession) -> dict | None:
    return await get_kis_user_credentials(user_id, db)



async def _collect_positions(user_id: uuid.UUID, db: AsyncSession) -> dict[tuple[str, str], dict]:
    """활성 주식 계좌의 최신 스냅샷에서 (ticker, market) → {value_krw, name, invested_krw, qty} 수집."""
    subq = (
        select(
            AssetSnapshot.account_id,
            func.max(AssetSnapshot.snapshot_date).label("max_date"),
        )
        .where(AssetSnapshot.user_id == user_id)
        .group_by(AssetSnapshot.account_id)
        .subquery()
    )
    result = await db.execute(
        select(AssetSnapshot, AssetAccount)
        .options(selectinload(AssetSnapshot.position_items))
        .join(subq, (AssetSnapshot.account_id == subq.c.account_id) & (AssetSnapshot.snapshot_date == subq.c.max_date))
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
                    positions_map[key] = {"value_krw": 0.0, "name": name, "invested_krw": 0.0, "qty": 0.0}
                positions_map[key]["value_krw"] += value
                positions_map[key]["invested_krw"] += invested
                positions_map[key]["qty"] += float(p.qty or 0)

    return positions_map




async def _load_user_overrides(user_id: uuid.UUID, db: AsyncSession) -> dict[tuple[str, str], list[int]]:
    """사용자 ticker 설정에서 배당월 override map 로드."""
    result = await db.execute(
        select(UserTickerSettings).where(UserTickerSettings.user_id == user_id)
    )
    rows = result.scalars().all()
    return {
        (row.ticker, row.market): list(row.dividend_months)
        for row in rows
        if row.dividend_months
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

    # 실수령 배당금 ticker별 집계
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

    # 거래 기록에 종목명으로 저장된 경우를 종목코드로 정규화
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
    loop = asyncio.get_running_loop()
    kis_creds = await _get_kis_credentials(user_id, db)

    usd_krw_rate: float = await get_usd_krw_rate(redis)

    async def _fetch_estimated(ticker: str, market: str, value_krw: float, invested_krw: float, qty: float) -> dict:
        is_korean = market.upper() in ("KOSPI", "KOSDAQ", "KRX")
        is_etf = is_korean_etf(ticker, market)
        override_months = overrides.get((ticker, market))
        yield_decimal, dps, months, _ = await fetch_ticker_dividend_info(
            ticker, market, redis, sem, loop, kis_creds, dart_key, overrides
        )
        if is_korean and not is_etf and dps > 0 and qty > 0:
            # 국내 일반주식: 연간 합산 DPS 기반
            annual = dps * qty
            cost_per_share = (invested_krw / qty) if (invested_krw > 0) else (value_krw / qty)
            investment_yield = round(dps / cost_per_share * 100, 2) if cost_per_share > 0 else 0.0
            # 비정상적으로 높은 투자배당율 감지 (50% 초과는 데이터 오류)
            if investment_yield > 50.0:
                logger.warning(
                    "investment_yield_abnormal",
                    ticker=ticker, market=market,
                    investment_yield=investment_yield,
                    dps=dps,
                    cost_per_share=cost_per_share,
                    yield_decimal=yield_decimal,
                )
                investment_yield = round(yield_decimal * 100, 2) if yield_decimal > 0 else 0.0
        else:
            # 국내 ETF, 해외 주식/ETF: 연간 분배율(yield) 기반
            annual = value_krw * yield_decimal
            investment_yield = (
                round(annual / invested_krw * 100, 2) if (invested_krw > 0 and yield_decimal > 0)
                else round(yield_decimal * 100, 2)
            )
        is_usd = not is_korean
        estimated_monthly_usd = (
            round(annual / 12 / usd_krw_rate, 2) if (is_usd and annual > 0 and usd_krw_rate > 0) else None
        )
        return {
            "ticker": ticker,
            "market": market,
            "yield_decimal": yield_decimal,
            "dps": round(dps, 2),
            "estimated_annual_krw": round(annual),
            "estimated_monthly_krw": round(annual / 12),
            "dividend_months": months,
            "dividend_months_is_manual": override_months is not None,
            "investment_yield": investment_yield,
            "currency": "USD" if is_usd else "KRW",
            "estimated_monthly_usd": estimated_monthly_usd,
        }

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
        key = (item["ticker"], item.get("market", ""))
        if key not in estimated_map:
            estimated_map[key] = item
        else:
            existing = estimated_map[key]
            existing["estimated_annual_krw"] = (
                existing.get("estimated_annual_krw", 0) + item.get("estimated_annual_krw", 0)
            )
            existing["estimated_monthly_krw"] = (
                existing.get("estimated_monthly_krw", 0) + item.get("estimated_monthly_krw", 0)
            )
            existing["dividend_months"] = sorted(
                set(existing.get("dividend_months", []) + item.get("dividend_months", []))
            )

    ticker_to_est_keys: dict[str, list[tuple[str, str]]] = {}
    for (tkr, mkt) in estimated_map:
        ticker_to_est_keys.setdefault(tkr, []).append((tkr, mkt))

    all_tickers: set[str] = set(received_map.keys()) | set(ticker_to_est_keys.keys())
    output: list[dict] = []

    for ticker_key in all_tickers:
        if ticker_key == "__unclassified__":
            output.append({
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
            })
            continue

        est_keys = ticker_to_est_keys.get(ticker_key, [])
        if est_keys:
            primary_est = estimated_map[est_keys[0]]
            combined_annual = sum(estimated_map[k].get("estimated_annual_krw", 0) for k in est_keys)
            combined_monthly = sum(estimated_map[k].get("estimated_monthly_krw", 0) for k in est_keys)
            combined_months = sorted(set(
                m for k in est_keys for m in estimated_map[k].get("dividend_months", [])
            ))
            market_val = primary_est.get("market")
            yield_decimal = primary_est.get("yield_decimal", 0.0)
            dps = primary_est.get("dps", 0.0)
            investment_yield = primary_est.get("investment_yield", 0.0)
            is_manual = primary_est.get("dividend_months_is_manual", False)
            currency = primary_est.get("currency", "KRW")
            combined_monthly_usd = (
                round(sum(estimated_map[k].get("estimated_monthly_usd") or 0 for k in est_keys), 2)
                if currency == "USD" else None
            )
        else:
            combined_annual = 0
            combined_monthly = 0
            combined_months = []
            market_val = None
            yield_decimal = 0.0
            dps = 0.0
            investment_yield = 0.0
            is_manual = False
            currency = "KRW"
            combined_monthly_usd = None

        pos_entry = next(
            (v for (t, _m), v in positions.items() if t == ticker_key),
            {"name": ticker_key},
        )
        output.append({
            "ticker": ticker_key,
            "name": pos_entry.get("name", ticker_key),
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
        })

    output.sort(key=lambda x: x["estimated_annual_krw"] + x["received_krw"], reverse=True)

    has_yield = any(item.get("investment_yield", 0) > 0 for item in output)
    ttl = 86400 if has_yield else 3600
    await redis.setex(cache_key, ttl, json.dumps(output))
    logger.info("dividend_by_ticker_computed", user_id=str(user_id), count=len(output))
    return output


async def get_position_dividend_yields(user_id: uuid.UUID, db: AsyncSession) -> list[dict]:
    """보유 종목별 배당수익률과 예상 배당금을 반환한다."""
    positions = await _collect_positions(user_id, db)
    overrides = await _load_user_overrides(user_id, db)
    dart_key = await _get_dart_key(user_id, db)

    # KIS 인증 정보 사전 조회 (동시 태스크에서 DB 세션 공유 방지)
    kis_creds = await _get_kis_credentials(user_id, db)

    sem = asyncio.Semaphore(5)
    redis = await get_redis()
    loop = asyncio.get_running_loop()

    async def fetch_one(ticker: str, market: str, value_krw: float, invested_krw: float, qty: float) -> dict:
        is_korean = market.upper() in ("KOSPI", "KOSDAQ", "KRX")
        is_etf = is_korean_etf(ticker, market)
        override_months = overrides.get((ticker, market))
        yield_decimal, dps, months, ex_dividend_date = await fetch_ticker_dividend_info(
            ticker, market, redis, sem, loop, kis_creds, dart_key, overrides
        )
        if is_korean and not is_etf and dps > 0 and qty > 0:
            # 국내 일반주식: 연간 합산 DPS 기반
            annual = dps * qty
            cost_per_share = (invested_krw / qty) if (invested_krw > 0) else (value_krw / qty)
            investment_yield = round(dps / cost_per_share * 100, 2) if cost_per_share > 0 else 0.0
            if investment_yield > 50.0:
                logger.warning(
                    "investment_yield_abnormal",
                    ticker=ticker, market=market,
                    investment_yield=investment_yield, dps=dps,
                    cost_per_share=cost_per_share, yield_decimal=yield_decimal,
                )
                investment_yield = round(yield_decimal * 100, 2) if yield_decimal > 0 else 0.0
        else:
            # 국내 ETF, 해외 주식/ETF: 연간 분배율(yield) 기반
            annual = value_krw * yield_decimal
            investment_yield = (
                round(annual / invested_krw * 100, 2) if (invested_krw > 0 and yield_decimal > 0)
                else round(yield_decimal * 100, 2)
            )
        return {
            "ticker": ticker,
            "market": market,
            "dividend_yield": round(yield_decimal * 100, 2),
            "dps": round(dps, 2),
            "ex_dividend_date": ex_dividend_date,
            "estimated_annual_krw": round(annual),
            "estimated_monthly_krw": round(annual / 12),
            "dividend_months": months,
            "dividend_months_is_manual": override_months is not None,
            "investment_yield": investment_yield,
        }

    tasks = [
        fetch_one(ticker, market, info["value_krw"], info["invested_krw"], info.get("qty", 0.0))
        for (ticker, market), info in positions.items()
    ]
    return list(await asyncio.gather(*tasks))


# ── ticker 설정 CRUD ───────────────────────────────────────

async def get_ticker_settings(
    user_id: uuid.UUID, ticker: str, market: str, db: AsyncSession
) -> dict | None:
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
    await redis.delete(f"dividend:info:{ticker}:{market}")
    logger.info("ticker_settings_upserted", user_id=str(user_id), ticker=ticker, market=market)

    return {"ticker": ticker, "market": market, "dividend_months": dividend_months, "is_manual": True}


async def delete_ticker_settings(
    user_id: uuid.UUID, ticker: str, market: str, db: AsyncSession
) -> bool:
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
    await redis.delete(f"dividend:months:{ticker}:{market}")
    await redis.delete(f"dividend:info:{ticker}:{market}")
    logger.info("ticker_settings_deleted", user_id=str(user_id), ticker=ticker, market=market)

    return True
