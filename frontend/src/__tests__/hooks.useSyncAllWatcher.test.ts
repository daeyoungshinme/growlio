import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

// ── mocks ────────────────────────────────────────────────────────────────────

vi.mock("@/api/assets", () => ({
  getSyncAllStatus: vi.fn(),
}));

vi.mock("@/utils/queryInvalidation", () => ({
  invalidateSyncData: vi.fn().mockResolvedValue(undefined),
}));

vi.mock("@/utils/toast", () => ({
  toast: vi.fn(),
}));

// ── imports ───────────────────────────────────────────────────────────────────

import { useSyncAllWatcher } from "@/hooks/useSyncAllWatcher";
import { getSyncAllStatus } from "@/api/assets";
import { invalidateSyncData } from "@/utils/queryInvalidation";
import { toast } from "@/utils/toast";
import { useSyncStore } from "@/stores/syncStore";

// ── helpers ───────────────────────────────────────────────────────────────────

function createWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
}

describe("useSyncAllWatcher", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useSyncStore.getState().reset();
  });

  it("isSyncingAll이 false면 폴링하지 않는다", () => {
    renderHook(() => useSyncAllWatcher(), { wrapper: createWrapper() });
    expect(getSyncAllStatus).not.toHaveBeenCalled();
  });

  it("동기화 진행 중이면 진행 상태를 store에 반영한다", async () => {
    vi.mocked(getSyncAllStatus).mockResolvedValue({
      status: "running",
      total: 3,
      done: 1,
      failed: 0,
    });
    useSyncStore.getState().startSyncAll(3);

    renderHook(() => useSyncAllWatcher(), { wrapper: createWrapper() });

    await waitFor(() => {
      expect(useSyncStore.getState().done).toBe(1);
    });
    expect(useSyncStore.getState().isSyncingAll).toBe(true);
  });

  it("완료되면 캐시를 무효화하고 성공 토스트를 표시한 뒤 store를 리셋한다", async () => {
    vi.mocked(getSyncAllStatus).mockResolvedValue({
      status: "done",
      total: 2,
      done: 2,
      failed: 0,
    });
    useSyncStore.getState().startSyncAll(2);

    renderHook(() => useSyncAllWatcher(), { wrapper: createWrapper() });

    await waitFor(() => {
      expect(invalidateSyncData).toHaveBeenCalled();
    });
    expect(toast).toHaveBeenCalledWith("전체 동기화 완료", "success");
    expect(useSyncStore.getState().isSyncingAll).toBe(false);
  });

  it("일부 계좌 실패 시 실패 토스트를 표시한다", async () => {
    vi.mocked(getSyncAllStatus).mockResolvedValue({
      status: "done",
      total: 3,
      done: 3,
      failed: 1,
    });
    useSyncStore.getState().startSyncAll(3);

    renderHook(() => useSyncAllWatcher(), { wrapper: createWrapper() });

    await waitFor(() => {
      expect(toast).toHaveBeenCalledWith("1개 계좌 동기화에 실패했습니다", "error");
    });
  });
});
