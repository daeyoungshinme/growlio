"""리밸런싱 알림 CRUD."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.v1._account_deps import get_owned_or_404
from app.limiter import limiter
from app.models.alert import RebalancingAlert
from app.models.asset import AssetAccount
from app.models.portfolio import Portfolio
from app.models.user import User
from app.schemas.rebalancing import RebalancingAlertCreate, RebalancingAlertResponse, TestAlertResponse
from app.services._rebalancing_alert_queries import get_alert_by_portfolio

router = APIRouter()


def _build_response(alert: RebalancingAlert) -> RebalancingAlertResponse:
    return RebalancingAlertResponse(
        id=alert.id,
        portfolio_id=alert.portfolio_id,
        is_active=alert.is_active,
        threshold_pct=float(alert.threshold_pct),
        schedule_type=alert.schedule_type,
        schedule_day_of_week=alert.schedule_day_of_week,
        schedule_day_of_month=alert.schedule_day_of_month,
        trigger_condition=alert.trigger_condition,
        mode=alert.mode,
        strategy=alert.strategy,
        account_id=alert.account_id,
        order_type=alert.order_type,
        market_condition_mode=alert.market_condition_mode,
        auto_execution_time=getattr(alert, "auto_execution_time", None),
        notify_time=getattr(alert, "notify_time", "08:30"),
        last_triggered_at=alert.last_triggered_at,
        created_at=alert.created_at,
        updated_at=alert.updated_at,
    )


@router.get("/rebalancing", response_model=list[RebalancingAlertResponse])
@limiter.limit("30/minute")
async def list_rebalancing_alerts(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """내 리밸런싱 알림 목록 조회."""
    result = await db.execute(
        select(RebalancingAlert)
        .where(RebalancingAlert.user_id == current_user.id)
        .order_by(RebalancingAlert.created_at)
    )
    alerts = result.scalars().all()
    return [_build_response(a) for a in alerts]


@router.get("/rebalancing/{portfolio_id}", response_model=RebalancingAlertResponse)
@limiter.limit("30/minute")
async def get_rebalancing_alert(
    request: Request,
    portfolio_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """포트폴리오 리밸런싱 알림 설정 조회."""
    alert = await get_alert_by_portfolio(db, portfolio_id, current_user.id)
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="알림이 설정되지 않았습니다")
    return _build_response(alert)


@router.put("/rebalancing/{portfolio_id}", response_model=RebalancingAlertResponse)
@limiter.limit("30/minute")
async def upsert_rebalancing_alert(
    request: Request,
    portfolio_id: uuid.UUID,
    body: RebalancingAlertCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """포트폴리오 리밸런싱 알림 생성 또는 수정 (upsert)."""
    await get_owned_or_404(db, Portfolio, portfolio_id, current_user.id, "포트폴리오를 찾을 수 없습니다")

    if body.mode == "AUTO":
        if body.account_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="자동 실행 모드에는 KIS 연동 계좌를 선택해야 합니다",
            )
        exec_account = await db.scalar(
            select(AssetAccount).where(
                AssetAccount.id == body.account_id,
                AssetAccount.user_id == current_user.id,
            )
        )
        if not exec_account or exec_account.asset_type != "STOCK_KIS":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="자동 실행 계좌는 KIS 연동 계좌만 사용할 수 있습니다",
            )

    alert = await get_alert_by_portfolio(db, portfolio_id, current_user.id)
    if alert:
        alert.threshold_pct = body.threshold_pct
        alert.schedule_type = body.schedule_type
        alert.schedule_day_of_week = body.schedule_day_of_week
        alert.schedule_day_of_month = body.schedule_day_of_month
        alert.trigger_condition = body.trigger_condition
        alert.mode = body.mode
        alert.strategy = body.strategy
        alert.account_id = body.account_id
        alert.order_type = body.order_type
        alert.market_condition_mode = body.market_condition_mode
        alert.auto_execution_time = body.auto_execution_time
        alert.notify_time = body.notify_time
        alert.is_active = True
    else:
        alert = RebalancingAlert(
            user_id=current_user.id,
            portfolio_id=portfolio_id,
            threshold_pct=body.threshold_pct,
            schedule_type=body.schedule_type,
            schedule_day_of_week=body.schedule_day_of_week,
            schedule_day_of_month=body.schedule_day_of_month,
            trigger_condition=body.trigger_condition,
            mode=body.mode,
            strategy=body.strategy,
            account_id=body.account_id,
            order_type=body.order_type,
            market_condition_mode=body.market_condition_mode,
            auto_execution_time=body.auto_execution_time,
            notify_time=body.notify_time,
            is_active=True,
        )
        db.add(alert)

    await db.commit()
    await db.refresh(alert)
    return _build_response(alert)


@router.post("/rebalancing/{portfolio_id}/test", response_model=TestAlertResponse)
@limiter.limit("3/minute")
async def trigger_rebalancing_alert_test(
    request: Request,
    portfolio_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """리밸런싱 자동화 알림 테스트 발송.

    스케줄/드리프트 조건 없이 즉시 현재 포트폴리오 데이터로 이메일+FCM 발송.
    """
    from app.services.rebalancing_alert_service import send_test_rebalancing_alert

    alert = await get_alert_by_portfolio(db, portfolio_id, current_user.id)
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="알림이 설정되지 않았습니다")

    result = await send_test_rebalancing_alert(
        portfolio_id=portfolio_id,
        user_id=current_user.id,
        db=db,
    )

    email_sent = result["email_sent"]
    push_sent = result["push_sent"]

    if email_sent and push_sent:
        message = "테스트 알림 발송 완료 (이메일 ✓, 푸시 ✓)"
    elif email_sent:
        message = "테스트 이메일 발송 완료 (FCM 미설정 또는 토큰 없음)"
    elif push_sent:
        message = "테스트 푸시 발송 완료 (SMTP 미설정)"
    else:
        message = "알림 채널 없음 — 이메일 또는 FCM 설정을 확인해주세요"

    return TestAlertResponse(email_sent=email_sent, push_sent=push_sent, message=message)


@router.delete("/rebalancing/{portfolio_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("20/minute")
async def delete_rebalancing_alert(
    request: Request,
    portfolio_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """포트폴리오 리밸런싱 알림 삭제."""
    alert = await get_alert_by_portfolio(db, portfolio_id, current_user.id)
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="알림을 찾을 수 없습니다")
    await db.delete(alert)
    await db.commit()
