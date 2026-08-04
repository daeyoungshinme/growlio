"""자매 앱(nestlio) 등 외부 서비스가 같은 Supabase 프로젝트의 사용자 JWT로 호출하는
읽기 전용 엔드포인트. growlio 자체 프론트엔드는 이 라우터를 사용하지 않는다.
"""

from datetime import date

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.enums import AssetType
from app.limiter import limiter
from app.models.user import User
from app.services.asset_service import list_accounts as _list_accounts
from app.services.snapshot_service import get_latest_snapshot_with_positions

router = APIRouter(prefix="/external", tags=["external"])


class ExternalAccountBalance(BaseModel):
    id: str
    name: str
    asset_type: AssetType
    current_value_krw: float
    as_of: date | None = None


@router.get("/accounts", response_model=list[ExternalAccountBalance])
@limiter.limit("20/minute")
async def list_account_balances(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """현재 사용자의 활성 계좌별 최신 평가액(KRW)을 반환한다.

    KIS/키움 실시간 재동기화를 트리거하지 않고, 매일 적재되는 스냅샷(`AssetSnapshot.amount_krw`)
    중 계좌별 최신 값을 그대로 돌려준다 — growlio 자체 조회 API와 달리 이 엔드포인트는
    외부 서비스가 자유 빈도로 호출할 수 있어야 하므로 평가 비용이 드는 실시간 재계산을 피한다.
    """
    accounts = await _list_accounts(current_user.id, db, skip=0, limit=200)
    result: list[ExternalAccountBalance] = []
    for account in accounts:
        latest_snap, _positions = await get_latest_snapshot_with_positions(db, account.id)
        if latest_snap is not None:
            value = latest_snap.amount_krw
            as_of = latest_snap.snapshot_date
        else:
            value = account.manual_amount or 0
            as_of = None
        result.append(
            ExternalAccountBalance(
                id=str(account.id),
                name=account.name,
                asset_type=account.asset_type,
                current_value_krw=value,
                as_of=as_of,
            )
        )
    return result
