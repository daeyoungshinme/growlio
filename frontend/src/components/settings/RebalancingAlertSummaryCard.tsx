import { Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { mergeAlertsByPortfolio } from "@/utils/portfolio";
import { TOUCH_TARGET_ROW } from "@/constants/uiSizes";
import SkeletonCard from "@/components/common/SkeletonCard";
import { rebalancingUrl } from "@/utils/rebalancingUrl";
import { portfoliosQuery, rebalancingAlertsQuery } from "@/api/queryOptions";

/** 설정 페이지 알림 섹션에 노출되는 리밸런싱 알림 현황 요약 — 실제 편집은 리밸런싱 탭에서 이뤄지므로
 * 여기서는 상태 요약 + 딥링크만 제공한다 (frontend/CLAUDE.md "다른 설정" 패턴과 동일). */
export default function RebalancingAlertSummaryCard() {
  const {
    data: alerts,
    isLoading: alertsLoading,
    isError: alertsError,
  } = useQuery(rebalancingAlertsQuery);
  const {
    data: portfolios,
    isLoading: portfoliosLoading,
    isError: portfoliosError,
  } = useQuery(portfoliosQuery);

  if (alertsLoading || portfoliosLoading) {
    return <SkeletonCard rows={1} height="h-4" />;
  }

  // 실패 시 "설정된 자동화가 없어요"로 보이면 기존 AUTO 설정이 사라진 것처럼 오해한다
  if (alertsError || portfoliosError) {
    return (
      <Link
        to={rebalancingUrl({ tab: "포트폴리오" })}
        className={`w-full gap-3 -mx-3 px-3 rounded-lg text-xs text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors ${TOUCH_TARGET_ROW}`}
      >
        <span className="flex-1 leading-relaxed">
          리밸런싱 자동화 현황을 불러오지 못했어요 — 리밸런싱 탭에서 확인합니다.
        </span>
        <ChevronRight size={14} className="text-gray-300 dark:text-gray-600 shrink-0" />
      </Link>
    );
  }

  const merged = mergeAlertsByPortfolio((alerts ?? []).filter((a) => a.is_active));
  const alertedCount = Object.keys(merged).length;
  const autoCount = Object.values(merged).filter((a) => a.mode === "AUTO").length;
  const totalCount = portfolios?.length ?? 0;
  // 대상이 하나로 정해지면(포트폴리오 1개, 또는 자동화된 포트폴리오 1개) 그 포트폴리오의 자동화 설정까지
  // 바로 연다 — 목록에서 다시 찾아 모달을 열던 단계를 없앤다(plans/63 P3-4). 여럿이면 목록으로.
  const targetId =
    totalCount === 1
      ? (portfolios?.[0]?.id ?? null)
      : alertedCount === 1
        ? (Object.keys(merged)[0] ?? null)
        : null;
  const linkTo = targetId
    ? rebalancingUrl({ tab: "포트폴리오", portfolioId: targetId, openAlert: "1" })
    : rebalancingUrl({ tab: "포트폴리오" });

  return (
    <Link
      to={linkTo}
      className={`w-full gap-3 -mx-3 px-3 rounded-lg text-xs text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors ${TOUCH_TARGET_ROW}`}
    >
      <span className="flex-1 leading-relaxed">
        {alertedCount === 0
          ? "아직 설정된 리밸런싱 자동화가 없어요 — 리밸런싱 탭 포트폴리오의 '자동화 설정'에서 설정합니다."
          : `포트폴리오 ${totalCount}개 중 ${alertedCount}개에 자동화 설정됨${
              autoCount > 0 ? ` (자동 실행 ${autoCount}개)` : ""
            } — 리밸런싱 탭에서 관리합니다.`}
      </span>
      <ChevronRight size={14} className="text-gray-300 dark:text-gray-600 shrink-0" />
    </Link>
  );
}
