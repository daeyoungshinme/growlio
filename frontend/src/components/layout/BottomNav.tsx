import { useMemo } from "react";
import { NavLink } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { NAV_ITEMS } from "@/constants/nav";
import { useChallenges } from "@/hooks/useChallenges";
import { useChallengeNudge } from "@/hooks/useChallengeNudge";
import { actionItemsQuery, driftSummaryQuery } from "@/api/queryOptions";

/**
 * 리밸런싱 배지 — 직접 drift-summary를 부르지 않는다. 이 내비는 모든 화면에 떠 있어 예전엔 부팅마다(포트폴리오 조회를
 * 기다린 뒤) 백엔드의 무거운 이탈 계산을 홈의 지금 할 일과 동시에 한 번 더 돌렸고, 관련 무효화마다 어느 화면에서든
 * 즉시 재조회했다(plans/125 C4). 리밸런싱 탭·홈 펼침이 받아 둔 drift-summary 캐시가 있으면 그 판정을 쓰고,
 * 없으면 지금 할 일(같은 판정 `get_drift_summaries`)의 REBALANCE 행으로 대신한다.
 */
function useRebalancingNeedsCount(): number {
  const { data: driftSummaries } = useQuery({ ...driftSummaryQuery, enabled: false });
  const { data: actionItems } = useQuery({ ...actionItemsQuery, enabled: false });
  return useMemo(() => {
    if (driftSummaries) return driftSummaries.filter((s) => s.needs_rebalancing).length;
    return (actionItems ?? []).filter((item) => item.kind === "REBALANCE").length;
  }, [driftSummaries, actionItems]);
}

export default function BottomNav() {
  const needsCount = useRebalancingNeedsCount();
  const showRebalancingBadge = needsCount > 0;

  const { data: challenges } = useChallenges();
  const hasChallenges = (challenges?.length ?? 0) > 0;

  const { data: challengeNudge } = useChallengeNudge(hasChallenges);
  const showChallengeBadge = challengeNudge?.needs_attention ?? false;

  return (
    <nav
      aria-label="하단 내비게이션"
      className="lg:hidden fixed bottom-0 inset-x-0 bg-white dark:bg-gray-900 border-t border-gray-200 dark:border-gray-700 flex items-stretch justify-around z-50 pb-[env(safe-area-inset-bottom)]"
    >
      {NAV_ITEMS.map(({ to, icon: Icon, label }) => (
        <NavLink
          key={to}
          to={to}
          className={({ isActive }) =>
            `flex flex-col items-center justify-center gap-0.5 px-2 h-(--bottom-nav-h) sm:px-4 min-w-0 flex-1 text-xs font-medium transition-colors ${
              isActive
                ? "text-blue-600 dark:text-blue-400 border-t-2 border-blue-600 dark:border-blue-400 -mt-px"
                : "text-gray-500 dark:text-gray-400 border-t-2 border-transparent -mt-px"
            }`
          }
        >
          <div className="relative">
            <Icon size={22} aria-hidden="true" />
            {to === "/rebalancing" && showRebalancingBadge && (
              <span
                className="absolute -top-0.5 -right-0.5 w-2 h-2 bg-red-500 rounded-full"
                aria-label={`리밸런싱 필요 ${needsCount}개`}
              />
            )}
            {to === "/invest-plan" && showChallengeBadge && (
              <span
                className="absolute -top-0.5 -right-0.5 w-2 h-2 bg-red-500 rounded-full"
                aria-label="이번 달 적립 챌린지 미완료"
              />
            )}
          </div>
          <span className="truncate max-w-full">{label}</span>
        </NavLink>
      ))}
    </nav>
  );
}
