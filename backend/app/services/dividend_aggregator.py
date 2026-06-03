"""트랜잭션 기반 배당금 집계 서비스."""

from __future__ import annotations

import uuid
from datetime import date

import structlog
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Transaction
from app.services.dividend_service import get_ticker_dividend_summary

logger = structlog.get_logger()


async def get_dividend_summary(user_id: uuid.UUID, db: AsyncSession) -> dict:
    current_year = date.today().year

    annual_received = await _sum_transactions(user_id, db, "DIVIDEND", current_year)
    monthly_breakdown = await _monthly_dividend_breakdown(user_id, db, current_year)
    monthly_ticker_breakdown = await _monthly_dividend_ticker_breakdown(user_id, db, current_year)

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
    month_col = func.to_char(Transaction.transaction_date, "YYYY-MM").label("month")
    result = await db.execute(
        select(month_col, func.sum(Transaction.amount).label("total"))
        .where(
            Transaction.user_id == user_id,
            Transaction.transaction_type == "DIVIDEND",
            func.extract("year", Transaction.transaction_date) == year,
        )
        .group_by(month_col)
        .order_by(month_col)
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
