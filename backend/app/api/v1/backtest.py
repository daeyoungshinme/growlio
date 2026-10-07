"""백테스팅 API."""

import hashlib
import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.cache_store import get_cache_store
from app.limiter import limiter
from app.models.user import User
from app.schemas.backtest import BacktestResult, BacktestRunRequest
from app.services.backtest_service import run_backtest
from app.utils.cache_keys import TTL_BACKTEST, backtest_key

router = APIRouter(prefix="/backtest", tags=["backtest"])


@router.post("/run", response_model=BacktestResult)
@limiter.limit("2/minute")
async def run_backtest_endpoint(
    request: Request,
    body: BacktestRunRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """백테스팅 실행. yfinance 호출로 수 초 소요될 수 있습니다."""
    if not body.portfolio_ids and not body.include_spy and not body.include_real_portfolio:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="최소 1개의 포트폴리오 또는 벤치마크를 선택해주세요",
        )

    cache = await get_cache_store()
    payload = json.dumps(body.model_dump(), sort_keys=True, default=str).encode()
    param_hash = hashlib.md5(payload, usedforsecurity=False).hexdigest()
    cache_key = backtest_key(current_user.id, param_hash)

    cached = await cache.get(cache_key)
    if cached:
        return BacktestResult.model_validate_json(cached)

    result = await run_backtest(current_user.id, body, db)
    await cache.setex(cache_key, TTL_BACKTEST, result.model_dump_json())
    return result
