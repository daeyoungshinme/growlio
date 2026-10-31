from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.cache_store import get_cache_store
from app.limiter import limiter
from app.models.user import User
from app.services.tax.isa_service import get_isa_status_summary
from app.services.tax.overseas_realized_service import get_overseas_realized_summary
from app.services.tax.pension_contribution_service import calc_pension_contribution_status
from app.services.tax.tax_action_service import get_tax_action_plan
from app.services.tax.tax_service import get_overseas_positions_detail, get_tax_summary, load_tax_stock_rows
from app.utils.cache_keys import TTL_TAX_OVERSEAS, get_cached_json, set_cached_json, tax_overseas_key
from app.utils.kst import today_kst

router = APIRouter(prefix="/tax", tags=["tax"])


@router.get("/overseas-positions")
@limiter.limit("30/minute")
async def overseas_positions_tax(
    request: Request,
    account_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """해외 종목별 미실현 손익 목록. account_id 미지정 시 전체 계좌 통합 기준."""
    cache = await get_cache_store()
    cache_key = tax_overseas_key(current_user.id, str(account_id) if account_id else "all")
    cached = await get_cached_json(cache, cache_key)
    if cached is not None:
        return cached
    result = await get_overseas_positions_detail(current_user.id, db, account_id)
    await set_cached_json(cache, cache_key, result, TTL_TAX_OVERSEAS)
    return result


@router.get("/summary")
@limiter.limit("30/minute")
async def tax_summary(
    request: Request,
    year: int | None = None,
    account_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """연도별 세금 추정 요약. account_id 미지정 시 전체 계좌 통합 기준.

    해외 양도세 추정에는 올해 실현손익(KIS 실전 계좌는 증권사 체결, 나머지는 수기 SELL 기록)을 합산한다 —
    기록도 없는 미지원 계좌는 0으로 본다.
    """
    current_year = today_kst().year
    target_year = year if year is not None else current_year
    if target_year < 2000 or target_year > current_year + 1:
        raise HTTPException(status_code=400, detail="유효하지 않은 연도입니다.")
    rows, positions = await load_tax_stock_rows(current_user.id, db, account_id)
    realized_krw: float | None = None
    if target_year <= current_year:
        realized = await get_overseas_realized_summary(
            current_user.id, target_year, db, account_id, overseas_positions=positions
        )
        realized_krw = realized["realized_gain_krw"]
    return await get_tax_summary(
        current_user.id, target_year, db, account_id, overseas_realized_krw=realized_krw, stock_rows=rows
    )


@router.get("/overseas-realized")
@limiter.limit("20/minute")
async def overseas_realized(
    request: Request,
    year: int | None = None,
    account_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """해외주식 올해 실현손익(증권사 체결 + 수기 SELL 기록 기준 집계) — 250만원 공제 잔여 계산용.

    KIS 실전 계좌는 브로커 조회(method=BROKER), 키움·토스·수기·모의 계좌는 해외 SELL 기록이 있으면 그 기록으로
    계산(method=TRADE_RECORD)하고, 기록 없이 해외 종목을 보유 중이면 `uncovered_accounts`로 반환한다.
    """
    current_year = today_kst().year
    target_year = year if year is not None else current_year
    if target_year < 2000 or target_year > current_year:
        raise HTTPException(status_code=400, detail="유효하지 않은 연도입니다.")
    return dict(await get_overseas_realized_summary(current_user.id, target_year, db, account_id))


@router.get("/isa-status")
@limiter.limit("30/minute")
async def isa_status(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return dict(await get_isa_status_summary(current_user.id, db))


@router.get("/pension-contribution")
@limiter.limit("30/minute")
async def pension_contribution(
    request: Request,
    year: int | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    current_year = today_kst().year
    target_year = year if year is not None else current_year
    if target_year < 2000 or target_year > current_year + 1:
        raise HTTPException(status_code=400, detail="유효하지 않은 연도입니다.")
    return dict(await calc_pension_contribution_status(current_user.id, target_year, db))


@router.get("/action-plan")
@limiter.limit("30/minute")
async def tax_action_plan(
    request: Request,
    year: int | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """절세 액션 플랜 — 연금 세액공제·ISA 이전/납입·해외 이익실현/손실수확·금융소득 한도 액션 목록.

    마감일이 올해 12/31 기준이라 올해만 지원한다.
    """
    current_year = today_kst().year
    if year is not None and year != current_year:
        raise HTTPException(status_code=400, detail="절세 액션 플랜은 올해만 조회할 수 있습니다.")
    return dict(await get_tax_action_plan(current_user.id, current_year, db))
