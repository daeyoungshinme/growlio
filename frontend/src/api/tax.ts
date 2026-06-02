import { api } from "./client";

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
  api.get<OverseasPositionDetail[]>("/tax/overseas-positions").then((r) => r.data);

export interface TaxSummary {
  year: number;
  dividend_income_krw: number;
  dividend_tax_krw: number;
  overseas_unrealized_gain_krw: number;
  overseas_gain_deduction_krw: number;
  overseas_tax_estimated_krw: number;
  domestic_stock_value_krw: number;
  domestic_large_holder_warning: boolean;
  comprehensive_tax_warning: boolean;
  total_estimated_tax_krw: number;
  note: string;
  rates: {
    dividend_tax_rate_pct: number;
    overseas_tax_rate_pct: number;
  };
}

export const fetchTaxSummary = (year?: number) =>
  api
    .get<TaxSummary>("/tax/summary", { params: year ? { year } : undefined })
    .then((r) => r.data);
