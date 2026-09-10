"""적립식 투자 챌린지 서비스 — 진행률/스트릭 계산 + CRUD.

진행률·스트릭은 저장하지 않고 매 조회 시 `transactions`/스냅샷에서 재계산한다.
스트릭 기본 단위는 "해당 월 순입금 > 0" — 목표액(target_amount)을 나중에 수정해도 과거
스트릭이 소급 변경되지 않도록 한다(dca_service의 소급 재계산 함정 회피).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from dateutil.relativedelta import relativedelta
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.challenge import (
    CHALLENGE_ACTIVE,
    CHALLENGE_DEPOSIT,
    CHALLENGE_RETURN_PCT,
    CHALLENGE_TARGET_VALUE,
    InvestmentChallenge,
)
from app.schemas.challenge import (
    ChallengeCreate,
    ChallengeMonth,
    ChallengeProgress,
    ChallengeResponse,
    ChallengeSummary,
    ChallengeUpdate,
)
from app.services.composition_calculator import build_asset_totals, exclude_real_estate
from app.utils.cache_keys import (
    TTL_CHALLENGE_PROGRESS,
    CacheStoreType,
    challenge_progress_key,
    get_cached_json,
    invalidate_user_caches,
    set_cached_json,
)

_KST = ZoneInfo("Asia/Seoul")
_NUDGE_DAY_OF_MONTH = 20  # 이 날짜 이후부터 "이번 달 아직 적립 안 함"을 네비 배지로 노출


def _now_kst_date() -> date:
    return datetime.now(_KST).date()


def _month_key(d: date) -> str:
    return d.strftime("%Y-%m")


def _add_months(month_str: str, delta: int) -> str:
    y, m = (int(x) for x in month_str.split("-"))
    return _month_key(date(y, m, 1) + relativedelta(months=delta))


def _iter_months(start_month: str, end_month: str) -> list[str]:
    """start_month..end_month(포함) 월 키 리스트. start > end면 빈 리스트."""
    if start_month > end_month:
        return []
    out = []
    cur = start_month
    while cur <= end_month:
        out.append(cur)
        cur = _add_months(cur, 1)
    return out


async def _monthly_net_deposits(
    user_id: uuid.UUID,
    db: AsyncSession,
    start_month: str,
    account_id: uuid.UUID | None,
) -> dict[str, float]:
    """start_month 이후 각 월의 순입금(DEPOSIT - WITHDRAWAL) 합계. {"2026-01": 500000.0, ...}"""
    base_sql = """
        SELECT to_char(transaction_date, 'YYYY-MM') AS month,
               SUM(CASE WHEN transaction_type = 'DEPOSIT' THEN amount ELSE -amount END) AS net
        FROM transactions
        WHERE user_id = :user_id
          AND transaction_type IN ('DEPOSIT', 'WITHDRAWAL')
          AND to_char(transaction_date, 'YYYY-MM') >= :start_month
    """
    params: dict[str, Any] = {"user_id": str(user_id), "start_month": start_month}
    if account_id is not None:
        base_sql += " AND account_id = :account_id"
        params["account_id"] = str(account_id)
    sql = text(base_sql + " GROUP BY 1")
    result = await db.execute(sql, params)
    return {row.month: float(row.net) for row in result.all()}


def _compute_streaks(monthly_net: dict[str, float], start_month: str, current_month: str) -> tuple[int, int]:
    """(current_streak, longest_streak) 반환.

    current_streak: 가장 최근 월부터 연속으로 순입금>0인 개월수(이번 달이 아직 미입금이면 이번 달은 건너뜀).
    longest_streak: start_month..current_month 전체에서 순입금>0의 최장 연속 구간.
    """
    months = _iter_months(start_month, current_month)
    if not months:
        return 0, 0

    def satisfied(m: str) -> bool:
        return monthly_net.get(m, 0.0) > 0

    current_streak = 0
    for m in reversed(months):
        if satisfied(m):
            current_streak += 1
        elif m == current_month:
            continue  # 이번 달은 아직 입금 기회가 남아 스트릭을 끊지 않음
        else:
            break

    longest_streak = 0
    run = 0
    for m in months:
        if satisfied(m):
            run += 1
            longest_streak = max(longest_streak, run)
        else:
            run = 0
    return current_streak, longest_streak


def _build_months(
    monthly_net: dict[str, float], start_month: str, current_month: str, target_amount: float | None
) -> list[ChallengeMonth]:
    out = []
    for m in _iter_months(start_month, current_month):
        net = monthly_net.get(m, 0.0)
        satisfied = net > 0
        target_met = (net >= target_amount) if target_amount else satisfied
        out.append(ChallengeMonth(month=m, net_krw=net, satisfied=satisfied, target_met=target_met))
    return out


def _current_return_pct(summary: dict[str, Any]) -> float | None:
    xirr = summary.get("xirr_pct")
    annual = summary.get("annual_return_pct")
    cumulative = summary.get("cumulative_return_pct")
    if xirr is not None:
        return float(xirr)
    if annual is not None:
        return float(annual)
    return float(cumulative) if cumulative is not None else None


async def compute_progress(
    challenge: InvestmentChallenge,
    user_id: uuid.UUID,
    db: AsyncSession,
    cache: CacheStoreType = None,
) -> ChallengeProgress:
    current_month = _month_key(_now_kst_date())

    if challenge.challenge_type == CHALLENGE_DEPOSIT:
        target_amount = float(challenge.target_amount) if challenge.target_amount else None
        monthly_net = await _monthly_net_deposits(user_id, db, challenge.start_month, challenge.account_id)
        current_streak, longest_streak = _compute_streaks(monthly_net, challenge.start_month, current_month)
        months = _build_months(monthly_net, challenge.start_month, current_month, target_amount)
        this_month = next((mo for mo in months if mo.month == current_month), None)
        progress_pct: float | None = None
        if challenge.target_months:
            progress_pct = round(min(current_streak / challenge.target_months * 100, 100.0), 1)
        return ChallengeProgress(
            progress_pct=progress_pct,
            current_streak=current_streak,
            longest_streak=longest_streak,
            this_month_net_krw=this_month.net_krw if this_month else 0.0,
            this_month_satisfied=this_month.satisfied if this_month else False,
            this_month_target_met=this_month.target_met if this_month else False,
            months=months,
        )

    if challenge.challenge_type == CHALLENGE_RETURN_PCT:
        from app.services.asset_aggregator import get_dashboard_summary

        summary = await get_dashboard_summary(user_id, db, cache)
        cur = _current_return_pct(summary)
        target_pct = float(challenge.target_pct) if challenge.target_pct is not None else None
        progress_pct = None
        if target_pct and target_pct > 0 and cur is not None:
            progress_pct = round(cur / target_pct * 100, 1)
        return ChallengeProgress(progress_pct=progress_pct, current_return_pct=cur)

    if challenge.challenge_type == CHALLENGE_TARGET_VALUE:
        total, _, _, by_type = await build_asset_totals(user_id, db, cache)
        cur_val = exclude_real_estate(total, by_type)
        target_amount = float(challenge.target_amount) if challenge.target_amount else None
        progress_pct = round(cur_val / target_amount * 100, 1) if target_amount else None
        return ChallengeProgress(progress_pct=progress_pct, current_value_krw=cur_val)

    return ChallengeProgress()


def _serialize(challenge: InvestmentChallenge, progress: ChallengeProgress) -> ChallengeResponse:
    return ChallengeResponse(
        id=challenge.id,
        title=challenge.title,
        challenge_type=challenge.challenge_type,
        target_amount=float(challenge.target_amount) if challenge.target_amount is not None else None,
        target_pct=float(challenge.target_pct) if challenge.target_pct is not None else None,
        target_months=challenge.target_months,
        account_id=challenge.account_id,
        start_month=challenge.start_month,
        deadline_month=challenge.deadline_month,
        reminder_enabled=challenge.reminder_enabled,
        status=challenge.status,
        completed_at=challenge.completed_at.isoformat() if challenge.completed_at else None,
        created_at=challenge.created_at.isoformat() if challenge.created_at else "",
        progress=progress,
    )


async def _fetch_challenges(user_id: uuid.UUID, db: AsyncSession) -> list[InvestmentChallenge]:
    result = await db.execute(
        select(InvestmentChallenge)
        .where(InvestmentChallenge.user_id == user_id)
        .order_by(InvestmentChallenge.created_at.desc())
    )
    return list(result.scalars().all())


async def list_challenges_with_progress(
    user_id: uuid.UUID, db: AsyncSession, cache: CacheStoreType = None
) -> list[ChallengeResponse]:
    cached = await get_cached_json(cache, challenge_progress_key(user_id))
    if cached is not None:
        return [ChallengeResponse(**item) for item in cached]

    challenges = await _fetch_challenges(user_id, db)
    responses = []
    for ch in challenges:
        progress = await compute_progress(ch, user_id, db, cache)
        responses.append(_serialize(ch, progress))

    await set_cached_json(
        cache,
        challenge_progress_key(user_id),
        [r.model_dump(mode="json") for r in responses],
        TTL_CHALLENGE_PROGRESS,
    )
    return responses


async def get_challenge_response(
    challenge: InvestmentChallenge, user_id: uuid.UUID, db: AsyncSession, cache: CacheStoreType = None
) -> ChallengeResponse:
    progress = await compute_progress(challenge, user_id, db, cache)
    return _serialize(challenge, progress)


async def create_challenge(
    user_id: uuid.UUID, db: AsyncSession, payload: ChallengeCreate, cache: CacheStoreType = None
) -> InvestmentChallenge:
    challenge = InvestmentChallenge(
        user_id=user_id,
        title=payload.title,
        challenge_type=payload.challenge_type,
        target_amount=payload.target_amount,
        target_pct=payload.target_pct,
        target_months=payload.target_months,
        account_id=payload.account_id,
        start_month=payload.start_month,
        deadline_month=payload.deadline_month,
        reminder_enabled=payload.reminder_enabled,
        status=CHALLENGE_ACTIVE,
    )
    db.add(challenge)
    await db.commit()
    await db.refresh(challenge)
    await invalidate_challenge_cache(cache, user_id)
    return challenge


async def update_challenge(
    challenge: InvestmentChallenge, db: AsyncSession, payload: ChallengeUpdate, cache: CacheStoreType = None
) -> InvestmentChallenge:
    data = payload.model_dump(exclude_unset=True)
    for field in ("title", "target_amount", "target_pct", "target_months", "deadline_month", "reminder_enabled"):
        if field in data:
            setattr(challenge, field, data[field])
    if "status" in data and data["status"] is not None:
        challenge.status = data["status"]
        if data["status"] == "COMPLETED" and challenge.completed_at is None:
            challenge.completed_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(challenge)
    await invalidate_challenge_cache(cache, challenge.user_id)
    return challenge


async def delete_challenge(challenge: InvestmentChallenge, db: AsyncSession, cache: CacheStoreType = None) -> None:
    user_id = challenge.user_id
    await db.delete(challenge)
    await db.commit()
    await invalidate_challenge_cache(cache, user_id)


async def get_challenge_summary(user_id: uuid.UUID, db: AsyncSession, cache: CacheStoreType = None) -> ChallengeSummary:
    today = _now_kst_date()
    current_month = _month_key(today)
    result = await db.execute(
        select(InvestmentChallenge).where(
            InvestmentChallenge.user_id == user_id,
            InvestmentChallenge.status == CHALLENGE_ACTIVE,
            InvestmentChallenge.challenge_type == CHALLENGE_DEPOSIT,
            InvestmentChallenge.reminder_enabled == True,
        )
    )
    challenges = list(result.scalars().all())
    unmet = 0
    for ch in challenges:
        monthly_net = await _monthly_net_deposits(user_id, db, current_month, ch.account_id)
        if monthly_net.get(current_month, 0.0) <= 0:
            unmet += 1
    return ChallengeSummary(needs_attention=(unmet > 0 and today.day >= _NUDGE_DAY_OF_MONTH), count=unmet)


async def invalidate_challenge_cache(cache: CacheStoreType, user_id: uuid.UUID) -> None:
    await invalidate_user_caches(cache, challenge_progress_key(user_id))
