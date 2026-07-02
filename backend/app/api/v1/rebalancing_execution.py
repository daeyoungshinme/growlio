"""리밸런싱 실행 API — 주문 실행, 이력 조회."""

import uuid
from collections import defaultdict
from typing import Literal, cast

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db, get_owned_or_404
from app.api.v1._account_deps import get_owned_account
from app.limiter import limiter
from app.models.alert import RebalancingAlert
from app.models.asset import RebalancingExecution
from app.models.portfolio import Portfolio
from app.models.user import User
from app.redis_client import get_redis
from app.schemas.rebalancing import (
    ExecutionOrderItem as ExecItem,
)
from app.schemas.rebalancing import (
    ExecutionRequest,
    ExecutionResult,
    OrderResult,
    QuickExecuteOverride,
    RebalancingExecutionDetail,
    RebalancingExecutionSummary,
)
from app.services.alert_service import build_rebalancing_orders, refresh_live_prices
from app.services.portfolio_service import build_portfolio_overview
from app.services.rebalancing_execution_service import execute_rebalancing
from app.services.rebalancing_service import analyze_rebalancing

router = APIRouter(prefix="/rebalancing", tags=["rebalancing"])
logger = structlog.get_logger()


@router.post("/portfolios/{portfolio_id}/execute", response_model=list[ExecutionResult])
@limiter.limit("2/minute")
async def execute_portfolio_rebalancing(
    request: Request,
    portfolio_id: uuid.UUID,
    body: ExecutionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """선택된 주문 항목을 KIS API를 통해 실제로 매수/매도 실행한다."""
    await get_owned_or_404(db, Portfolio, portfolio_id, current_user.id, "포트폴리오를 찾을 수 없습니다")
    if body.account_id:
        await get_owned_account(body.account_id, current_user.id, db)

    return await execute_rebalancing(
        user_id=current_user.id,
        account_id=body.account_id,
        orders=body.orders,
        db=db,
        redis=redis,
        portfolio_id=portfolio_id,
        triggered_by="MANUAL",
        strategy=getattr(body, "strategy", "FULL") or "FULL",
    )


@router.post("/portfolios/{portfolio_id}/quick-execute", response_model=list[ExecutionResult])
@limiter.limit("2/minute")
async def quick_execute_rebalancing(
    request: Request,
    portfolio_id: uuid.UUID,
    body: QuickExecuteOverride | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """포트폴리오 리밸런싱 알림 설정에 기반해 분석 후 즉시 실행한다 (원클릭 실행).

    `body`에 값이 있으면 저장된 알림 설정 대신 화면에서 선택한 값을 우선 사용한다
    (저장하지 않고 바로 테스트 실행할 때 화면 값이 반영되도록).
    """
    portfolio = await db.scalar(
        select(Portfolio)
        .options(
            selectinload(Portfolio.linked_accounts),
            selectinload(Portfolio.items),
        )
        .where(
            Portfolio.id == portfolio_id,
            Portfolio.user_id == current_user.id,
        )
    )
    if not portfolio:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="포트폴리오를 찾을 수 없습니다")

    alert_row = await db.scalar(
        select(RebalancingAlert).where(
            RebalancingAlert.portfolio_id == portfolio_id,
            RebalancingAlert.user_id == current_user.id,
            RebalancingAlert.is_active == True,  # noqa: E712
        )
    )
    if not alert_row or not alert_row.account_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="이 포트폴리오에 자동 실행 계좌가 설정되지 않았습니다. 자동화 설정에서 계좌를 선택해주세요.",
        )

    if body and body.account_id and body.account_id != alert_row.account_id:
        await get_owned_account(body.account_id, current_user.id, db)

    account_id = (body.account_id if body and body.account_id else None) or alert_row.account_id
    strategy = (body.strategy if body and body.strategy else None) or alert_row.strategy or "BUY_ONLY"
    order_type = cast(
        Literal["MARKET", "LIMIT"],
        (body.order_type if body and body.order_type else None) or alert_row.order_type or "MARKET",
    )

    saved_ids = getattr(portfolio, "account_ids", None)
    effective_account_ids = [uuid.UUID(aid) for aid in saved_ids] if saved_ids else None
    overview = await build_portfolio_overview(current_user.id, db, account_ids=effective_account_ids)
    analysis = analyze_rebalancing(portfolio, overview)

    await refresh_live_prices(analysis.items, current_user.id, db, redis)

    orders: list[ExecItem] = build_rebalancing_orders(
        analysis.items, analysis.ticker_account_map, strategy, order_type, str(account_id)
    )

    if not orders:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="실행할 주문이 없습니다. 포트폴리오가 이미 균형을 이루고 있거나 매수 가능한 수량이 없습니다.",
        )

    return await execute_rebalancing(
        user_id=current_user.id,
        account_id=account_id,
        orders=orders,
        db=db,
        redis=redis,
        portfolio_id=portfolio_id,
        triggered_by="ONE_CLICK",
        strategy=strategy,
    )


@router.get("/history", response_model=list[RebalancingExecutionSummary])
@limiter.limit("20/minute")
async def get_rebalancing_history(
    request: Request,
    limit: int = Query(default=20, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """리밸런싱 실행 이력 목록을 반환한다 (최신순)."""
    result = await db.execute(
        select(RebalancingExecution)
        .where(RebalancingExecution.user_id == current_user.id)
        .order_by(desc(RebalancingExecution.executed_at))
        .limit(limit)
    )
    return result.scalars().all()


@router.get("/history/{execution_id}", response_model=RebalancingExecutionDetail)
@limiter.limit("30/minute")
async def get_rebalancing_execution_detail(
    request: Request,
    execution_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """리밸런싱 실행 이력 상세 (주문 결과 포함)."""
    result = await db.execute(
        select(RebalancingExecution)
        .options(selectinload(RebalancingExecution.result_items))
        .where(
            RebalancingExecution.id == execution_id,
            RebalancingExecution.user_id == current_user.id,
        )
    )
    execution = result.scalar_one_or_none()
    if not execution:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="실행 이력을 찾을 수 없습니다")

    detail = RebalancingExecutionDetail.model_validate(execution)
    if execution.result_items:
        by_account: dict[str, dict] = defaultdict(
            lambda: {"orders": [], "is_mock": False, "account_name": "", "executed_at": ""}
        )
        for ri in execution.result_items:
            key = ri.account_id or ""
            by_account[key]["account_name"] = ri.account_name or ""
            by_account[key]["is_mock"] = ri.is_mock
            by_account[key]["executed_at"] = execution.executed_at.isoformat()
            by_account[key]["orders"].append(
                OrderResult(
                    ticker=ri.ticker or "",
                    name=ri.name or "",
                    market=ri.market or "",
                    side=ri.action,
                    quantity=ri.quantity or 0,
                    status=ri.status,
                    order_no=ri.order_no,
                    error_msg=ri.error_message,
                    order_type=ri.order_type,
                )
            )
        detail.results = [
            ExecutionResult(
                account_id=acc_id,
                account_name=data["account_name"],
                is_mock=data["is_mock"],
                orders=data["orders"],
                success_count=sum(1 for o in data["orders"] if o.status == "SUCCESS"),
                fail_count=sum(1 for o in data["orders"] if o.status == "FAILED"),
                executed_at=data["executed_at"],
            )
            for acc_id, data in by_account.items()
        ]
    return detail
