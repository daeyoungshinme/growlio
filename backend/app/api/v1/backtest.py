"""백테스팅 API."""
import hashlib
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.limiter import limiter
from app.models.backtest import BacktestPortfolio
from app.models.user import User
from app.redis_client import get_redis
from app.schemas.backtest import (
    BacktestPortfolioCreate,
    BacktestPortfolioResponse,
    BacktestPortfolioUpdate,
    BacktestResult,
    BacktestRunRequest,
    CorrelationRequest,
    CorrelationResult,
)
from app.services.backtest_service import compute_correlation, run_backtest

router = APIRouter(prefix="/backtest", tags=["backtest"])


@router.get("/portfolios", response_model=list[BacktestPortfolioResponse])
async def list_portfolios(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """저장된 백테스팅 포트폴리오 목록."""
    rows = await db.execute(
        select(BacktestPortfolio)
        .where(BacktestPortfolio.user_id == current_user.id)
        .order_by(BacktestPortfolio.created_at)
    )
    return rows.scalars().all()


@router.post("/portfolios", response_model=BacktestPortfolioResponse, status_code=status.HTTP_201_CREATED)
async def create_portfolio(
    body: BacktestPortfolioCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """새 백테스팅 포트폴리오 생성."""
    portfolio = BacktestPortfolio(
        user_id=current_user.id,
        name=body.name,
        holdings=[h.model_dump() for h in body.holdings],
    )
    db.add(portfolio)
    await db.commit()
    await db.refresh(portfolio)
    return portfolio


@router.put("/portfolios/{portfolio_id}", response_model=BacktestPortfolioResponse)
async def update_portfolio(
    portfolio_id: uuid.UUID,
    body: BacktestPortfolioUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """백테스팅 포트폴리오 수정."""
    portfolio = await db.scalar(
        select(BacktestPortfolio).where(
            BacktestPortfolio.id == portfolio_id,
            BacktestPortfolio.user_id == current_user.id,
        )
    )
    if not portfolio:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="포트폴리오를 찾을 수 없습니다.")

    if body.name is not None:
        portfolio.name = body.name
    if body.holdings is not None:
        portfolio.holdings = [h.model_dump() for h in body.holdings]

    await db.commit()
    await db.refresh(portfolio)
    return portfolio


@router.delete("/portfolios/{portfolio_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_portfolio(
    portfolio_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """백테스팅 포트폴리오 삭제."""
    portfolio = await db.scalar(
        select(BacktestPortfolio).where(
            BacktestPortfolio.id == portfolio_id,
            BacktestPortfolio.user_id == current_user.id,
        )
    )
    if not portfolio:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="포트폴리오를 찾을 수 없습니다.")

    await db.delete(portfolio)
    await db.commit()


_BACKTEST_CACHE_TTL = 86400  # 24시간


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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="최소 1개의 포트폴리오 또는 벤치마크를 선택해주세요.")

    redis = await get_redis()
    param_hash = hashlib.md5(
        json.dumps(body.model_dump(), sort_keys=True, default=str).encode()
    ).hexdigest()
    cache_key = f"backtest:{current_user.id}:{param_hash}"

    cached = await redis.get(cache_key)
    if cached:
        return BacktestResult.model_validate_json(cached)

    result = await run_backtest(current_user.id, body, db)
    await redis.setex(cache_key, _BACKTEST_CACHE_TTL, result.model_dump_json())
    return result


@router.post("/correlation", response_model=CorrelationResult)
@limiter.limit("5/minute")
async def run_correlation_endpoint(
    request: Request,
    body: CorrelationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """선택된 포트폴리오 종목 간 월별 수익률 상관관계 분석."""
    if not body.portfolio_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="최소 1개의 포트폴리오를 선택해주세요.",
        )

    redis = await get_redis()
    param_hash = hashlib.md5(
        json.dumps(body.model_dump(), sort_keys=True, default=str).encode()
    ).hexdigest()
    cache_key = f"correlation:{current_user.id}:{param_hash}"

    cached = await redis.get(cache_key)
    if cached:
        return CorrelationResult.model_validate_json(cached)

    result = await compute_correlation(current_user.id, body, db)
    await redis.setex(cache_key, _BACKTEST_CACHE_TTL, result.model_dump_json())
    return result
