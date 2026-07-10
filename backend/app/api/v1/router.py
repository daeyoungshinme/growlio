from fastapi import APIRouter

from app.api.v1 import (
    alerts,
    assets,
    auth,
    backtest,
    dashboard,
    dividends,
    economic_indicators,
    insights,
    invest,
    market_signals,
    portfolio_analysis,
    portfolios,
    rebalancing,
    rebalancing_execution,
    rebalancing_plan,
    rebalancing_plan_public,
    settings,
    stocks,
    tax,
    transactions,
    ws_prices,
)

router = APIRouter(prefix="/api/v1")

router.include_router(auth.router)
router.include_router(assets.router)
router.include_router(dashboard.router)
router.include_router(portfolio_analysis.router)
router.include_router(portfolios.router)
router.include_router(settings.router)
router.include_router(stocks.router)
router.include_router(transactions.router)
router.include_router(dividends.router)
router.include_router(insights.router)
router.include_router(invest.router)
router.include_router(backtest.router)
router.include_router(rebalancing.router)
router.include_router(rebalancing_execution.router)
router.include_router(rebalancing_plan.router)
router.include_router(rebalancing_plan_public.router)
router.include_router(alerts.router)
router.include_router(tax.router)
router.include_router(ws_prices.router)
router.include_router(economic_indicators.router)
router.include_router(market_signals.router)
