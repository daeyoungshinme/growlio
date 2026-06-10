"""AI 시황 분석 및 포트폴리오 추천 스키마."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class MarketIndexItem(BaseModel):
    symbol: str
    name: str
    price: float | None
    change_pct: float | None
    week_change_pct: float | None


class ExchangeRateInfo(BaseModel):
    usd_krw: float | None
    change_pct: float | None


class SectorInfo(BaseModel):
    sector: str
    etf_ticker: str
    change_pct: float | None


class PortfolioRisk(BaseModel):
    score: int
    concentration_risk: str
    sector_bias: list[str]
    description: str


class RecommendedAction(BaseModel):
    ticker: str
    name: str
    action: str
    reason: str
    priority: str


class AlternativePortfolioItem(BaseModel):
    ticker: str
    name: str
    weight: float
    reason: str


class AlternativePortfolio(BaseModel):
    risk_level: str
    expected_return: str
    items: list[AlternativePortfolioItem]


class AIAnalysisResult(BaseModel):
    market_summary: str
    portfolio_risk: PortfolioRisk
    recommendations: list[RecommendedAction]
    alternative_portfolios: list[AlternativePortfolio]
    disclaimer: str


class AIAnalysisResponse(BaseModel):
    status: str
    cached_at: datetime | None
    market_indices: list[MarketIndexItem]
    exchange_rate: ExchangeRateInfo
    sector_performance: list[SectorInfo]
    analysis: AIAnalysisResult | None
    error_message: str | None
