"""수동 입력 브로커 프로바이더."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.exceptions import BadRequestError
from app.models.asset import Position as DBPosition
from app.providers.base import BalanceResult, BrokerProvider
from app.providers.base import Position as ProviderPosition
from app.utils.currency import fetch_usd_krw

if TYPE_CHECKING:
    import redis.asyncio as aioredis
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.asset import AssetAccount


class ManualProvider(BrokerProvider):
    PROVIDER_ID = "MANUAL"
    PROVIDER_NAME = "수동 입력"

    async def sync(self, account: AssetAccount, db: AsyncSession, redis: aioredis.Redis | None) -> BalanceResult:
        from app.kis.constants import OVERSEAS_MARKETS

        # 현재 포지션을 positions 테이블에서 로드
        pos_result = await db.execute(
            select(DBPosition).where(
                DBPosition.account_id == account.id,
                DBPosition.snapshot_id == None,  # noqa: E711
            )
        )
        db_positions = pos_result.scalars().all()

        if db_positions and redis is not None:
            from app.services.price_service import fetch_prices_batch

            tickers = [(p.ticker, p.market) for p in db_positions]
            price_map = await fetch_prices_batch(account.user_id, tickers, db, redis)

            has_overseas = any(p.market in OVERSEAS_MARKETS for p in db_positions)
            usd_rate: float | None = None
            if has_overseas:
                usd_rate = await fetch_usd_krw(redis, force_refresh=True) or None

            for p in db_positions:
                raw_price = price_map.get(p.ticker)
                if raw_price and p.market in OVERSEAS_MARKETS and usd_rate:
                    price_krw = raw_price * usd_rate
                elif raw_price:
                    price_krw = raw_price
                else:
                    price_krw = float(p.current_price or p.avg_price or 0)
                p.current_price = price_krw
                p.value_krw = price_krw * float(p.qty or 0)

            account.manual_updated_at = datetime.now(UTC)

        positions = [_db_to_provider_position(p) for p in db_positions]
        invested = sum(p.avg_price * p.qty for p in positions)
        value = sum((p.current_price or p.avg_price) * p.qty for p in positions)
        pnl = value - invested if positions else 0.0

        if positions:
            usd_rate_val = await fetch_usd_krw(redis)
            deposit = float(account.deposit_krw or 0) + float(account.deposit_usd or 0) * usd_rate_val
            amount_krw = (value if value else invested) + deposit
            account.manual_amount = amount_krw
        elif account.asset_type == "REAL_ESTATE":
            gross = float(account.manual_amount or 0)
            mortgage = float((account.real_estate_details or {}).get("mortgage_balance_krw", 0) or 0)
            amount_krw = gross - mortgage
            if gross == 0:
                raise BadRequestError("부동산 시세(manual_amount)가 설정되지 않았습니다")
        elif account.deposit_krw is not None or account.deposit_usd is not None:
            usd_rate2 = await fetch_usd_krw(redis)
            amount_krw = float(account.deposit_krw or 0) + float(account.deposit_usd or 0) * usd_rate2
        else:
            amount_krw = float(account.manual_amount or 0)
            if amount_krw == 0:
                raise BadRequestError("수동 금액이 설정되지 않았습니다")

        return BalanceResult(
            positions=positions,
            total_value_krw=amount_krw,
            deposit_krw=float(account.deposit_krw or 0),
            invested_krw=invested if positions else 0.0,
            pnl_krw=pnl,
            extra={"source": "MANUAL", "snapshot_date": date.today()},
        )


def _db_to_provider_position(p: DBPosition) -> ProviderPosition:
    return ProviderPosition(
        ticker=p.ticker,
        name=p.name or "",
        market=p.market,
        qty=int(p.qty or 0),
        avg_price=float(p.avg_price or 0),
        current_price=float(p.current_price or p.avg_price or 0),
        currency=p.currency or "KRW",
        value_krw=float(p.value_krw or 0),
        avg_price_usd=float(p.avg_price_usd) if p.avg_price_usd else None,
        usd_rate=float(p.usd_rate) if p.usd_rate else None,
    )
