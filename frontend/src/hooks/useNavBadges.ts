import { useCallback, useMemo, useSyncExternalStore } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useChallengeNudge } from "@/hooks/useChallengeNudge";
import { actionItemsQuery, driftSummaryQuery } from "@/api/queryOptions";

/**
 * 리밸런싱 배지 — 직접 drift-summary를 부르지 않는다. 이 내비는 모든 화면에 떠 있어 예전엔 부팅마다(포트폴리오 조회를
 * 기다린 뒤) 백엔드의 무거운 이탈 계산을 홈의 지금 할 일과 동시에 한 번 더 돌렸고, 관련 무효화마다 어느 화면에서든
 * 즉시 재조회했다(plans/125 C4). 리밸런싱 탭·홈 펼침이 받아 둔 drift-summary 캐시가 있으면 그 판정을 쓰고,
 * 없으면 지금 할 일(같은 판정 `get_drift_summaries`)의 REBALANCE 행으로 대신한다.
 */
function useRebalancingNeedsCount(): number {
  const qc = useQueryClient();
  const { data: driftSummaries } = useQuery({ ...driftSummaryQuery, enabled: false });
  const { data: actionItems } = useQuery({ ...actionItemsQuery, enabled: false });
  // enabled:false 관찰자는 무효화돼도 다시 받지 않는다(v5는 isStale도 항상 false) — 무효화된 drift 캐시는
  // 리밸런싱 탭을 다시 열 때까지 옛 판정이라, 그동안은 지금 할 일(홈이 다시 받음)로 대신한다(plans/126 A2)
  const driftInvalidated = useSyncExternalStore(
    useCallback((onChange) => qc.getQueryCache().subscribe(onChange), [qc]),
    () => qc.getQueryState(driftSummaryQuery.queryKey)?.isInvalidated ?? false,
  );
  return useMemo(() => {
    if (driftSummaries && !driftInvalidated)
      return driftSummaries.filter((s) => s.needs_rebalancing).length;
    // 이탈 포트폴리오가 2개↑면 서버가 한 행(`rebalance:all`)으로 묶고 개수는 `count`에 싣는다.
    // 전술 적용 행이 뜬 포트폴리오는 서버가 REBALANCE 행에서 빼므로(같은 포트폴리오 중복 방지) 이 폴백은
    // drift-summary 경로보다 적게 셀 수 있다 — 의도된 차이(plans/153 B3)
    return (actionItems ?? [])
      .filter((item) => item.kind === "REBALANCE")
      .reduce((sum, item) => sum + (item.count ?? 1), 0);
  }, [driftSummaries, driftInvalidated, actionItems]);
}

export interface NavBadges {
  /** 리밸런싱이 필요한 포트폴리오 수(0이면 배지 없음) */
  rebalancingNeedsCount: number;
  /** 이번 달 적립 챌린지 미완료 */
  challengeNeedsAttention: boolean;
}

/** 하단 내비(모바일)·사이드바(데스크톱) 공용 빨간 점 판정 — 두 내비가 같은 기준을 쓰도록 한곳에서(plans/150 A4) */
export function useNavBadges(): NavBadges {
  const rebalancingNeedsCount = useRebalancingNeedsCount();
  const challengeNeedsAttention = useChallengeNudge();
  return { rebalancingNeedsCount, challengeNeedsAttention };
}

/** 배지 접근성 라벨 — 내비 항목 경로별. 배지가 없으면 null */
export function navBadgeLabel(to: string, badges: NavBadges): string | null {
  if (to === "/rebalancing" && badges.rebalancingNeedsCount > 0)
    return `리밸런싱 필요 ${badges.rebalancingNeedsCount}개`;
  if (to === "/invest-plan" && badges.challengeNeedsAttention) return "이번 달 적립 챌린지 미완료";
  return null;
}
