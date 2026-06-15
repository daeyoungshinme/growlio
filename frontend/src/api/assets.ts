import { apiDelete, apiGet, apiPatch, apiPost, apiPut } from "./client";

export interface RealEstateDetails {
  address?: string;
  property_type?: string; // 아파트|오피스텔|상가|토지|단독주택|기타
  purchase_price_krw?: number;
  purchase_date?: string; // YYYY-MM-DD
  mortgage_balance_krw?: number;
}

export interface AssetAccount {
  id: string;
  name: string;
  asset_type: string;
  data_source: string;
  institution: string | null;
  kis_account_no: string | null;
  kiwoom_account_no: string | null;
  is_mock_mode: boolean;
  manual_amount: number | null;
  manual_currency: string;
  manual_updated_at: string | null;
  deposit_krw: number | null;
  deposit_usd: number | null;
  real_estate_details: RealEstateDetails | null;
  include_in_total: boolean;
  is_active: boolean;
  sort_order: number;
  notes: string | null;
  created_at: string;
  has_own_kis_credentials: boolean;
  has_own_kiwoom_credentials: boolean;
  target_portfolio_id?: string | null;
}

export interface AssetAccountCreate {
  name: string;
  asset_type: string;
  data_source?: string;
  institution?: string;
  kis_account_no?: string;
  kis_app_key?: string;
  kis_app_secret?: string;
  kiwoom_account_no?: string;
  kiwoom_app_key?: string;
  kiwoom_app_secret?: string;
  ob_fintech_use_no?: string;
  is_mock_mode?: boolean;
  manual_amount?: number;
  deposit_krw?: number;
  deposit_usd?: number;
  notes?: string;
  sort_order?: number;
  real_estate_details?: RealEstateDetails;
  include_in_total?: boolean;
}

export const fetchAccounts = () =>
  apiGet<AssetAccount[]>("/assets");

export const createAccount = (data: AssetAccountCreate) =>
  apiPost<AssetAccount>("/assets", data);

export const updateAccount = (
  id: string,
  data: Partial<AssetAccountCreate & { is_active: boolean; deposit_krw: number; real_estate_details: RealEstateDetails }>,
) => apiPut<AssetAccount>(`/assets/${id}`, data);

export const deleteAccount = (id: string) =>
  apiDelete(`/assets/${id}`);

export const syncAccount = (id: string) =>
  apiPost(`/assets/${id}/sync`);

export const setAccountTargetPortfolio = (accountId: string, portfolioId: string | null) =>
  apiPatch<AssetAccount>(`/assets/${accountId}/target-portfolio`, {
    target_portfolio_id: portfolioId,
  });

export const batchSetTargetPortfolio = (
  portfolioId: string | null,
  accountIds: string[],
): Promise<AssetAccount[]> =>
  apiPatch<AssetAccount[]>("/assets/batch-target-portfolio", {
    portfolio_id: portfolioId,
    account_ids: accountIds,
  });

export const verifyKisCredentials = (data: {
  kis_app_key: string;
  kis_app_secret: string;
  is_mock: boolean;
}) => apiPost<{ valid: boolean; message: string }>("/assets/verify-kis-credentials", data);

export const fetchSnapshots = (start?: string, end?: string) =>
  apiGet("/assets/snapshots/range", { params: { start_date: start, end_date: end } });

export interface StockSuggestion {
  ticker: string;
  name: string;
  market: string;
  exchange: string;
}

export const searchStocks = (q: string, signal?: AbortSignal): Promise<StockSuggestion[]> =>
  apiGet<StockSuggestion[]>("/stocks/search", { params: { q }, signal });

export const fetchExchangeRate = (): Promise<{ usd_krw: number }> =>
  apiGet<{ usd_krw: number }>("/stocks/exchange-rate");

export interface StockPrice {
  price_krw: number | null;
  price_usd: number | null;
  usd_rate: number | null;
}

export const fetchStockPrice = (ticker: string, market: string): Promise<StockPrice> =>
  apiGet<StockPrice>("/stocks/price", { params: { ticker, market } });
