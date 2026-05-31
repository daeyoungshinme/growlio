"""통합 포트폴리오 CRUD API (백테스팅·리밸런싱 공용)."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.asset import AssetAccount
from app.models.portfolio import Portfolio
from app.models.user import User
from app.schemas.portfolio import PortfolioCreate, PortfolioReorderRequest, PortfolioResponse, PortfolioUpdate

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


@router.get("", response_model=list[PortfolioResponse])
async def list_portfolios(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """저장된 포트폴리오 목록."""
    rows = await db.execute(
        select(Portfolio)
        .where(Portfolio.user_id == current_user.id)
        .order_by(Portfolio.sort_order, Portfolio.created_at)
    )
    return rows.scalars().all()


@router.post("", response_model=PortfolioResponse, status_code=status.HTTP_201_CREATED)
async def create_portfolio(
    body: PortfolioCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """새 포트폴리오 생성."""
    await _validate_account_ids(body.account_ids, current_user.id, db)
    portfolio = Portfolio(
        user_id=current_user.id,
        name=body.name,
        items=[i.model_dump() for i in body.items],
        base_type=body.base_type,
        account_ids=[str(aid) for aid in body.account_ids] if body.account_ids else None,
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="포트폴리오를 찾을 수 없습니다.")

    if body.account_ids is not None:
        await _validate_account_ids(body.account_ids, current_user.id, db)
    if body.name is not None:
        portfolio.name = body.name
    if body.items is not None:
        portfolio.items = [i.model_dump() for i in body.items]
    if body.base_type is not None:
        portfolio.base_type = body.base_type
    if body.account_ids is not None:
        portfolio.account_ids = [str(aid) for aid in body.account_ids] if body.account_ids else None

    await db.commit()
    await db.refresh(portfolio)
    return portfolio


@router.delete("/{portfolio_id}", status_code=status.HTTP_204_NO_CONTENT)
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="포트폴리오를 찾을 수 없습니다.")

    await db.delete(portfolio)
    await db.commit()


@router.patch("/reorder", status_code=status.HTTP_204_NO_CONTENT)
async def reorder_portfolios(
    body: PortfolioReorderRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """포트폴리오 순서 일괄 업데이트."""
    for item in body.items:
        await db.execute(
            update(Portfolio)
            .where(Portfolio.id == item.id, Portfolio.user_id == current_user.id)
            .values(sort_order=item.sort_order)
        )
    await db.commit()
