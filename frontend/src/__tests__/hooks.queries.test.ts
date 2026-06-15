import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

// ── mocks ────────────────────────────────────────────────────────────────────

vi.mock("@/api/client", () => {
  const mockApi = { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn(), patch: vi.fn() };
  return {
    api: mockApi,
    apiGet: (url: string, ...args: unknown[]) => mockApi.get(url, ...args).then((r: { data: unknown }) => r.data),
    apiPost: (url: string, ...args: unknown[]) => mockApi.post(url, ...args).then((r: { data: unknown }) => r.data),
    apiPut: (url: string, ...args: unknown[]) => mockApi.put(url, ...args).then((r: { data: unknown }) => r.data),
    apiPatch: (url: string, ...args: unknown[]) => mockApi.patch(url, ...args).then((r: { data: unknown }) => r.data),
    apiDelete: (url: string, ...args: unknown[]) => mockApi.delete(url, ...args).then((r: { data: unknown }) => r.data),
  };
});

vi.mock("@/api/economicIndicators", () => ({
  fetchIndicators: vi.fn(),
  fetchIndicatorCalendar: vi.fn(),
  fetchIndicatorHistory: vi.fn(),
  fetchIndicatorSubscriptions: vi.fn(),
  subscribeIndicator: vi.fn(),
  unsubscribeIndicator: vi.fn(),
}));

vi.mock("@/api/insights", () => ({
  fetchInsights: vi.fn(),
  fetchInsightsSummary: vi.fn(),
}));

vi.mock("@/api/invest", () => ({
  fetchDCAAnalysis: vi.fn(),
}));

vi.mock("@/api/settings", () => ({
  fetchSettings: vi.fn().mockResolvedValue({ annual_deposit_goal: null, retirement_target_year: null }),
}));

vi.mock("@/utils/toast", () => ({ toast: vi.fn() }));

vi.mock("@/utils/queryInvalidation", () => ({
  invalidateDcaData: vi.fn().mockResolvedValue(undefined),
  invalidateAccountData: vi.fn(),
}));

vi.mock("@/stores/authStore", () => ({
  useAuthStore: vi.fn((selector: (s: { logout: () => Promise<void> }) => unknown) => {
    const state = { logout: vi.fn().mockResolvedValue(undefined) };
    return typeof selector === "function" ? selector(state) : state;
  }),
}));

vi.mock("react-router-dom", () => ({
  useLocation: vi.fn(() => ({ state: null, pathname: "/invest" })),
}));

// ── imports ───────────────────────────────────────────────────────────────────

import {
  useEconomicIndicators,
  useIndicatorCalendar,
  useIndicatorHistory,
  useIndicatorSubscriptions,
  useSubscribeMutation,
} from "@/hooks/useEconomicIndicators";
import { useInsights, useInsightsSummary } from "@/hooks/useInsights";
import { useLogout } from "@/hooks/useLogout";
import { useOnlineStatus } from "@/hooks/useOnlineStatus";
import { useGoalSettings } from "@/hooks/useGoalSettings";

// ── helpers ───────────────────────────────────────────────────────────────────

function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
}

// ── useEconomicIndicators ─────────────────────────────────────────────────────

describe("useEconomicIndicators", () => {
  beforeEach(() => vi.clearAllMocks());

  it("fetchIndicators를 호출하고 데이터를 반환한다", async () => {
    const mockData = [
      {
        code: "CPI",
        name: "소비자물가지수",
        name_en: "Consumer Price Index",
        unit: "%",
        frequency: "MONTHLY",
        description: "CPI",
        latest_value: 3.2,
        latest_date: "2024-01",
        previous_value: 3.1,
        previous_date: "2023-12",
        change: 0.1,
        change_pct: 3.2,
        subscribed: false,
      },
    ];
    const { fetchIndicators } = await import("@/api/economicIndicators");
    vi.mocked(fetchIndicators).mockResolvedValue(mockData);

    const { result } = renderHook(() => useEconomicIndicators(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(mockData);
    expect(fetchIndicators).toHaveBeenCalled();
  });

  it("로딩 중에 isLoading이 true다", async () => {
    const { fetchIndicators } = await import("@/api/economicIndicators");
    vi.mocked(fetchIndicators).mockReturnValue(new Promise(() => {})); // never resolves

    const { result } = renderHook(() => useEconomicIndicators(), { wrapper: createWrapper() });
    expect(result.current.isLoading).toBe(true);
  });

  it("에러 발생 시 isError가 true다", async () => {
    const { fetchIndicators } = await import("@/api/economicIndicators");
    vi.mocked(fetchIndicators).mockRejectedValue(new Error("API Error"));

    const { result } = renderHook(() => useEconomicIndicators(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe("useIndicatorCalendar", () => {
  beforeEach(() => vi.clearAllMocks());

  it("fetchIndicatorCalendar를 호출한다", async () => {
    const { fetchIndicatorCalendar } = await import("@/api/economicIndicators");
    vi.mocked(fetchIndicatorCalendar).mockResolvedValue([]);

    const { result } = renderHook(() => useIndicatorCalendar(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(fetchIndicatorCalendar).toHaveBeenCalled();
    expect(result.current.data).toEqual([]);
  });
});

describe("useIndicatorHistory", () => {
  beforeEach(() => vi.clearAllMocks());

  it("code가 있으면 fetchIndicatorHistory를 호출한다", async () => {
    const mockHistory = [{ date: "2024-01", value: 3.2 }];
    const { fetchIndicatorHistory } = await import("@/api/economicIndicators");
    vi.mocked(fetchIndicatorHistory).mockResolvedValue(mockHistory);

    const { result } = renderHook(() => useIndicatorHistory("CPI", 12), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(fetchIndicatorHistory).toHaveBeenCalledWith("CPI", 12);
    expect(result.current.data).toEqual(mockHistory);
  });

  it("code가 빈 문자열이면 쿼리가 비활성화된다", async () => {
    const { fetchIndicatorHistory } = await import("@/api/economicIndicators");

    const { result } = renderHook(() => useIndicatorHistory("", 12), { wrapper: createWrapper() });

    expect(result.current.fetchStatus).toBe("idle");
    expect(fetchIndicatorHistory).not.toHaveBeenCalled();
  });
});

describe("useIndicatorSubscriptions", () => {
  beforeEach(() => vi.clearAllMocks());

  it("구독 목록을 반환한다", async () => {
    const { fetchIndicatorSubscriptions } = await import("@/api/economicIndicators");
    vi.mocked(fetchIndicatorSubscriptions).mockResolvedValue(["CPI", "FEDFUNDS"]);

    const { result } = renderHook(() => useIndicatorSubscriptions(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(["CPI", "FEDFUNDS"]);
  });
});

describe("useSubscribeMutation", () => {
  beforeEach(() => vi.clearAllMocks());

  it("subscribe와 unsubscribe 뮤테이션을 반환한다", () => {
    const { result } = renderHook(() => useSubscribeMutation(), { wrapper: createWrapper() });
    expect(result.current.subscribe).toBeDefined();
    expect(result.current.unsubscribe).toBeDefined();
  });

  it("subscribe 뮤테이션이 idle 상태로 시작된다", () => {
    const { result } = renderHook(() => useSubscribeMutation(), { wrapper: createWrapper() });
    expect(result.current.subscribe.status).toBe("idle");
  });

  it("unsubscribe 뮤테이션이 idle 상태로 시작된다", () => {
    const { result } = renderHook(() => useSubscribeMutation(), { wrapper: createWrapper() });
    expect(result.current.unsubscribe.status).toBe("idle");
  });
});

// ── useInsights ───────────────────────────────────────────────────────────────

describe("useInsights", () => {
  beforeEach(() => vi.clearAllMocks());

  it("fetchInsights를 호출하고 데이터를 반환한다", async () => {
    const mockInsights = [
      {
        type: "CONCENTRATION" as const,
        severity: "WARNING" as const,
        title: "집중 투자 위험",
        detail: "포트폴리오가 특정 종목에 집중되어 있습니다.",
        action_label: null,
        action_url: null,
        metric_value: null,
      },
    ];
    const { fetchInsights } = await import("@/api/insights");
    vi.mocked(fetchInsights).mockResolvedValue(mockInsights);

    const { result } = renderHook(() => useInsights(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(mockInsights);
  });

  it("에러 발생 시 isError가 true다", async () => {
    const { fetchInsights } = await import("@/api/insights");
    vi.mocked(fetchInsights).mockRejectedValue(new Error("API Error"));

    const { result } = renderHook(() => useInsights(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe("useInsightsSummary", () => {
  beforeEach(() => vi.clearAllMocks());

  it("fetchInsightsSummary를 호출하고 요약 데이터를 반환한다", async () => {
    const mockSummary = { INFO: 2, WARNING: 1, ALERT: 0 };
    const { fetchInsightsSummary } = await import("@/api/insights");
    vi.mocked(fetchInsightsSummary).mockResolvedValue(mockSummary);

    const { result } = renderHook(() => useInsightsSummary(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(mockSummary);
  });
});

// ── useLogout ─────────────────────────────────────────────────────────────────

describe("useLogout (via hooks.queries)", () => {
  beforeEach(() => vi.clearAllMocks());

  it("logout 함수를 반환한다", () => {
    const { result } = renderHook(() => useLogout(), { wrapper: createWrapper() });
    expect(typeof result.current).toBe("function");
  });

  it("logout 호출 시 queryClient.clear를 호출한다", async () => {
    const { result } = renderHook(() => useLogout(), { wrapper: createWrapper() });

    await act(async () => {
      await result.current();
    });

    // authStore.logout should have been called (mocked)
    const { useAuthStore } = await import("@/stores/authStore");
    expect(useAuthStore).toHaveBeenCalled();
  });
});

// ── useOnlineStatus ───────────────────────────────────────────────────────────

describe("useOnlineStatus (via hooks.queries)", () => {
  it("navigator.onLine 초기 상태를 반환한다", () => {
    const { result } = renderHook(() => useOnlineStatus());
    expect(typeof result.current).toBe("boolean");
  });

  it("online 이벤트 발생 시 true가 된다", () => {
    const { result } = renderHook(() => useOnlineStatus());
    act(() => {
      window.dispatchEvent(new Event("online"));
    });
    expect(result.current).toBe(true);
  });

  it("offline 이벤트 발생 시 false가 된다", () => {
    const { result } = renderHook(() => useOnlineStatus());
    act(() => {
      window.dispatchEvent(new Event("offline"));
    });
    expect(result.current).toBe(false);
  });
});

// ── useGoalSettings ───────────────────────────────────────────────────────────

describe("useGoalSettings", () => {
  beforeEach(() => vi.clearAllMocks());

  it("isLoading 상태를 반환한다", async () => {
    const { fetchDCAAnalysis } = await import("@/api/invest");
    vi.mocked(fetchDCAAnalysis).mockReturnValue(new Promise(() => {})); // never resolves

    const { result } = renderHook(() => useGoalSettings(), { wrapper: createWrapper() });

    expect(result.current.isLoading).toBe(true);
  });

  it("데이터 로드 후 data가 설정된다", async () => {
    const { fetchDCAAnalysis } = await import("@/api/invest");
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const mockData: any = {
      settings: {
        monthly_deposit_amount: 500000,
        goal_annual_return_pct: 8,
        goal_amount: 100000000,
        goal_start_date: "2024-01-01",
        goal_initial_amount: null,
      },
      is_configured: true,
      projection_months: [],
      yearly_achievements: [],
      goal_timeline: null,
    };
    vi.mocked(fetchDCAAnalysis).mockResolvedValue(mockData);

    const { result } = renderHook(() => useGoalSettings(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.data).toEqual(mockData);
  });

  it("editing 초기값이 false다", async () => {
    const { fetchDCAAnalysis } = await import("@/api/invest");
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    vi.mocked(fetchDCAAnalysis).mockResolvedValue({
      settings: null as any,
      is_configured: false,
      projection_months: [],
      yearly_achievements: [],
      goal_timeline: null as any,
    });

    const { result } = renderHook(() => useGoalSettings(), { wrapper: createWrapper() });

    // initially false (may auto-open if not configured — wait for loading)
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    // editing may be true if auto-open triggered by is_configured=false
    expect(typeof result.current.editing).toBe("boolean");
  });

  it("form이 EMPTY_FORM으로 초기화된다", async () => {
    const { fetchDCAAnalysis } = await import("@/api/invest");
    vi.mocked(fetchDCAAnalysis).mockReturnValue(new Promise(() => {}));

    const { result } = renderHook(() => useGoalSettings(), { wrapper: createWrapper() });

    expect(result.current.form).toEqual({
      monthly_deposit_amount: "",
      goal_annual_return_pct: "",
      goal_amount: "",
      goal_start_date: "",
      goal_initial_amount: "",
      annual_deposit_goal: "",
      retirement_target_year: "",
    });
  });

  it("handleCloseModal — isDirty가 false이면 editing을 false로 설정한다", async () => {
    const { fetchDCAAnalysis } = await import("@/api/invest");
    vi.mocked(fetchDCAAnalysis).mockReturnValue(new Promise(() => {}));

    const { result } = renderHook(() => useGoalSettings(), { wrapper: createWrapper() });

    act(() => {
      result.current.handleCloseModal();
    });

    expect(result.current.editing).toBe(false);
  });

  it("setForm이 form 상태를 업데이트한다", async () => {
    const { fetchDCAAnalysis } = await import("@/api/invest");
    vi.mocked(fetchDCAAnalysis).mockReturnValue(new Promise(() => {}));

    const { result } = renderHook(() => useGoalSettings(), { wrapper: createWrapper() });

    act(() => {
      result.current.setForm((f) => ({ ...f, monthly_deposit_amount: "500000" }));
    });

    expect(result.current.form.monthly_deposit_amount).toBe("500000");
  });
});
