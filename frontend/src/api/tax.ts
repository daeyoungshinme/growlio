import { apiGet } from "./client";

export interface OverseasPositionDetail {
  ticker: string;
  name: string;
  market: string;
  currency: string;
  account_id: string;
  account_name: string;
  qty: number;
  avg_price_krw: number;
  current_price_krw: number;
  avg_price_usd: number | null;
  value_krw: number;
  invested_krw: number;
  unrealized_pnl_krw: number;
  unrealized_pnl_pct: number;
}

export const fetchOverseasPositionsTax = () =>
  apiGet<OverseasPositionDetail[]>("/tax/overseas-positions");

export interface HarvestingRecommendation {
  ticker: string;
  name: string;
  market: string;
  unrealized_loss_krw: number;
  tax_saved_krw: number;
  qty: number;
}

export interface GeumtSimulation {
  overseas_gain_krw: number;
  overseas_deduction_krw: number;
  overseas_taxable_krw: number;
  overseas_tax_krw: number;
  domestic_gain_krw: number;
  domestic_deduction_krw: number;
  domestic_taxable_krw: number;
  domestic_tax_krw: number;
  total_tax_krw: number;
  current_overseas_tax_krw: number;
  tax_difference_krw: number;
  note: string;
  rates: {
    standard_pct: number;
    excess_above_300m_pct: number;
  };
}

export interface TaxSummary {
  year: number;
  dividend_income_krw: number;
  dividend_tax_krw: number;
  overseas_unrealized_gain_krw: number;
  overseas_gain_deduction_krw: number;
  overseas_tax_estimated_krw: number;
  domestic_stock_value_krw: number;
  domestic_unrealized_gain_krw: number;
  domestic_large_holder_warning: boolean;
  comprehensive_tax_warning: boolean;
  total_estimated_tax_krw: number;
  total_fees_krw: number;
  harvesting_recommendations: HarvestingRecommendation[];
  financial_investment_tax_simulation: GeumtSimulation;
  note: string;
  rates: {
    dividend_tax_rate_pct: number;
    overseas_tax_rate_pct: number;
  };
}

export const fetchTaxSummary = (year?: number) =>
  apiGet<TaxSummary>("/tax/summary", { params: year ? { year } : undefined });
