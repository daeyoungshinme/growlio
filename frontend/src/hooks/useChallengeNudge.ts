import { useQuery } from "@tanstack/react-query";
import { fetchChallengeSummary } from "@/api/challenges";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";

/** 하단 네비 배지용 — 이번 달 미충족 상태인 활성 입금 챌린지 유무(월 20일 이후).
 * `enabled`가 false면 조회 자체를 건너뛴다 — 챌린지를 만든 적 없는 사용자가 앱을 켤 때마다
 * 불필요하게 이 엔드포인트를 호출하는 것을 막기 위해 호출부(BottomNav)에서 챌린지 존재
 * 여부로 게이트한다. */
export const useChallengeNudge = (enabled = true) =>
  useQuery({
    queryKey: QUERY_KEYS.challengeSummary,
    queryFn: fetchChallengeSummary,
    staleTime: STALE_TIME.MEDIUM,
    enabled,
  });
