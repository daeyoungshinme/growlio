import { create } from "zustand";
import type { FailedSyncAccount } from "@/api/assets";

interface SyncState {
  isSyncingAll: boolean;
  done: number;
  total: number;
  failed: number;
  failedAccounts: FailedSyncAccount[];
  startSyncAll: (total: number) => void;
  updateProgress: (done: number, total: number, failed?: number) => void;
  finishSyncAll: (failed: number, failedAccounts?: FailedSyncAccount[]) => void;
  removeFailedAccount: (accountId: string) => void;
  dismissFailedAccounts: () => void;
  reset: () => void;
}

export const useSyncStore = create<SyncState>((set) => ({
  isSyncingAll: false,
  done: 0,
  total: 0,
  failed: 0,
  failedAccounts: [],
  startSyncAll: (total) =>
    set({ isSyncingAll: true, done: 0, total, failed: 0, failedAccounts: [] }),
  updateProgress: (done, total, failed = 0) => set({ isSyncingAll: true, done, total, failed }),
  finishSyncAll: (failed, failedAccounts = []) =>
    set((state) => ({ isSyncingAll: false, failed, done: state.total, failedAccounts })),
  removeFailedAccount: (accountId) =>
    set((state) => ({
      failedAccounts: state.failedAccounts.filter((a) => a.account_id !== accountId),
    })),
  dismissFailedAccounts: () => set({ failedAccounts: [] }),
  reset: () => set({ isSyncingAll: false, done: 0, total: 0, failed: 0, failedAccounts: [] }),
}));
