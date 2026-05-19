import { api } from "./client";

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
  created_at: string;
  updated_at: string;
}

export const fetchPortfolios = () =>
  api.get<Portfolio[]>("/portfolios").then((r) => r.data);

export const createPortfolio = (body: {
  name: string;
  items: PortfolioItem[];
  base_type?: string;
}) => api.post<Portfolio>("/portfolios", body).then((r) => r.data);

export const updatePortfolio = (
  id: string,
  body: { name?: string; items?: PortfolioItem[]; base_type?: string }
) => api.put<Portfolio>(`/portfolios/${id}`, body).then((r) => r.data);

export const deletePortfolio = (id: string) =>
  api.delete(`/portfolios/${id}`);
