"""리밸런싱 실행 API — 주문 실행, 이력 조회."""

import uuid
from collections import defaultdict
from collections.abc import Callable

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db, get_owned_or_404
from app.api.v1._account_deps import get_owned_account
from app.core.cache_store import get_cache_store
from app.limiter import limiter
from app.models.asset import RebalancingExecution
from app.models.portfolio import Portfolio
from app.models.user import User
from app.schemas.rebalancing import (
    ExecutionPlanOverride,
    ExecutionPlanResult,
    ExecutionRequest,
    ExecutionResult,
    OrderResult,
    RebalancingExecutionDetail,
    RebalancingExecutionSummary,
)
from app.services.rebalancing.execution_service import execute_rebalancing
from app.services.rebalancing.quick_execute_service import (
    QuickExecuteOutcome,
    QuickExecuteStatus,
    quick_execute_plan,
)

router = APIRouter(prefix="/rebalancing", tags=["rebalancing"])
logger = structlog.get_logger()


def _plan_generated_message(o: QuickExecuteOutcome) -> str:
    if o.email_sent:
        message = f"계획이 생성되어 이메일로 발송되었습니다 — 매수 {o.buy_count}건"
    elif o.has_email:
        message = f"계획이 생성되었지만 이메일 발송에 실패했습니다 — 매수 {o.buy_count}건"
    else:
        message = f"계획이 생성되었습니다 (등록된 이메일이 없어 알림은 발송되지 않았습니다) — 매수 {o.buy_count}건"
    if o.sell_count:
        message += f", 매도 승인대기 {o.sell_count}건"
    return message


def _tax_blocked_message(o: QuickExecuteOutcome) -> str:
    assert o.tax_gate is not None
    return (
        f"매도로 인한 추정 양도세(약 {o.tax_gate.estimated_tax_krw:,.0f}원)가 설정하신 상한"
        f"({o.tax_gate.max_tax_impact_krw:,.0f}원)을 초과해 실행이 보류됩니다. "
        "자동화 설정의 세금영향 상한을 확인해주세요."
    )


def _daily_cap_blocked_message(o: QuickExecuteOutcome) -> str:
    assert o.daily_cap is not None
    return (
        f"오늘 자동 실행된 금액(약 {o.daily_cap.today_total_krw:,.0f}원)에 이번 계획 예상 금액"
        f"(약 {o.daily_cap.attempted_value_krw:,.0f}원)을 더하면 설정하신 하루 합산 상한"
        f"({o.daily_cap.cap_krw:,.0f}원)을 초과해 실행이 보류됩니다."
    )


_QUICK_EXECUTE_MESSAGES: dict[QuickExecuteStatus, Callable[[QuickExecuteOutcome], str]] = {
    QuickExecuteStatus.ALREADY_PENDING: lambda _o: (
        "이미 대기중인 계획이 있습니다. 리밸런싱 계획 목록에서 확인해주세요."
    ),
    QuickExecuteStatus.MARKET_BLOCKED: lambda o: (
        f"현재 시장 위험 신호({o.composite_level})로 인해 실행이 보류됩니다. "
        "자동화 설정의 시장 상황 조건을 확인해주세요."
    ),
    QuickExecuteStatus.TAX_BLOCKED: _tax_blocked_message,
    QuickExecuteStatus.DAILY_CAP_BLOCKED: _daily_cap_blocked_message,
    QuickExecuteStatus.GENERATION_IN_PROGRESS: lambda _o: "다른 요청이 이미 처리 중입니다. 잠시 후 다시 시도해주세요.",
    QuickExecuteStatus.NO_DRIFT: lambda _o: "포트폴리오가 이미 균형을 이루고 있거나 실행할 주문이 없습니다.",
    QuickExecuteStatus.PLAN_GENERATED: _plan_generated_message,
}


@router.post("/portfolios/{portfolio_id}/execute", response_model=list[ExecutionResult])
@limiter.limit("2/minute")
async def execute_portfolio_rebalancing(
    request: Request,
    portfolio_id: uuid.UUID,
    body: ExecutionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    cache=Depends(get_cache_store),
):
    """선택된 주문 항목을 KIS API를 통해 실제로 매수/매도 실행한다."""
    await get_owned_or_404(db, Portfolio, portfolio_id, current_user.id, "포트폴리오를 찾을 수 없습니다")
    if body.account_id:
        await get_owned_account(body.account_id, current_user.id, db)

    results, _execution_id = await execute_rebalancing(
        user_id=current_user.id,
        account_id=body.account_id,
        orders=body.orders,
        db=db,
        cache=cache,
        portfolio_id=portfolio_id,
        triggered_by="MANUAL",
        strategy=getattr(body, "strategy", "FULL") or "FULL",
    )
    return results


@router.post(
    "/portfolios/{portfolio_id}/quick-execute",
    response_model=ExecutionPlanResult,
    summary="리밸런싱 대기 계획 생성 (즉시 체결 아님)",
)
@limiter.limit("2/minute")
async def create_rebalancing_execution_plan(
    request: Request,
    portfolio_id: uuid.UUID,
    body: ExecutionPlanOverride | None = None,
    account_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    cache=Depends(get_cache_store),
):
    """저장된(또는 화면 미저장) 자동화 알림 설정 기준으로 지금 바로 대기 플랜을 생성한다.

    실제 스케줄 AUTO 실행과 동일한 파이프라인(드리프트 분석 → 대기 플랜 생성 → 계획 안내
    이메일 발송)을 태운다 — 즉시 체결이 아니라 매수는 대기시간 후 자동 실행, 매도는 이메일
    승인이 필요하다. `body`에 값이 있으면 저장된 설정 대신 화면에서 선택한 값을 우선 사용한다.
    `alert_scope == PER_ACCOUNT`인 포트폴리오는 쿼리파라미터 `account_id`로 어느 계좌 전용
    알림 행을 실행할지 반드시 지정해야 한다.
    """
    outcome = await quick_execute_plan(
        portfolio_id,
        account_id,
        body,
        current_user.id,
        db,
        cache,
        verify_account_owned=lambda acc_id: get_owned_account(acc_id, current_user.id, db),
    )
    return ExecutionPlanResult(
        status=outcome.status.value,
        message=_QUICK_EXECUTE_MESSAGES[outcome.status](outcome),
        email_sent=outcome.email_sent,
        plan_id=outcome.plan_id,
        buy_count=outcome.buy_count,
        sell_count=outcome.sell_count,
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
