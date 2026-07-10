import { create } from "zustand";

interface SyncState {
  isSyncingAll: boolean;
  done: number;
  total: number;
  failed: number;
  startSyncAll: (total: number) => void;
  updateProgress: (done: number, total: number, failed?: number) => void;
  finishSyncAll: (failed: number) => void;
  reset: () => void;
}

export const useSyncStore = create<SyncState>((set) => ({
  isSyncingAll: false,
  done: 0,
  total: 0,
  failed: 0,
  startSyncAll: (total) => set({ isSyncingAll: true, done: 0, total, failed: 0 }),
  updateProgress: (done, total, failed = 0) => set({ isSyncingAll: true, done, total, failed }),
  finishSyncAll: (failed) => set((state) => ({ isSyncingAll: false, failed, done: state.total })),
  reset: () => set({ isSyncingAll: false, done: 0, total: 0, failed: 0 }),
}));
