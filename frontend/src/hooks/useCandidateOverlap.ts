import { useEffect, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { analyzeCandidateOverlap, type OverlapCandidateInput } from "@/api/rebalancing";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";

/** 후보 관리 모달에서 연달아 추가·삭제·자산군 변경할 때 매 편집마다 요청이 나가지 않도록 묶는 간격. */
export const CANDIDATE_OVERLAP_DEBOUNCE_MS = 400;

function overlapSignature(candidates?: OverlapCandidateInput[]): string {
  return candidates
    ? candidates
        .map((c) => `${c.ticker}:${c.market}:${c.asset_class ?? "EQUITY"}`)
        .sort()
        .join(",")
    : "saved";
}

/** 후보 ETF ↔ 보유 종목·다른 후보 간 중복/총보수 비교.
 *
 * `candidates`를 생략하면 저장된 후보 목록 기준(추천 결과 화면 — 3개 탭이 같은 쿼리를 공유한다).
 * 목록을 넘기면 편집 중 목록 기준(후보 관리 모달) — 첫 목록은 바로 조회하고, 이후 편집은
 * `CANDIDATE_OVERLAP_DEBOUNCE_MS`만큼 묶어 마지막 목록만 조회한다(그 사이엔 이전 결과 유지).
 * 참고 정보라 실패해도 화면을 막지 않는다(retry 1회). */
export function useCandidateOverlap(candidates?: OverlapCandidateInput[], enabled = true) {
  const signature = overlapSignature(candidates);
  const [settled, setSettled] = useState({ signature, candidates });

  useEffect(() => {
    if (signature === settled.signature) return;
    const timer = setTimeout(
      () => setSettled({ signature, candidates }),
      CANDIDATE_OVERLAP_DEBOUNCE_MS,
    );
    return () => clearTimeout(timer);
  }, [signature, candidates, settled.signature]);

  return useQuery({
    queryKey: QUERY_KEYS.candidateOverlap(settled.signature),
    queryFn: () => analyzeCandidateOverlap(settled.candidates),
    staleTime: STALE_TIME.LONG,
    retry: 1,
    placeholderData: keepPreviousData,
    enabled: enabled && (candidates === undefined || candidates.length > 0),
  });
}
