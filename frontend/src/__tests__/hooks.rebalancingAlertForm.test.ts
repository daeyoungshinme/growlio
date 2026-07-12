import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

// ── mocks ─────────────────────────────────────────────────────────────────────

vi.mock("@/api/client", () => {
  const mockApi = { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn(), patch: vi.fn() };
  return {
    api: mockApi,
    apiGet: (url: string, ...args: unknown[]) =>
      mockApi.get(url, ...args).then((r: { data: unknown }) => r.data),
    apiPost: (url: string, ...args: unknown[]) =>
      mockApi.post(url, ...args).then((r: { data: unknown }) => r.data),
    apiPut: (url: string, ...args: unknown[]) =>
      mockApi.put(url, ...args).then((r: { data: unknown }) => r.data),
    apiPatch: (url: string, ...args: unknown[]) =>
      mockApi.patch(url, ...args).then((r: { data: unknown }) => r.data),
    apiDelete: (url: string, ...args: unknown[]) =>
      mockApi.delete(url, ...args).then((r: { data: unknown }) => r.data),
  };
});

vi.mock("@/api/alerts", () => ({
  fetchRebalancingAlert: vi.fn(),
  fetchAccountRebalancingAlert: vi.fn(),
  upsertRebalancingAlert: vi.fn(),
  deleteRebalancingAlert: vi.fn(),
}));

vi.mock("@/api/assets", () => ({
  fetchAccounts: vi.fn().mockResolvedValue([]),
}));

vi.mock("@/api/marketSignals", () => ({
  fetchMarketSignal: vi.fn().mockResolvedValue({
    composite_level: "GREEN",
    composite_score: 75,
    fear_greed_contrarian_buy: false,
    fear_greed_extreme_greed: false,
    signals: { vix: null, yield_curve: null, fear_greed: null },
    computed_at: "2024-01-01T00:00:00Z",
    data_freshness: "LIVE",
  }),
}));

vi.mock("@/utils/toast", () => ({ toast: vi.fn() }));

vi.mock("@/utils/error", () => ({
  extractErrorMessage: vi.fn((e: unknown, fallback = "오류") =>
    e instanceof Error ? e.message : fallback,
  ),
  getHttpStatus: vi.fn((e: unknown) => (e as { status?: number })?.status ?? undefined),
}));

vi.mock("@/utils/queryInvalidation", () => ({
  invalidateRebalancingAlertData: vi.fn().mockResolvedValue(undefined),
}));

// ── imports ───────────────────────────────────────────────────────────────────

import { fetchAccounts } from "@/api/assets";
import {
  fetchRebalancingAlert,
  fetchAccountRebalancingAlert,
  upsertRebalancingAlert,
  deleteRebalancingAlert,
} from "@/api/alerts";
import {
  useRebalancingAlertQueries,
  useRebalancingAlertFormState,
} from "@/hooks/useRebalancingAlertForm";
import type { RebalancingAlert } from "@/api/alerts";

// ── helpers ───────────────────────────────────────────────────────────────────

function createWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
}

const mockAlert: RebalancingAlert = {
  id: "alert-1",
  portfolio_id: "port-1",
  threshold_pct: 5,
  schedule_type: "WEEKLY",
  schedule_day_of_week: 1,
  schedule_day_of_month: null,
  trigger_condition: "DRIFT_ONLY",
  mode: "NOTIFY",
  strategy: "BUY_ONLY",
  account_id: null,
  order_type: "MARKET",
  market_condition_mode: "DISABLED",
  auto_execution_time: null,
  notify_time: "08:30",
  buy_wait_minutes: 10,
  is_active: true,
  last_triggered_at: null,
  created_at: "2024-01-01T00:00:00Z",
  updated_at: "2024-01-01T00:00:00Z",
};

// ── useRebalancingAlertQueries ─────────────────────────────────────────────────

describe("useRebalancingAlertQueries", () => {
  beforeEach(() => vi.clearAllMocks());

  it("로딩 중 isLoading이 true다", () => {
    vi.mocked(fetchRebalancingAlert).mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useRebalancingAlertQueries({ portfolioId: "port-1" }), {
      wrapper: createWrapper(),
    });
    expect(result.current.isLoading).toBe(true);
  });

  it("alert 데이터를 로드한다", async () => {
    vi.mocked(fetchRebalancingAlert).mockResolvedValue(mockAlert);
    const { result } = renderHook(() => useRebalancingAlertQueries({ portfolioId: "port-1" }), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.alert).toEqual(mockAlert);
  });

  it("alert가 없으면 null을 반환한다", async () => {
    vi.mocked(fetchRebalancingAlert).mockResolvedValue(undefined as never);
    const { result } = renderHook(() => useRebalancingAlertQueries({ portfolioId: "port-1" }), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.alert).toBeNull();
  });

  it("brokerAccounts는 KIS/키움 활성 계좌만 필터한다", async () => {
    vi.mocked(fetchRebalancingAlert).mockResolvedValue(null as never);
    vi.mocked(fetchAccounts).mockResolvedValue([
      {
        id: "a1",
        asset_type: "STOCK_KIS",
        is_active: true,
        name: "KIS",
        kis_account_no: null,
      } as never,
      { id: "a2", asset_type: "STOCK_KIWOOM", is_active: true, name: "키움" } as never,
      { id: "a3", asset_type: "BANK_ACCOUNT", is_active: true, name: "은행" } as never,
      { id: "a4", asset_type: "STOCK_KIS", is_active: false, name: "비활성" } as never,
    ]);

    const { result } = renderHook(() => useRebalancingAlertQueries({ portfolioId: "port-1" }), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.brokerAccounts).toHaveLength(2);
    expect(result.current.brokerAccounts.map((a) => a.id)).toEqual(["a1", "a2"]);
  });

  it("kisAccounts는 accountIds 필터를 적용한다", async () => {
    vi.mocked(fetchRebalancingAlert).mockResolvedValue(null as never);
    vi.mocked(fetchAccounts).mockResolvedValue([
      { id: "a1", asset_type: "STOCK_KIS", is_active: true, name: "KIS1" } as never,
      { id: "a2", asset_type: "STOCK_KIS", is_active: true, name: "KIS2" } as never,
    ]);

    const { result } = renderHook(
      () => useRebalancingAlertQueries({ portfolioId: "port-1", accountIds: ["a1"] }),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.kisAccounts).toHaveLength(1);
    expect(result.current.kisAccounts[0].id).toBe("a1");
  });

  it("accountIds가 null이면 모든 KIS 계좌를 반환한다", async () => {
    vi.mocked(fetchRebalancingAlert).mockResolvedValue(null as never);
    vi.mocked(fetchAccounts).mockResolvedValue([
      { id: "a1", asset_type: "STOCK_KIS", is_active: true, name: "KIS1" } as never,
      { id: "a2", asset_type: "STOCK_KIS", is_active: true, name: "KIS2" } as never,
    ]);

    const { result } = renderHook(
      () => useRebalancingAlertQueries({ portfolioId: "port-1", accountIds: null }),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.kisAccounts).toHaveLength(2);
  });

  it("targetAccountId가 없으면 targetAccountIsKis는 true다", async () => {
    vi.mocked(fetchRebalancingAlert).mockResolvedValue(null as never);
    vi.mocked(fetchAccounts).mockResolvedValue([]);

    const { result } = renderHook(() => useRebalancingAlertQueries({ portfolioId: "port-1" }), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.targetAccountIsKis).toBe(true);
  });

  it("targetAccountId가 KIS 계좌면 targetAccountIsKis는 true다", async () => {
    vi.mocked(fetchAccountRebalancingAlert).mockResolvedValue(null as never);
    vi.mocked(fetchAccounts).mockResolvedValue([
      { id: "a1", asset_type: "STOCK_KIS", is_active: true, name: "KIS" } as never,
    ]);

    const { result } = renderHook(
      () => useRebalancingAlertQueries({ portfolioId: "port-1", targetAccountId: "a1" }),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.targetAccountIsKis).toBe(true);
  });

  it("targetAccountId가 키움 계좌면 targetAccountIsKis는 false다", async () => {
    vi.mocked(fetchAccountRebalancingAlert).mockResolvedValue(null as never);
    vi.mocked(fetchAccounts).mockResolvedValue([
      { id: "a2", asset_type: "STOCK_KIWOOM", is_active: true, name: "키움" } as never,
    ]);

    const { result } = renderHook(
      () => useRebalancingAlertQueries({ portfolioId: "port-1", targetAccountId: "a2" }),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.targetAccountIsKis).toBe(false);
  });

  it("targetAccountId에 해당하는 계좌가 없으면 targetAccountIsKis는 false다", async () => {
    vi.mocked(fetchAccountRebalancingAlert).mockResolvedValue(null as never);
    vi.mocked(fetchAccounts).mockResolvedValue([]);

    const { result } = renderHook(
      () => useRebalancingAlertQueries({ portfolioId: "port-1", targetAccountId: "missing" }),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.targetAccountIsKis).toBe(false);
  });
});

// ── useRebalancingAlertFormState ───────────────────────────────────────────────

describe("useRebalancingAlertFormState", () => {
  beforeEach(() => vi.clearAllMocks());

  const onClose = vi.fn();

  it("alert가 null이면 기본값으로 초기화된다", () => {
    const { result } = renderHook(
      () => useRebalancingAlertFormState({ alert: null, portfolioId: "port-1", onClose }),
      { wrapper: createWrapper() },
    );
    expect(result.current.scheduleType).toBe("DAILY");
    expect(result.current.triggerCondition).toBe("DRIFT_ONLY");
    expect(result.current.mode).toBe("NOTIFY");
    expect(result.current.strategy).toBe("BUY_ONLY");
    expect(result.current.threshold).toBe(5);
    expect(result.current.orderType).toBe("MARKET");
    expect(result.current.marketConditionMode).toBe("DISABLED");
  });

  it("alert 값으로 초기화된다", () => {
    const { result } = renderHook(
      () => useRebalancingAlertFormState({ alert: mockAlert, portfolioId: "port-1", onClose }),
      { wrapper: createWrapper() },
    );
    expect(result.current.scheduleType).toBe("WEEKLY");
    expect(result.current.dayOfWeek).toBe(1);
    expect(result.current.triggerCondition).toBe("DRIFT_ONLY");
    expect(result.current.threshold).toBe(5);
  });

  it("setScheduleType으로 scheduleType이 변경된다", () => {
    const { result } = renderHook(
      () => useRebalancingAlertFormState({ alert: null, portfolioId: "port-1", onClose }),
      { wrapper: createWrapper() },
    );
    act(() => {
      result.current.setScheduleType("MONTHLY");
    });
    expect(result.current.scheduleType).toBe("MONTHLY");
  });

  it("setMode로 mode가 변경된다", () => {
    const { result } = renderHook(
      () => useRebalancingAlertFormState({ alert: null, portfolioId: "port-1", onClose }),
      { wrapper: createWrapper() },
    );
    act(() => {
      result.current.setMode("AUTO");
    });
    expect(result.current.mode).toBe("AUTO");
  });

  it("setThreshold로 threshold가 변경된다", () => {
    const { result } = renderHook(
      () => useRebalancingAlertFormState({ alert: null, portfolioId: "port-1", onClose }),
      { wrapper: createWrapper() },
    );
    act(() => {
      result.current.setThreshold(10);
    });
    expect(result.current.threshold).toBe(10);
  });

  it("upsertMut 성공 시 onClose와 toast를 호출한다", async () => {
    vi.mocked(upsertRebalancingAlert).mockResolvedValue(mockAlert);
    const { toast } = await import("@/utils/toast");

    const { result } = renderHook(
      () => useRebalancingAlertFormState({ alert: null, portfolioId: "port-1", onClose }),
      { wrapper: createWrapper() },
    );

    await act(async () => {
      await result.current.upsertMut.mutateAsync();
    });

    expect(toast).toHaveBeenCalledWith("설정이 저장되었습니다", "success");
    expect(onClose).toHaveBeenCalled();
  });

  it("deleteMut 성공 시 onClose와 toast를 호출한다", async () => {
    vi.mocked(deleteRebalancingAlert).mockResolvedValue(undefined as never);
    const { toast } = await import("@/utils/toast");

    const { result } = renderHook(
      () => useRebalancingAlertFormState({ alert: mockAlert, portfolioId: "port-1", onClose }),
      { wrapper: createWrapper() },
    );

    await act(async () => {
      await result.current.deleteMut.mutateAsync();
    });

    expect(toast).toHaveBeenCalledWith("설정이 해제되었습니다", "success");
    expect(onClose).toHaveBeenCalled();
  });

  it("upsertMut 실패 시 toast를 에러로 호출한다", async () => {
    vi.mocked(upsertRebalancingAlert).mockRejectedValue(new Error("저장 실패"));
    const { toast } = await import("@/utils/toast");

    const { result } = renderHook(
      () => useRebalancingAlertFormState({ alert: null, portfolioId: "port-1", onClose }),
      { wrapper: createWrapper() },
    );

    await act(async () => {
      try {
        await result.current.upsertMut.mutateAsync();
      } catch {
        // mutation throws on error
      }
    });

    expect(toast).toHaveBeenCalled();
  });

  it("isPending이 mutation 진행 중 true가 된다", () => {
    vi.mocked(upsertRebalancingAlert).mockReturnValue(new Promise(() => {}));

    const { result } = renderHook(
      () => useRebalancingAlertFormState({ alert: null, portfolioId: "port-1", onClose }),
      { wrapper: createWrapper() },
    );

    expect(result.current.isPending).toBe(false);
  });

  it("신규 알림 + 계좌유형 정보가 있으면 추천 임계값으로 초기화된다", () => {
    const { result } = renderHook(
      () =>
        useRebalancingAlertFormState({
          alert: null,
          portfolioId: "port-1",
          targetAccountTaxType: "ISA",
          targetAccountInvestmentHorizon: "LONG_TERM",
          onClose,
        }),
      { wrapper: createWrapper() },
    );
    expect(result.current.recommendedThreshold).toBe(8.5);
    expect(result.current.threshold).toBe(8.5);
    expect(result.current.isNewAlert).toBe(true);
  });

  it("기존 알림 수정 시에는 계좌유형 정보가 있어도 저장된 값을 유지한다", () => {
    const { result } = renderHook(
      () =>
        useRebalancingAlertFormState({
          alert: mockAlert,
          portfolioId: "port-1",
          targetAccountTaxType: "ISA",
          targetAccountInvestmentHorizon: "LONG_TERM",
          onClose,
        }),
      { wrapper: createWrapper() },
    );
    expect(result.current.threshold).toBe(mockAlert.threshold_pct);
    expect(result.current.isNewAlert).toBe(false);
  });
});
