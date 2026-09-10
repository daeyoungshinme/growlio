"""적립식 투자 챌린지 CRUD + 진행률 조회."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_owned_or_404
from app.api.v1._account_deps import get_owned_account
from app.core.cache_store import get_cache_store
from app.limiter import limiter
from app.models.challenge import CHALLENGE_DEPOSIT, InvestmentChallenge
from app.models.user import User
from app.schemas.challenge import (
    ChallengeCreate,
    ChallengeResponse,
    ChallengeSummary,
    ChallengeUpdate,
)
from app.services import challenge_service

router = APIRouter(prefix="/challenges", tags=["challenges"])


@router.get("", response_model=list[ChallengeResponse])
@limiter.limit("60/minute")
async def list_challenges(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """챌린지 목록 + 진행률/스트릭."""
    cache = await get_cache_store()
    return await challenge_service.list_challenges_with_progress(current_user.id, db, cache)


@router.get("/summary", response_model=ChallengeSummary)
@limiter.limit("60/minute")
async def get_challenge_summary(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """네비 배지용 경량 — 이번 달 미충족 상태인 활성 입금 챌린지 유무."""
    cache = await get_cache_store()
    return await challenge_service.get_challenge_summary(current_user.id, db, cache)


@router.post("", response_model=ChallengeResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
async def create_challenge(
    request: Request,
    req: ChallengeCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """챌린지 생성."""
    if req.account_id is not None:
        await get_owned_account(req.account_id, current_user.id, db)
    cache = await get_cache_store()
    challenge = await challenge_service.create_challenge(current_user.id, db, req, cache)
    return await challenge_service.get_challenge_response(challenge, current_user.id, db, cache)


@router.get("/{challenge_id}", response_model=ChallengeResponse)
@limiter.limit("60/minute")
async def get_challenge(
    request: Request,
    challenge_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """챌린지 상세 (월별 그리드 포함)."""
    challenge = await get_owned_or_404(
        db, InvestmentChallenge, challenge_id, current_user.id, "챌린지를 찾을 수 없습니다"
    )
    cache = await get_cache_store()
    return await challenge_service.get_challenge_response(challenge, current_user.id, db, cache)


@router.patch("/{challenge_id}", response_model=ChallengeResponse)
@limiter.limit("20/minute")
async def update_challenge(
    request: Request,
    challenge_id: uuid.UUID,
    req: ChallengeUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """챌린지 수정 / 보관(status)."""
    challenge = await get_owned_or_404(
        db, InvestmentChallenge, challenge_id, current_user.id, "챌린지를 찾을 수 없습니다"
    )
    if challenge.challenge_type != CHALLENGE_DEPOSIT and req.target_months is not None:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail="이 유형에는 연속 목표 개월수를 설정할 수 없습니다")
    cache = await get_cache_store()
    updated = await challenge_service.update_challenge(challenge, db, req, cache)
    return await challenge_service.get_challenge_response(updated, current_user.id, db, cache)


@router.delete("/{challenge_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("20/minute")
async def delete_challenge(
    request: Request,
    challenge_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """챌린지 삭제."""
    challenge = await get_owned_or_404(
        db, InvestmentChallenge, challenge_id, current_user.id, "챌린지를 찾을 수 없습니다"
    )
    cache = await get_cache_store()
    await challenge_service.delete_challenge(challenge, db, cache)
