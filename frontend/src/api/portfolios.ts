import { apiDelete, apiGet, apiPatch, apiPost, apiPut } from "./client";
import type { PortfolioOverview } from "@/types";

export const fetchPortfolioOverview = () =>
  apiGet<PortfolioOverview>("/portfolio/overview");

export const fetchPortfolioOverviewLite = () =>
  apiGet<PortfolioOverview>("/portfolio/overview", { params: { lite: true } });

export interface AllocationTypeItem {
  asset_type: string;
  label: string;
  amount_krw: number;
  weight_pct: number;
}

export interface AllocationHistoryPoint {
  month: string;
  total_krw: number;
  allocations: AllocationTypeItem[];
}

export const fetchAllocationHistory = (months: number) =>
  apiGet<AllocationHistoryPoint[]>("/portfolio/allocation-history", { params: { months } });

export interface PortfolioItem {
  ticker: string;
  name: string;    // 빈 문자열 가능 (백테스트 전용 항목 등)
  market: string;
  weight: number;
}

export interface Portfolio {
  id: string;
  name: string;
  items: PortfolioItem[];
  base_type: string;   // "STOCK_ONLY" | "TOTAL_ASSETS"
  account_ids?: string[] | null;  // null이면 모든 활성 주식 계좌 사용
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export const fetchPortfolios = () =>
  apiGet<Portfolio[]>("/portfolios");

export const createPortfolio = (body: {
  name: string;
  items: PortfolioItem[];
  base_type?: string;
  account_ids?: string[] | null;
}) => apiPost<Portfolio>("/portfolios", body);

export const updatePortfolio = (
  id: string,
  body: { name?: string; items?: PortfolioItem[]; base_type?: string; account_ids?: string[] | null },
) => apiPut<Portfolio>(`/portfolios/${id}`, body);

export const deletePortfolio = (id: string) =>
  apiDelete(`/portfolios/${id}`);

export const reorderPortfolios = (items: { id: string; sort_order: number }[]) =>
  apiPatch("/portfolios/reorder", { items });
