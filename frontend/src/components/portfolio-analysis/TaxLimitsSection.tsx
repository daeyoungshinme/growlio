import { useQuery } from "@tanstack/react-query";
import { fetchIsaStatus } from "@/api/tax";
import { fetchPortfolioOverviewLite } from "@/api/portfolios";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import IsaMaturityCard from "@/components/dashboard/IsaMaturityCard";
import PensionContributionCard from "@/components/dashboard/PensionContributionCard";
import HealthInsuranceRiskCard from "@/components/dashboard/HealthInsuranceRiskCard";

/** ISA 만기·연금저축/IRP 납입 한도·건강보험 피부양자 기준 현황. 계좌 필터와 무관하게 항상 전체
 * 계좌 기준으로 표시한다(ISA 비과세한도·연금 공제한도·배당소득은 계좌 단위로 축소해 볼 개념이 아님).
 * DashboardPage와 동일 queryKey를 공유해 캐시를 재사용한다. `TaxTabContainer`의 "한도 현황" 탭이
 * 항상 펼친 상태로 렌더하므로(2026-07-25 세금정보 3곳→2곳 통합) 자체 접기 카드는 두지 않는다.
 * `HealthInsuranceRiskCard`는 ISA/연금 계좌 유무와 무관하게 항상 렌더되므로(배당소득 기준) 이
 * 탭이 완전히 비어있는 상태는 이제 없다 — ISA/연금 계좌가 둘 다 없어도 건강보험 카드는 보인다. */
export default function TaxLimitsSection() {
  const { data: overview } = useQuery({
    queryKey: QUERY_KEYS.portfolioOverviewLite,
    queryFn: fetchPortfolioOverviewLite,
    staleTime: STALE_TIME.EXCHANGE_RATE,
  });

  const accounts = overview?.accounts ?? [];
  const hasPension = accounts.some((a) => a.tax_type === "PENSION_SAVINGS" || a.tax_type === "IRP");

  const { data: isaData } = useQuery({
    queryKey: QUERY_KEYS.isaStatus,
    queryFn: fetchIsaStatus,
    staleTime: STALE_TIME.MEDIUM,
  });
  const hasIsa = (isaData?.accounts.length ?? 0) > 0;

  return (
    <div className="space-y-4 divide-y divide-gray-100 dark:divide-gray-700 [&>*:not(:first-child)]:pt-4">
      {hasIsa && <IsaMaturityCard />}
      {hasPension && <PensionContributionCard overview={overview} />}
      <HealthInsuranceRiskCard />
    </div>
  );
}
