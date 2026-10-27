import type { ExecutionResult } from "@/api/rebalancing";
import { useSyncAccounts } from "@/hooks/useSyncAccounts";
import { OrderResultList } from "./OrderResultList";

interface Props {
  results: ExecutionResult[];
  /** 동기화가 모두 성공하면 호출 — 분석 화면이 실행 후 잔고로 다시 분석한다 */
  onSynced?: () => void;
}

export function RebalancingResultSection({ results, onSynced }: Props) {
  const { state: syncState, run: syncAccounts } = useSyncAccounts();

  async function handleSync() {
    const ok = await syncAccounts([...new Set(results.map((r) => r.account_id))]);
    if (ok) onSynced?.();
  }

  if (results.length === 0) return null;
  return (
    <div className="space-y-4">
      <OrderResultList results={results} />
      <div className="flex justify-end pt-2 border-t border-gray-200 dark:border-gray-700">
        {syncState === "idle" && (
          <button
            onClick={() => void handleSync()}
            className="px-4 py-2 text-sm bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-200 rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
          >
            {onSynced ? "계좌 동기화 후 다시 분석" : "계좌 동기화"}
          </button>
        )}
        {syncState === "syncing" && (
          <div className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
            <span className="w-4 h-4 border-2 border-indigo-400 border-t-transparent rounded-full animate-spin" />
            동기화 중...
          </div>
        )}
        {syncState === "done" && (
          <span className="text-sm text-green-600 dark:text-green-400">
            {onSynced ? "동기화 완료 — 분석을 갱신했어요" : "동기화 완료"}
          </span>
        )}
        {syncState === "error" && (
          <div className="flex items-center gap-2">
            <span className="text-sm text-yellow-600 dark:text-yellow-400">동기화 실패</span>
            <button
              onClick={() => void handleSync()}
              className="px-3 py-1.5 text-xs bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-200 rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
            >
              재시도
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
