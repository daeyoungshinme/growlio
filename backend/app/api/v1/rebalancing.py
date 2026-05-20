"""리밸런싱 API."""
import asyncio
import uuid
from functools import partial

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.v1.portfolio import _build_portfolio_overview
from app.database import get_db
from app.models.portfolio import Portfolio
from app.models.rebalancing import TargetPortfolio
from app.models.user import User
from app.redis_client import get_redis
from app.schemas.rebalancing import (
    ExecutionRequest,
    ExecutionResult,
    RebalancingAnalysis,
    TargetPortfolioCreate,
    TargetPortfolioResponse,
    TargetPortfolioUpdate,
)
from app.services.dividend_constants import is_korean_etf
from app.services.dividend_providers import (
    sync_naver_etf_dividend_info,
    sync_naver_stock_dividend_info,
    sync_yahoo_dividend_info,
)
from app.services.dividend_service import get_ticker_dividend_summary
from app.services.price_service import _to_yahoo_symbol, get_historical_returns
from app.services.rebalancing_service import analyze_rebalancing

router = APIRouter(prefix="/rebalancing", tags=["rebalancing"])


@router.get("/portfolios", response_model=list[TargetPortfolioResponse])
async def list_portfolios(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """저장된 목표 포트폴리오 목록."""
    rows = await db.execute(
        select(TargetPortfolio)
        .where(TargetPortfolio.user_id == current_user.id)
        .order_by(TargetPortfolio.created_at)
    )
    return rows.scalars().all()


@router.post("/portfolios", response_model=TargetPortfolioResponse, status_code=status.HTTP_201_CREATED)
async def create_portfolio(
    body: TargetPortfolioCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """새 목표 포트폴리오 생성."""
    portfolio = TargetPortfolio(
        user_id=current_user.id,
        name=body.name,
        items=[i.model_dump() for i in body.items],
        base_type=body.base_type,
    )
    db.add(portfolio)
    await db.commit()
    await db.refresh(portfolio)
    return portfolio


@router.put("/portfolios/{portfolio_id}", response_model=TargetPortfolioResponse)
async def update_portfolio(
    portfolio_id: uuid.UUID,
    body: TargetPortfolioUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """목표 포트폴리오 수정."""
    portfolio = await db.scalar(
        select(TargetPortfolio).where(
            TargetPortfolio.id == portfolio_id,
            TargetPortfolio.user_id == current_user.id,
        )
    )
    if not portfolio:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="포트폴리오를 찾을 수 없습니다.")

    if body.name is not None:
        portfolio.name = body.name
    if body.items is not None:
        portfolio.items = [i.model_dump() for i in body.items]
    if body.base_type is not None:
        portfolio.base_type = body.base_type

    await db.commit()
    await db.refresh(portfolio)
    return portfolio


@router.delete("/portfolios/{portfolio_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_portfolio(
    portfolio_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """목표 포트폴리오 삭제."""
    portfolio = await db.scalar(
        select(TargetPortfolio).where(
            TargetPortfolio.id == portfolio_id,
            TargetPortfolio.user_id == current_user.id,
        )
    )
    if not portfolio:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="포트폴리오를 찾을 수 없습니다.")

    await db.delete(portfolio)
    await db.commit()


@router.get("/portfolios/{portfolio_id}/analyze", response_model=RebalancingAnalysis)
async def analyze_portfolio(
    portfolio_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """현재 자산과 목표 포트폴리오를 비교해 리밸런싱 제안을 반환한다."""
    # 통합 portfolios 테이블에서 먼저 조회; 없으면 레거시 target_portfolios에서 폴백
    portfolio = await db.scalar(
        select(Portfolio).where(
            Portfolio.id == portfolio_id,
            Portfolio.user_id == current_user.id,
        )
    )
    if not portfolio:
        portfolio = await db.scalar(
            select(TargetPortfolio).where(
                TargetPortfolio.id == portfolio_id,
                TargetPortfolio.user_id == current_user.id,
            )
        )
    if not portfolio:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="포트폴리오를 찾을 수 없습니다.")

    overview = await _build_portfolio_overview(current_user.id, db)

    dividend_items = await get_ticker_dividend_summary(current_user.id, db)
    dividend_map = {
        (item["ticker"], item["market"]): item
        for item in dividend_items
        if item.get("ticker")
    }

    # 목표 포트폴리오 종목 중 현재 미보유(dividend_map에 없음)인 종목 배당수익률 보완
    loop = asyncio.get_running_loop()
    for raw_item in portfolio.items:
        ticker = raw_item["ticker"] if isinstance(raw_item, dict) else raw_item.ticker
        market = raw_item["market"] if isinstance(raw_item, dict) else raw_item.market
        if ticker == "CASH" or market == "KR_PROPERTY":
            continue
        key = (ticker, market)
        if key in dividend_map:
            continue
        is_korean = market.upper() in ("KOSPI", "KOSDAQ", "KRX")
        if is_korean:
            is_etf = is_korean_etf(ticker, market)
            fn = sync_naver_etf_dividend_info if is_etf else sync_naver_stock_dividend_info
            naver_info = await loop.run_in_executor(None, partial(fn, ticker))
            if naver_info["dividend_yield"] > 0:
                dividend_map[key] = {
                    "ticker": ticker,
                    "market": market,
                    "dividend_yield": naver_info["dividend_yield"] * 100,  # % 단위
                    "estimated_annual_krw": 0.0,
                }
        else:
            yahoo_sym = _to_yahoo_symbol(ticker, market)
            info = await loop.run_in_executor(None, partial(sync_yahoo_dividend_info, yahoo_sym))
            if info["dividend_yield"] > 0:
                dividend_map[key] = {
                    "ticker": ticker,
                    "market": market,
                    "dividend_yield": info["dividend_yield"] * 100,  # % 단위
                    "estimated_annual_krw": 0.0,
                }

    # 목표 포트폴리오 종목 10년 수익률 수집 (CASH 제외)
    target_tickers = [
        (raw_item["ticker"] if isinstance(raw_item, dict) else raw_item.ticker,
         raw_item["market"] if isinstance(raw_item, dict) else raw_item.market)
        for raw_item in portfolio.items
        if (raw_item["ticker"] if isinstance(raw_item, dict) else raw_item.ticker) != "CASH"
        and (raw_item["market"] if isinstance(raw_item, dict) else raw_item.market) != "KR_PROPERTY"
    ]
    # 현재 보유 종목도 포함 (배당 포트폴리오처럼 목표와 현재 보유가 다를 경우 current CAGR 계산을 위해)
    current_tickers = [
        (p["ticker"], p["market"])
        for p in overview.get("all_positions", [])
        if p.get("ticker") and p.get("ticker") != "CASH"
    ]
    all_return_tickers = list(set(target_tickers) | set(current_tickers))
    returns_map = await get_historical_returns(all_return_tickers, redis=redis)

    return analyze_rebalancing(portfolio, overview, dividend_map, returns_map)


@router.post("/portfolios/{portfolio_id}/execute", response_model=ExecutionResult)
async def execute_portfolio_rebalancing(
    portfolio_id: uuid.UUID,
    body: ExecutionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """선택된 주문 항목을 KIS API를 통해 실제로 매수/매도 실행한다."""
    portfolio = await db.scalar(
        select(Portfolio).where(
            Portfolio.id == portfolio_id,
            Portfolio.user_id == current_user.id,
        )
    )
    if not portfolio:
        portfolio = await db.scalar(
            select(TargetPortfolio).where(
                TargetPortfolio.id == portfolio_id,
                TargetPortfolio.user_id == current_user.id,
            )
        )
    if not portfolio:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="포트폴리오를 찾을 수 없습니다.")

    from app.services.rebalancing_execution_service import execute_rebalancing
    return await execute_rebalancing(
        user_id=current_user.id,
        account_id=body.account_id,
        orders=body.orders,
        db=db,
        redis=redis,
    )
