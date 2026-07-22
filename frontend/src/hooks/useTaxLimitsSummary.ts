import { useQuery } from "@tanstack/react-query";
import { fetchIsaStatus, fetchPensionContribution, fetchTaxSummary } from "@/api/tax";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { fmtKrw } from "@/utils/format";
import type { PortfolioOverview } from "@/types";

export interface TaxLimitsSummary {
  parts: string[];
  warningText: string | null;
}

/** ISA 만기·연금 공제한도·세금 추정 현황을 한 줄 요약으로 압축한다.
 * `TaxLimitsBanner`(본문 렌더)와 `InvestmentSnapshotCard`(헤더 경고 배지·collapsedHint) 양쪽에서 호출되지만
 * 동일 queryKey 요청은 React Query가 자동으로 중복 제거하므로 네트워크 요청은 늘지 않는다. */
export function useTaxLimitsSummary(overview: PortfolioOverview | undefined): TaxLimitsSummary {
  const accounts = overview?.accounts ?? [];
  const hasPension = accounts.some((a) => a.tax_type === "PENSION_SAVINGS" || a.tax_type === "IRP");
  const currentYear = new Date().getFullYear();

  const { data: isaData } = useQuery({
    queryKey: QUERY_KEYS.isaStatus,
    queryFn: fetchIsaStatus,
    staleTime: STALE_TIME.MEDIUM,
  });
  const { data: pensionData } = useQuery({
    queryKey: QUERY_KEYS.pensionContribution(currentYear),
    queryFn: () => fetchPensionContribution(currentYear),
    staleTime: STALE_TIME.MEDIUM,
    enabled: hasPension,
  });
  const { data: taxData } = useQuery({
    queryKey: QUERY_KEYS.taxSummary(currentYear, undefined),
    queryFn: () => fetchTaxSummary(currentYear, undefined),
    staleTime: STALE_TIME.LONG,
  });

  const isaAccounts = isaData?.accounts ?? [];

  const overLimitCount = isaAccounts.filter((a) => a.taxable_excess_krw > 0).length;
  const nearestMaturity = isaAccounts
    .filter((a) => !a.is_mature && !a.needs_open_date && a.days_remaining != null)
    .sort((a, b) => (a.days_remaining ?? 0) - (b.days_remaining ?? 0))[0];

  const parts: string[] = [];
  if (overLimitCount > 0) parts.push(`ISA 한도초과 ${overLimitCount}건`);
  else if (nearestMaturity) parts.push(`ISA D-${nearestMaturity.days_remaining}`);
  if (pensionData)
    parts.push(`연금공제 ${Math.min(pensionData.total_achievement_pct, 999).toFixed(0)}% 달성`);
  if (taxData && taxData.total_estimated_tax_krw > 0) {
    parts.push(`예상세금 ${fmtKrw(taxData.total_estimated_tax_krw)}`);
  }

  const warningText = taxData?.comprehensive_tax_warning
    ? "금융소득 종합과세 대상 가능"
    : taxData?.domestic_large_holder_warning
      ? "국내주식 대주주요건 주의"
      : null;

  return { parts, warningText };
}
