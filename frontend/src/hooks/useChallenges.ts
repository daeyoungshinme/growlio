import { useQuery } from "@tanstack/react-query";
import { challengesQuery } from "@/api/queryOptions";

/** 적립 챌린지 목록 + 진행률/스트릭 조회 (계획 탭 · 홈 대시보드 공용). */
export const useChallenges = () => useQuery(challengesQuery);
