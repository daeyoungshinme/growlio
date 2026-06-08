"""자산 집계 및 대시보드 계산 서비스."""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from datetime import date
from typing import Any

import structlog
from redis.exceptions import RedisError
from sqlalchemy import and_, asc, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import AssetType
from app.models.asset import AssetAccount, AssetSnapshot, Position, Transaction
from app.models.user import UserSettings
from app.services._snapshot_queries import latest_snapshot_subquery
from app.services.dividend_aggregator import get_dividend_summary
from app.utils.cache_keys import (
    TTL_DASHBOARD_SUMMARY,
    TTL_MONTHLY_TREND,
    dashboard_summary_key,
    monthly_trend_key,
)
from app.utils.currency import fetch_usd_krw
from app.utils.pnl import eval_value as _eval_value
from app.utils.pnl import invested_value as _invested_value

logger = structlog.get_logger()

_STOCK_TYPES = {AssetType.STOCK_KIS, AssetType.STOCK_KIWOOM, AssetType.STOCK_OTHER}


async def _get_latest_snapshot_rows(
    user_id: uuid.UUID, db: AsyncSession
) -> tuple[list, set]:
    """활성 계좌의 최신 스냅샷 행과 스냅샷이 있는 계좌 ID 집합을 반환한다."""
    subq = latest_snapshot_subquery(user_id=user_id)
    result = await db.execute(
        select(AssetSnapshot, AssetAccount)
        .join(subq, (AssetSnapshot.account_id == subq.c.account_id) & (AssetSnapshot.snapshot_date == subq.c.max_date))
        .join(AssetAccount, AssetAccount.id == AssetSnapshot.account_id)
        .where(AssetAccount.is_active == True)  # noqa: E712
    )
    rows = result.all()
    snapped_ids = {acc.id for _, acc in rows}
    return rows, snapped_ids


async def _get_no_snap_accounts(
    user_id: uuid.UUID, db: AsyncSession, snapped_ids: set
) -> list:
    """스냅샷 없이 manual_amount/deposit만 있는 활성 계좌를 반환한다."""
    conditions = [
        AssetAccount.user_id == user_id,
        AssetAccount.is_active == True,  # noqa: E712
        or_(
            and_(AssetAccount.manual_amount.isnot(None), AssetAccount.manual_amount > 0),
            AssetAccount.deposit_krw > 0,
            AssetAccount.deposit_usd > 0,
        ),
    ]
    if snapped_ids:
        conditions.append(AssetAccount.id.not_in(snapped_ids))
    result = await db.execute(select(AssetAccount).where(*conditions))
    return list(result.scalars().all())


async def _fetch_position_maps(
    snap_ids: list, stock_acc_ids: list, db: AsyncSession
) -> tuple[dict, dict]:
    """스냅샷별·계좌별 포지션을 각각 dict로 batch 조회한다."""
    snap_positions: dict[Any, list] = {}
    if snap_ids:
        pos_result = await db.execute(
            select(Position).where(Position.snapshot_id.in_(snap_ids))
        )
        for pos in pos_result.scalars().all():
            snap_positions.setdefault(pos.snapshot_id, []).append(pos)

    current_positions: dict[Any, list] = {}
    if stock_acc_ids:
        cur_result = await db.execute(
            select(Position).where(
                Position.account_id.in_(stock_acc_ids),
                Position.snapshot_id == None,  # noqa: E711
            )
        )
        for pos in cur_result.scalars().all():
            current_positions.setdefault(pos.account_id, []).append(pos)

    return snap_positions, current_positions


async def _build_asset_totals(
    user_id: uuid.UUID,
    db: AsyncSession,
    redis: Any = None,
) -> tuple[float, float, float, dict[str, float]]:
    """최신 스냅샷 기준 총자산·투자금·주식평가액·유형별 금액을 집계한다.
    Returns: (total_assets_krw, total_invested, stock_value, by_type)
    """
    usd_rate = await fetch_usd_krw(redis)
    rows, snapped_ids = await _get_latest_snapshot_rows(user_id, db)
    no_snap_accounts = await _get_no_snap_accounts(user_id, db, snapped_ids)

    snap_ids = [snap.id for snap, acc in rows if acc.asset_type in _STOCK_TYPES]
    stock_acc_ids = [acc.id for _, acc in rows if acc.asset_type in _STOCK_TYPES]
    stock_acc_ids += [acc.id for acc in no_snap_accounts if acc.asset_type in _STOCK_TYPES]
    snap_positions, current_positions = await _fetch_position_maps(snap_ids, stock_acc_ids, db)

    total_assets_krw = 0.0
    total_invested = 0.0
    stock_value = 0.0
    by_type: dict[str, float] = {}

    for snap, acc in rows:
        if not acc.include_in_total:
            continue
        amount = float(snap.amount_krw)
        if acc.asset_type in _STOCK_TYPES:
            pos_list = snap_positions.get(snap.id) or current_positions.get(acc.id) or []
            stock_equity = _eval_value(pos_list) if pos_list else amount
            cash = amount - stock_equity
            inv = float(snap.invested_amount or 0) or _invested_value(pos_list)
            stock_value += stock_equity
            total_invested += inv
            by_type[acc.asset_type] = by_type.get(acc.asset_type, 0) + stock_equity
            by_type["CASH_STOCK"] = by_type.get("CASH_STOCK", 0) + cash
        else:
            by_type[acc.asset_type] = by_type.get(acc.asset_type, 0) + amount
        total_assets_krw += amount

    for acc in no_snap_accounts:
        if not acc.include_in_total:
            continue
        if acc.asset_type in _STOCK_TYPES:
            pos_list = current_positions.get(acc.id) or []
            pos_equity = _eval_value(pos_list) if pos_list else 0.0
            deposit = float(acc.deposit_krw or 0) + float(acc.deposit_usd or 0) * usd_rate
            computed = pos_equity + deposit
            amount = computed if computed > 0 else float(acc.manual_amount or 0)
            inv = _invested_value(pos_list) if pos_list else float(acc.manual_amount or 0)
            stock_value += pos_equity or amount
            total_invested += inv
            if computed > 0:
                by_type[acc.asset_type] = by_type.get(acc.asset_type, 0) + pos_equity
                by_type["CASH_STOCK"] = by_type.get("CASH_STOCK", 0) + deposit
            else:
                by_type[acc.asset_type] = by_type.get(acc.asset_type, 0) + amount
        elif acc.asset_type == "REAL_ESTATE":
            gross = float(acc.manual_amount or 0)
            mortgage = float((acc.real_estate_details or {}).get("mortgage_balance_krw", 0) or 0)
            amount = gross - mortgage
            by_type[acc.asset_type] = by_type.get(acc.asset_type, 0) + amount
        else:
            amount = float(acc.manual_amount or 0)
            by_type[acc.asset_type] = by_type.get(acc.asset_type, 0) + amount
        total_assets_krw += amount

    return total_assets_krw, total_invested, stock_value, by_type


async def get_dashboard_summary(user_id: uuid.UUID, db: AsyncSession, redis=None) -> dict[str, Any]:
    """전체 자산 집계 + 목표 달성률 + 수익률 계산."""
    if redis:
        cached = await redis.get(dashboard_summary_key(user_id))
        if cached:
            return json.loads(cached)

    first_snap_date = await _get_first_snap_date(user_id, db)

    # DB 쿼리는 같은 세션을 공유하므로 순차 실행 (SQLAlchemy AsyncSession 안전 요구사항)
    settings_row = await db.scalar(select(UserSettings).where(UserSettings.user_id == user_id))
    total_assets_krw, total_invested, stock_value, by_type = await _build_asset_totals(user_id, db, redis)
    monthly_trend = await _get_monthly_trend(user_id, db, redis)
    net_deposits_ytd = await _calc_net_deposits_this_year(user_id, db)
    div_summary = await get_dividend_summary(user_id, db, redis)
    xirr_pct, xirr_is_estimated = await _calc_xirr(user_id, total_assets_krw, db)

    bank_total = total_assets_krw - stock_value
    base = bank_total + total_invested
    annualized_return, cumulative_return = _calc_returns(total_assets_krw, base, first_snap_date)
    stock_return_pct = ((stock_value / total_invested) - 1) * 100 if total_invested > 0 else 0.0

    goal = float(settings_row.goal_amount) if settings_row and settings_row.goal_amount else None
    goal_pct = (total_assets_krw / goal * 100) if goal else None
    annual_deposit_goal = float(settings_row.annual_deposit_goal) if settings_row and settings_row.annual_deposit_goal else None
    deposit_achievement_pct = (net_deposits_ytd / annual_deposit_goal * 100) if annual_deposit_goal else None
    goal_annual_return_pct = float(settings_row.goal_annual_return_pct) if settings_row and settings_row.goal_annual_return_pct else None
    retirement_target_year = settings_row.retirement_target_year if settings_row else None

    result: dict[str, Any] = {
        "total_assets_krw": total_assets_krw,
        "asset_allocation": [
            {"type": k, "amount_krw": v, "pct": v / total_assets_krw * 100 if total_assets_krw else 0}
            for k, v in by_type.items()
        ],
        "goal_amount": goal,
        "goal_achievement_pct": goal_pct,
        "stock_return_pct": stock_return_pct,
        "annual_return_pct": annualized_return,
        "cumulative_return_pct": cumulative_return,
        "xirr_pct": xirr_pct,
        "xirr_is_estimated": xirr_is_estimated,
        "goal_annual_return_pct": goal_annual_return_pct,
        "retirement_target_year": retirement_target_year,
        "monthly_trend": monthly_trend,
        "annual_deposit_goal": annual_deposit_goal,
        "deposit_achievement_pct": deposit_achievement_pct,
        "annual_dividends_received": div_summary["annual_received"],
        "estimated_annual_dividends": div_summary["estimated_annual"],
        "dividend_monthly_breakdown": div_summary["monthly_breakdown"],
    }
    if redis:
        with contextlib.suppress(RedisError):
            await redis.setex(
                dashboard_summary_key(user_id), TTL_DASHBOARD_SUMMARY, json.dumps(result)
            )
    return result


async def _get_first_snap_date(user_id: uuid.UUID, db: AsyncSession) -> date | None:
    result = await db.execute(
        select(func.min(AssetSnapshot.snapshot_date)).where(AssetSnapshot.user_id == user_id)
    )
    return result.scalar()


def _calc_returns(
    current_total: float, base: float, first_date: date | None
) -> tuple[float | None, float | None]:
    if base <= 0 or not first_date:
        return None, None

    today = date.today()
    if first_date >= today:
        return None, None
    months = max((today.year - first_date.year) * 12 + (today.month - first_date.month), 1)
    cumulative = (current_total / base - 1) * 100
    annualized = ((current_total / base) ** (12 / months) - 1) * 100
    return annualized, cumulative


async def _get_monthly_trend(user_id: uuid.UUID, db: AsyncSession, redis=None) -> list[dict]:
    cache_key = monthly_trend_key(user_id)
    if redis:
        with contextlib.suppress(RedisError):
            cached = await redis.get(cache_key)
            if cached:
                return json.loads(cached)

    result = await db.execute(
        text("""
            WITH ranked AS (
                SELECT
                    date_trunc('month', s.snapshot_date)::date AS month,
                    s.amount_krw,
                    ROW_NUMBER() OVER (
                        PARTITION BY s.account_id, date_trunc('month', s.snapshot_date)
                        ORDER BY s.snapshot_date DESC
                    ) AS rn
                FROM asset_snapshots s
                JOIN asset_accounts a ON a.id = s.account_id
                WHERE s.user_id = :uid
                    AND a.is_active = TRUE
                    AND a.include_in_total = TRUE
                    AND s.snapshot_date >= (date_trunc('month', CURRENT_DATE) - INTERVAL '11 months')
            )
            SELECT month, SUM(amount_krw) AS total_krw
            FROM ranked
            WHERE rn = 1
            GROUP BY month
            ORDER BY month
        """),
        {"uid": str(user_id)},
    )
    data = [{"month": str(row.month), "total_krw": float(row.total_krw)} for row in result]

    if redis:
        with contextlib.suppress(RedisError):
            await redis.set(cache_key, json.dumps(data), ex=TTL_MONTHLY_TREND)

    return data


def _xirr(cashflows: list[tuple[date, float]]) -> float | None:
    """Newton-Raphson XIRR. cashflows: [(date, amount)] 음수=유출, 양수=유입."""
    if len(cashflows) < 2:
        return None
    amounts = [a for _, a in cashflows]
    if all(a >= 0 for a in amounts) or all(a <= 0 for a in amounts):
        return None

    d0 = min(d for d, _ in cashflows)
    days = [(d - d0).days for d, _ in cashflows]

    pairs = list(zip(amounts, days, strict=True))
    rate = 0.1
    for _ in range(200):
        try:
            npv = sum(cf / (1 + rate) ** (d / 365.0) for cf, d in pairs)
            dnpv = sum(
                -cf * (d / 365.0) / (1 + rate) ** (d / 365.0 + 1) for cf, d in pairs
            )
        except (ZeroDivisionError, OverflowError):
            return None
        if abs(dnpv) < 1e-12:
            max_cf = max(abs(cf) for cf, _ in pairs)
            if max_cf > 0 and abs(npv) / max_cf < 1e-6:
                return round(rate * 100, 2)
            return None
        new_rate = rate - npv / dnpv
        if abs(new_rate - rate) < 1e-7:
            result = round(new_rate * 100, 2)
            return result if -99 < result < 1000 else None
        rate = min(max(new_rate, -0.99), 10.0)
    return None


async def _calc_xirr(
    user_id: uuid.UUID, current_total: float, db: AsyncSession
) -> tuple[float | None, bool]:
    """Transaction 기반 XIRR 계산. 트랜잭션 없으면 스냅샷으로 추정."""

    result = await db.execute(
        select(Transaction.transaction_date, Transaction.transaction_type, Transaction.amount)
        .where(
            Transaction.user_id == user_id,
            Transaction.transaction_type.in_(["DEPOSIT", "WITHDRAWAL"]),
        )
        .order_by(asc(Transaction.transaction_date))
    )
    rows = result.all()

    if not rows:
        snap_result = await db.execute(
            select(
                AssetSnapshot.snapshot_date,
                func.sum(AssetSnapshot.amount_krw).label("total"),
            )
            .join(AssetAccount, AssetAccount.id == AssetSnapshot.account_id)
            .where(
                AssetSnapshot.user_id == user_id,
                AssetAccount.is_active == True,  # noqa: E712
                AssetAccount.include_in_total == True,  # noqa: E712
            )
            .group_by(AssetSnapshot.snapshot_date)
            .order_by(asc(AssetSnapshot.snapshot_date))
            .limit(1)
        )
        first = snap_result.first()
        today = date.today()
        if not first or float(first.total) <= 0 or first.snapshot_date >= today:
            return None, False
        cashflows: list[tuple[date, float]] = [
            (first.snapshot_date, -float(first.total)),
            (today, current_total),
        ]
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _xirr, cashflows), True

    cashflows = []
    for row in rows:
        if row.transaction_type == "DEPOSIT":
            cashflows.append((row.transaction_date, -float(row.amount)))
        else:
            cashflows.append((row.transaction_date, float(row.amount)))

    cashflows.append((date.today(), current_total))
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _xirr, cashflows), False


async def _calc_net_deposits_this_year(user_id: uuid.UUID, db: AsyncSession) -> float:
    """올해 순입금액 = DEPOSIT 합계 - WITHDRAWAL 합계."""
    year = date.today().year
    result = await db.execute(
        select(
            Transaction.transaction_type,
            func.sum(Transaction.amount).label("total"),
        )
        .where(
            Transaction.user_id == user_id,
            func.extract("year", Transaction.transaction_date) == year,
            Transaction.transaction_type.in_(["DEPOSIT", "WITHDRAWAL"]),
        )
        .group_by(Transaction.transaction_type)
    )
    rows = {r.transaction_type: float(r.total) for r in result}
    return rows.get("DEPOSIT", 0.0) - rows.get("WITHDRAWAL", 0.0)
