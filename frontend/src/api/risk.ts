import { apiGet } from "./client";

// ---------------------------------------------------------------------------
// 위험 지표 — 원화 기준 최근 1년, 예수금 포함(plans/137 A)
// ---------------------------------------------------------------------------

export interface RiskIndexExposure {
  key: string;
  label: string;
  /** 주식 평가액 대비 % */
  pct_of_stock: number;
}

export interface PortfolioRiskMetrics {
  data_available: boolean;
  total_value_krw: number;
  cash_weight_pct: number;
  /** 가격 이력이 있어 계산에 반영된 종목 평가액 비중(%) */
  coverage_pct: number;
  var_95_pct: number;
  var_95_krw: number;
  annualized_volatility_pct: number;
  max_drawdown_pct: number;
  /** 주간 수익률 기준, 표본 부족이면 null */
  beta_sp500: number | null;
  /** S&P500(원화) 대비 연간 변동성 배율 — 1.0이면 시장과 같음 */
  vol_ratio_vs_sp500: number | null;
  sp500_10pct_drop_krw: number | null;
  top_holding_weight_pct: number;
  top_holding_name: string | null;
  top_index_exposures: RiskIndexExposure[];
  position_count: number;
  note: string | null;
}

// ---------------------------------------------------------------------------
// 리밸런싱 전략
// ---------------------------------------------------------------------------

export interface FactorChange {
  current: number;
  target: number;
  delta: number;
}

export interface FrontierChanges {
  current_risk: number | null;
  current_return: number | null;
  target_risk: number | null;
  target_return: number | null;
  risk_change: number | null;
  return_change: number | null;
  sharpe_improvement: boolean | null;
  current_sharpe: number | null;
  target_sharpe: number | null;
}

export interface TradeRecommendation {
  action: string;
  ticker: string;
  market: string;
  name: string;
  current_weight: number;
  target_weight: number;
  reason: string;
}

export interface RebalancingStrategy {
  portfolio_id: string;
  portfolio_name: string;
  factor_changes: Record<string, FactorChange>;
  frontier_changes: FrontierChanges;
  trade_recommendations: TradeRecommendation[];
  overall_direction: string;
  summary: string;
}

// ---------------------------------------------------------------------------
// API 함수
// ---------------------------------------------------------------------------

// 전체 계좌 통합 기준만 있다 — 백엔드가 portfolio_id를 계산에 반영하지 않아 파라미터를 없앴다
export const fetchPortfolioRisk = () => apiGet<PortfolioRiskMetrics>("/portfolio/risk");

export const fetchRebalancingStrategy = (portfolioId: string) =>
  apiGet<RebalancingStrategy>(`/portfolio/rebalancing-strategy?portfolio_id=${portfolioId}`);
