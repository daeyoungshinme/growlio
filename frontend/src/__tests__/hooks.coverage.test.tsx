import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

// ── mocks ────────────────────────────────────────────────────────────────────

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

vi.mock("@/utils/toast", () => ({ toast: vi.fn() }));

vi.mock("@/utils/error", () => ({
  extractErrorMessage: vi.fn((e: unknown, fallback = "오류") =>
    e instanceof Error ? e.message : fallback,
  ),
  getHttpStatus: vi.fn((e: unknown) => (e as { status?: number })?.status ?? null),
}));

vi.mock("@/context/ExchangeRateContext", () => ({
  useExchangeRateContext: vi.fn(() => ({ rate: 1350, isLoading: false, error: null })),
  ExchangeRateProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock("@/api/rebalancing", () => ({
  analyzePortfolio: vi.fn(),
  fetchRebalancingAlerts: vi.fn(),
}));

vi.mock("@/utils/queryInvalidation", () => ({
  invalidateAccountData: vi.fn().mockResolvedValue(undefined),
  invalidateSyncData: vi.fn().mockResolvedValue(undefined),
  invalidatePortfolioData: vi.fn().mockResolvedValue(undefined),
  invalidateDcaData: vi.fn().mockResolvedValue(undefined),
  invalidateTransactionData: vi.fn().mockResolvedValue(undefined),
  invalidateAlertData: vi.fn().mockResolvedValue(undefined),
  invalidateRebalancingAlertData: vi.fn().mockResolvedValue(undefined),
}));

// ── imports ───────────────────────────────────────────────────────────────────

import { api } from "@/api/client";
import { executionReducer } from "@/hooks/rebalancingExecution/reducer";
import { useAccountMutations } from "@/hooks/useAccountMutations";
import type { ExecutionState } from "@/hooks/rebalancingExecution/types";
import { useAccountPositions } from "@/hooks/useAccountPositions";
import { useOptimizationSuggestions } from "@/hooks/useOptimizationSuggestions";
import { useBacktestDateRange } from "@/hooks/useBacktestDateRange";
import { useAllocationHistory } from "@/hooks/useAllocationHistory";
import { useAlertCrud } from "@/hooks/useAlertCrud";
import { useAnalysisState } from "@/hooks/useAnalysisState";
import { useAssetManagementData } from "@/hooks/useAssetManagementData";

// ── helpers ───────────────────────────────────────────────────────────────────

function createWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
}

// ─── useAccountPositions ──────────────────────────────────────────────────────

describe("useAccountPositions", () => {
  beforeEach(() => vi.clearAllMocks());

  it("enabled=false이면 빈 배열을 반환하고 API를 호출하지 않는다", () => {
    const { result } = renderHook(() => useAccountPositions("acc-1", false), {
      wrapper: createWrapper(),
    });
    expect(result.current).toEqual([]);
    expect(vi.mocked(api.get)).not.toHaveBeenCalled();
  });

  it("accountId가 빈 문자열이면 조회하지 않는다", () => {
    const { result } = renderHook(() => useAccountPositions("", true), {
      wrapper: createWrapper(),
    });
    expect(result.current).toEqual([]);
  });

  it("데이터를 로드하면 positions 배열을 반환한다", async () => {
    vi.mocked(api.get).mockResolvedValue({
      data: { positions: [{ ticker: "005930", name: "삼성전자", qty: 10 }] },
    });

    const { result } = renderHook(() => useAccountPositions("acc-1", true), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current).toHaveLength(1));
    expect(result.current[0].ticker).toBe("005930");
    expect(result.current[0].qty).toBe(10);
  });

  it("데이터 없으면 빈 배열을 반환한다", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { positions: [] } });

    const { result } = renderHook(() => useAccountPositions("acc-1", true), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(vi.mocked(api.get)).toHaveBeenCalled());
    expect(result.current).toEqual([]);
  });
});

// ─── useOptimizationSuggestions ───────────────────────────────────────────────

describe("useOptimizationSuggestions", () => {
  beforeEach(() => vi.clearAllMocks());

  it("로딩 중 isLoading이 true다", () => {
    vi.mocked(api.get).mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useOptimizationSuggestions(), { wrapper: createWrapper() });
    expect(result.current.isLoading).toBe(true);
    expect(result.current.suggestions).toBeUndefined();
  });

  it("데이터를 로드하면 suggestions를 반환한다", async () => {
    const mockData = [
      {
        month: 1,
        ticker: "005930",
        name: "삼성전자",
        market: "KOSPI",
        estimated_monthly_krw: 50000,
        current_monthly_total_krw: 30000,
      },
    ];
    vi.mocked(api.get).mockResolvedValue({ data: mockData });

    const { result } = renderHook(() => useOptimizationSuggestions(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.suggestions).toEqual(mockData);
  });
});

// ─── useBacktestDateRange ─────────────────────────────────────────────────────

describe("useBacktestDateRange", () => {
  it("기본 preset이 5로 설정된다", () => {
    const { result } = renderHook(() => useBacktestDateRange());
    expect(result.current.activePreset).toBe(5);
    expect(typeof result.current.startDate).toBe("string");
    expect(typeof result.current.endDate).toBe("string");
  });

  it("setStartDate 호출 시 날짜가 변경되고 activePreset이 null이 된다", () => {
    const { result } = renderHook(() => useBacktestDateRange());
    act(() => {
      result.current.setStartDate("2020-01-01");
    });
    expect(result.current.startDate).toBe("2020-01-01");
    expect(result.current.activePreset).toBeNull();
  });

  it("setEndDate 호출 시 날짜가 변경되고 activePreset이 null이 된다", () => {
    const { result } = renderHook(() => useBacktestDateRange());
    act(() => {
      result.current.setEndDate("2024-12-31");
    });
    expect(result.current.endDate).toBe("2024-12-31");
    expect(result.current.activePreset).toBeNull();
  });

  it("setPreset(3) 호출 시 activePreset이 3이 된다", () => {
    const { result } = renderHook(() => useBacktestDateRange());
    act(() => {
      result.current.setPreset(3);
    });
    expect(result.current.activePreset).toBe(3);
    expect(result.current.startDate).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it("setPreset(30) 호출 시 1월 1일로 시작 날짜가 설정된다", () => {
    const { result } = renderHook(() => useBacktestDateRange());
    act(() => {
      result.current.setPreset(30);
    });
    expect(result.current.startDate).toMatch(/^\d{4}-01-01$/);
    expect(result.current.activePreset).toBe(30);
  });

  it("setPreset 후 setStartDate 호출 시 activePreset이 null이 된다", () => {
    const { result } = renderHook(() => useBacktestDateRange());
    act(() => {
      result.current.setPreset(1);
    });
    expect(result.current.activePreset).toBe(1);
    act(() => {
      result.current.setStartDate("2023-06-01");
    });
    expect(result.current.activePreset).toBeNull();
  });
});

// ─── useAllocationHistory ─────────────────────────────────────────────────────

describe("useAllocationHistory", () => {
  beforeEach(() => vi.clearAllMocks());

  it("데이터 없을 때 빈 배열과 isLoading=true를 반환한다", () => {
    vi.mocked(api.get).mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useAllocationHistory(), { wrapper: createWrapper() });
    expect(result.current.isLoading).toBe(true);
    expect(result.current.chartData).toEqual([]);
    expect(result.current.allTypes).toEqual([]);
  });

  it("데이터 로드 시 chartData와 allTypes를 변환한다", async () => {
    const mockData = [
      {
        month: "2024-01-01",
        total_krw: 1000000,
        allocations: [
          { asset_type: "STOCK_KIS", label: "KIS 주식", amount_krw: 700000, weight_pct: 70 },
          { asset_type: "BANK_ACCOUNT", label: "은행", amount_krw: 300000, weight_pct: 30 },
        ],
      },
    ];
    vi.mocked(api.get).mockResolvedValue({ data: mockData });

    const { result } = renderHook(() => useAllocationHistory(12), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.allTypes).toContain("STOCK_KIS");
    expect(result.current.allTypes).toContain("BANK_ACCOUNT");
    expect(result.current.chartData).toHaveLength(1);
    expect(result.current.chartData[0]["STOCK_KIS"]).toBe(700000);
    expect(result.current.chartData[0]["BANK_ACCOUNT"]).toBe(300000);
  });

  it("labelMap이 asset_type → label 매핑을 제공한다", async () => {
    const mockData = [
      {
        month: "2024-01-01",
        total_krw: 1000000,
        allocations: [
          { asset_type: "STOCK_KIS", label: "KIS 주식", amount_krw: 700000, weight_pct: 70 },
        ],
      },
    ];
    vi.mocked(api.get).mockResolvedValue({ data: mockData });

    const { result } = renderHook(() => useAllocationHistory(12), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.labelMap["STOCK_KIS"]).toBe("KIS 주식");
  });

  it("reversedMonthly가 역순으로 정렬된다", async () => {
    const mockData = [
      { month: "2024-01-01", total_krw: 100, allocations: [] },
      { month: "2024-02-01", total_krw: 200, allocations: [] },
    ];
    vi.mocked(api.get).mockResolvedValue({ data: mockData });

    const { result } = renderHook(() => useAllocationHistory(12), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.reversedMonthly[0].month).toBe("2024-02-01");
    expect(result.current.reversedMonthly[1].month).toBe("2024-01-01");
  });

  it("데이터가 빈 배열이면 labelMap이 빈 객체다", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] });

    const { result } = renderHook(() => useAllocationHistory(12), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.labelMap).toEqual({});
  });
});

// ─── useAlertCrud ─────────────────────────────────────────────────────────────

describe("useAlertCrud", () => {
  beforeEach(() => vi.clearAllMocks());

  it("queryFn에서 items를 로드한다", async () => {
    const mockItems = [{ id: "1", label: "alert-1" }];
    const queryFn = vi.fn().mockResolvedValue(mockItems);

    const { result } = renderHook(
      () =>
        useAlertCrud({
          queryKey: ["coverage-alerts-1"],
          queryFn,
          reactivateFn: vi.fn(),
          deleteFn: vi.fn(),
          invalidateFn: vi.fn(),
        }),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.items).toEqual(mockItems));
  });

  it("reactivateMutation 성공 시 invalidateFn과 toast를 호출한다", async () => {
    const invalidateFn = vi.fn();
    const reactivateFn = vi.fn().mockResolvedValue(undefined);
    const { toast } = await import("@/utils/toast");

    const { result } = renderHook(
      () =>
        useAlertCrud({
          queryKey: ["coverage-alerts-2"],
          queryFn: vi.fn().mockResolvedValue([]),
          reactivateFn,
          deleteFn: vi.fn(),
          invalidateFn,
        }),
      { wrapper: createWrapper() },
    );

    await act(async () => {
      await result.current.reactivateMutation.mutateAsync("alert-1");
    });

    expect(reactivateFn.mock.calls[0][0]).toBe("alert-1");
    expect(invalidateFn).toHaveBeenCalled();
    expect(toast).toHaveBeenCalledWith("알림이 재활성화되었습니다", "success");
  });

  it("deleteMutation 성공 시 invalidateFn을 호출한다", async () => {
    const invalidateFn = vi.fn();
    const deleteFn = vi.fn().mockResolvedValue(undefined);

    const { result } = renderHook(
      () =>
        useAlertCrud({
          queryKey: ["coverage-alerts-3"],
          queryFn: vi.fn().mockResolvedValue([]),
          reactivateFn: vi.fn(),
          deleteFn,
          invalidateFn,
        }),
      { wrapper: createWrapper() },
    );

    await act(async () => {
      await result.current.deleteMutation.mutateAsync("alert-1");
    });

    expect(deleteFn.mock.calls[0][0]).toBe("alert-1");
    expect(invalidateFn).toHaveBeenCalled();
  });

  it("reactivateMutation 실패 시 toast를 에러로 호출한다", async () => {
    const { toast } = await import("@/utils/toast");
    const reactivateFn = vi.fn().mockRejectedValue(new Error("서버 오류"));

    const { result } = renderHook(
      () =>
        useAlertCrud({
          queryKey: ["coverage-alerts-4"],
          queryFn: vi.fn().mockResolvedValue([]),
          reactivateFn,
          deleteFn: vi.fn(),
          invalidateFn: vi.fn(),
        }),
      { wrapper: createWrapper() },
    );

    await act(async () => {
      try {
        await result.current.reactivateMutation.mutateAsync("alert-1");
      } catch {
        // expected: mutation throws on error, toast assertion follows
      }
    });

    expect(toast).toHaveBeenCalledWith(expect.any(String), "error");
  });
});

// ─── useAnalysisState ────────────────────────────────────────────────────────

describe("useAnalysisState", () => {
  beforeEach(() => vi.clearAllMocks());

  it("초기 상태는 모두 null/false다", () => {
    const { result } = renderHook(() => useAnalysisState({ selectedIdStr: "" }));
    expect(result.current.mode).toBeNull();
    expect(result.current.analysis).toBeNull();
    expect(result.current.analyzing).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("setMode('strategy')가 mode를 설정한다", () => {
    const { result } = renderHook(() => useAnalysisState({ selectedIdStr: "1" }));
    act(() => {
      result.current.setMode("strategy");
    });
    expect(result.current.mode).toBe("strategy");
  });

  it("setMode('rebalancing')가 mode를 설정한다", () => {
    const { result } = renderHook(() => useAnalysisState({ selectedIdStr: "1" }));
    act(() => {
      result.current.setMode("rebalancing");
    });
    expect(result.current.mode).toBe("rebalancing");
    expect(result.current.analysis).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it("triggerRebalancingAnalysis 성공 시 analysis가 설정된다", async () => {
    const { analyzePortfolio } = await import("@/api/rebalancing");
    const mockAnalysis = { portfolio_id: 1, items: [], drift_pct: 5 };
    vi.mocked(analyzePortfolio).mockResolvedValue(mockAnalysis as never);

    const { result } = renderHook(() => useAnalysisState({ selectedIdStr: "1" }));

    await act(async () => {
      await result.current.triggerRebalancingAnalysis("1");
    });

    expect(result.current.analysis).toEqual(mockAnalysis);
    expect(result.current.analyzing).toBe(false);
    expect(result.current.mode).toBe("rebalancing");
  });

  it("triggerRebalancingAnalysis 실패 시 error가 설정된다", async () => {
    const { analyzePortfolio } = await import("@/api/rebalancing");
    vi.mocked(analyzePortfolio).mockRejectedValue(new Error("분석 실패"));

    const { result } = renderHook(() => useAnalysisState({ selectedIdStr: "1" }));

    await act(async () => {
      await result.current.triggerRebalancingAnalysis("1");
    });

    expect(result.current.error).toBe("분석 실패");
    expect(result.current.analyzing).toBe(false);
  });

  it("selectedIdStr 변경으로 다중 선택이 되면 mode가 null로 리셋된다", () => {
    const { result, rerender } = renderHook(
      ({ selectedIdStr }: { selectedIdStr: string }) =>
        useAnalysisState({ selectedIdStr }),
      { initialProps: { selectedIdStr: "1" } },
    );

    act(() => {
      result.current.setMode("strategy");
    });
    expect(result.current.mode).toBe("strategy");

    rerender({ selectedIdStr: "1,2" });
    expect(result.current.mode).toBeNull();
  });
});

// ─── useAnalysisState — autoAnalyzeId & rebalancing ID reset (additional) ────

describe("useAnalysisState — additional coverage", () => {
  beforeEach(() => vi.clearAllMocks());

  it("autoAnalyzeId와 selectedIdStr이 일치하면 자동 분석이 트리거된다", async () => {
    const { analyzePortfolio } = await import("@/api/rebalancing");
    vi.mocked(analyzePortfolio).mockResolvedValue({ portfolio_id: 5 } as never);

    const { result } = renderHook(() =>
      useAnalysisState({ autoAnalyzeId: "5", selectedIdStr: "5" }),
    );

    await waitFor(() => expect(result.current.analyzing).toBe(false));
    expect(analyzePortfolio).toHaveBeenCalledWith("5", undefined, undefined);
    expect(result.current.analysis).toBeDefined();
  });

  it("autoAnalyzeId가 없으면 자동 분석이 트리거되지 않는다", () => {
    const { result } = renderHook(() => useAnalysisState({ selectedIdStr: "5" }));
    expect(result.current.analyzing).toBe(false);
    expect(result.current.mode).toBeNull();
  });

  it("rebalancing 분석 후 selectedIdStr이 바뀌면 analysis가 리셋된다", async () => {
    const { analyzePortfolio } = await import("@/api/rebalancing");
    const mockAnalysis = { portfolio_id: 1, items: [] };
    vi.mocked(analyzePortfolio).mockResolvedValue(mockAnalysis as never);

    const { result, rerender } = renderHook(
      ({ selectedIdStr }: { selectedIdStr: string }) =>
        useAnalysisState({ selectedIdStr }),
      { initialProps: { selectedIdStr: "1" } },
    );

    await act(async () => {
      await result.current.triggerRebalancingAnalysis("1");
    });
    expect(result.current.analysis).toEqual(mockAnalysis);

    rerender({ selectedIdStr: "2" });
    expect(result.current.analysis).toBeNull();
    expect(result.current.mode).toBeNull();
  });
});

// ─── useAssetManagementData ───────────────────────────────────────────────────

describe("useAssetManagementData", () => {
  beforeEach(() => vi.clearAllMocks());

  it("로딩 중 isLoading이 true다", () => {
    vi.mocked(api.get).mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useAssetManagementData("은행계좌"), {
      wrapper: createWrapper(),
    });
    expect(result.current.isLoading).toBe(true);
  });

  it("accounts 데이터를 반환한다", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [{ id: "acc-1", name: "내 계좌" }] });
    const { result } = renderHook(() => useAssetManagementData("은행계좌"), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.accounts).toHaveLength(1);
    expect(result.current.accounts[0].id).toBe("acc-1");
  });

  it("usdRate를 ExchangeRateContext에서 제공받는다", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] });
    const { result } = renderHook(() => useAssetManagementData("은행계좌"), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.usdRate).toBe(1350);
  });

  it("증권계좌 탭에서는 overview와 allTx도 조회한다", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] });
    const { result } = renderHook(() => useAssetManagementData("증권계좌"), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.allTx).toBeDefined();
  });
});

// ─── executionReducer — missing action types ──────────────────────────────────

const baseReducerState: ExecutionState = {
  liveBalances: {},
  balanceState: {},
  depositKrw: {},
  orderableKrw: {},
  priceState: "idle",
  priceLoadProgress: { loaded: 0, total: 0 },
  livePricesKrw: {},
  livePricesUsd: {},
  globalUsdRate: null,
  orderType: "MARKET",
  strategy: "FULL",
  limitPriceOverrides: {},
  qtyOverrides: {},
  buyAccounts: {},
  selected: new Set(),
  phase: "confirm",
  results: [],
  errorMsg: null,
  confirmed: false,
};

describe("executionReducer — missing actions", () => {
  it("SET_LIMIT_PRICE — 가격 오버라이드를 설정한다", () => {
    const result = executionReducer(baseReducerState, {
      type: "SET_LIMIT_PRICE",
      key: "buy_005930_acc1",
      price: 75000,
    });
    expect(result.limitPriceOverrides["buy_005930_acc1"]).toBe(75000);
  });

  it("SET_LIMIT_PRICE — 음수 가격은 0으로 클램프된다", () => {
    const result = executionReducer(baseReducerState, {
      type: "SET_LIMIT_PRICE",
      key: "sell_005930_acc1",
      price: -1000,
    });
    expect(result.limitPriceOverrides["sell_005930_acc1"]).toBe(0);
  });

  it("UNCONFIRM — confirmed를 false로 설정한다", () => {
    const state = { ...baseReducerState, confirmed: true };
    const result = executionReducer(state, { type: "UNCONFIRM" });
    expect(result.confirmed).toBe(false);
  });

  it("BULK_SET_QTY — 여러 항목의 수량을 한 번에 설정한다", () => {
    const result = executionReducer(baseReducerState, {
      type: "BULK_SET_QTY",
      entries: [
        { key: "buy_005930_acc1", qty: 5 },
        { key: "buy_000660_acc1", qty: 3 },
      ],
    });
    expect(result.qtyOverrides["buy_005930_acc1"]).toBe(5);
    expect(result.qtyOverrides["buy_000660_acc1"]).toBe(3);
  });

  it("BULK_SET_QTY — qty<=0이면 selected에서 제거한다", () => {
    const state = {
      ...baseReducerState,
      selected: new Set(["buy_005930_acc1"]),
      qtyOverrides: { "buy_005930_acc1": 5 },
    };
    const result = executionReducer(state, {
      type: "BULK_SET_QTY",
      entries: [{ key: "buy_005930_acc1", qty: 0 }],
    });
    expect(result.selected.has("buy_005930_acc1")).toBe(false);
    expect(result.qtyOverrides["buy_005930_acc1"]).toBe(0);
  });

  it("unknown action — 상태를 그대로 반환한다 (default case)", () => {
    executionReducer(baseReducerState, { type: "CONFIRM_CLICK" });
    // CONFIRM_CLICK IS a valid action, just use a trick to test default:
    // Pass a genuinely unknown action type via type assertion
    const unknownResult = executionReducer(baseReducerState, { type: "UNKNOWN" } as never);
    expect(unknownResult).toBe(baseReducerState);
  });
});

// ─── useAccountMutations ──────────────────────────────────────────────────────

const mockCallbacks = {
  onBankModalClose: vi.fn(),
  onStockModalClose: vi.fn(),
  onEditBankClose: vi.fn(),
  onEditRealEstateClose: vi.fn(),
  onEditStockClose: vi.fn(),
};

describe("useAccountMutations", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.delete).mockResolvedValue({ data: undefined });
    vi.mocked(api.post).mockResolvedValue({ data: {} });
    vi.mocked(api.put).mockResolvedValue({ data: {} });
  });

  it("초기 상태를 반환한다", () => {
    const { result } = renderHook(() => useAccountMutations(mockCallbacks), {
      wrapper: createWrapper(),
    });
    expect(result.current.deletingId).toBeNull();
    expect(result.current.syncingBankId).toBeNull();
    expect(result.current.syncingStockIds.size).toBe(0);
  });

  it("deleteMutation 성공 시 toast를 호출한다", async () => {
    const { toast } = await import("@/utils/toast");

    const { result } = renderHook(() => useAccountMutations(mockCallbacks), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await result.current.deleteMutation.mutateAsync("acc-1" as never);
    });

    expect(toast).toHaveBeenCalledWith("계좌가 삭제되었습니다", "success");
  });

  it("handleSyncBank 성공 시 toast를 호출한다", async () => {
    const { toast } = await import("@/utils/toast");
    vi.mocked(api.post).mockResolvedValue({ data: { synced: true } });

    const { result } = renderHook(() => useAccountMutations(mockCallbacks), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await result.current.handleSyncBank("acc-1");
    });

    expect(toast).toHaveBeenCalledWith("동기화 완료", "success");
    expect(result.current.syncingBankId).toBeNull();
  });

  it("handleSyncBank 실패 시 에러 toast를 호출한다", async () => {
    const { toast } = await import("@/utils/toast");
    vi.mocked(api.post).mockRejectedValue(new Error("sync failed"));

    const { result } = renderHook(() => useAccountMutations(mockCallbacks), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await result.current.handleSyncBank("acc-1");
    });

    expect(toast).toHaveBeenCalledWith("동기화에 실패했습니다");
    expect(result.current.syncingBankId).toBeNull();
  });

  it("createMutation 성공 시 (MANUAL) toast와 onBankModalClose를 호출한다", async () => {
    const { toast } = await import("@/utils/toast");
    vi.mocked(api.post).mockResolvedValue({ data: { id: "acc-1", data_source: "MANUAL", name: "test" } });

    const { result } = renderHook(() => useAccountMutations(mockCallbacks), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await result.current.createMutation.mutateAsync({ name: "test", asset_type: "BANK_ACCOUNT" } as never);
    });

    expect(toast).toHaveBeenCalledWith("계좌가 추가되었습니다", "success");
    expect(mockCallbacks.onBankModalClose).toHaveBeenCalled();
  });

  it("createMutation 성공 시 (KIS_API) syncAccount를 호출한다", async () => {
    const { toast } = await import("@/utils/toast");
    vi.mocked(api.post)
      .mockResolvedValueOnce({ data: { id: "acc-1", data_source: "KIS_API", name: "KIS" } })
      .mockResolvedValueOnce({ data: {} });

    const { result } = renderHook(() => useAccountMutations(mockCallbacks), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await result.current.createMutation.mutateAsync({ name: "KIS", asset_type: "STOCK_KIS" } as never);
    });

    expect(toast).toHaveBeenCalledWith("계좌가 추가되었습니다", "success");
  });

  it("createMutation KIS_API sync 실패 시 에러 toast를 호출한다", async () => {
    const { toast } = await import("@/utils/toast");
    vi.mocked(api.post)
      .mockResolvedValueOnce({ data: { id: "acc-1", data_source: "KIS_API", name: "KIS" } })
      .mockRejectedValueOnce(new Error("sync error"));

    const { result } = renderHook(() => useAccountMutations(mockCallbacks), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await result.current.createMutation.mutateAsync({ name: "KIS", asset_type: "STOCK_KIS" } as never);
    });

    expect(toast).toHaveBeenCalledWith(expect.stringContaining("동기화 실패"));
  });

  it("updateBankMutation 성공 시 onEditBankClose와 toast를 호출한다", async () => {
    const { toast } = await import("@/utils/toast");
    vi.mocked(api.put).mockResolvedValue({ data: { id: "acc-1", name: "updated" } });

    const { result } = renderHook(() => useAccountMutations(mockCallbacks), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await result.current.updateBankMutation.mutateAsync({
        id: "acc-1",
        data: { name: "updated" },
      } as never);
    });

    expect(toast).toHaveBeenCalledWith("저장되었습니다", "success");
    expect(mockCallbacks.onEditBankClose).toHaveBeenCalled();
  });

  it("updateDepositMutation 성공 시 toast를 호출한다", async () => {
    const { toast } = await import("@/utils/toast");
    vi.mocked(api.put).mockResolvedValue({ data: {} });

    const { result } = renderHook(() => useAccountMutations(mockCallbacks), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await result.current.updateDepositMutation.mutateAsync({
        id: "acc-1",
        deposit_krw: 500000,
      } as never);
    });

    expect(toast).toHaveBeenCalledWith("예수금이 업데이트되었습니다", "success");
  });

  it("updateNameMutation 성공 시 toast를 호출한다", async () => {
    const { toast } = await import("@/utils/toast");
    vi.mocked(api.put).mockResolvedValue({ data: {} });

    const { result } = renderHook(() => useAccountMutations(mockCallbacks), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await result.current.updateNameMutation.mutateAsync({ id: "acc-1", name: "새 이름" } as never);
    });

    expect(toast).toHaveBeenCalledWith("계좌명이 저장되었습니다", "success");
  });

  it("handleSyncKisAccount 성공 시 toast를 호출한다", async () => {
    const { toast } = await import("@/utils/toast");
    vi.mocked(api.post).mockResolvedValue({ data: {} });

    const { result } = renderHook(() => useAccountMutations(mockCallbacks), {
      wrapper: createWrapper(),
    });

    const accounts = [{ id: "acc-1", asset_type: "STOCK_KIS", is_active: true }] as never[];

    await act(async () => {
      await result.current.handleSyncKisAccount("acc-1", accounts);
    });

    expect(toast).toHaveBeenCalledWith("동기화 완료", "success");
  });

  it("handleSyncKisAccount 실패 시 broker별 에러 toast를 호출한다 (KIS)", async () => {
    const { toast } = await import("@/utils/toast");
    vi.mocked(api.post).mockRejectedValue(new Error("sync error"));

    const { result } = renderHook(() => useAccountMutations(mockCallbacks), {
      wrapper: createWrapper(),
    });

    const accounts = [{ id: "acc-1", asset_type: "STOCK_KIS", is_active: true }] as never[];

    await act(async () => {
      await result.current.handleSyncKisAccount("acc-1", accounts);
    });

    expect(toast).toHaveBeenCalledWith(expect.stringContaining("KIS"));
  });

  it("handleSyncKisAccount 실패 시 broker별 에러 toast를 호출한다 (키움)", async () => {
    const { toast } = await import("@/utils/toast");
    vi.mocked(api.post).mockRejectedValue(new Error("sync error"));

    const { result } = renderHook(() => useAccountMutations(mockCallbacks), {
      wrapper: createWrapper(),
    });

    const accounts = [{ id: "acc-1", asset_type: "STOCK_KIWOOM", is_active: true }] as never[];

    await act(async () => {
      await result.current.handleSyncKisAccount("acc-1", accounts);
    });

    expect(toast).toHaveBeenCalledWith(expect.stringContaining("키움"));
  });
});
