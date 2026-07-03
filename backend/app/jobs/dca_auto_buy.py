"""DCA 자동매매 Job — 매일 09:00 KST 실행, auto_dca_day와 오늘 날짜 비교 후 매수."""

from __future__ import annotations

import math
import uuid
from datetime import UTC, date, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.kis.auth import get_access_token
from app.kis.order import is_overseas_market, place_domestic_order, place_overseas_order
from app.models.asset import AssetAccount
from app.models.portfolio import Portfolio
from app.models.user import UserSettings
from app.redis_client import get_redis
from app.services.credential_service import decrypt
from app.services.price_service import fetch_prices_batch
from app.utils.cache_keys import TTL_JOB_LOCK_DCA
from app.utils.redis_lock import redis_lock

logger = structlog.get_logger()


async def run_dca_auto_execution() -> None:
    """매일 09:00 KST — auto_dca_day가 오늘인 유저 DCA 자동 매수."""
    today = date.today()
    redis = await get_redis()

    async with redis_lock(redis, "dca_auto_execution_lock", ttl=TTL_JOB_LOCK_DCA) as acquired:
        if not acquired:
            logger.info("dca_auto_execution_skipped_lock_held")
            return
        await _run_dca_auto_execution(today, redis)


async def _run_dca_auto_execution(today: date, redis) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(UserSettings).where(
                UserSettings.auto_dca_enabled == True,  # noqa: E712
                UserSettings.auto_dca_day == today.day,
                UserSettings.auto_dca_portfolio_id.isnot(None),
                UserSettings.auto_dca_account_id.isnot(None),
                UserSettings.auto_dca_amount.isnot(None),
            )
        )
        settings_list = result.scalars().all()

    for settings in settings_list:
        try:
            async with AsyncSessionLocal() as db:
                await _execute_dca_for_user(settings, db, redis)
                settings_row = await db.scalar(select(UserSettings).where(UserSettings.user_id == settings.user_id))
                if settings_row:
                    settings_row.auto_dca_last_executed_at = datetime.now(UTC)
                    await db.commit()
            logger.info("dca_auto_executed", user_id=str(settings.user_id), day=today.day)
        except Exception as e:
            logger.error("dca_auto_buy_failed", user_id=str(settings.user_id), error=str(e))


async def _execute_dca_for_user(settings: UserSettings, db: AsyncSession, redis) -> None:
    portfolio_id = settings.auto_dca_portfolio_id
    account_id = settings.auto_dca_account_id
    total_amount = float(settings.auto_dca_amount or 0)
    user_id: uuid.UUID = settings.user_id

    # 포트폴리오 종목 비중 조회
    portfolio = await db.scalar(select(Portfolio).where(Portfolio.id == portfolio_id))
    if not portfolio or not portfolio.items:
        logger.warning("dca_no_portfolio", user_id=str(user_id), portfolio_id=str(portfolio_id))
        return

    items = portfolio.items

    # 계좌 조회 및 자격증명 로드
    account = await db.scalar(
        select(AssetAccount).where(
            AssetAccount.id == account_id,
            AssetAccount.is_active == True,  # noqa: E712
        )
    )
    if not account or account.asset_type != "STOCK_KIS":
        logger.warning("dca_invalid_account", user_id=str(user_id), account_id=str(account_id))
        return
    if not account.kis_app_key or not account.kis_app_secret:
        logger.warning("dca_missing_credentials", user_id=str(user_id))
        return
    if not account.kis_account_no:
        logger.warning("dca_missing_account_no", user_id=str(user_id), account_id=str(account_id))
        return

    app_key = decrypt(account.kis_app_key)
    app_secret = decrypt(account.kis_app_secret)
    access_token = await get_access_token(
        app_key,
        app_secret,
        is_mock=account.is_mock_mode,
        redis=redis,
        db=db,
        user_id=str(user_id),
        account_id=str(account_id),
    )

    # 현재가 조회 (PortfolioItem 모델 → attribute 접근)
    tickers = [(item.ticker, item.market) for item in items]
    price_map = await fetch_prices_batch(user_id, tickers, db, redis)

    # 종목별 배분 및 매수
    total_weight = sum(float(item.weight) for item in items)
    if total_weight <= 0:
        return

    for item in items:
        ticker = item.ticker
        market = item.market
        weight = float(item.weight) / total_weight
        alloc_amount = total_amount * weight

        price = price_map.get(ticker)
        if not price or price <= 0:
            logger.warning("dca_no_price", ticker=ticker)
            continue

        qty = math.floor(alloc_amount / price)
        if qty <= 0:
            continue

        try:
            if is_overseas_market(market):
                await place_overseas_order(
                    app_key,
                    app_secret,
                    access_token,
                    account.kis_account_no,
                    side="BUY",
                    ticker=ticker,
                    market=market,
                    quantity=qty,
                    is_mock=account.is_mock_mode,
                )
            else:
                await place_domestic_order(
                    app_key,
                    app_secret,
                    access_token,
                    account.kis_account_no,
                    side="BUY",
                    ticker=ticker,
                    quantity=qty,
                    is_mock=account.is_mock_mode,
                )
            logger.info(
                "dca_order_placed",
                ticker=ticker,
                qty=qty,
                price=price,
                is_mock=account.is_mock_mode,
            )
        except Exception as e:
            logger.error("dca_order_failed", ticker=ticker, error=str(e))
