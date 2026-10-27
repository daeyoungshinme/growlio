"""리밸런싱 분석용 portfolio overview 보완 로직.

목표 포트폴리오 중 미보유 종목의 배당수익률·현재가를 조회해 overview/dividend_map에
채워 넣는다 — api/v1/rebalancing.py의 analyze_portfolio 엔드포인트 전용 헬퍼.
"""

from __future__ import annotations

import asyncio
import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import is_non_tradable
from app.models.portfolio import Portfolio
from app.services.credential_service import get_kis_user_credentials
from app.services.dividend._dividend_queries import fetch_dart_api_key
from app.services.dividend.fetcher import fetch_ticker_dividend_info
from app.services.price_service import fetch_prices_batch_krw
from app.services.rebalancing.service import _item_attr, _item_get

logger = structlog.get_logger()

_DIVIDEND_FETCH_CONCURRENCY = 8  # yfinance 가격 조회와 별개 I/O이므로 더 높은 동시성 허용


async def collect_dividend_map(
    user_id: uuid.UUID,
    db: AsyncSession,
    cache,
    portfolio: Portfolio,
    base_dividend_map: dict,
) -> dict:
    """목표 포트폴리오 중 미보유 종목의 배당수익률을 캐시(TTL_DIVIDEND_INFO=24h) 경유로 보완한다.

    보유 종목 배당 집계(get_ticker_dividend_summary)가 쓰는 것과 동일한 (ticker, market) 단위
    캐시·멀티소스 폴백 체인(fetch_ticker_dividend_info)을 재사용한다.
    """
    dividend_map = dict(base_dividend_map)
    sem = asyncio.Semaphore(_DIVIDEND_FETCH_CONCURRENCY)
    kis_creds = await get_kis_user_credentials(user_id, db)
    dart_key = await fetch_dart_api_key(user_id, db)

    async def _fetch_one(raw_item) -> None:
        ticker = str(_item_attr(raw_item, "ticker"))
        market = str(_item_attr(raw_item, "market"))
        if is_non_tradable(ticker, market):
            return
        key = (ticker, market)
        if key in dividend_map:
            return
        try:
            yield_decimal, _dps, _months, _ex_dividend_date = await fetch_ticker_dividend_info(
                ticker, market, cache, sem, kis_creds, dart_key
            )
            if yield_decimal > 0:
                dividend_map[key] = {
                    "ticker": ticker,
                    "market": market,
                    "dividend_yield": yield_decimal * 100,
                    "estimated_annual_krw": 0.0,
                }
        except Exception as e:
            logger.warning("dividend_fetch_failed", ticker=ticker, market=market, error=str(e))

    await asyncio.gather(*[_fetch_one(item) for item in portfolio.items])
    return dividend_map


def _target_names(portfolio: Portfolio) -> dict[tuple[str, str], str]:
    """목표 항목 + 지수 그룹 멤버(국내 대체 매수 종목 포함, plans/74)의 (ticker, market) → 이름."""
    names: dict[tuple[str, str], str] = {}
    for raw_item in portfolio.items:
        names[(str(_item_attr(raw_item, "ticker")), str(_item_attr(raw_item, "market")))] = str(
            _item_attr(raw_item, "name")
        )
        members = _item_get(raw_item, "members")
        for m in members or []:
            names.setdefault((str(_item_attr(m, "ticker")), str(_item_attr(m, "market"))), str(_item_attr(m, "name")))
    return names


async def enrich_overview_with_prices(
    portfolio: Portfolio,
    overview: dict,
    user_id: uuid.UUID,
    db,
    cache,
) -> dict:
    """목표 포트폴리오 중 미보유 종목의 현재가를 조회해 overview에 보완한다."""
    existing_price_keys: set[tuple[str, str]] = {
        (pos["ticker"], pos["market"]) for pos in overview.get("all_positions", []) if pos.get("current_price")
    }
    names = _target_names(portfolio)
    unpriced: list[tuple[str, str]] = [
        key for key in names if not is_non_tradable(*key) and key not in existing_price_keys
    ]
    if not unpriced:
        return overview

    fetched_prices = await fetch_prices_batch_krw(user_id, unpriced, db, cache)
    extra_positions = [
        {
            "ticker": ticker,
            "market": market,
            "name": names.get((ticker, market)) or ticker,
            "value_krw": 0.0,
            "current_price": fetched_prices[ticker],
            "qty": 0.0,
        }
        for ticker, market in unpriced
        if ticker in fetched_prices and fetched_prices[ticker] > 0
    ]
    if not extra_positions:
        return overview
    return {**overview, "all_positions": list(overview.get("all_positions", [])) + extra_positions}
