"""배당금 집계 및 예상 배당금 계산 서비스."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import date
from functools import partial

import structlog
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.kis.auth import get_access_token
from app.kis.domestic_quote import get_domestic_dividend_info, get_domestic_etf_dividend_info
from app.models.asset import AssetAccount, AssetSnapshot, Transaction, UserTickerSettings
from app.models.user import UserSettings
from app.redis_client import get_redis
from app.services.credential_service import decrypt, get_kis_user_credentials
from app.services.dart_service import fetch_dart_dividend
from app.services.dividend_constants import (
    KNOWN_DIVIDEND_INFO,
    KNOWN_DIVIDEND_SCHEDULES,
    is_korean_etf,
)
from app.services.dividend_providers import (
    sync_fdr_etf_dividend_info,
    sync_fetch_dividend_months,
    sync_naver_etf_dividend_info,
    sync_naver_stock_dividend_info,
    sync_pykrx_etf_dividend_info,
    sync_yahoo_dividend_info,
)
from app.services.price_service import _to_yahoo_symbol
from app.utils.currency import get_usd_krw_rate

logger = structlog.get_logger()


async def get_dividend_summary(user_id: uuid.UUID, db: AsyncSession) -> dict:
    current_year = date.today().year

    annual_received = await _sum_transactions(user_id, db, "DIVIDEND", current_year)
    monthly_breakdown = await _monthly_dividend_breakdown(user_id, db, current_year)
    monthly_ticker_breakdown = await _monthly_dividend_ticker_breakdown(user_id, db, current_year)

    # 종목별 테이블과 동일한 소스 사용 → StatBox와 per-ticker 합산 일치 보장 + Redis 캐시 재사용
    ticker_summaries = await get_ticker_dividend_summary(user_id, db)
    estimated_annual = sum(
        item["estimated_annual_krw"]
        for item in ticker_summaries
        if item.get("estimated_annual_krw", 0) > 0
    )

    return {
        "annual_received": annual_received,
        "monthly_breakdown": monthly_breakdown,
        "monthly_ticker_breakdown": monthly_ticker_breakdown,
        "estimated_annual": estimated_annual,
    }


async def _sum_transactions(user_id: uuid.UUID, db: AsyncSession, tx_type: str, year: int) -> float:
    result = await db.execute(
        select(func.sum(Transaction.amount)).where(
            Transaction.user_id == user_id,
            Transaction.transaction_type == tx_type,
            func.extract("year", Transaction.transaction_date) == year,
        )
    )
    return float(result.scalar() or 0)


async def _monthly_dividend_breakdown(user_id: uuid.UUID, db: AsyncSession, year: int) -> list[dict]:
    result = await db.execute(
        text("""
            SELECT to_char(transaction_date, 'YYYY-MM') AS month, SUM(amount) AS total
            FROM transactions
            WHERE user_id = :uid
              AND transaction_type = 'DIVIDEND'
              AND EXTRACT(year FROM transaction_date) = :yr
            GROUP BY 1
            ORDER BY 1
        """),
        {"uid": str(user_id), "yr": year},
    )
    return [{"month": row.month, "amount": float(row.total)} for row in result]


async def _monthly_dividend_ticker_breakdown(user_id: uuid.UUID, db: AsyncSession, year: int) -> list[dict]:
    result = await db.execute(
        text("""
            SELECT to_char(transaction_date, 'YYYY-MM') AS month,
                   ticker,
                   SUM(amount) AS total
            FROM transactions
            WHERE user_id = :uid
              AND transaction_type = 'DIVIDEND'
              AND EXTRACT(year FROM transaction_date) = :yr
            GROUP BY 1, 2
            ORDER BY 1, 2
        """),
        {"uid": str(user_id), "yr": year},
    )
    return [{"month": row.month, "ticker": row.ticker, "amount": float(row.total)} for row in result]


async def _get_dart_key(user_id: uuid.UUID, db: AsyncSession) -> str:
    """user_settings에서 DART API 키 조회 및 복호화. 없으면 config 기본값 사용."""
    row = await db.scalar(select(UserSettings).where(UserSettings.user_id == user_id))
    if row and row.dart_api_key:
        return decrypt(row.dart_api_key)
    return settings.dart_api_key


async def _get_kis_dividend_fallback(
    ticker: str,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> dict | None:
    """사용자의 KIS 계좌로 국내 종목 배당 정보 조회. KIS 계좌 없거나 데이터 없으면 None 반환."""
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
        result = await get_domestic_dividend_info(
            app_key=app_key,
            app_secret=app_secret,
            access_token=access_token,
            ticker=ticker,
            is_mock=account.is_mock_mode,
        )
        if result["dps"] > 0 or result["dividend_yield"] > 0:
            logger.info("kis_dividend_fallback_used", ticker=ticker)
            return result
        return None
    except Exception as e:
        logger.warning("kis_dividend_fallback_failed", ticker=ticker, error=str(e))
        return None


async def _get_kis_etf_dividend_fallback(
    ticker: str,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> dict | None:
    """국내 ETF 전용 KIS API(FHPET01010000)로 분배율 조회. 자격증명 없거나 데이터 없으면 None 반환."""
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
        result = await get_domestic_etf_dividend_info(
            app_key=app_key,
            app_secret=app_secret,
            access_token=access_token,
            ticker=ticker,
            is_mock=account.is_mock_mode,
        )
        if result["dps"] > 0 or result["dividend_yield"] > 0:
            logger.info("kis_etf_dividend_fallback_used", ticker=ticker)
            return result
        return None
    except Exception as e:
        logger.warning("kis_etf_dividend_fallback_failed", ticker=ticker, error=str(e))
        return None


async def _get_kis_credentials(user_id: uuid.UUID, db: AsyncSession) -> dict | None:
    return await get_kis_user_credentials(user_id, db)



async def _collect_positions(user_id: uuid.UUID, db: AsyncSession) -> dict[tuple[str, str], float]:
    """활성 주식 계좌의 최신 스냅샷에서 (ticker, market) → value_krw 수집."""
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
        .join(subq, (AssetSnapshot.account_id == subq.c.account_id) & (AssetSnapshot.snapshot_date == subq.c.max_date))
        .join(AssetAccount, AssetAccount.id == AssetSnapshot.account_id)
        .where(
            AssetAccount.is_active == True,  # noqa: E712
            AssetAccount.asset_type.like("STOCK%"),
        )
    )
    rows = result.all()

    positions_map: dict[tuple[str, str], float] = {}
    for snap, _acc in rows:
        if not snap.positions:
            continue
        pos_list = snap.positions if isinstance(snap.positions, list) else []
        for p in pos_list:
            ticker = p.get("ticker", "")
            market = (p.get("market") or "KOSPI").upper()
            raw_value_krw = p.get("value_krw")
            if raw_value_krw and float(raw_value_krw) > 0:
                value = float(raw_value_krw)
            else:
                qty = float(p.get("qty") or 0)
                price = float(p.get("current_price") or p.get("avg_price") or 0)
                value = qty * price if qty > 0 and price > 0 else float(p.get("value_usd") or 0)
            if ticker and value > 0:
                key = (ticker, market)
                positions_map[key] = positions_map.get(key, 0) + value

    return positions_map


async def _collect_positions_with_names(user_id: uuid.UUID, db: AsyncSession) -> dict[tuple[str, str], dict]:
    """최신 스냅샷에서 (ticker, market) → {value_krw, name, invested_krw} 수집."""
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
        if not snap.positions:
            continue
        pos_list = snap.positions if isinstance(snap.positions, list) else []
        for p in pos_list:
            ticker = p.get("ticker", "")
            market = (p.get("market") or "KOSPI").upper()
            name = p.get("name", ticker)
            raw_value_krw = p.get("value_krw")
            if raw_value_krw and float(raw_value_krw) > 0:
                value = float(raw_value_krw)
            else:
                qty = float(p.get("qty") or 0)
                price = float(p.get("current_price") or p.get("avg_price") or 0)
                value = qty * price if qty > 0 and price > 0 else float(p.get("value_usd") or 0)
            raw_invested = p.get("invested_krw")
            if raw_invested and float(raw_invested) > 0:
                invested = float(raw_invested)
            else:
                invested = float(p.get("avg_price") or 0) * float(p.get("qty") or 0)
            if ticker and value > 0:
                key = (ticker, market)
                if key not in positions_map:
                    positions_map[key] = {"value_krw": 0.0, "name": name, "invested_krw": 0.0, "qty": 0.0}
                positions_map[key]["value_krw"] += value
                positions_map[key]["invested_krw"] += invested
                positions_map[key]["qty"] += float(p.get("qty") or 0)

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
    cache_key = f"dividend:by-ticker:{user_id}:{current_year}"

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

    positions = await _collect_positions_with_names(user_id, db)

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
        yahoo_sym = _to_yahoo_symbol(ticker, market)
        yield_decimal = 0.0
        dps = 0.0
        naver_info: dict = {"dps": 0.0, "dividend_yield": 0.0, "dividend_months": []}

        # 배당월: override > 정적 스케줄 > Redis 캐시 > yfinance
        override_months = overrides.get((ticker, market))
        months: list[int]
        need_months_fetch: bool
        if override_months is not None:
            months = override_months
            need_months_fetch = False
        else:
            known = KNOWN_DIVIDEND_SCHEDULES.get((ticker, market.upper()))
            if known is not None:
                months = known
                need_months_fetch = False
            else:
                months = []
                need_months_fetch = True
        months_cache_key = f"dividend:months:{ticker}:{market}"
        info_cache_key = f"dividend:info:{ticker}:{market}"

        if need_months_fetch:
            cached_months = await redis.get(months_cache_key)
            if cached_months:
                months = json.loads(cached_months)
                need_months_fetch = False

        if dps == 0.0 or yield_decimal == 0.0:
            cached_info = await redis.get(info_cache_key)
            if cached_info:
                cached = json.loads(cached_info)
                if dps == 0.0:
                    dps = cached["dps"]
                if yield_decimal == 0.0:
                    yield_decimal = cached["yield_decimal"]

        async with sem:
            is_etf = is_korean_etf(ticker, market)

            # 0순위: Naver Finance (국내 종목 전용, 인증 불필요)
            # ETF: etfAnalysis API (DPS + yield + 배당월)
            # 일반주식: summary API (yield만 제공 — DPS는 이후 yfinance/KIS/DART에서 보완)
            if is_korean:
                if is_etf:
                    naver_info = await loop.run_in_executor(
                        None, partial(sync_naver_etf_dividend_info, ticker)
                    )
                else:
                    naver_info = await loop.run_in_executor(
                        None, partial(sync_naver_stock_dividend_info, ticker)
                    )
                if naver_info["dps"] > 0:
                    dps = naver_info["dps"]
                if naver_info["dividend_yield"] > 0:
                    yield_decimal = naver_info["dividend_yield"]
                if need_months_fetch and naver_info["dividend_months"]:
                    months = naver_info["dividend_months"]
                    need_months_fetch = False

            # 1순위: yfinance (국내/해외 공통)
            if dps == 0.0 or yield_decimal == 0.0:
                info = await loop.run_in_executor(None, partial(sync_yahoo_dividend_info, yahoo_sym))
                if info["dividend_yield"] > 0 and yield_decimal == 0.0:
                    yield_decimal = info["dividend_yield"]
                if info["dps"] > 0 and dps == 0.0:
                    dps = info["dps"]

            # 2순위 (ETF): KIS ETF 전용 API (FHPET01010000) — 실시간 분배율
            if is_korean and is_etf and (dps == 0.0 or yield_decimal == 0.0) and kis_creds:
                try:
                    kis_etf_info = await get_domestic_etf_dividend_info(
                        app_key=kis_creds["app_key"],
                        app_secret=kis_creds["app_secret"],
                        access_token=kis_creds["access_token"],
                        ticker=ticker,
                        is_mock=kis_creds["is_mock"],
                    )
                    if kis_etf_info["dps"] > 0 or kis_etf_info["dividend_yield"] > 0:
                        logger.info("kis_etf_dividend_fallback_used", ticker=ticker)
                        if dps == 0.0 and kis_etf_info["dps"] > 0:
                            dps = kis_etf_info["dps"]
                        if yield_decimal == 0.0 and kis_etf_info["dividend_yield"] > 0:
                            yield_decimal = kis_etf_info["dividend_yield"]
                except Exception as e:
                    logger.warning("kis_etf_dividend_fallback_failed", ticker=ticker, error=str(e))

            # 3순위: pykrx (국내 — 연간 DPS 합산 방식)
            if is_korean and (dps == 0.0 or yield_decimal == 0.0):
                pykrx_info = await loop.run_in_executor(None, partial(sync_pykrx_etf_dividend_info, ticker))
                if pykrx_info["dps"] > 0 and dps == 0.0:
                    dps = pykrx_info["dps"]
                if pykrx_info["dividend_yield"] > 0 and yield_decimal == 0.0:
                    yield_decimal = pykrx_info["dividend_yield"]

            # 3.5순위: FinanceDataReader ETF (국내 ETF — pykrx 실패 시 fallback)
            if is_korean and is_etf and (dps == 0.0 or yield_decimal == 0.0):
                fdr_info = await loop.run_in_executor(None, partial(sync_fdr_etf_dividend_info, ticker))
                if fdr_info["dps"] > 0 and dps == 0.0:
                    dps = fdr_info["dps"]
                if fdr_info["dividend_yield"] > 0 and yield_decimal == 0.0:
                    yield_decimal = fdr_info["dividend_yield"]

            # 4순위: KIS API 일반주식 (ETF 아닌 종목 또는 위 소스 모두 실패 시)
            if is_korean and (dps == 0.0 or yield_decimal == 0.0) and kis_creds:
                try:
                    kis_info = await get_domestic_dividend_info(
                        app_key=kis_creds["app_key"],
                        app_secret=kis_creds["app_secret"],
                        access_token=kis_creds["access_token"],
                        ticker=ticker,
                        is_mock=kis_creds["is_mock"],
                    )
                    if kis_info["dps"] > 0 or kis_info["dividend_yield"] > 0:
                        logger.info("kis_dividend_fallback_used", ticker=ticker)
                        if dps == 0.0 and kis_info["dps"] > 0:
                            dps = kis_info["dps"]
                        if yield_decimal == 0.0 and kis_info["dividend_yield"] > 0:
                            yield_decimal = kis_info["dividend_yield"]
                except Exception as e:
                    logger.warning("kis_dividend_fallback_failed", ticker=ticker, error=str(e))

            # 5순위: DART (국내 종목이고 여전히 데이터 없을 때)
            if is_korean and yield_decimal == 0.0:
                dart = await fetch_dart_dividend(ticker, api_key=dart_key)
                if dart:
                    yield_decimal = dart["dividend_yield"]
                    if dps == 0.0:
                        dps = dart["dps"]

            # 6순위: 정적 폴백 (위 소스 모두 실패 시)
            if is_korean and dps == 0.0 and yield_decimal == 0.0:
                known_info = KNOWN_DIVIDEND_INFO.get((ticker, market.upper()))
                if known_info:
                    dps, yield_decimal = known_info
                    logger.info("known_dividend_info_used", ticker=ticker, market=market, dps=dps, yield_decimal=yield_decimal)

            if need_months_fetch:
                months = await loop.run_in_executor(None, partial(sync_fetch_dividend_months, yahoo_sym))

        if need_months_fetch:
            await redis.setex(months_cache_key, 604800, json.dumps(months))  # 7일 캐시

        if dps > 0 or yield_decimal > 0:
            await redis.setex(info_cache_key, 86400, json.dumps({"dps": dps, "yield_decimal": yield_decimal}))

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
            # ETF는 소스별 DPS 단위가 혼용되므로 yield 기반으로 통일
            annual = value_krw * yield_decimal
            investment_yield = (
                round(annual / invested_krw * 100, 2) if (invested_krw > 0 and yield_decimal > 0)
                else round(yield_decimal * 100, 2)
            )

        is_usd = not is_korean
        estimated_monthly_usd = (
            round(annual / 12 / usd_krw_rate, 2)
            if (is_usd and annual > 0 and usd_krw_rate > 0)
            else None
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
    positions = await _collect_positions_with_names(user_id, db)
    overrides = await _load_user_overrides(user_id, db)
    dart_key = await _get_dart_key(user_id, db)

    # KIS 인증 정보 사전 조회 (동시 태스크에서 DB 세션 공유 방지)
    kis_creds = await _get_kis_credentials(user_id, db)

    sem = asyncio.Semaphore(5)
    redis = await get_redis()

    async def fetch_one(ticker: str, market: str, value_krw: float, invested_krw: float, qty: float) -> dict:
        is_korean = market.upper() in ("KOSPI", "KOSDAQ", "KRX")
        is_etf = is_korean_etf(ticker, market)
        yahoo_sym = _to_yahoo_symbol(ticker, market)
        yield_decimal = 0.0
        dps = 0.0
        ex_dividend_date = None

        # 배당월: override > 정적 스케줄 > Redis 캐시 > yfinance
        override_months = overrides.get((ticker, market))
        months: list[int]
        need_months_fetch: bool
        if override_months is not None:
            months = override_months
            need_months_fetch = False
        else:
            known = KNOWN_DIVIDEND_SCHEDULES.get((ticker, market.upper()))
            if known is not None:
                months = known
                need_months_fetch = False
            else:
                months = []
                need_months_fetch = True
        months_cache_key = f"dividend:months:{ticker}:{market}"
        info_cache_key = f"dividend:info:{ticker}:{market}"

        if need_months_fetch:
            cached_months = await redis.get(months_cache_key)
            if cached_months:
                months = json.loads(cached_months)
                need_months_fetch = False

        async with sem:
            loop = asyncio.get_running_loop()

            # 0순위: Naver Finance etfAnalysis (국내 종목 전용, 캐시와 무관하게 항상 먼저 시도)
            if is_korean:
                naver_info = await loop.run_in_executor(
                    None, partial(sync_naver_etf_dividend_info, ticker)
                )
                if naver_info["dps"] > 0:
                    dps = naver_info["dps"]
                if naver_info["dividend_yield"] > 0:
                    yield_decimal = naver_info["dividend_yield"]
                if need_months_fetch and naver_info["dividend_months"]:
                    months = naver_info["dividend_months"]
                    need_months_fetch = False

        # Naver로 dps·yield 모두 채워졌으면 나머지 소스 생략, 아니면 캐시 → yfinance/KIS/pykrx 순서
        if dps == 0.0 or yield_decimal == 0.0:
            cached_info = await redis.get(info_cache_key)
            if cached_info:
                cached = json.loads(cached_info)
                if dps == 0.0:
                    dps = cached["dps"]
                if yield_decimal == 0.0:
                    yield_decimal = cached["yield_decimal"]
                if need_months_fetch:
                    async with sem:
                        loop = asyncio.get_running_loop()
                        months = await loop.run_in_executor(None, partial(sync_fetch_dividend_months, yahoo_sym))
                    need_months_fetch = False
                    await redis.setex(months_cache_key, 604800, json.dumps(months))

        if dps == 0.0 or yield_decimal == 0.0:
            async with sem:
                loop = asyncio.get_running_loop()

                # 1순위: yfinance (국내/해외 공통)
                if dps == 0.0 or yield_decimal == 0.0:
                    info = await loop.run_in_executor(None, partial(sync_yahoo_dividend_info, yahoo_sym))
                    if info["dividend_yield"] > 0 and yield_decimal == 0.0:
                        yield_decimal = info["dividend_yield"]
                    if info["dps"] > 0 and dps == 0.0:
                        dps = info["dps"]
                    ex_dividend_date = info["ex_dividend_date"]

                # 2순위 (ETF): KIS ETF 전용 API (FHPET01010000) — 실시간 분배율
                if is_korean and is_etf and (dps == 0.0 or yield_decimal == 0.0) and kis_creds:
                    try:
                        kis_etf_info = await get_domestic_etf_dividend_info(
                            app_key=kis_creds["app_key"],
                            app_secret=kis_creds["app_secret"],
                            access_token=kis_creds["access_token"],
                            ticker=ticker,
                            is_mock=kis_creds["is_mock"],
                        )
                        if kis_etf_info["dps"] > 0 or kis_etf_info["dividend_yield"] > 0:
                            logger.info("kis_etf_dividend_fallback_used", ticker=ticker)
                            if dps == 0.0 and kis_etf_info["dps"] > 0:
                                dps = kis_etf_info["dps"]
                            if yield_decimal == 0.0 and kis_etf_info["dividend_yield"] > 0:
                                yield_decimal = kis_etf_info["dividend_yield"]
                    except Exception as e:
                        logger.warning("kis_etf_dividend_fallback_failed", ticker=ticker, error=str(e))

                # 3순위: pykrx (국내 — 연간 DPS 합산 방식)
                if is_korean and (dps == 0.0 or yield_decimal == 0.0):
                    pykrx_info = await loop.run_in_executor(None, partial(sync_pykrx_etf_dividend_info, ticker))
                    if pykrx_info["dps"] > 0 and dps == 0.0:
                        dps = pykrx_info["dps"]
                    if pykrx_info["dividend_yield"] > 0 and yield_decimal == 0.0:
                        yield_decimal = pykrx_info["dividend_yield"]

                # 3.5순위: FinanceDataReader ETF (국내 ETF — pykrx 실패 시 fallback)
                if is_korean and is_etf and (dps == 0.0 or yield_decimal == 0.0):
                    fdr_info = await loop.run_in_executor(None, partial(sync_fdr_etf_dividend_info, ticker))
                    if fdr_info["dps"] > 0 and dps == 0.0:
                        dps = fdr_info["dps"]
                    if fdr_info["dividend_yield"] > 0 and yield_decimal == 0.0:
                        yield_decimal = fdr_info["dividend_yield"]

                # 4순위: KIS API 일반주식 (ETF 아닌 종목 또는 위 소스 모두 실패 시)
                if is_korean and (dps == 0.0 or yield_decimal == 0.0) and kis_creds:
                    try:
                        kis_info = await get_domestic_dividend_info(
                            app_key=kis_creds["app_key"],
                            app_secret=kis_creds["app_secret"],
                            access_token=kis_creds["access_token"],
                            ticker=ticker,
                            is_mock=kis_creds["is_mock"],
                        )
                        if kis_info["dps"] > 0 or kis_info["dividend_yield"] > 0:
                            logger.info("kis_dividend_fallback_used", ticker=ticker)
                            if dps == 0.0 and kis_info["dps"] > 0:
                                dps = kis_info["dps"]
                            if yield_decimal == 0.0 and kis_info["dividend_yield"] > 0:
                                yield_decimal = kis_info["dividend_yield"]
                    except Exception as e:
                        logger.warning("kis_dividend_fallback_failed", ticker=ticker, error=str(e))

                # 5순위: DART (국내 종목이고 여전히 데이터 없을 때)
                if is_korean and yield_decimal == 0.0:
                    dart = await fetch_dart_dividend(ticker, api_key=dart_key)
                    if dart:
                        yield_decimal = dart["dividend_yield"]
                        if dps == 0.0:
                            dps = dart["dps"]

                # 6순위: 정적 폴백 (위 소스 모두 실패 시)
                if is_korean and dps == 0.0 and yield_decimal == 0.0:
                    known_info = KNOWN_DIVIDEND_INFO.get((ticker, market.upper()))
                    if known_info:
                        dps, yield_decimal = known_info
                        logger.info("known_dividend_info_used", ticker=ticker, market=market, dps=dps, yield_decimal=yield_decimal)

                if need_months_fetch:
                    months = await loop.run_in_executor(None, partial(sync_fetch_dividend_months, yahoo_sym))
                    need_months_fetch = False

            # dividend info 캐시 저장 (24h) — yfinance/KIS/pykrx 등 비-Naver 소스 결과만 캐시
            if dps > 0 or yield_decimal > 0:
                await redis.setex(info_cache_key, 86400, json.dumps({"dps": dps, "yield_decimal": yield_decimal}))

        # 배당월: Naver·캐시 모두 실패한 경우 yfinance로 최종 조회
        if need_months_fetch:
            async with sem:
                loop = asyncio.get_running_loop()
                months = await loop.run_in_executor(None, partial(sync_fetch_dividend_months, yahoo_sym))
            await redis.setex(months_cache_key, 604800, json.dumps(months))

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
            # ETF는 소스별 DPS 단위가 혼용되므로 yield 기반으로 통일
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
    await redis.delete(f"dividend:by-ticker:{user_id}:{current_year}")
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
    await redis.delete(f"dividend:by-ticker:{user_id}:{current_year}")
    await redis.delete(f"dividend:months:{ticker}:{market}")
    await redis.delete(f"dividend:info:{ticker}:{market}")
    logger.info("ticker_settings_deleted", user_id=str(user_id), ticker=ticker, market=market)

    return True
