"""리밸런싱 실행 서비스 — KIS API를 통해 매수/매도 주문을 일괄 실행한다."""
import uuid
from datetime import UTC, datetime

import structlog
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.kis.auth import get_access_token
from app.kis.order import is_overseas_market, place_domestic_order, place_overseas_order
from app.models.asset import AssetAccount
from app.models.user import UserSettings
from app.schemas.rebalancing import ExecutionOrderItem, ExecutionResult, OrderResult
from app.services.credential_service import decrypt

logger = structlog.get_logger()


async def execute_rebalancing(
    user_id: uuid.UUID,
    account_id: uuid.UUID,
    orders: list[ExecutionOrderItem],
    db: AsyncSession,
    redis,
) -> ExecutionResult:
    """선택된 리밸런싱 주문 항목을 KIS API를 통해 순차 실행한다.

    매도 주문을 먼저 처리해 현금을 확보한 뒤 매수 주문을 실행한다.
    개별 주문 실패 시 나머지 주문은 계속 진행된다.
    """
    # KIS 계좌 확인
    account = await db.scalar(
        select(AssetAccount).where(
            AssetAccount.id == account_id,
            AssetAccount.user_id == user_id,
            AssetAccount.is_active == True,  # noqa: E712
        )
    )
    if not account:
        raise HTTPException(status_code=404, detail="계좌를 찾을 수 없습니다.")
    if account.asset_type != "STOCK_KIS":
        raise HTTPException(status_code=400, detail="KIS 계좌만 실행 주문이 가능합니다.")
    if not account.kis_account_no:
        raise HTTPException(status_code=400, detail="계좌번호가 설정되지 않았습니다.")

    # KIS 자격증명 로드
    settings = await db.scalar(
        select(UserSettings).where(UserSettings.user_id == user_id)
    )
    if not settings or not settings.kis_app_key or not settings.kis_app_secret:
        raise HTTPException(status_code=400, detail="KIS 자격증명이 설정되지 않았습니다.")

    app_key = decrypt(settings.kis_app_key)
    app_secret = decrypt(settings.kis_app_secret)
    is_mock = account.is_mock_mode
    account_no = account.kis_account_no

    access_token = await get_access_token(
        app_key, app_secret, is_mock=is_mock, redis=redis, db=db, user_id=str(user_id)
    )

    # 매도 우선: sells → buys 순으로 처리
    sells = [o for o in orders if o.side == "SELL"]
    buys = [o for o in orders if o.side == "BUY"]

    results: list[OrderResult] = []
    for order in sells + buys:
        results.append(
            await _execute_single_order(
                order, app_key, app_secret, access_token, account_no, is_mock
            )
        )

    success_count = sum(1 for r in results if r.status == "SUCCESS")
    fail_count = sum(1 for r in results if r.status == "FAILED")

    logger.info(
        "rebalancing_executed",
        user_id=str(user_id),
        account_id=str(account_id),
        is_mock=is_mock,
        success=success_count,
        failed=fail_count,
    )

    return ExecutionResult(
        account_id=str(account_id),
        account_name=account.name,
        is_mock=is_mock,
        orders=results,
        success_count=success_count,
        fail_count=fail_count,
        executed_at=datetime.now(UTC).isoformat(),
    )


async def _execute_single_order(
    order: ExecutionOrderItem,
    app_key: str,
    app_secret: str,
    access_token: str,
    account_no: str,
    is_mock: bool,
) -> OrderResult:
    if order.quantity <= 0:
        return OrderResult(
            ticker=order.ticker,
            name=order.name,
            market=order.market,
            side=order.side,
            quantity=order.quantity,
            status="SKIPPED",
            error_msg="주문 수량이 0 이하입니다.",
        )

    try:
        if is_overseas_market(order.market):
            result = await place_overseas_order(
                app_key, app_secret, access_token, account_no,
                side=order.side,
                ticker=order.ticker,
                market=order.market,
                quantity=order.quantity,
                is_mock=is_mock,
            )
        else:
            result = await place_domestic_order(
                app_key, app_secret, access_token, account_no,
                side=order.side,
                ticker=order.ticker,
                quantity=order.quantity,
                is_mock=is_mock,
            )

        logger.info(
            "order_placed",
            ticker=order.ticker,
            side=order.side,
            quantity=order.quantity,
            order_no=result.get("order_no"),
            is_mock=is_mock,
        )
        return OrderResult(
            ticker=order.ticker,
            name=order.name,
            market=order.market,
            side=order.side,
            quantity=order.quantity,
            status="SUCCESS",
            order_no=result.get("order_no"),
        )

    except Exception as e:
        logger.warning(
            "order_failed",
            ticker=order.ticker,
            side=order.side,
            quantity=order.quantity,
            error=str(e),
        )
        return OrderResult(
            ticker=order.ticker,
            name=order.name,
            market=order.market,
            side=order.side,
            quantity=order.quantity,
            status="FAILED",
            error_msg=str(e),
        )
