"""리밸런싱 실행 주문의 취소 가능 판정 (plans/89·90).

execution_service(실행 직후 결과)와 order_cancel_service·이력 상세가 같은 규칙을 쓰도록 분리했다 —
order_cancel_service는 execution_service를 import하므로, 규칙을 거기 두면 실행 쪽에서 쓸 수 없다.
"""

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import ORDER_EXECUTABLE_ASSET_TYPES, OVERSEAS_MARKETS
from app.models.asset import AssetAccount, RebalancingExecutionResult
from app.utils.kst import KST

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
    if asset_type not in ORDER_EXECUTABLE_ASSET_TYPES:
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


async def active_account_asset_types(
    db: AsyncSession, user_id: uuid.UUID, account_ids: Iterable[str | None]
) -> dict[str, str]:
    """주문들의 계좌 id(문자열) → asset_type. 삭제·비활성이거나 UUID가 아닌 계좌는 빠진다(취소 불가).

    비활성 계좌를 넣으면 취소 요청이 `_load_account`(활성 계좌만)에서 404가 되므로 같은 기준으로 거른다.
    """
    ids: set[uuid.UUID] = set()
    for raw in account_ids:
        try:
            ids.add(uuid.UUID(raw or ""))
        except ValueError:
            continue
    if not ids:
        return {}
    rows = await db.execute(
        select(AssetAccount.id, AssetAccount.asset_type).where(
            AssetAccount.user_id == user_id,
            AssetAccount.id.in_(ids),
            AssetAccount.is_active == True,
        )
    )
    return {str(acc_id): asset_type for acc_id, asset_type in rows.all()}
