"""리밸런싱 실행 API — 주문 실행, 이력 조회."""

import uuid
from collections import defaultdict

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
from app.models.user import User, UserSettings
from app.redis_client import get_redis
from app.schemas.rebalancing import (
    ExecutionRequest,
    ExecutionResult,
    OrderResult,
    QuickExecuteOverride,
    QuickExecuteResult,
    RebalancingExecutionDetail,
    RebalancingExecutionSummary,
)
from app.services.rebalancing_execution_service import execute_rebalancing
from app.services.rebalancing_plan_service import (
    build_pending_plan_for_alert,
    has_pending_plan_for_alert,
    notify_plan_generated,
)

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

    results, _execution_id = await execute_rebalancing(
        user_id=current_user.id,
        account_id=body.account_id,
        orders=body.orders,
        db=db,
        redis=redis,
        portfolio_id=portfolio_id,
        triggered_by="MANUAL",
        strategy=getattr(body, "strategy", "FULL") or "FULL",
    )
    return results


@router.post("/portfolios/{portfolio_id}/quick-execute", response_model=QuickExecuteResult)
@limiter.limit("2/minute")
async def quick_execute_rebalancing(
    request: Request,
    portfolio_id: uuid.UUID,
    body: QuickExecuteOverride | None = None,
    account_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """저장된(또는 화면 미저장) 자동화 알림 설정 기준으로 지금 바로 대기 플랜을 생성한다.

    실제 스케줄 AUTO 실행과 동일한 파이프라인(드리프트 분석 → 대기 플랜 생성 → 계획 안내
    이메일 발송)을 태운다 — 즉시 체결이 아니라 매수는 대기시간 후 자동 실행, 매도는 이메일
    승인이 필요하다. `body`에 값이 있으면 저장된 설정 대신 화면에서 선택한 값을 우선 사용한다.
    `alert_scope == PER_ACCOUNT`인 포트폴리오는 쿼리파라미터 `account_id`로 어느 계좌 전용
    알림 행을 실행할지 반드시 지정해야 한다.
    """
    from app.services.market_signal_service import get_market_signal

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

    is_per_account = getattr(portfolio, "alert_scope", "AGGREGATE") == "PER_ACCOUNT"
    if is_per_account and account_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="계좌별 독립 설정 포트폴리오는 account_id를 지정해야 합니다",
        )

    account_filter = (
        (RebalancingAlert.alert_scope == "PER_ACCOUNT") & (RebalancingAlert.account_id == account_id)
        if is_per_account
        else RebalancingAlert.alert_scope == "AGGREGATE"
    )
    alert_row = await db.scalar(
        select(RebalancingAlert).where(
            RebalancingAlert.portfolio_id == portfolio_id,
            RebalancingAlert.user_id == current_user.id,
            RebalancingAlert.is_active == True,  # noqa: E712
            account_filter,
        )
    )
    if not alert_row or not alert_row.account_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="이 포트폴리오에 자동 실행 계좌가 설정되지 않았습니다. 자동화 설정에서 계좌를 선택해주세요.",
        )

    if body and body.account_id and body.account_id != alert_row.account_id:
        await get_owned_account(body.account_id, current_user.id, db)

    if await has_pending_plan_for_alert(alert_row.id, db):
        return QuickExecuteResult(
            status="ALREADY_PENDING",
            message="이미 대기중인 계획이 있습니다. 리밸런싱 계획 목록에서 확인해주세요.",
        )

    try:
        market_signal = await get_market_signal(redis)
        composite_level: str = market_signal.get("composite_level", "GREEN")
    except Exception as exc:
        logger.warning("market_signal_fetch_failed_in_quick_execute", error=str(exc))
        composite_level = "GREEN"

    market_mode = getattr(alert_row, "market_condition_mode", "DISABLED")
    blocked = (market_mode == "CAUTIOUS" and composite_level == "RED") or (
        market_mode == "STRICT" and composite_level in ("YELLOW", "RED")
    )
    if blocked:
        return QuickExecuteResult(
            status="MARKET_BLOCKED",
            message=f"현재 시장 위험 신호({composite_level})로 인해 실행이 보류됩니다. "
            "자동화 설정의 시장 상황 조건을 확인해주세요.",
        )

    generated = await build_pending_plan_for_alert(
        alert_row,
        portfolio,
        db,
        composite_level,
        strategy_override=body.strategy if body else None,
        order_type_override=body.order_type if body else None,
        account_id_override=body.account_id if body else None,
    )
    if generated is None:
        return QuickExecuteResult(
            status="NO_DRIFT",
            message="포트폴리오가 이미 균형을 이루고 있거나 실행할 주문이 없습니다.",
        )
    plan, buy_token, sell_token = generated

    settings_row = await db.execute(
        select(User.email, UserSettings.notification_email, UserSettings.fcm_token)
        .select_from(User)
        .outerjoin(UserSettings, UserSettings.user_id == User.id)
        .where(User.id == current_user.id)
    )
    user_email, notification_email, fcm_token = settings_row.first() or (None, None, None)
    email = notification_email or user_email

    email_sent = await notify_plan_generated(
        plan,
        alert_row,
        portfolio,
        buy_token,
        sell_token,
        email,
        fcm_token,
        composite_level,
        db,
        note="수동 테스트",
    )
    await db.commit()

    buy_count = sum(len(leg.items) for leg in plan.legs if leg.side == "BUY")
    sell_count = sum(len(leg.items) for leg in plan.legs if leg.side == "SELL")
    if email_sent:
        message = f"계획이 생성되어 이메일로 발송되었습니다 — 매수 {buy_count}건"
    elif email:
        message = f"계획이 생성되었지만 이메일 발송에 실패했습니다 — 매수 {buy_count}건"
    else:
        message = f"계획이 생성되었습니다 (등록된 이메일이 없어 알림은 발송되지 않았습니다) — 매수 {buy_count}건"
    if sell_count:
        message += f", 매도 승인대기 {sell_count}건"
    return QuickExecuteResult(
        status="PLAN_GENERATED",
        message=message,
        email_sent=email_sent,
        plan_id=plan.id,
        buy_count=buy_count,
        sell_count=sell_count,
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
