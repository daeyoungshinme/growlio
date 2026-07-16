import { useQuery } from "@tanstack/react-query";
import { Landmark } from "lucide-react";
import { fetchIsaStatus } from "@/api/tax";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { useCollapsible } from "@/hooks/useCollapsible";
import type { PortfolioOverview } from "@/types";
import CollapsibleCard from "@/components/common/CollapsibleCard";
import HorizonSummaryCard from "./HorizonSummaryCard";
import IsaMaturityCard from "./IsaMaturityCard";
import PensionContributionCard from "./PensionContributionCard";

interface Props {
  overview: PortfolioOverview | undefined;
}

/** 투자기간별 자산현황·ISA 만기·연금저축/IRP 납입 현황을 하나의 접이식 카드로 묶어 보여준다.
 * 셋 다 세제·기간 관련 참고용 정보라는 공통점이 있어 통합 — 각 카드는 embedded 모드로 렌더된다.
 * 니치 정보이므로 데스크탑/모바일 모두 기본 접힘. */
export default function TaxHorizonSummarySection({ overview }: Props) {
  const accounts = overview?.accounts ?? [];
  const hasHorizon = accounts.some((a) => a.investment_horizon);
  const hasPension = accounts.some((a) => a.tax_type === "PENSION_SAVINGS" || a.tax_type === "IRP");

  // IsaMaturityCard와 동일 queryKey를 공유해 중복 네트워크 요청 없이 캐시를 재사용한다.
  const { data: isaData } = useQuery({
    queryKey: QUERY_KEYS.isaStatus,
    queryFn: fetchIsaStatus,
    staleTime: STALE_TIME.MEDIUM,
  });
  const hasIsa = (isaData?.accounts.length ?? 0) > 0;

  const [isOpen, toggleOpen] = useCollapsible(false, "growlio:taxHorizonSection:open");

  if (!hasHorizon && !hasIsa && !hasPension) return null;

  return (
    <CollapsibleCard
      icon={Landmark}
      title="세제·기간 현황"
      isOpen={isOpen}
      onToggle={toggleOpen}
      collapsedHint="탭하여 투자기간·ISA·연금 현황 보기"
    >
      <div className="space-y-4 divide-y divide-gray-100 dark:divide-gray-700 [&>*:not(:first-child)]:pt-4">
        {hasHorizon && <HorizonSummaryCard overview={overview} embedded />}
        {hasIsa && <IsaMaturityCard embedded />}
        {hasPension && <PensionContributionCard overview={overview} embedded />}
      </div>
    </CollapsibleCard>
  );
}
