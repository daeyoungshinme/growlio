"""통합 포트폴리오 CRUD API (백테스팅·리밸런싱 공용)."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.portfolio import Portfolio
from app.models.user import User
from app.schemas.portfolio import PortfolioCreate, PortfolioResponse, PortfolioUpdate

router = APIRouter(prefix="/portfolios", tags=["portfolios"])


@router.get("", response_model=list[PortfolioResponse])
async def list_portfolios(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """저장된 포트폴리오 목록."""
    rows = await db.execute(
        select(Portfolio)
        .where(Portfolio.user_id == current_user.id)
        .order_by(Portfolio.created_at)
    )
    return rows.scalars().all()


@router.post("", response_model=PortfolioResponse, status_code=201)
async def create_portfolio(
    body: PortfolioCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """새 포트폴리오 생성."""
    portfolio = Portfolio(
        user_id=current_user.id,
        name=body.name,
        items=[i.model_dump() for i in body.items],
        base_type=body.base_type,
    )
    db.add(portfolio)
    await db.commit()
    await db.refresh(portfolio)
    return portfolio


@router.put("/{portfolio_id}", response_model=PortfolioResponse)
async def update_portfolio(
    portfolio_id: uuid.UUID,
    body: PortfolioUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """포트폴리오 수정."""
    portfolio = await db.scalar(
        select(Portfolio).where(
            Portfolio.id == portfolio_id,
            Portfolio.user_id == current_user.id,
        )
    )
    if not portfolio:
        raise HTTPException(status_code=404, detail="포트폴리오를 찾을 수 없습니다.")

    if body.name is not None:
        portfolio.name = body.name
    if body.items is not None:
        portfolio.items = [i.model_dump() for i in body.items]
    if body.base_type is not None:
        portfolio.base_type = body.base_type

    await db.commit()
    await db.refresh(portfolio)
    return portfolio


@router.delete("/{portfolio_id}", status_code=204)
async def delete_portfolio(
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
        raise HTTPException(status_code=404, detail="포트폴리오를 찾을 수 없습니다.")

    await db.delete(portfolio)
    await db.commit()
