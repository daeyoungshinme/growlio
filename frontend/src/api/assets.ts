import { api } from "./client";

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
  real_estate_details: RealEstateDetails | null;
  include_in_total: boolean;
  is_active: boolean;
  sort_order: number;
  notes: string | null;
  created_at: string;
  has_own_kis_credentials: boolean;
  has_own_kiwoom_credentials: boolean;
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
  notes?: string;
  sort_order?: number;
  real_estate_details?: RealEstateDetails;
  include_in_total?: boolean;
}

export const fetchAccounts = () =>
  api.get<AssetAccount[]>("/assets").then((r) => r.data);

export const createAccount = (data: AssetAccountCreate) =>
  api.post<AssetAccount>("/assets", data).then((r) => r.data);

export const updateAccount = (id: string, data: Partial<AssetAccountCreate & { is_active: boolean; deposit_krw: number; real_estate_details: RealEstateDetails }>) =>
  api.put<AssetAccount>(`/assets/${id}`, data).then((r) => r.data);

export const deleteAccount = (id: string) =>
  api.delete(`/assets/${id}`);

export const syncAccount = (id: string) =>
  api.post(`/assets/${id}/sync`).then((r) => r.data);

export const verifyKisCredentials = (data: { kis_app_key: string; kis_app_secret: string; is_mock: boolean }) =>
  api.post<{ valid: boolean; message: string }>("/assets/verify-kis-credentials", data).then((r) => r.data);

export const fetchSnapshots = (start?: string, end?: string) =>
  api.get("/assets/snapshots/range", { params: { start_date: start, end_date: end } }).then((r) => r.data);

export interface StockSuggestion {
  ticker: string;
  name: string;
  market: string;
  exchange: string;
}

export const searchStocks = (q: string, signal?: AbortSignal): Promise<StockSuggestion[]> =>
  api.get<StockSuggestion[]>("/stocks/search", { params: { q }, signal }).then((r) => r.data);

export const fetchExchangeRate = (): Promise<{ usd_krw: number }> =>
  api.get<{ usd_krw: number }>("/stocks/exchange-rate").then((r) => r.data);

export interface StockPrice {
  price_krw: number | null;
  price_usd: number | null;
  usd_rate: number | null;
}

export const fetchStockPrice = (ticker: string, market: string): Promise<StockPrice> =>
  api.get<StockPrice>("/stocks/price", { params: { ticker, market } }).then((r) => r.data);
