import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { getSyncAllStatus } from "@/api/assets";
import { useSyncStore } from "@/stores/syncStore";
import { invalidateSyncData } from "@/utils/queryInvalidation";
import { toast } from "@/utils/toast";
import { SYNC_ALL_POLL_INTERVAL } from "@/constants/timers";

/**
 * "전체 갱신" 백그라운드 진행 상태를 폴링한다. App.tsx 최상단에서 한 번만
 * 마운트되어야 탭 이동과 무관하게 계속 폴링된다 (syncStore가 전역 상태를 들고 있음).
 */
export function useSyncAllWatcher() {
  const qc = useQueryClient();
  const isSyncingAll = useSyncStore((s) => s.isSyncingAll);
  const updateProgress = useSyncStore((s) => s.updateProgress);
  const finishSyncAll = useSyncStore((s) => s.finishSyncAll);

  useEffect(() => {
    if (!isSyncingAll) return;

    let cancelled = false;

    const poll = async () => {
      try {
        const status = await getSyncAllStatus();
        if (cancelled) return;

        if (status.status === "running") {
          updateProgress(status.done ?? 0, status.total ?? 0, status.failed ?? 0);
        } else if (status.status === "done" || status.status === "error") {
          finishSyncAll(status.failed ?? 0);
          await invalidateSyncData(qc);
          if (status.status === "error" || (status.failed ?? 0) > 0) {
            toast(`${status.failed ?? 0}개 계좌 동기화에 실패했습니다`, "error");
          } else {
            toast("전체 동기화 완료", "success");
          }
        }
      } catch {
        if (!cancelled) finishSyncAll(0);
      }
    };

    void poll();
    const timer = setInterval(poll, SYNC_ALL_POLL_INTERVAL);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [isSyncingAll, qc, updateProgress, finishSyncAll]);
}
