import { useCallback, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { syncAccount } from "@/api/assets";
import { invalidateSyncData } from "@/utils/queryInvalidation";

export type SyncAccountsState = "idle" | "syncing" | "done" | "error";

/**
 * 여러 계좌를 동기화하고 동기화 관련 쿼리를 무효화한다 — 리밸런싱 실행 결과·분석 하단 "계좌 데이터 갱신"·
 * 실행 후 낡은 분석 배너가 같은 동작을 각자 구현하던 것을 하나로 모은다(plans/63 P2-3).
 * `run`은 전부 성공했는지 돌려줘 호출부가 이어서 재분석할 수 있게 한다.
 */
export function useSyncAccounts() {
  const queryClient = useQueryClient();
  const [state, setState] = useState<SyncAccountsState>("idle");

  const run = useCallback(
    async (accountIds: string[]): Promise<boolean> => {
      if (accountIds.length === 0) return false;
      setState("syncing");
      const settled = await Promise.allSettled(accountIds.map((id) => syncAccount(id)));
      const allOk = settled.every((s) => s.status === "fulfilled");
      await invalidateSyncData(queryClient);
      setState(allOk ? "done" : "error");
      return allOk;
    },
    [queryClient],
  );

  return { state, run };
}
