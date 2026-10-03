import { useQuery } from "@tanstack/react-query";
import { analyzeCandidateOverlap, type OverlapCandidateInput } from "@/api/rebalancing";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";

/** 후보 ETF ↔ 보유 종목·다른 후보 간 중복/총보수 비교.
 *
 * `candidates`를 생략하면 저장된 후보 목록 기준(추천 결과 화면 — 3개 탭이 같은 쿼리를 공유한다).
 * 목록을 넘기면 편집 중 목록 기준(후보 관리 모달). 참고 정보라 실패해도 화면을 막지 않는다(retry 1회). */
export function useCandidateOverlap(candidates?: OverlapCandidateInput[], enabled = true) {
  const signature = candidates
    ? candidates
        .map((c) => `${c.ticker}:${c.market}:${c.asset_class ?? "EQUITY"}`)
        .sort()
        .join(",")
    : "saved";
  return useQuery({
    queryKey: QUERY_KEYS.candidateOverlap(signature),
    queryFn: () => analyzeCandidateOverlap(candidates),
    staleTime: STALE_TIME.LONG,
    retry: 1,
    enabled: enabled && (candidates === undefined || candidates.length > 0),
  });
}
