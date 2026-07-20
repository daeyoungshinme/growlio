import { Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { fetchRebalancingAlerts } from "@/api/alerts";
import { fetchPortfolios } from "@/api/portfolios";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { mergeAlertsByPortfolio } from "@/utils/portfolio";
import { TOUCH_TARGET_ROW } from "@/constants/uiSizes";
import SkeletonCard from "@/components/common/SkeletonCard";

/** 설정 페이지 알림 섹션에 노출되는 리밸런싱 알림 현황 요약 — 실제 편집은 리밸런싱 탭에서 이뤄지므로
 * 여기서는 상태 요약 + 딥링크만 제공한다 (frontend/CLAUDE.md "다른 설정" 패턴과 동일). */
export default function RebalancingAlertSummaryCard() {
  const { data: alerts, isLoading: alertsLoading } = useQuery({
    queryKey: QUERY_KEYS.rebalancingAlerts,
    queryFn: fetchRebalancingAlerts,
  });
  const { data: portfolios, isLoading: portfoliosLoading } = useQuery({
    queryKey: QUERY_KEYS.portfolios,
    queryFn: fetchPortfolios,
  });

  if (alertsLoading || portfoliosLoading) {
    return <SkeletonCard rows={1} height="h-4" />;
  }

  const merged = mergeAlertsByPortfolio((alerts ?? []).filter((a) => a.is_active));
  const alertedCount = Object.keys(merged).length;
  const autoCount = Object.values(merged).filter((a) => a.mode === "AUTO").length;
  const totalCount = portfolios?.length ?? 0;

  return (
    <Link
      to="/rebalancing?rtab=포트폴리오"
      className={`w-full gap-3 -mx-3 px-3 rounded-lg text-xs text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors ${TOUCH_TARGET_ROW}`}
    >
      <span className="flex-1 leading-relaxed">
        {alertedCount === 0
          ? "아직 설정된 리밸런싱 알림이 없어요 — 리밸런싱 탭에서 포트폴리오별로 설정합니다."
          : `포트폴리오 ${totalCount}개 중 ${alertedCount}개에 알림 설정됨${
              autoCount > 0 ? ` (AUTO ${autoCount}개)` : ""
            } — 리밸런싱 탭에서 관리합니다.`}
      </span>
      <ChevronRight size={14} className="text-gray-300 dark:text-gray-600 shrink-0" />
    </Link>
  );
}
