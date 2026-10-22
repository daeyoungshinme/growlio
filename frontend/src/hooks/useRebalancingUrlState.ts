import { useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import {
  applyRebalancingParams,
  parseRebalancingTab,
  type RebalancingUrlOptions,
} from "@/utils/rebalancingUrl";

/**
 * 리밸런싱 페이지의 URL 상태(탭·목표 조정 모드·선택 포트폴리오·일회성 딥링크) 읽기/쓰기.
 * 탭은 state로 복사하지 않고 URL에서 파생한다 — 페이지가 열린 채 들어온 딥링크(푸시 등)가
 * URL만 바꾸고 화면은 그대로 남지 않도록(plans/62 B4).
 */
export function useRebalancingUrlState() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { tab, mode } = parseRebalancingTab(searchParams);
  const portfolioId = searchParams.get("portfolioId") ?? undefined;

  const navigateTo = useCallback(
    (options: RebalancingUrlOptions) => {
      setSearchParams((prev) => applyRebalancingParams(new URLSearchParams(prev), options), {
        replace: true,
      });
    },
    [setSearchParams],
  );

  const clearParam = useCallback(
    (key: string) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          next.delete(key);
          return next;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  return { searchParams, tab, mode, portfolioId, navigateTo, clearParam };
}
