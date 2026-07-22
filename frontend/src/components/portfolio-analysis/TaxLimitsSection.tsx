import { useQuery } from "@tanstack/react-query";
import { Landmark } from "lucide-react";
import { fetchIsaStatus } from "@/api/tax";
import { fetchPortfolioOverviewLite } from "@/api/portfolios";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { useCollapsible } from "@/hooks/useCollapsible";
import CollapsibleCard from "@/components/common/CollapsibleCard";
import IsaMaturityCard from "@/components/dashboard/IsaMaturityCard";
import PensionContributionCard from "@/components/dashboard/PensionContributionCard";

/** ISA 만기·연금저축/IRP 납입 한도 현황. 계좌 필터와 무관하게 항상 전체 계좌 기준으로 표시한다
 * (ISA 비과세한도·연금 공제한도는 계좌 단위로 축소해 볼 개념이 아님).
 * DashboardPage와 동일 queryKey를 공유해 캐시를 재사용한다. */
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

  const [isOpen, toggleOpen] = useCollapsible(false, "growlio:taxLimitsSection:open");

  if (!hasIsa && !hasPension) return null;

  return (
    <CollapsibleCard
      icon={Landmark}
      title="한도·기한 현황"
      isOpen={isOpen}
      onToggle={toggleOpen}
      collapsedHint="탭하여 ISA·연금 한도 현황 보기"
    >
      <div className="space-y-4 divide-y divide-gray-100 dark:divide-gray-700 [&>*:not(:first-child)]:pt-4">
        {hasIsa && <IsaMaturityCard embedded />}
        {hasPension && <PensionContributionCard overview={overview} embedded />}
      </div>
    </CollapsibleCard>
  );
}
