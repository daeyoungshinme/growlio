import { apiDelete, apiGet, apiPatch, apiPost, apiPut } from "./client";
import type { IndexExposure, PortfolioOverview } from "@/types";
import type { AccountTaxType, InvestmentHorizon } from "@/api/assets";

export const fetchPortfolioOverview = (accountId?: string | null) =>
  accountId
    ? apiGet<PortfolioOverview>("/portfolio/overview", { params: { account_id: accountId } })
    : apiGet<PortfolioOverview>("/portfolio/overview");

export const fetchPortfolioOverviewLite = () =>
  apiGet<PortfolioOverview>("/portfolio/overview", { params: { lite: true } });

export const fetchIndexExposure = (accountId?: string | null) =>
  apiGet<IndexExposure>(
    "/portfolio/index-exposure",
    accountId ? { params: { account_id: accountId } } : undefined,
  );

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

export const fetchAllocationHistory = (months: number, accountId?: string | null) =>
  apiGet<AllocationHistoryPoint[]>("/portfolio/allocation-history", {
    params: { months, account_id: accountId || undefined },
  });

export interface PortfolioGroupMember {
  ticker: string;
  market: string;
  name: string;
  /** 정방향 레버리지 배수(QLD=2) — 그룹 비중은 노출 기준(평가액 × 배수)으로 합산. 없으면 1배 */
  leverage?: number;
}

/** 지수 그룹 항목(plans/74) — 항목의 ticker/market이 대표 매수 종목, members는 그 외에 합산할 종목. */
export interface PortfolioItemGroup {
  key: string;
  label: string;
  members: PortfolioGroupMember[];
  /** ISA·연금저축·IRP 계좌에서 대표 종목(해외 상장) 대신 살 국내 상장 종목 — 그룹 합산에도 포함 */
  domestic_alt?: PortfolioGroupMember | null;
}

export interface PortfolioItem {
  ticker: string;
  name: string; // 빈 문자열 가능 (백테스트 전용 항목 등)
  market: string;
  weight: number;
  group?: PortfolioItemGroup | null;
}

export interface IndexGroupSuggestionMember extends PortfolioGroupMember {
  value_krw: number;
  /** 분석 대상 계좌에 보유 중인지 — false면 다른 계좌에만 있어 그 계좌를 분석 대상에 추가해야 합산된다 */
  in_scope?: boolean;
  account_names?: string[];
}

export interface IndexGroupSuggestion {
  key: string;
  label: string;
  value_krw: number;
  /** 노출 합계(평가액 × 레버리지 배수) */
  exposure_krw: number;
  pct_of_stock: number;
  primary: IndexGroupSuggestionMember;
  domestic_alt: IndexGroupSuggestionMember | null;
  members: IndexGroupSuggestionMember[];
  primary_candidates: IndexGroupSuggestionMember[];
  domestic_alt_candidates: IndexGroupSuggestionMember[];
}

export interface IndexGroupSuggestionResponse {
  groups: IndexGroupSuggestion[];
  profiles_complete: boolean;
}

export const fetchIndexGroupSuggestions = (accountIds: string[] | null) => {
  const params = new URLSearchParams();
  for (const aid of accountIds ?? []) params.append("account_ids", aid);
  return apiGet<IndexGroupSuggestionResponse>("/portfolios/index-group-suggestions", {
    params: params.size > 0 ? params : undefined,
  });
};

export interface Portfolio {
  id: string;
  name: string;
  items: PortfolioItem[];
  base_type: string; // "STOCK_ONLY" | "TOTAL_ASSETS"
  account_ids?: string[] | null; // null이면 모든 활성 주식 계좌 사용
  alert_scope?: "AGGREGATE" | "PER_ACCOUNT"; // 리밸런싱 알림/AUTO 설정 스코프 (기본 AGGREGATE)
  // 명시적으로 지정된 기간/세제유형 태그 — null이면 기준 포트폴리오 지정 계좌들의 태그로부터 추론
  investment_horizon?: InvestmentHorizon | null;
  tax_type?: AccountTaxType | null;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export const fetchPortfolios = () => apiGet<Portfolio[]>("/portfolios");

export const createPortfolio = (body: {
  name: string;
  items: PortfolioItem[];
  base_type?: string;
  account_ids?: string[] | null;
  investment_horizon?: InvestmentHorizon | null;
  tax_type?: AccountTaxType | null;
}) => apiPost<Portfolio>("/portfolios", body);

export const updatePortfolio = (
  id: string,
  body: {
    name?: string;
    items?: PortfolioItem[];
    base_type?: string;
    account_ids?: string[] | null;
    investment_horizon?: InvestmentHorizon | null;
    tax_type?: AccountTaxType | null;
  },
) => apiPut<Portfolio>(`/portfolios/${id}`, body);

export const deletePortfolio = (id: string) => apiDelete(`/portfolios/${id}`);

export const reorderPortfolios = (items: { id: string; sort_order: number }[]) =>
  apiPatch("/portfolios/reorder", { items });
