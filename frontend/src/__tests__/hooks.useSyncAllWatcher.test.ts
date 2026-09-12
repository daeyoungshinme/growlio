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

  it("실패 계좌 상세가 있으면 계좌명을 포함한 토스트를 표시하고 store에 저장한다", async () => {
    const failedAccounts = [
      { account_id: "acc-1", account_name: "키움 종합계좌", error: "인증에 실패했습니다" },
    ];
    vi.mocked(getSyncAllStatus).mockResolvedValue({
      status: "done",
      total: 2,
      done: 2,
      failed: 1,
      failed_accounts: failedAccounts,
    });
    useSyncStore.getState().startSyncAll(2);

    renderHook(() => useSyncAllWatcher(), { wrapper: createWrapper() });

    await waitFor(() => {
      expect(toast).toHaveBeenCalledWith("키움 종합계좌 동기화 실패", "error");
    });
    expect(useSyncStore.getState().failedAccounts).toEqual(failedAccounts);
  });

  it("실패 계좌가 3개 이상이면 앞 2개 이름 뒤 '외 N개'로 요약한다", async () => {
    const failedAccounts = [
      { account_id: "a1", account_name: "계좌A", error: "e1" },
      { account_id: "a2", account_name: "계좌B", error: "e2" },
      { account_id: "a3", account_name: "계좌C", error: "e3" },
    ];
    vi.mocked(getSyncAllStatus).mockResolvedValue({
      status: "done",
      total: 5,
      done: 5,
      failed: 3,
      failed_accounts: failedAccounts,
    });
    useSyncStore.getState().startSyncAll(5);

    renderHook(() => useSyncAllWatcher(), { wrapper: createWrapper() });

    await waitFor(() => {
      expect(toast).toHaveBeenCalledWith("계좌A, 계좌B 외 1개 계좌 동기화 실패", "error");
    });
  });

  it("배치 전체 실패(error 상태)면 error 메시지를 토스트로 표시한다", async () => {
    vi.mocked(getSyncAllStatus).mockResolvedValue({
      status: "error",
      total: 2,
      done: 0,
      failed: 2,
      failed_accounts: [],
      error: "boom",
    });
    useSyncStore.getState().startSyncAll(2);

    renderHook(() => useSyncAllWatcher(), { wrapper: createWrapper() });

    await waitFor(() => {
      expect(toast).toHaveBeenCalledWith("전체 동기화 실패: boom", "error");
    });
  });
});
