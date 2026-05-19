// 포트폴리오 포지션 (API: /portfolio/overview → all_positions)
export interface PortfolioPosition {
  ticker: string;
  name: string;
  market: string;
  qty: number;
  avg_price: number;
  current_price: number;
  value_krw: number;
  invested_krw: number;
  pnl: number;
  pnl_pct: number;
  currency: string;
  account_id: string;
  account_name: string;
  weight_in_stock: number;
}

// 티커별 집계 포지션 (PortfolioPage, PortfolioSummaryCard)
export interface AggregatedPosition {
  ticker: string;
  name: string;
  market: string;
  currency: string;
  total_qty: number;
  weighted_avg_price: number;
  current_price: number;
  total_value_krw: number;
  total_invested_krw: number;
  total_pnl: number;
  pnl_pct: number;
  weight_in_stock: number;
}

// 자산 배분 항목 (asset_type_allocation, stock_allocation)
export interface AllocationItem {
  type?: string;
  ticker?: string;
  name: string;
  label?: string;
  account_name?: string;
  amount_krw?: number;
  value_krw?: number;
  pct: number;
}

// 계좌별 행 (Overview.accounts)
export interface AccountRow {
  id: string;
  name: string;
  asset_type: string;
  asset_type_label: string;
  data_source: string;
  institution: string | null;
  amount_krw: number;
  invested_krw: number;
  unrealized_pnl: number;
  position_count: number;
  positions: PortfolioPosition[];
}

// 포트폴리오 전체 overview (API: /portfolio/overview)
export interface PortfolioOverview {
  total_assets_krw: number;
  total_stock_krw: number;
  total_non_stock_krw: number;
  total_invested_krw: number;
  unrealized_pnl_krw: number;
  stock_return_pct: number;
  asset_type_allocation: AllocationItem[];
  stock_allocation: AllocationItem[];
  all_positions: PortfolioPosition[];
  accounts: AccountRow[];
}

// 종목별 배당 수익률 (API: /dividends/positions)
export interface DividendYield {
  ticker: string;
  market: string;
  dividend_yield: number;
  dps: number;
  ex_dividend_date: string | null;
  estimated_annual_krw: number;
  estimated_monthly_krw: number;
  dividend_months: number[];
  dividend_months_is_manual: boolean;
  investment_yield: number;
}

// 배당금 티커별 요약 (API: /dividends/by-ticker)
export interface DividendByTicker {
  ticker: string | null;
  name: string;
  market: string | null;
  received_krw: number;
  estimated_annual_krw: number;
  estimated_monthly_krw: number;
  dividend_yield: number;
  dps: number;
  dividend_months: number[];
  dividend_months_is_manual: boolean;
  investment_yield: number;
  currency: string;
  estimated_monthly_usd: number | null;
}
