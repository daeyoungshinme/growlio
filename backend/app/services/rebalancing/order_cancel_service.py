"""리밸런싱 실행 주문의 미체결분 취소 (plans/89).

체결 여부를 미리 조회하지 않고 취소를 바로 요청한다 — KIS 미체결 조회는 모의투자를 지원하지 않고, 조회와
취소 사이에 체결될 수 있어 조회가 정확성을 보장하지도 못한다. 이미 체결된 주문은 증권사가 거부하며 그 사유를
그대로 기록·노출한다. 부분체결이면 잔량 전부를 취소한다. 체결분 되돌리기(반대매매)는 하지 않는다.
"""

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import OVERSEAS_MARKETS
from app.core.logging import public_error_message, redact_secrets
from app.exceptions import BrokerOrderRejectedError
from app.kis import order as kis_order
from app.kis.auth import get_access_token
from app.kis.client import KisApiError
from app.kiwoom import order as kiwoom_order
from app.kiwoom.auth import get_access_token as kiwoom_get_access_token
from app.kiwoom.client import KiwoomApiError
from app.models.asset import AssetAccount, RebalancingExecution, RebalancingExecutionResult
from app.services.rebalancing.execution_service import _load_account, _load_credentials, _load_kiwoom_credentials
from app.utils.cache_keys import invalidate_rebalancing_analysis_cache
from app.utils.kst import KST

logger = structlog.get_logger()

CANCELED = "CANCELED"
CANCEL_FAILED = "CANCEL_FAILED"

# 미국 정규장은 KST 자정을 넘기므로 해외 주문은 날짜 대신 경과 시간으로 본다
_OVERSEAS_CANCEL_WINDOW = timedelta(hours=24)


def cancel_block_reason(
    row: RebalancingExecutionResult, executed_at: datetime, asset_type: str | None, now: datetime | None = None
) -> str | None:
    """앱에서 취소를 요청할 수 없는 사유(한국어), 요청 가능하면 None. 체결 여부는 판단하지 않는다."""
    if row.status != "SUCCESS" or row.action not in ("BUY", "SELL") or not row.order_no:
        return "접수된 주문만 취소할 수 있습니다."
    if row.cancel_status == CANCELED:
        return "이미 취소된 주문입니다."
    if asset_type not in ("STOCK_KIS", "STOCK_KIWOOM"):
        return "이 계좌는 앱에서 주문을 취소할 수 없습니다."
    is_overseas = (row.market or "").upper() in OVERSEAS_MARKETS
    now = now or datetime.now(UTC)
    if is_overseas:
        if now - executed_at > _OVERSEAS_CANCEL_WINDOW:
            return "유효기간이 지난 주문입니다."
    elif executed_at.astimezone(KST).date() != now.astimezone(KST).date():
        # 국내 주문은 당일 장 마감과 함께 소멸한다
        return "당일 주문만 취소할 수 있습니다."
    if asset_type == "STOCK_KIS" and not is_overseas and not row.order_org_no:
        return "이 주문은 앱에서 취소할 수 없습니다. 증권사 앱에서 취소하세요."
    return None


async def _request_broker_cancel(
    row: RebalancingExecutionResult, account: AssetAccount, user_id: uuid.UUID, db: AsyncSession, cache
) -> None:
    is_mock = row.is_mock
    is_overseas = (row.market or "").upper() in OVERSEAS_MARKETS
    order_no = row.order_no or ""
    ticker = row.ticker or ""
    market = row.market or ""

    if account.asset_type == "STOCK_KIWOOM":
        app_key, app_secret = _load_kiwoom_credentials(account)
        token = await kiwoom_get_access_token(
            app_key, app_secret, is_mock=is_mock, cache=cache, db=db, user_id=str(user_id), account_id=str(account.id)
        )
        kiwoom_no = account.kiwoom_account_no or ""
        if is_overseas:
            await kiwoom_order.cancel_overseas_order(
                token, kiwoom_no, ticker=ticker, market=market, order_no=order_no, is_mock=is_mock
            )
        else:
            await kiwoom_order.cancel_domestic_order(
                token, kiwoom_no, ticker=ticker, order_no=order_no, is_mock=is_mock
            )
        return

    app_key, app_secret = _load_credentials(account)
    token = await get_access_token(
        app_key, app_secret, is_mock=is_mock, cache=cache, db=db, user_id=str(user_id), account_id=str(account.id)
    )
    kis_no = account.kis_account_no or ""
    if is_overseas:
        await kis_order.cancel_overseas_order(
            app_key,
            app_secret,
            token,
            kis_no,
            ticker=ticker,
            market=market,
            order_no=order_no,
            quantity=row.quantity or 0,
            is_mock=is_mock,
        )
    else:
        await kis_order.cancel_domestic_order(
            app_key, app_secret, token, kis_no, order_org_no=row.order_org_no or "", order_no=order_no, is_mock=is_mock
        )


async def cancel_execution_order(
    user_id: uuid.UUID, result_id: uuid.UUID, db: AsyncSession, cache
) -> RebalancingExecutionResult:
    """실행 이력의 주문 한 건에 대해 미체결 잔량 취소를 요청하고 결과를 주문 행에 기록한다.

    증권사 거부(이미 체결 등)는 CANCEL_FAILED로 기록해 돌려준다. 네트워크 등 그 밖의 실패는 기록하지 않고
    502로 올려 다시 시도할 수 있게 한다 — 응답 유실이면 실제로는 취소됐을 수 있어 "실패"로 단정하지 않는다.
    """
    row_with_exec = (
        await db.execute(
            select(RebalancingExecutionResult, RebalancingExecution)
            .join(RebalancingExecution, RebalancingExecution.id == RebalancingExecutionResult.execution_id)
            .where(RebalancingExecutionResult.id == result_id, RebalancingExecution.user_id == user_id)
            .with_for_update(of=RebalancingExecutionResult)  # 연속 클릭으로 같은 주문을 두 번 취소 요청하지 않게
        )
    ).first()
    if row_with_exec is None:
        raise HTTPException(status_code=404, detail="주문을 찾을 수 없습니다.")
    row, execution = row_with_exec

    try:
        account_uuid = uuid.UUID(row.account_id or "")
    except ValueError:
        raise HTTPException(status_code=400, detail="이 주문은 앱에서 취소할 수 없습니다.") from None
    account = await _load_account(account_uuid, user_id, db)
    reason = cancel_block_reason(row, execution.executed_at, account.asset_type)
    if reason:
        raise HTTPException(status_code=400, detail=reason)

    try:
        await _request_broker_cancel(row, account, user_id, db, cache)
    except HTTPException:
        raise
    except (BrokerOrderRejectedError, KisApiError, KiwoomApiError) as e:
        # 증권사 논리 오류는 클라이언트가 Kis/KiwoomApiError로 먼저 올린다("취소가능수량 없음" = 이미 체결 등)
        row.cancel_status = CANCEL_FAILED
        row.cancel_message = public_error_message(e)
        logger.warning("rebalancing_order_cancel_rejected", result_id=str(result_id), message=row.cancel_message)
    except Exception as e:
        # 프레임 지역변수에 복호화된 자격증명이 있어 exc_info는 남기지 않는다(execution_service와 같은 이유)
        logger.error(
            "rebalancing_order_cancel_failed",
            result_id=str(result_id),
            error=redact_secrets(str(e)),
            error_type=type(e).__name__,
        )
        await db.rollback()
        raise HTTPException(
            status_code=502, detail="증권사 응답을 받지 못했습니다. 증권사 앱에서 주문 상태를 확인하세요."
        ) from None
    else:
        row.cancel_status = CANCELED
        row.cancel_message = None
        row.canceled_at = datetime.now(UTC)
        logger.info("rebalancing_order_canceled", result_id=str(result_id), ticker=row.ticker, side=row.action)

    await db.commit()
    if execution.portfolio_id and cache:
        await invalidate_rebalancing_analysis_cache(cache, user_id, execution.portfolio_id)
    return row
