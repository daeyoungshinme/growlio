"""통합 포트폴리오 CRUD API (백테스팅·리밸런싱 공용)."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import case, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.database import get_db
from app.limiter import limiter
from app.models.asset import AssetAccount
from app.models.portfolio import Portfolio, PortfolioAccount, PortfolioItem
from app.models.user import User
from app.schemas.portfolio import (
    PortfolioCreate,
    PortfolioReorderRequest,
    PortfolioResponse,
    PortfolioUpdate,
)

router = APIRouter(prefix="/portfolios", tags=["portfolios"])


async def _validate_account_ids(
    account_ids: list[uuid.UUID] | None,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> None:
    """account_ids가 모두 현재 유저 소유인지 확인한다."""
    if not account_ids:
        return
    result = await db.execute(
        select(AssetAccount.id).where(
            AssetAccount.id.in_(account_ids),
            AssetAccount.user_id == user_id,
        )
    )
    owned = {row[0] for row in result.all()}
    invalid = [str(aid) for aid in account_ids if aid not in owned]
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"유효하지 않은 계좌 ID: {', '.join(invalid)}",
        )


def _with_relations(q):
    return q.options(
        selectinload(Portfolio.items),
        selectinload(Portfolio.linked_accounts),
    )


@router.get("", response_model=list[PortfolioResponse])
@limiter.limit("60/minute")
async def list_portfolios(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """저장된 포트폴리오 목록."""
    rows = await db.execute(
        _with_relations(
            select(Portfolio)
            .where(Portfolio.user_id == current_user.id)
            .order_by(Portfolio.sort_order, Portfolio.created_at)
        )
    )
    return rows.scalars().all()


@router.post("", response_model=PortfolioResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def create_portfolio(
    request: Request,
    body: PortfolioCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """새 포트폴리오 생성."""
    await _validate_account_ids(body.account_ids, current_user.id, db)
    portfolio = Portfolio(
        user_id=current_user.id,
        name=body.name,
        base_type=body.base_type,
    )
    db.add(portfolio)
    await db.flush()  # id 생성

    for idx, item in enumerate(body.items):
        db.add(PortfolioItem(
            portfolio_id=portfolio.id,
            ticker=item.ticker,
            name=item.name,
            market=item.market,
            weight=item.weight,
            sort_order=idx,
        ))

    if body.account_ids:
        for aid in body.account_ids:
            db.add(PortfolioAccount(portfolio_id=portfolio.id, account_id=aid))

    await db.commit()

    result = await db.execute(
        _with_relations(select(Portfolio).where(Portfolio.id == portfolio.id))
    )
    return result.scalar_one()


@router.put("/{portfolio_id}", response_model=PortfolioResponse)
@limiter.limit("30/minute")
async def update_portfolio(
    request: Request,
    portfolio_id: uuid.UUID,
    body: PortfolioUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """포트폴리오 수정."""
    result = await db.execute(
        _with_relations(
            select(Portfolio).where(
                Portfolio.id == portfolio_id,
                Portfolio.user_id == current_user.id,
            )
        )
    )
    portfolio = result.scalar_one_or_none()
    if not portfolio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="포트폴리오를 찾을 수 없습니다"
        )

    if body.account_ids is not None:
        await _validate_account_ids(body.account_ids, current_user.id, db)
    if body.name is not None:
        portfolio.name = body.name
    if body.base_type is not None:
        portfolio.base_type = body.base_type

    if body.items is not None:
        await db.execute(delete(PortfolioItem).where(PortfolioItem.portfolio_id == portfolio_id))
        for idx, item in enumerate(body.items):
            db.add(PortfolioItem(
                portfolio_id=portfolio.id,
                ticker=item.ticker,
                name=item.name,
                market=item.market,
                weight=item.weight,
                sort_order=idx,
            ))

    if body.account_ids is not None:
        await db.execute(
            delete(PortfolioAccount).where(PortfolioAccount.portfolio_id == portfolio_id)
        )
        for aid in body.account_ids:
            db.add(PortfolioAccount(portfolio_id=portfolio.id, account_id=aid))

    await db.commit()

    result2 = await db.execute(
        _with_relations(select(Portfolio).where(Portfolio.id == portfolio_id))
    )
    return result2.scalar_one()


@router.delete("/{portfolio_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("30/minute")
async def delete_portfolio(
    request: Request,
    portfolio_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """포트폴리오 삭제."""
    portfolio = await db.scalar(
        select(Portfolio).where(
            Portfolio.id == portfolio_id,
            Portfolio.user_id == current_user.id,
        )
    )
    if not portfolio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="포트폴리오를 찾을 수 없습니다"
        )

    await db.delete(portfolio)
    await db.commit()


@router.patch("/reorder", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("30/minute")
async def reorder_portfolios(
    request: Request,
    body: PortfolioReorderRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """포트폴리오 순서 일괄 업데이트."""
    if not body.items:
        return
    sort_case = case(
        *[(Portfolio.id == item.id, item.sort_order) for item in body.items],
        else_=Portfolio.sort_order,
    )
    await db.execute(
        update(Portfolio)
        .where(
            Portfolio.user_id == current_user.id,
            Portfolio.id.in_([item.id for item in body.items]),
        )
        .values(sort_order=sort_case)
    )
    await db.commit()
