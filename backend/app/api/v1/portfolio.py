"""포트폴리오 API — 전체 계좌 통합 조회."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.enums import DataSource
from app.kis.balance import get_domestic_balance, get_overseas_balance
from app.limiter import limiter
from app.models.asset import AssetAccount
from app.models.user import User
from app.services.credential_service import get_kis_user_credentials
from app.services.portfolio_service import build_portfolio_overview

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("/overview")
@limiter.limit("10/minute")
async def portfolio_overview(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """모든 계좌 자산을 통합해 포트폴리오 전체 현황을 반환한다."""
    return await build_portfolio_overview(current_user.id, db)


@router.get("/summary")
async def portfolio_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """KIS 등록 계좌 전체 실시간 포트폴리오 집계."""
    kis_creds = await get_kis_user_credentials(current_user.id, db)
    if not kis_creds:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="KIS 설정이 필요합니다")

    kis_result = await db.execute(
        select(AssetAccount).where(
            AssetAccount.user_id == current_user.id,
            AssetAccount.data_source == DataSource.KIS_API,
            AssetAccount.is_active == True,  # noqa: E712
        )
    )
    kis_accounts = kis_result.scalars().all()
    if not kis_accounts:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="등록된 KIS 계좌가 없습니다")

    app_key = kis_creds["app_key"]
    app_secret = kis_creds["app_secret"]
    is_mock = kis_creds["is_mock"]
    access_token = kis_creds["access_token"]

    async def _fetch(account_no: str) -> tuple[str, dict, dict]:
        d = await get_domestic_balance(app_key, app_secret, access_token, account_no, is_mock=is_mock)
        o = await get_overseas_balance(app_key, app_secret, access_token, account_no, is_mock=is_mock)
        return account_no, d, o

    results = await asyncio.gather(*[_fetch(acc.kis_account_no) for acc in kis_accounts])

    merged_domestic: dict = {"total_value_krw": 0.0, "invested_krw": 0.0, "pnl_krw": 0.0, "deposit_krw": 0.0, "positions": []}
    merged_overseas: dict = {"total_value_usd": 0.0, "deposit_usd": 0.0, "positions": []}
    account_details = []
    for account_no, d, o in results:
        merged_domestic["total_value_krw"] += d.get("total_value_krw", 0.0)
        merged_domestic["invested_krw"] += d.get("invested_krw", 0.0)
        merged_domestic["pnl_krw"] += d.get("pnl_krw", 0.0)
        merged_domestic["deposit_krw"] += d.get("deposit_krw", 0.0)
        merged_domestic["positions"].extend(d.get("positions", []))
        merged_overseas["total_value_usd"] += o.get("total_value_usd", 0.0)
        merged_overseas["deposit_usd"] += o.get("deposit_usd", 0.0)
        merged_overseas["positions"].extend(o.get("positions", []))
        account_details.append({"account_no": account_no, "domestic": d, "overseas": o})

    stock_return_pct = 0.0
    if merged_domestic["invested_krw"] > 0:
        stock_return_pct = (merged_domestic["total_value_krw"] / merged_domestic["invested_krw"] - 1) * 100

    return {
        "domestic": merged_domestic,
        "overseas": merged_overseas,
        "total_value_krw": merged_domestic["total_value_krw"],
        "total_invested_krw": merged_domestic["invested_krw"],
        "unrealized_pnl_krw": merged_domestic["pnl_krw"],
        "stock_return_pct": stock_return_pct,
        "is_mock": is_mock,
        "accounts": account_details,
    }
