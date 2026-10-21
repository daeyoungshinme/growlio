import { useQuery } from "@tanstack/react-query";
import { fetchRebalancingAlerts } from "@/api/alerts";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { mergeAlertsByPortfolio } from "@/utils/portfolio";

/**
 * 목표 비중을 바꾸는 확인창(추천 적용·전술 적용)에 붙일 안내 — 그 포트폴리오에 켜진 자동 실행이 있으면
 * 다음 자동 실행이 새 목표로 추가 확인 없이 주문한다는 사실을 알린다(plans/63 P4-4). 없으면 null.
 */
export function useAutoExecutionNotice(portfolioId: string | undefined): string | null {
  const { data } = useQuery({
    queryKey: QUERY_KEYS.rebalancingAlerts,
    queryFn: fetchRebalancingAlerts,
    staleTime: STALE_TIME.MEDIUM,
    enabled: !!portfolioId,
  });
  if (!portfolioId || !Array.isArray(data)) return null;
  const alert = mergeAlertsByPortfolio(data)[portfolioId];
  if (!alert?.is_active || alert.mode !== "AUTO") return null;
  const when = alert.auto_execution_time ? `(${alert.auto_execution_time}) ` : "";
  return `이 포트폴리오는 자동 실행이 켜져 있어, 다음 자동 실행${when}부터 새 목표 비중으로 계획이 만들어지고 매수는 대기 후 자동 실행돼요.`;
}
