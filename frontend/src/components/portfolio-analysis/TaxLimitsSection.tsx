import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import IsaMaturityCard from "@/components/tax/IsaMaturityCard";
import PensionContributionCard from "@/components/tax/PensionContributionCard";
import HealthInsuranceRiskCard from "@/components/tax/HealthInsuranceRiskCard";
import TaxActionPlanCard from "@/components/tax/TaxActionPlanCard";
import { isaStatusQuery, portfolioOverviewLiteQuery } from "@/api/queryOptions";
import EmptyState from "@/components/common/EmptyState";

/** 절세 액션 플랜(최상단) + ISA 만기·연금저축/IRP 납입 한도·건강보험 피부양자 기준 현황. 계좌 필터와 무관하게 항상 전체
 * 계좌 기준으로 표시한다(ISA 비과세한도·연금 공제한도·배당소득은 계좌 단위로 축소해 볼 개념이 아님).
 * DashboardPage와 동일 queryKey를 공유해 캐시를 재사용한다. `TaxTabContainer`의 "한도 현황" 탭이
 * 항상 펼친 상태로 렌더하므로(2026-07-25 세금정보 3곳→2곳 통합) 자체 접기 카드는 두지 않는다.
 * `HealthInsuranceRiskCard`는 ISA/연금 계좌 유무와 무관하게 항상 렌더되므로(배당소득 기준) 이
 * 탭이 완전히 비어있는 상태는 이제 없다 — ISA/연금 계좌가 둘 다 없어도 건강보험 카드는 보인다. */
/** 백엔드 `tax_action_service._LINK_ISA_STATUS`의 해시와 같아야 한다 */
const ISA_STATUS_ANCHOR = "isa-status";

export default function TaxLimitsSection() {
  const {
    data: overview,
    isError: overviewFailed,
    refetch: refetchOverview,
  } = useQuery(portfolioOverviewLiteQuery);

  const accounts = overview?.accounts ?? [];
  const hasPension = accounts.some((a) => a.tax_type === "PENSION_SAVINGS" || a.tax_type === "IRP");

  const { data: isaData, isError: isaFailed, refetch: refetchIsa } = useQuery(isaStatusQuery);
  const hasIsa = (isaData?.accounts.length ?? 0) > 0;

  // 절세 액션 "ISA 현황 보기"(`#isa-status`)로 들어오면 ISA 카드로 스크롤 — 카드는 조회 뒤에야 렌더되므로 hasIsa도 의존
  const { hash } = useLocation();
  useEffect(() => {
    if (hash === `#${ISA_STATUS_ANCHOR}` && hasIsa) {
      document.getElementById(ISA_STATUS_ANCHOR)?.scrollIntoView({ block: "start" });
    }
  }, [hash, hasIsa]);

  return (
    <div className="space-y-4 divide-y divide-gray-100 dark:divide-gray-700 [&>*:not(:first-child)]:pt-4">
      <TaxActionPlanCard />
      {/* 카드가 조용히 사라지면 ISA·연금 계좌가 없는 것처럼 보인다 */}
      {((overviewFailed && !overview) || (isaFailed && !isaData)) && (
        <EmptyState
          title="ISA·연금 현황을 불러오지 못했습니다."
          action={{
            label: "다시 시도",
            onClick: () => {
              void refetchOverview();
              void refetchIsa();
            },
          }}
          compact
        />
      )}
      {hasIsa && (
        <div id={ISA_STATUS_ANCHOR} className="scroll-mt-4">
          <IsaMaturityCard />
        </div>
      )}
      {hasPension && <PensionContributionCard overview={overview} />}
      <HealthInsuranceRiskCard />
    </div>
  );
}
