import { useQuery } from "@tanstack/react-query";
import { fetchChallengeSummary } from "@/api/challenges";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";

/** 하단 네비 배지용 — 이번 달 미충족 상태인 활성 입금 챌린지 유무(월 20일 이후). */
export const useChallengeNudge = () =>
  useQuery({
    queryKey: QUERY_KEYS.challengeSummary,
    queryFn: fetchChallengeSummary,
    staleTime: STALE_TIME.MEDIUM,
  });
