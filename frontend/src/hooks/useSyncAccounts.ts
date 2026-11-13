import { useCallback, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { syncAccount } from "@/api/assets";
import { invalidateSyncData } from "@/utils/queryInvalidation";

export type SyncAccountsState = "idle" | "syncing" | "done" | "error";

export interface SyncAccountsResult {
  total: number;
  failed: number;
}

// 백엔드 `sync_accounts` 세마포어와 같은 수 — 계좌를 한꺼번에 보내면 증권사 호출·서버 커넥션이 몰린다(plans/128 A2)
const SYNC_CONCURRENCY = 3;

/** 계좌를 `SYNC_CONCURRENCY`개씩 동기화하고 실패한 수를 돌려준다 */
async function syncInBatches(accountIds: string[]): Promise<number> {
  let failed = 0;
  let next = 0;
  const worker = async () => {
    while (next < accountIds.length) {
      const id = accountIds[next++];
      if (id === undefined) return;
      try {
        await syncAccount(id);
      } catch {
        failed += 1;
      }
    }
  };
  await Promise.all(Array.from({ length: Math.min(SYNC_CONCURRENCY, accountIds.length) }, worker));
  return failed;
}

/**
 * 여러 계좌를 동기화하고 동기화 관련 쿼리를 무효화한다 — 리밸런싱 실행 결과·분석 하단 "계좌 데이터 갱신"·
 * 실행 후 낡은 분석 배너가 같은 동작을 각자 구현하던 것을 하나로 모은다(plans/63 P2-3).
 * `run`은 전부 성공했는지 돌려줘 호출부가 이어서 재분석할 수 있게 한다. 실패 수가 필요하면 `runWithResult`.
 */
export function useSyncAccounts() {
  const queryClient = useQueryClient();
  const [state, setState] = useState<SyncAccountsState>("idle");

  const runWithResult = useCallback(
    async (accountIds: string[]): Promise<SyncAccountsResult> => {
      const total = accountIds.length;
      if (total === 0) return { total, failed: 0 };
      setState("syncing");
      const failed = await syncInBatches(accountIds);
      await invalidateSyncData(queryClient);
      setState(failed === 0 ? "done" : "error");
      return { total, failed };
    },
    [queryClient],
  );

  const run = useCallback(
    async (accountIds: string[]): Promise<boolean> => {
      const { total, failed } = await runWithResult(accountIds);
      return total > 0 && failed === 0;
    },
    [runWithResult],
  );

  return { state, run, runWithResult };
}
