import { apiDelete, apiGet, apiPatch, apiPost, apiPut } from "./client";
import type { AssetClass, IndexRegion } from "./settings";

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
  tax_type?: AccountTaxType;
  investment_horizon?: InvestmentHorizon | null;
  isa_open_date?: string | null;
  isa_type?: IsaType | null;
  isa_manual_cumulative_pnl_krw?: number | null;
}

// GENERAL: 일반 | ISA: ISA | PENSION_SAVINGS: 연금저축 | IRP: IRP | OVERSEAS_DEDICATED: 해외전용
export type AccountTaxType = "GENERAL" | "ISA" | "PENSION_SAVINGS" | "IRP" | "OVERSEAS_DEDICATED";

export type InvestmentHorizon = "SHORT_TERM" | "MID_TERM" | "LONG_TERM";

// GENERAL: 일반형(비과세 200만원) | PREFERENTIAL: 서민형·농어민형(비과세 400만원)
export type IsaType = "GENERAL" | "PREFERENTIAL";

export const ACCOUNT_TAX_TYPE_LABELS: Record<AccountTaxType, string> = {
  GENERAL: "일반",
  ISA: "ISA",
  PENSION_SAVINGS: "연금저축",
  IRP: "IRP",
  OVERSEAS_DEDICATED: "해외전용",
};

export const INVESTMENT_HORIZON_LABELS: Record<InvestmentHorizon, string> = {
  SHORT_TERM: "단기",
  MID_TERM: "중기",
  LONG_TERM: "장기",
};

export const ISA_TYPE_LABELS: Record<IsaType, string> = {
  GENERAL: "일반형 (비과세 200만원)",
  PREFERENTIAL: "서민형·농어민형 (비과세 400만원)",
};

export interface AssetAccountCreate {
  name: string;
  asset_type: string;
  data_source?: string;
  institution?: string;
  tax_type?: AccountTaxType;
  investment_horizon?: InvestmentHorizon | null;
  isa_open_date?: string | null;
  isa_type?: IsaType | null;
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

export const fetchAccounts = () => apiGet<AssetAccount[]>("/assets");

export const createAccount = (data: AssetAccountCreate) => apiPost<AssetAccount>("/assets", data);

export const updateAccount = (
  id: string,
  data: Partial<
    AssetAccountCreate & {
      is_active: boolean;
      deposit_krw: number;
      real_estate_details: RealEstateDetails;
    }
  >,
) => apiPut<AssetAccount>(`/assets/${id}`, data);

export const deleteAccount = (id: string) => apiDelete(`/assets/${id}`);

export const syncAccount = (id: string) => apiPost(`/assets/${id}/sync`);

export interface SyncAllStatus {
  status: "idle" | "running" | "done" | "error";
  total?: number;
  done?: number;
  failed?: number;
}

export const syncAllAccounts = () => apiPost<{ total: number; status: string }>("/assets/sync-all");

export const getSyncAllStatus = () => apiGet<SyncAllStatus>("/assets/sync-all/status");

export const setAccountTargetPortfolio = (accountId: string, portfolioId: string | null) =>
  apiPatch<AssetAccount>(`/assets/${accountId}/target-portfolio`, {
    target_portfolio_id: portfolioId,
  });

export const updateIsaPnlOverride = (accountId: string, cumulativePnlKrw: number | null) =>
  apiPatch<AssetAccount>(`/assets/${accountId}/isa-pnl-override`, {
    cumulative_pnl_krw: cumulativePnlKrw,
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
  /** 종목명 패턴 기반 추정치 — 확정 근거 아님, 사용자가 후보 ETF 관리에서 직접 수정 가능해야 함 */
  asset_class?: AssetClass;
  /** 상장거래소·큐레이션 목록 기반 추정치 — 위와 동일하게 사용자 수정 가능해야 함 */
  index_region?: IndexRegion;
}

export const searchStocks = (q: string, signal?: AbortSignal): Promise<StockSuggestion[]> =>
  apiGet<StockSuggestion[]>("/stocks/search", { params: { q }, signal });

export const fetchIndexRegion = (
  ticker: string,
  market: string,
): Promise<{ index_region: IndexRegion }> =>
  apiGet<{ index_region: IndexRegion }>("/stocks/index-region", { params: { ticker, market } });

export const fetchExchangeRate = (): Promise<{ usd_krw: number }> =>
  apiGet<{ usd_krw: number }>("/stocks/exchange-rate");

export interface StockPrice {
  price_krw: number | null;
  price_usd: number | null;
  usd_rate: number | null;
}

export const fetchStockPrice = (ticker: string, market: string): Promise<StockPrice> =>
  apiGet<StockPrice>("/stocks/price", { params: { ticker, market } });

export const fetchStockPricesBatch = (
  items: { ticker: string; market: string }[],
): Promise<Record<string, StockPrice>> =>
  apiPost<Record<string, StockPrice>>("/stocks/prices-batch", { items });
