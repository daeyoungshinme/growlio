import { useCallback, useState } from "react";
import { storageGet, storageSet } from "@/utils/safeStorage";
import { parseAccountSortMode, type AccountSortMode } from "@/utils/accountSort";

const STORAGE_KEY = "growlio:assets:accountSort";

/** 계좌관리 목록 정렬 선택 — 편의 설정이라 기기별 localStorage에만 둔다(plans/144 C3) */
export function useAccountSortMode(): [AccountSortMode, (next: AccountSortMode) => void] {
  const [mode, setModeState] = useState<AccountSortMode>(() =>
    parseAccountSortMode(storageGet(STORAGE_KEY)),
  );
  const setMode = useCallback((next: AccountSortMode) => {
    setModeState(next);
    storageSet(STORAGE_KEY, next);
  }, []);
  return [mode, setMode];
}
