"""통합 포트폴리오 CRUD — 항목·지수 그룹 행 생성, 연동 계좌와 `AssetAccount.target_portfolio_id` 동기화.

캐시 무효화와 응답 조립은 라우터(`api/v1/portfolios.py`)가 맡는다.
"""

from __future__ import annotations

import uuid
from collections.abc import Collection, Sequence

from sqlalchemy import case, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.exceptions import BadRequestError, NotFoundError
from app.models.asset import AssetAccount
from app.models.portfolio import (
    GROUP_ROLE_DOMESTIC_ALT,
    GROUP_ROLE_MEMBER,
    Portfolio,
    PortfolioAccount,
    PortfolioItem,
    PortfolioItemMember,
)
from app.schemas.portfolio import PortfolioCreate, PortfolioReorderItem, PortfolioUpdate
from app.schemas.portfolio import PortfolioItem as PortfolioItemSchema

PORTFOLIO_NOT_FOUND = "포트폴리오를 찾을 수 없습니다"
PORTFOLIO_RELATIONS = (selectinload(Portfolio.items), selectinload(Portfolio.linked_accounts))


async def validate_owned_account_ids(
    db: AsyncSession,
    user_id: uuid.UUID,
    account_ids: list[uuid.UUID] | None,
) -> None:
    """account_ids가 모두 user_id 소유인지 확인한다. 아니면 400."""
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
        raise BadRequestError(f"유효하지 않은 계좌 ID: {', '.join(invalid)}")


def build_portfolio_item(portfolio_id: uuid.UUID, idx: int, item: PortfolioItemSchema) -> PortfolioItem:
    """요청 항목 → ORM 행. 지수 그룹이면 멤버·국내 대체 종목 행도 함께 만든다(plans/74)."""
    row = PortfolioItem(
        portfolio_id=portfolio_id,
        ticker=item.ticker,
        name=item.name,
        market=item.market,
        weight=item.weight,
        sort_order=idx,
    )
    group = item.group
    if group is None:
        return row
    row.group_key = group.key
    row.group_label = group.label or None
    members = [(m, GROUP_ROLE_MEMBER) for m in group.members]
    if group.domestic_alt is not None:
        members.append((group.domestic_alt, GROUP_ROLE_DOMESTIC_ALT))
    row.members = [
        PortfolioItemMember(ticker=m.ticker, market=m.market, name=m.name, role=role, leverage=m.leverage, sort_order=i)
        for i, (m, role) in enumerate(members)
    ]
    return row


def _add_items(db: AsyncSession, portfolio_id: uuid.UUID, items: Sequence[PortfolioItemSchema]) -> None:
    for idx, item in enumerate(items):
        db.add(build_portfolio_item(portfolio_id, idx, item))


def _link_accounts(db: AsyncSession, portfolio_id: uuid.UUID, account_ids: Collection[uuid.UUID]) -> None:
    for aid in account_ids:
        db.add(PortfolioAccount(portfolio_id=portfolio_id, account_id=aid))


async def _claim_target(db: AsyncSession, portfolio_id: uuid.UUID, account_ids: Collection[uuid.UUID]) -> None:
    """목표 포트폴리오가 비어 있는 계좌만 이 포트폴리오로 채운다(다른 포트폴리오를 목표로 둔 계좌는 그대로)."""
    if not account_ids:
        return
    await db.execute(
        update(AssetAccount)
        .where(AssetAccount.id.in_(list(account_ids)), AssetAccount.target_portfolio_id.is_(None))
        .values(target_portfolio_id=portfolio_id)
    )


async def _release_target(db: AsyncSession, portfolio_id: uuid.UUID, account_ids: Collection[uuid.UUID]) -> None:
    """연동에서 빠진 계좌 중 이 포트폴리오를 목표로 둔 계좌만 목표를 비운다."""
    if not account_ids:
        return
    await db.execute(
        update(AssetAccount)
        .where(AssetAccount.id.in_(list(account_ids)), AssetAccount.target_portfolio_id == portfolio_id)
        .values(target_portfolio_id=None)
    )


async def load_portfolio_with_relations(db: AsyncSession, portfolio_id: uuid.UUID) -> Portfolio:
    result = await db.execute(select(Portfolio).where(Portfolio.id == portfolio_id).options(*PORTFOLIO_RELATIONS))
    return result.scalar_one()


async def list_portfolios(db: AsyncSession, user_id: uuid.UUID) -> list[Portfolio]:
    rows = await db.execute(
        select(Portfolio)
        .where(Portfolio.user_id == user_id)
        .order_by(Portfolio.sort_order, Portfolio.created_at)
        .options(*PORTFOLIO_RELATIONS)
    )
    return list(rows.scalars().all())


async def create_portfolio(db: AsyncSession, user_id: uuid.UUID, body: PortfolioCreate) -> Portfolio:
    """포트폴리오를 만들고 커밋한 뒤 관계를 로드해 돌려준다."""
    await validate_owned_account_ids(db, user_id, body.account_ids)
    portfolio = Portfolio(
        user_id=user_id,
        name=body.name,
        base_type=body.base_type,
        investment_horizon=body.investment_horizon,
        tax_type=body.tax_type,
    )
    db.add(portfolio)
    await db.flush()  # id 생성

    _add_items(db, portfolio.id, body.items)
    if body.account_ids:
        _link_accounts(db, portfolio.id, body.account_ids)
        await _claim_target(db, portfolio.id, body.account_ids)

    await db.commit()
    return await load_portfolio_with_relations(db, portfolio.id)


async def update_portfolio(
    db: AsyncSession, user_id: uuid.UUID, portfolio_id: uuid.UUID, body: PortfolioUpdate
) -> Portfolio:
    """포트폴리오를 수정하고 커밋한 뒤 관계를 로드해 돌려준다. 소유하지 않았으면 404."""
    result = await db.execute(
        select(Portfolio)
        .where(Portfolio.id == portfolio_id, Portfolio.user_id == user_id)
        .options(*PORTFOLIO_RELATIONS)
    )
    portfolio = result.scalar_one_or_none()
    if not portfolio:
        raise NotFoundError(PORTFOLIO_NOT_FOUND)

    if body.account_ids is not None:
        await validate_owned_account_ids(db, user_id, body.account_ids)
    if body.name is not None:
        portfolio.name = body.name
    if body.base_type is not None:
        portfolio.base_type = body.base_type
    # 명시적으로 null을 보낸 경우(태그 해제)와 필드 미전송(변경 없음)을 구분
    fields_set = body.model_fields_set
    if "investment_horizon" in fields_set:
        portfolio.investment_horizon = body.investment_horizon
    if "tax_type" in fields_set:
        portfolio.tax_type = body.tax_type

    if body.items is not None:
        await db.execute(delete(PortfolioItem).where(PortfolioItem.portfolio_id == portfolio_id))
        _add_items(db, portfolio.id, body.items)

    if body.account_ids is not None:
        old_ids = {str(la.account_id) for la in portfolio.linked_accounts}
        new_ids = {str(aid) for aid in body.account_ids}

        await db.execute(delete(PortfolioAccount).where(PortfolioAccount.portfolio_id == portfolio_id))
        _link_accounts(db, portfolio.id, body.account_ids)
        await _claim_target(db, portfolio.id, [uuid.UUID(aid) for aid in new_ids - old_ids])
        await _release_target(db, portfolio.id, [uuid.UUID(aid) for aid in old_ids - new_ids])

    await db.commit()
    return await load_portfolio_with_relations(db, portfolio_id)


async def reorder_portfolios(db: AsyncSession, user_id: uuid.UUID, items: Sequence[PortfolioReorderItem]) -> None:
    """포트폴리오 순서를 일괄 갱신하고 커밋한다. user_id 소유 행만 바뀐다."""
    sort_case = case(
        *[(Portfolio.id == item.id, item.sort_order) for item in items],
        else_=Portfolio.sort_order,
    )
    await db.execute(
        update(Portfolio)
        .where(Portfolio.user_id == user_id, Portfolio.id.in_([item.id for item in items]))
        .values(sort_order=sort_case)
    )
    await db.commit()
