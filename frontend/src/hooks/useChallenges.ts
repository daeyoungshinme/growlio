import { useQuery } from "@tanstack/react-query";
import { fetchChallenges } from "@/api/challenges";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";

/** 적립 챌린지 목록 + 진행률/스트릭 조회 (계획 탭 · 홈 대시보드 공용). */
export const useChallenges = () =>
  useQuery({
    queryKey: QUERY_KEYS.challenges,
    queryFn: fetchChallenges,
    staleTime: STALE_TIME.MEDIUM,
  });
