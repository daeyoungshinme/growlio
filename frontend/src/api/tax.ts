import { api } from "./client";

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
