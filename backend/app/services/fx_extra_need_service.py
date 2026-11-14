"""추가 환전 항목(여행 등) — 날짜가 정해진 달러의 분할 환전 구간(plans/123).

- 적립 환전 계획(`fx_plan_service.get_fx_plan`)과 따로 계산한다. 증권 계좌 보유 달러로 상쇄하지 않는다 —
  여행 달러는 보통 은행·트래블카드로 따로 바꾸고, 증권 계좌 달러는 적립 매수에 쓰인다.
- 필요일까지 `FX_EXTRA_URGENT_DAYS` 이하면 목표 환율을 기다리지 않고 남은 금액 전부를 "지금" 구간으로 둔다.
- 증권 계좌 달러 예수금으로 바꿔 둔 항목은 `reserved_account_id`로 그 계좌를 지정한다 — 적립 환전 계획이
  그 계좌 보유 달러에서 `exchanged_usd`만큼 뺀다(`fx_plan_service.reserved_usd_by_account`, 필요일 전까지).
  총자산·리밸런싱·자동매수 가용 현금은 바꾸지 않는다.
- 구간 알림은 `fx_plan_service.sync_fx_plan_alerts(..., fx_need_id=)`가 맞춘다. 항목을 지우면 알림도 CASCADE로 지워지고,
  필요일이 지난 항목의 알림은 환율 알림 잡이 보내지 않는다.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import date
from typing import Any, Literal

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FX_EXTRA_URGENT_DAYS, MAX_FX_EXTRA_NEEDS_PER_USER, POSITION_STOCK_ASSET_TYPES
from app.core.database import release_read_connection
from app.exceptions import BadRequestError, ConflictError, NotFoundError
from app.models.asset import AssetAccount
from app.models.fx_extra_need import FxExtraNeed
from app.services.accounts._account_queries import active_accounts_stmt
from app.services.fx_plan_service import FxPosition, FxTranche, compute_fx_plan, load_fx_rate_context
from app.utils.cache_keys import CacheStoreType
from app.utils.kst import today_kst
from app.utils.quota_lock import lock_user_for_quota

logger = structlog.get_logger()

FxExtraNeedStatus = Literal["OK", "DONE", "PAST_DUE", "NO_RATE"]

_DONE_EPSILON_USD = 0.005


def compute_extra_need_tranches(
    position: FxPosition | None, remaining_usd: float, days_left: int, rate: float
) -> list[FxTranche]:
    """남은 달러를 구간으로 나눈다. 필요일이 가까우면(`FX_EXTRA_URGENT_DAYS` 이하) 전액 "지금"."""
    if remaining_usd <= _DONE_EPSILON_USD or days_left < 0:
        return []
    if days_left <= FX_EXTRA_URGENT_DAYS:
        return [FxTranche("지금", None, round(remaining_usd, 2), round(remaining_usd * rate))]
    tranches = compute_fx_plan(position, remaining_usd, rate)
    # 위치를 모르면 compute_fx_plan은 "적립일에 환전" 한 구간을 준다 — 추가 환전에는 적립일이 없다
    return [
        FxTranche("필요일 전에 환전", None, t.usd, t.krw_estimate) if t.label == "적립일에 환전" else t
        for t in tranches
    ]


def _need_status(remaining: float, days_left: int, has_rate: bool) -> FxExtraNeedStatus:
    if remaining <= _DONE_EPSILON_USD:
        return "DONE"
    if days_left < 0:
        return "PAST_DUE"
    if not has_rate:
        return "NO_RATE"
    return "OK"


def build_need_row(
    need: FxExtraNeed,
    position: FxPosition | None,
    rate: float,
    has_rate: bool,
    today: date,
    reserved_account_name: str | None = None,
) -> dict[str, Any]:
    amount = float(need.amount_usd)
    exchanged = min(float(need.exchanged_usd or 0), amount)
    remaining = max(0.0, amount - exchanged)
    days_left = (need.due_date - today).days
    status = _need_status(remaining, days_left, has_rate)
    tranches = compute_extra_need_tranches(position, remaining, days_left, rate) if status == "OK" else []
    return {
        "id": need.id,
        "name": need.name,
        "amount_usd": round(amount, 2),
        "exchanged_usd": round(exchanged, 2),
        "remaining_usd": round(remaining, 2),
        "due_date": need.due_date,
        "days_left": days_left,
        "status": status,
        "tranches": [asdict(t) for t in tranches],
        # 보관 계좌가 삭제(비활성)되면 이름이 None으로 온다 — 예약이 없는 것으로 보여 준다(fx_plan_service._held_usd도
        # 활성 계좌만 세므로 실제로 적용되지 않는다)
        "reserved_account_id": need.reserved_account_id if reserved_account_name else None,
        "reserved_account_name": reserved_account_name if need.reserved_account_id else None,
    }


async def _user_needs(db: AsyncSession, user_id: uuid.UUID) -> list[tuple[FxExtraNeed, str | None]]:
    """(항목, 보관 증권 계좌 이름) — 필요일 빠른 순."""
    rows = (
        await db.execute(
            select(FxExtraNeed, AssetAccount.name)
            .outerjoin(
                AssetAccount,
                (AssetAccount.id == FxExtraNeed.reserved_account_id) & (AssetAccount.is_active == True),
            )
            .where(FxExtraNeed.user_id == user_id)
            .order_by(FxExtraNeed.due_date, FxExtraNeed.created_at)
        )
    ).all()
    return [(need, name) for need, name in rows]


async def list_fx_extra_needs(db: AsyncSession, cache: CacheStoreType, user_id: uuid.UUID) -> dict[str, Any]:
    """사용자의 추가 환전 항목과 항목별 구간(필요일 빠른 순)."""
    needs = await _user_needs(db, user_id)
    if not needs:
        return {"rate": None, "rate_is_live": True, "needs": []}
    # 환율 1년 일봉(콜드면 Yahoo 수 초) 대기 중 커넥션을 쥐지 않는다(plans/126 B3)
    await release_read_connection(db)
    ctx = await load_fx_rate_context(cache)
    today = today_kst()
    return {
        "rate": round(ctx.rate, 2) if ctx.has_rate else None,
        "rate_is_live": ctx.rate_is_live,
        "needs": [build_need_row(n, ctx.position, ctx.rate, ctx.has_rate, today, name) for n, name in needs],
    }


async def get_owned_need(db: AsyncSession, user_id: uuid.UUID, need_id: uuid.UUID) -> FxExtraNeed:
    need = await db.scalar(select(FxExtraNeed).where(FxExtraNeed.id == need_id, FxExtraNeed.user_id == user_id))
    if need is None:
        raise NotFoundError(detail="추가 환전 항목을 찾을 수 없습니다")
    return need


async def _owned_stock_account(db: AsyncSession, user_id: uuid.UUID, account_id: uuid.UUID) -> AssetAccount:
    """보관 계좌는 사용자의 활성 증권 계좌만 — 그 외(타인·비활성·은행 계좌)는 404."""
    account = await db.scalar(
        active_accounts_stmt(user_id).where(
            AssetAccount.id == account_id, AssetAccount.asset_type.in_(POSITION_STOCK_ASSET_TYPES)
        )
    )
    if account is None:
        raise NotFoundError(detail="증권 계좌를 찾을 수 없습니다")
    return account


async def reserved_account_name(db: AsyncSession, need: FxExtraNeed) -> str | None:
    """생성·수정 응답 한 행에 실을 보관 계좌 이름."""
    if need.reserved_account_id is None:
        return None
    name: str | None = await db.scalar(
        select(AssetAccount.name).where(AssetAccount.id == need.reserved_account_id, AssetAccount.is_active == True)
    )
    return name


def _check_amounts(amount: float, exchanged: float) -> None:
    if exchanged > amount:
        raise BadRequestError(detail="이미 환전한 금액이 필요한 금액보다 클 수 없습니다")


async def create_fx_extra_need(
    db: AsyncSession,
    user_id: uuid.UUID,
    name: str,
    amount_usd: float,
    exchanged_usd: float,
    due_date: date,
    *,
    reserved_account_id: uuid.UUID | None = None,
) -> FxExtraNeed:
    if due_date < today_kst():
        raise BadRequestError(detail="필요일은 오늘 이후여야 합니다")
    _check_amounts(amount_usd, exchanged_usd)
    if reserved_account_id is not None:
        await _owned_stock_account(db, user_id, reserved_account_id)
    await lock_user_for_quota(db, user_id)  # 동시 생성이 상한을 넘지 않게(plans/129 B3)
    count = await db.scalar(select(func.count()).select_from(FxExtraNeed).where(FxExtraNeed.user_id == user_id))
    if (count or 0) >= MAX_FX_EXTRA_NEEDS_PER_USER:
        raise ConflictError(
            detail=f"추가 환전 항목은 {MAX_FX_EXTRA_NEEDS_PER_USER}개까지 만들 수 있습니다. 지난 항목은 지워주세요"
        )
    need = FxExtraNeed(
        user_id=user_id,
        name=name,
        amount_usd=amount_usd,
        exchanged_usd=exchanged_usd,
        due_date=due_date,
        reserved_account_id=reserved_account_id,
    )
    db.add(need)
    await db.commit()
    await db.refresh(need)
    logger.info("fx_extra_need_created", user_id=str(user_id), need_id=str(need.id))
    return need


async def update_fx_extra_need(
    db: AsyncSession, user_id: uuid.UUID, need_id: uuid.UUID, changes: dict[str, Any]
) -> FxExtraNeed:
    """보낸 필드만 바꾼다. 필요일을 과거로 옮길 수는 없다(이미 지난 항목의 다른 필드 수정은 허용).

    `reserved_account_id`는 None도 값이다(계좌 밖으로 해제) — 키가 있으면 그대로 반영한다.
    """
    need = await get_owned_need(db, user_id, need_id)
    due = changes.get("due_date")
    if due is not None and due != need.due_date and due < today_kst():
        raise BadRequestError(detail="필요일은 오늘 이후여야 합니다")
    amount = float(changes.get("amount_usd", need.amount_usd))
    exchanged = float(changes.get("exchanged_usd", need.exchanged_usd or 0))
    _check_amounts(amount, exchanged)
    if "reserved_account_id" in changes:
        account_id = changes["reserved_account_id"]
        # 같은 id를 다시 보내도 확인한다 — 그 사이 계좌가 삭제됐으면 예약을 살려 두지 않는다
        if account_id is not None:
            await _owned_stock_account(db, user_id, account_id)
        need.reserved_account_id = account_id
    for field in ("name", "amount_usd", "exchanged_usd", "due_date"):
        if field in changes and changes[field] is not None:
            setattr(need, field, changes[field])
    await db.commit()
    await db.refresh(need)
    return need


async def delete_fx_extra_need(db: AsyncSession, user_id: uuid.UUID, need_id: uuid.UUID) -> None:
    """항목을 지운다 — 이 항목의 구간 알림은 FK CASCADE로 함께 지워진다."""
    need = await get_owned_need(db, user_id, need_id)
    await db.delete(need)
    await db.commit()
    logger.info("fx_extra_need_deleted", user_id=str(user_id), need_id=str(need_id))
