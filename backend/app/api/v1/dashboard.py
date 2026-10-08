from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.cache_store import get_cache_store
from app.limiter import limiter
from app.models.user import User
from app.schemas.action_items import ActionItem
from app.schemas.dashboard import DashboardResponse
from app.services.action_items_service import get_action_items
from app.services.asset_aggregator import get_dashboard_summary

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardResponse)
@limiter.limit("10/minute")
async def dashboard(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cache = await get_cache_store()
    return await get_dashboard_summary(current_user.id, db, cache)


@router.get("/action-items", response_model=list[ActionItem])
@limiter.limit("10/minute")
async def action_items(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    cache=Depends(get_cache_store),
):
    """홈 "지금 할 일" — 리밸런싱·적립 예수금·세금·챌린지 행동 신호를 우선순위 순으로 최대 5건."""
    return await get_action_items(current_user.id, db, cache)
