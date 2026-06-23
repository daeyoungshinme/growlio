"""포트폴리오 월별 자산 배분 이력 서비스 (portfolio_service.py에서 분리)."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import AssetType
from app.utils.cache_keys import (
    TTL_ALLOC_HISTORY,
    alloc_history_key,
    get_cached_json,
    set_cached_json,
)

_EXTENDED_ASSET_TYPE_LABELS: dict[str, str] = {
    AssetType.BANK_ACCOUNT: "통장잔고",
    AssetType.DEPOSIT: "예금/적금",
    AssetType.STOCK_KIS: "주식",
    AssetType.STOCK_KIWOOM: "주식",
    AssetType.STOCK_OTHER: "주식",
    AssetType.CASH_OTHER: "예수금",
    AssetType.CASH_STOCK: "예수금",
    AssetType.OTHER: "기타자산",
    AssetType.REAL_ESTATE: "부동산",
    "STOCK_DOMESTIC": "국내주식",
    "STOCK_FOREIGN": "해외주식",
}

_STOCK_ASSET_TYPES = ("STOCK_KIS", "STOCK_KIWOOM", "STOCK_OTHER")


async def get_allocation_history(user_id: uuid.UUID, db: AsyncSession, months: int = 12, redis=None) -> list[dict]:
    """월별 자산 유형별 배분 이력 조회.

    각 월의 마지막 스냅샷 기준으로 asset_type별 금액/비중을 반환한다.
    주식 계좌는 positions.market으로 국내/해외 분리를 시도하고,
    포지션 데이터가 없는 월은 원래 asset_type으로 fallback한다.
    is_active = TRUE 필터 필수 — 비활성 계좌 스냅샷 합산 방지.
    """
    cache_key = alloc_history_key(user_id, months)
    cached = await get_cached_json(redis, cache_key)
    if cached is not None:
        return cached

    today = date.today()
    start_month = today.month - (months - 1)
    start_year = today.year
    while start_month <= 0:
        start_month += 12
        start_year -= 1
    start_date = date(start_year, start_month, 1)

    params = {"uid": str(user_id), "start_date": start_date}

    # 쿼리 1: 전체 계좌 snapshot 기준 집계 (기존 방식)
    result1 = await db.execute(
        text("""
            WITH ranked AS (
                SELECT
                    date_trunc('month', s.snapshot_date)::date AS month,
                    a.asset_type,
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
                    AND s.snapshot_date >= :start_date
            )
            SELECT month, asset_type, SUM(amount_krw) AS amount_krw
            FROM ranked WHERE rn = 1
            GROUP BY month, asset_type
            ORDER BY month, asset_type
        """),
        params,
    )

    monthly: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for row in result1.all():
        monthly[str(row.month)][row.asset_type] += float(row.amount_krw or 0)

    # 쿼리 2: 주식 계좌의 positions.market 기반 국내/해외 금액 산출
    result2 = await db.execute(
        text("""
            WITH ranked AS (
                SELECT
                    s.id AS snapshot_id,
                    date_trunc('month', s.snapshot_date)::date AS month,
                    ROW_NUMBER() OVER (
                        PARTITION BY s.account_id, date_trunc('month', s.snapshot_date)
                        ORDER BY s.snapshot_date DESC
                    ) AS rn
                FROM asset_snapshots s
                JOIN asset_accounts a ON a.id = s.account_id
                WHERE s.user_id = :uid
                    AND a.is_active = TRUE
                    AND a.include_in_total = TRUE
                    AND a.asset_type IN ('STOCK_KIS', 'STOCK_KIWOOM', 'STOCK_OTHER')
                    AND s.snapshot_date >= :start_date
            ),
            last_stock AS (
                SELECT snapshot_id, month FROM ranked WHERE rn = 1
            )
            SELECT
                ls.month,
                CASE
                    WHEN p.market IN ('KOSPI', 'KOSDAQ', 'KRX') THEN 'STOCK_DOMESTIC'
                    ELSE 'STOCK_FOREIGN'
                END AS asset_type,
                SUM(COALESCE(p.value_krw, p.qty * p.current_price, p.qty * p.avg_price, 0)) AS amount_krw
            FROM last_stock ls
            JOIN positions p ON p.snapshot_id = ls.snapshot_id
            WHERE p.market IS NOT NULL
            GROUP BY ls.month, asset_type
            HAVING SUM(COALESCE(p.value_krw, p.qty * p.current_price, p.qty * p.avg_price, 0)) > 0
            ORDER BY ls.month, asset_type
        """),
        params,
    )

    # 포지션 데이터가 있는 월: STOCK_* 항목을 STOCK_DOMESTIC/STOCK_FOREIGN으로 교체
    months_with_positions: set[str] = set()
    position_data: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for row in result2.all():
        month_str = str(row.month)
        months_with_positions.add(month_str)
        position_data[month_str][row.asset_type] += float(row.amount_krw or 0)

    for month_str in months_with_positions:
        for stock_type in _STOCK_ASSET_TYPES:
            monthly[month_str].pop(stock_type, None)
        for asset_type, amount in position_data[month_str].items():
            monthly[month_str][asset_type] += amount

    output = []
    for month_str in sorted(monthly.keys()):
        type_amounts = monthly[month_str]
        total_krw = sum(type_amounts.values())
        if total_krw <= 0:
            continue

        allocations = []
        for asset_type, amount_krw in sorted(type_amounts.items()):
            allocations.append(
                {
                    "asset_type": asset_type,
                    "label": _EXTENDED_ASSET_TYPE_LABELS.get(asset_type, asset_type),
                    "amount_krw": round(amount_krw, 2),
                    "weight_pct": round(amount_krw / total_krw * 100, 2),
                }
            )

        output.append(
            {
                "month": month_str,
                "total_krw": round(total_krw, 2),
                "allocations": allocations,
            }
        )

    await set_cached_json(redis, cache_key, output, TTL_ALLOC_HISTORY)
    return output
