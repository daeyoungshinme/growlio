import { useQuery } from "@tanstack/react-query";
import { rebalancingAlertsQuery } from "@/api/queryOptions";

/**
 * 목표 비중을 바꾸는 확인창(추천 적용·전술 적용)에 붙일 안내 — 그 포트폴리오에 켜진 자동 실행이 있으면
 * 다음 자동 실행이 새 목표로 추가 확인 없이 주문한다는 사실을 알린다(plans/63 P4-4). 없으면 null.
 */
export function useAutoExecutionNotice(portfolioId: string | undefined): string | null {
  const { data } = useQuery({
    ...rebalancingAlertsQuery,
    enabled: !!portfolioId,
  });
  if (!portfolioId || !Array.isArray(data)) return null;
  // 계좌별 알림이 여러 개면 병합 결과의 시각은 첫 행(NOTIFY일 수 있음) 값이다 — 활성 AUTO 행에서 직접 고른다
  const alert = data.find(
    (a) => a.portfolio_id === portfolioId && a.is_active && a.mode === "AUTO",
  );
  if (!alert) return null;
  const when = alert.auto_execution_time ? `(${alert.auto_execution_time}) ` : "";
  return `이 포트폴리오는 자동 실행이 켜져 있어, 다음 자동 실행${when}부터 새 목표 비중으로 계획이 만들어지고 매수는 대기 후 자동 실행돼요.`;
}
