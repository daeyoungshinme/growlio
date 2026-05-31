"""현재가 조회 서비스.

우선순위:
  1. Yahoo Finance (API 키 불필요 — 국내·해외 모두 지원, ~15분 지연)
  2. KIS API (설정된 경우, 실시간)

Yahoo Finance 티커 변환:
  KOSPI  005930  →  005930.KS
  KOSDAQ 035720  →  035720.KQ
  NYSE/NASDAQ AAPL → AAPL
"""

from __future__ import annotations

import asyncio
import uuid
from functools import partial

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import AssetAccount
from app.services.credential_service import decrypt

logger = structlog.get_logger()

DOMESTIC_MARKETS = {"KOSPI", "KOSDAQ", "KRX"}

_yfinance_sem = asyncio.Semaphore(5)


def _sync_usdkrw() -> float:
    """동기 함수 — run_in_executor로 호출. 실패 시 0.0 반환."""
    import yfinance as yf
    try:
        hist = yf.Ticker("USDKRW=X").history(period="5d")
        if not hist.empty:
            rate = float(hist["Close"].iloc[-1])
            if rate > 0:
                return rate
    except Exception as e:
        logger.warning("usdkrw_fetch_failed", error=str(e))
    return 0.0


# ── Yahoo Finance 변환 ──────────────────────────────────

def _to_yahoo_symbol(ticker: str, market: str) -> str:
    m = market.upper()
    if m in ("KOSPI", "KRX"):
        return f"{ticker.zfill(6)}.KS"
    if m == "KOSDAQ":
        return f"{ticker.zfill(6)}.KQ"
    return ticker  # 해외: AAPL, TSLA 등 그대로


def _sync_yahoo_price(ticker: str, market: str) -> float | None:
    """동기 함수 — run_in_executor로 호출."""
    import yfinance as yf
    sym = _to_yahoo_symbol(ticker, market)
    try:
        hist = yf.Ticker(sym).history(period="5d")
        if not hist.empty:
            price = float(hist["Close"].iloc[-1])
            return price if price > 0 else None
    except Exception as e:
        logger.warning("yahoo_price_failed", ticker=ticker, symbol=sym, error=str(e))
    return None


def _sync_yahoo_batch(items: list[tuple[str, str]]) -> dict[str, float]:
    """여러 종목을 한 번의 download 호출로 조회. {ticker: price}"""
    import yfinance as yf
    if not items:
        return {}

    sym_map = {_to_yahoo_symbol(t, m): t for t, m in items}
    symbols = list(sym_map.keys())

    try:
        data = yf.download(
            symbols,
            period="5d",
            auto_adjust=True,
            progress=False,
            threads=False,
        )
        close = data.get("Close")
        if close is None or (hasattr(close, "empty") and close.empty):
            return {}

        # yfinance 1.3+ 에서 단일·복수 모두 DataFrame으로 반환
        result: dict[str, float] = {}
        for sym, orig in sym_map.items():
            try:
                col = close[sym].dropna()
                if not col.empty:
                    val = float(col.iloc[-1])
                    if val > 0:
                        result[orig] = val
            except (KeyError, IndexError, ValueError):
                pass
        return result
    except Exception as e:
        logger.warning("yahoo_batch_failed", error=str(e))
        return {}


# ── 공개 API ───────────────────────────────────────────

async def fetch_current_price(
    user_id: uuid.UUID,
    ticker: str,
    market: str,
    db: AsyncSession,
    redis=None,
) -> float | None:
    """단일 종목 현재가 조회.
    Yahoo Finance → KIS 순으로 시도한다.
    """
    loop = asyncio.get_running_loop()

    # 1. Yahoo Finance (항상 시도)
    async with _yfinance_sem:
        price = await loop.run_in_executor(None, partial(_sync_yahoo_price, ticker, market))
    if price:
        return price

    # 2. KIS API fallback (KIS 계좌가 있는 경우)
    account = await _get_any_kis_account(user_id, db)
    if account:
        try:
            price = await _price_via_kis(account, ticker, market, db, redis)
            if price:
                return price
        except Exception as e:
            logger.warning("kis_price_failed", ticker=ticker, error=str(e))

    return None


async def fetch_prices_batch(
    user_id: uuid.UUID,
    tickers: list[tuple[str, str]],  # [(ticker, market), ...]
    db: AsyncSession,
    redis=None,
) -> dict[str, float]:
    """여러 종목 현재가를 한 번에 조회. {ticker: price}

    Yahoo Finance 배치 조회 후, 실패한 종목만 KIS로 보완한다.
    """
    if not tickers:
        return {}

    loop = asyncio.get_running_loop()

    # 1. Yahoo Finance 배치 (단일 네트워크 요청)
    async with _yfinance_sem:
        price_map: dict[str, float] = await loop.run_in_executor(
            None, partial(_sync_yahoo_batch, tickers)
        )

    # 2. 조회 실패한 종목만 KIS API로 보완 (KIS 계좌가 있는 경우)
    missing = [(t, m) for t, m in tickers if t not in price_map or price_map[t] == 0]
    if missing:
        account = await _get_any_kis_account(user_id, db)
        if account:
            fallback_tasks = [
                _fetch_fallback(account, ticker, market, db, redis)
                for ticker, market in missing
            ]
            results = await asyncio.gather(*fallback_tasks, return_exceptions=True)
            for (ticker, _), result in zip(missing, results):
                if isinstance(result, (int, float)) and result > 0:
                    price_map[ticker] = float(result)

    return price_map


# ── 내부 헬퍼 ──────────────────────────────────────────

async def _get_any_kis_account(user_id: uuid.UUID, db: AsyncSession) -> AssetAccount | None:
    """유저의 활성 KIS 계좌 중 자격증명이 있는 첫 번째 계좌를 반환."""
    return await db.scalar(
        select(AssetAccount).where(
            AssetAccount.user_id == user_id,
            AssetAccount.data_source == "KIS_API",
            AssetAccount.is_active == True,  # noqa: E712
            AssetAccount.kis_app_key != None,  # noqa: E711
        )
    )


async def _fetch_fallback(account: AssetAccount, ticker: str, market: str, db, redis) -> float | None:
    try:
        price = await _price_via_kis(account, ticker, market, db, redis)
        if price:
            return price
    except Exception as e:
        logger.warning("kis_price_fallback_failed", ticker=ticker, error=str(e))
    return None


async def _price_via_kis(account: AssetAccount, ticker: str, market: str, db, redis) -> float | None:
    from app.kis.auth import get_access_token

    app_key = decrypt(account.kis_app_key)
    app_secret = decrypt(account.kis_app_secret)
    is_mock = account.is_mock_mode
    token = await get_access_token(
        app_key, app_secret,
        is_mock=is_mock, redis=redis, db=db,
        user_id=str(account.user_id),
        account_id=str(account.id),
    )
    if market in DOMESTIC_MARKETS:
        from app.kis.domestic_quote import get_domestic_price
        return await get_domestic_price(app_key, app_secret, token, ticker, is_mock=is_mock)
    else:
        from app.kis.overseas_quote import get_overseas_price
        result = await get_overseas_price(app_key, app_secret, token, ticker, market, is_mock=is_mock)
        return float(result.get("price", 0)) or None


# ── 역사적 수익률 ───────────────────────────────────────

def _sync_calc_return(ticker: str, market: str, years: int = 10) -> dict | None:
    """동기 함수 — run_in_executor로 호출. yfinance로 N년 수익률 계산."""
    import yfinance as yf
    from datetime import date

    sym = _to_yahoo_symbol(ticker, market)
    end = date.today()
    try:
        start = end.replace(year=end.year - years)
    except ValueError:
        start = end.replace(year=end.year - years, day=28)

    try:
        hist = yf.Ticker(sym).history(start=start.isoformat(), end=end.isoformat(), auto_adjust=True)
        if hist.empty:
            return None

        close = hist["Close"].dropna()
        if len(close) < 2:
            return None

        start_price = float(close.iloc[0])
        end_price = float(close.iloc[-1])
        if start_price <= 0:
            return None

        actual_years = (close.index[-1] - close.index[0]).days / 365.25
        if actual_years < 0.1:
            return None

        cumulative = (end_price / start_price - 1) * 100
        cagr = ((end_price / start_price) ** (1 / actual_years) - 1) * 100
        return {
            "cumulative_return_pct": round(cumulative, 2),
            "cagr_pct": round(cagr, 2),
            "actual_years": round(actual_years, 1),
        }
    except Exception as e:
        logger.warning("historical_return_failed", ticker=ticker, symbol=sym, error=str(e))
        return None


async def get_historical_returns(
    tickers: list[tuple[str, str]],
    redis=None,
    years: int = 10,
) -> dict[tuple[str, str], dict]:
    """각 종목의 최근 N년 누적/연환산 수익률을 반환한다.

    Returns: {(ticker, market): {cumulative_return_pct, cagr_pct, actual_years}}
    """
    if not tickers:
        return {}

    import json

    loop = asyncio.get_running_loop()
    sem = asyncio.Semaphore(5)

    async def _get_one(ticker: str, market: str) -> dict | None:
        cache_key = f"return:{years}y:{ticker}:{market}"
        if redis:
            try:
                cached = await redis.get(cache_key)
                if cached:
                    return json.loads(cached)
            except Exception:
                pass

        async with sem:
            result = await loop.run_in_executor(
                None, partial(_sync_calc_return, ticker, market, years)
            )

        if result and redis:
            try:
                await redis.setex(cache_key, 86400, json.dumps(result))
            except Exception:
                pass

        return result

    tasks = [_get_one(ticker, market) for ticker, market in tickers]
    raw = await asyncio.gather(*tasks, return_exceptions=True)

    return_map: dict[tuple[str, str], dict] = {}
    for (ticker, market), res in zip(tickers, raw):
        if isinstance(res, dict):
            return_map[(ticker, market)] = res

    return return_map
