import { lazy, Suspense } from "react";
import { ChartNoAxesColumn } from "lucide-react";
import CollapsibleCard from "@/components/common/CollapsibleCard";
import SkeletonCard from "@/components/common/SkeletonCard";
import { useCollapsible } from "@/hooks/useCollapsible";

// AllocationHistoryChart의 기본 storageKey와 같은 키 — 차트 파일을 import하면 recharts까지 끌려오므로 복제
const OPEN_KEY = "growlio:dashboard:allocationHistoryOpen";

const AllocationHistoryChart = lazy(() => import("./AllocationHistoryChart"));

/**
 * 홈 "자산 추이" 카드 껍데기. 모바일 기본 접힘인데도 예전엔 접힌 카드를 그리려고 차트 청크(recharts)를
 * 받고 12개월 배분 이력을 조회했다 — 접혀 있는 동안은 헤더만 그리고, 펼칠 때 차트를 로드한다.
 */
export default function AllocationHistoryCard() {
  const [isOpen, toggle] = useCollapsible(() => window.innerWidth >= 1024, OPEN_KEY);

  if (!isOpen) {
    return (
      <CollapsibleCard
        icon={ChartNoAxesColumn}
        title="자산 추이"
        isOpen={false}
        onToggle={toggle}
        collapsedHint="탭하여 12개월 추이 보기"
      >
        {null}
      </CollapsibleCard>
    );
  }
  return (
    <Suspense fallback={<SkeletonCard rows={3} height="h-4" />}>
      <AllocationHistoryChart onCollapse={toggle} />
    </Suspense>
  );
}
