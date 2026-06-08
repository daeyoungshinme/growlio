from fastapi import APIRouter

from app.api.v1 import (
    alerts,
    assets,
    auth,
    backtest,
    dart,
    dashboard,
    dividends,
    invest,
    open_banking,
    portfolio,
    portfolios,
    rebalancing,
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
router.include_router(portfolio.router)
router.include_router(portfolios.router)
router.include_router(settings.router)
router.include_router(open_banking.router)
router.include_router(stocks.router)
router.include_router(transactions.router)
router.include_router(dividends.router)
router.include_router(invest.router)
router.include_router(backtest.router)
router.include_router(rebalancing.router)
router.include_router(alerts.router)
router.include_router(tax.router)
router.include_router(dart.router)
router.include_router(ws_prices.router)
