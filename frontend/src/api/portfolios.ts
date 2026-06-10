import { api } from "./client";
import type { PortfolioOverview } from "@/types";

export const fetchPortfolioOverview = () =>
  api.get<PortfolioOverview>("/portfolio/overview").then((r) => r.data);

export const fetchPortfolioOverviewLite = () =>
  api.get<PortfolioOverview>("/portfolio/overview", { params: { lite: true } }).then((r) => r.data);

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
  api.get<AllocationHistoryPoint[]>("/portfolio/allocation-history", { params: { months } }).then((r) => r.data);

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
  api.get<Portfolio[]>("/portfolios").then((r) => r.data);

export const createPortfolio = (body: {
  name: string;
  items: PortfolioItem[];
  base_type?: string;
  account_ids?: string[] | null;
}) => api.post<Portfolio>("/portfolios", body).then((r) => r.data);

export const updatePortfolio = (
  id: string,
  body: { name?: string; items?: PortfolioItem[]; base_type?: string; account_ids?: string[] | null }
) => api.put<Portfolio>(`/portfolios/${id}`, body).then((r) => r.data);

export const deletePortfolio = (id: string) =>
  api.delete(`/portfolios/${id}`);

export const reorderPortfolios = (items: { id: string; sort_order: number }[]) =>
  api.patch("/portfolios/reorder", { items });
