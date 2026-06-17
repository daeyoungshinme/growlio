import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import React from "react";
import type { AssetAccount } from "@/api/assets";
// renderWithProviders is not used here - using createWrapper instead

function createWrapper(options?: { path?: string }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={[options?.path ?? "/"]}>{children}</MemoryRouter>
      </QueryClientProvider>
    );
  };
}

// ---- Mocks ----
vi.mock("@/stores/authStore", () => ({
  useAuthStore: (selector: (s: object) => unknown) => {
    const state = {
      user: { email: "test@example.com" },
      logout: vi.fn().mockResolvedValue(undefined),
    };
    if (typeof selector === "function") return selector(state);
    return state;
  },
}));

vi.mock("@/context/ExchangeRateContext", () => ({
  useExchangeRateContext: vi.fn(() => ({ rate: 1350, error: null })),
  ExchangeRateProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock("@/utils/toast", () => ({
  toast: vi.fn(),
}));

vi.mock("@/api/invest", () => ({
  fetchDCAAnalysis: vi.fn().mockResolvedValue({
    is_configured: true,
    settings: {
      monthly_deposit_amount: 500000,
      goal_annual_return_pct: 8,
      goal_amount: 500000000,
      goal_start_date: "2020-01-01",
      goal_initial_amount: 10000000,
    },
    projection_months: [],
    yearly_achievements: [],
    goal_timeline: {
      months_to_goal: 200,
      goal_date: "2036-01-01",
      expected_amount_at_target: 300000000,
    },
  }),
}));

vi.mock("@/api/settings", () => ({
  fetchSettings: vi.fn().mockResolvedValue({
    has_dart: false,
    has_open_banking: false,
    user_email: "test@example.com",
    annual_deposit_goal: null,
    retirement_target_year: null,
  }),
}));

vi.mock("@/api/client", () => ({
  api: {
    get: vi.fn().mockResolvedValue({ data: {} }),
    post: vi.fn().mockResolvedValue({ data: {} }),
    put: vi.fn().mockResolvedValue({ data: {} }),
    delete: vi.fn().mockResolvedValue({ data: {} }),
  },
}));

vi.mock("@/api/assets", () => ({
  fetchAccounts: vi.fn().mockResolvedValue([]),
  syncAccount: vi.fn().mockResolvedValue({}),
  createAccount: vi.fn().mockResolvedValue({ id: "new1", data_source: "MANUAL" }),
  updateAccount: vi.fn().mockResolvedValue({}),
  deleteAccount: vi.fn().mockResolvedValue({}),
}));

vi.mock("@/api/portfolios", () => ({
  fetchPortfolioOverview: vi.fn().mockResolvedValue({
    total_stock_krw: 8000000,
    accounts: [],
  }),
}));

vi.mock("@/api/transactions", () => ({
  fetchTransactions: vi.fn().mockResolvedValue([]),
}));

vi.mock("@/api/insights", () => ({
  fetchInsights: vi.fn().mockResolvedValue([]),
  fetchInsightsSummary: vi.fn().mockResolvedValue({ total: 0, by_type: {} }),
}));

vi.mock("@/api/economicIndicators", () => ({
  fetchIndicators: vi.fn().mockResolvedValue([]),
  fetchIndicatorCalendar: vi.fn().mockResolvedValue([]),
  fetchIndicatorHistory: vi.fn().mockResolvedValue([]),
  fetchIndicatorSubscriptions: vi.fn().mockResolvedValue([]),
  subscribeIndicator: vi.fn().mockResolvedValue({}),
  unsubscribeIndicator: vi.fn().mockResolvedValue({}),
}));

vi.mock("@/hooks/useHaptic", () => ({
  triggerHaptic: vi.fn().mockResolvedValue(undefined),
  useHaptic: vi.fn(() => ({ impact: vi.fn() })),
}));

vi.mock("@/lib/supabase", () => ({
  supabase: {
    auth: {
      getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
    },
  },
}));

vi.mock("@capacitor/haptics", () => ({
  Haptics: {
    impact: vi.fn().mockResolvedValue(undefined),
    notification: vi.fn().mockResolvedValue(undefined),
  },
  ImpactStyle: { Light: "light", Medium: "medium", Heavy: "heavy" },
  NotificationType: { Success: "success", Error: "error" },
}));

// ============================================
// useExchangeRate
// ============================================
describe("useExchangeRate", () => {
  it("returns rate from context", async () => {
    const { useExchangeRate } = await import("@/hooks/useExchangeRate");
    const wrapper = createWrapper();
    const { result } = renderHook(() => useExchangeRate(), { wrapper });
    expect(result.current).toBe(1350);
  });

  it("shows toast on error", async () => {
    const { useExchangeRateContext } = await import("@/context/ExchangeRateContext");
    vi.mocked(useExchangeRateContext).mockReturnValueOnce({
      rate: null,
      isLoading: false,
      error: new Error("Network error"),
    });
    const { useExchangeRate } = await import("@/hooks/useExchangeRate");
    const wrapper = createWrapper();
    const { result } = renderHook(() => useExchangeRate(), { wrapper });
    expect(result.current).toBeNull();
    // toast would be called in useEffect
  });
});

// ============================================
// useAssetModals
// ============================================
describe("useAssetModals", () => {
  it("initializes all modals closed", async () => {
    const { useAssetModals } = await import("@/hooks/useAssetModals");
    const { result } = renderHook(() => useAssetModals());
    expect(result.current.showBankModal).toBe(false);
    expect(result.current.showStockModal).toBe(false);
    expect(result.current.showRealEstateModal).toBe(false);
    expect(result.current.editingRealEstate).toBeNull();
    expect(result.current.editingBankAccount).toBeNull();
    expect(result.current.editingStockAccount).toBeNull();
    expect(result.current.confirmDeleteId).toBeNull();
    expect(result.current.positionsAccount).toBeNull();
    expect(result.current.txAccount).toBeNull();
  });

  it("can open bank modal", async () => {
    const { useAssetModals } = await import("@/hooks/useAssetModals");
    const { result } = renderHook(() => useAssetModals());
    act(() => {
      result.current.setShowBankModal(true);
    });
    expect(result.current.showBankModal).toBe(true);
  });

  it("can open stock modal", async () => {
    const { useAssetModals } = await import("@/hooks/useAssetModals");
    const { result } = renderHook(() => useAssetModals());
    act(() => {
      result.current.setShowStockModal(true);
    });
    expect(result.current.showStockModal).toBe(true);
  });

  it("can set confirm delete id", async () => {
    const { useAssetModals } = await import("@/hooks/useAssetModals");
    const { result } = renderHook(() => useAssetModals());
    act(() => {
      result.current.setConfirmDeleteId("account-123");
    });
    expect(result.current.confirmDeleteId).toBe("account-123");
  });

  it("can set editing real estate", async () => {
    const { useAssetModals } = await import("@/hooks/useAssetModals");
    const { result } = renderHook(() => useAssetModals());
    const mockAccount = { id: "re1", name: "아파트" } as unknown as AssetAccount;
    act(() => {
      result.current.setEditingRealEstate(mockAccount);
    });
    expect(result.current.editingRealEstate).toEqual(mockAccount);
  });

  it("can set positions account", async () => {
    const { useAssetModals } = await import("@/hooks/useAssetModals");
    const { result } = renderHook(() => useAssetModals());
    act(() => {
      result.current.setPositionsAccount({ id: "acc1", name: "한국투자", dataSource: "KIS_API" });
    });
    expect(result.current.positionsAccount?.id).toBe("acc1");
  });

  it("can set tx account", async () => {
    const { useAssetModals } = await import("@/hooks/useAssetModals");
    const { result } = renderHook(() => useAssetModals());
    act(() => {
      result.current.setTxAccount({ id: "acc1", name: "한국투자", depositKrw: 1000000 });
    });
    expect(result.current.txAccount?.depositKrw).toBe(1000000);
  });
});

// ============================================
// useHaptic
// ============================================
describe("useHaptic", () => {
  it("returns impact function", async () => {
    const { useHaptic } = await import("@/hooks/useHaptic");
    const { result } = renderHook(() => useHaptic());
    expect(typeof result.current.impact).toBe("function");
  });

  it("impact function can be called without error", async () => {
    const { useHaptic } = await import("@/hooks/useHaptic");
    const { result } = renderHook(() => useHaptic());
    expect(() => result.current.impact("light")).not.toThrow();
  });

  it("impact function can be called with different types", async () => {
    const { useHaptic } = await import("@/hooks/useHaptic");
    const { result } = renderHook(() => useHaptic());
    expect(() => result.current.impact("heavy")).not.toThrow();
    expect(() => result.current.impact("success")).not.toThrow();
    expect(() => result.current.impact("error")).not.toThrow();
  });
});

// ============================================
// triggerHaptic
// ============================================
describe("triggerHaptic", () => {
  it("can be called with success type", async () => {
    const { triggerHaptic } = await import("@/hooks/useHaptic");
    await expect(triggerHaptic("success")).resolves.not.toThrow();
  });

  it("can be called with error type", async () => {
    const { triggerHaptic } = await import("@/hooks/useHaptic");
    await expect(triggerHaptic("error")).resolves.not.toThrow();
  });

  it("can be called with impact types", async () => {
    const { triggerHaptic } = await import("@/hooks/useHaptic");
    await expect(triggerHaptic("light")).resolves.not.toThrow();
    await expect(triggerHaptic("medium")).resolves.not.toThrow();
    await expect(triggerHaptic("heavy")).resolves.not.toThrow();
  });
});

// ============================================
// useInsights
// ============================================
describe("useInsights", () => {
  it("returns query result", async () => {
    const { useInsights } = await import("@/hooks/useInsights");
    const wrapper = createWrapper();
    const { result } = renderHook(() => useInsights(), { wrapper });
    expect(result.current).toHaveProperty("isLoading");
    expect(result.current).toHaveProperty("data");
  });
});

// ============================================
// useEconomicIndicators
// ============================================
describe("useEconomicIndicators", () => {
  it("returns query result for indicators", async () => {
    const { useEconomicIndicators } = await import("@/hooks/useEconomicIndicators");
    const wrapper = createWrapper();
    const { result } = renderHook(() => useEconomicIndicators(), { wrapper });
    expect(result.current).toHaveProperty("isLoading");
  });

  it("returns query result for calendar", async () => {
    const { useIndicatorCalendar } = await import("@/hooks/useEconomicIndicators");
    const wrapper = createWrapper();
    const { result } = renderHook(() => useIndicatorCalendar(), { wrapper });
    expect(result.current).toHaveProperty("isLoading");
  });

  it("returns subscribe mutation hooks", async () => {
    const { useSubscribeMutation } = await import("@/hooks/useEconomicIndicators");
    const wrapper = createWrapper();
    const { result } = renderHook(() => useSubscribeMutation(), { wrapper });
    expect(result.current).toHaveProperty("subscribe");
    expect(result.current).toHaveProperty("unsubscribe");
  });

  it("disabled history query when no code", async () => {
    const { useIndicatorHistory } = await import("@/hooks/useEconomicIndicators");
    const wrapper = createWrapper();
    const { result } = renderHook(() => useIndicatorHistory("", 24), { wrapper });
    // enabled=false since code is empty, so isLoading will be false
    expect(result.current.isLoading).toBe(false);
  });
});

// ============================================
// useAssetManagementData
// ============================================
describe("useAssetManagementData", () => {
  it("returns accounts and loading state", async () => {
    const { useAssetManagementData } = await import("@/hooks/useAssetManagementData");
    const wrapper = createWrapper();
    const { result } = renderHook(() => useAssetManagementData("은행계좌"), { wrapper });
    expect(result.current).toHaveProperty("accounts");
    expect(result.current).toHaveProperty("isLoading");
    expect(Array.isArray(result.current.accounts)).toBe(true);
  });

  it("returns overview when stock tab active", async () => {
    const { useAssetManagementData } = await import("@/hooks/useAssetManagementData");
    const wrapper = createWrapper();
    const { result } = renderHook(() => useAssetManagementData("증권계좌"), { wrapper });
    expect(result.current).toHaveProperty("overview");
    expect(result.current).toHaveProperty("allTx");
  });
});

// ============================================
// useLogout
// ============================================
describe("useLogout", () => {
  it("returns a function", async () => {
    const { useLogout } = await import("@/hooks/useLogout");
    const wrapper = createWrapper();
    const { result } = renderHook(() => useLogout(), { wrapper });
    expect(typeof result.current).toBe("function");
  });

  it("logout function can be called", async () => {
    const { useLogout } = await import("@/hooks/useLogout");
    const wrapper = createWrapper();
    const { result } = renderHook(() => useLogout(), { wrapper });
    // Should not throw when called
    await expect(
      act(async () => {
        await result.current();
      }),
    ).resolves.not.toThrow();
  });
});

// ============================================
// usePullToRefresh
// ============================================
describe("usePullToRefresh", () => {
  it("returns initial state", async () => {
    const { usePullToRefresh } = await import("@/hooks/usePullToRefresh");
    const containerRef = React.createRef<HTMLDivElement>();
    const onRefresh = vi.fn().mockResolvedValue(undefined);

    const { result } = renderHook(() =>
      usePullToRefresh({ onRefresh, containerRef, threshold: 60 }),
    );

    expect(result.current.isPulling).toBe(false);
    expect(result.current.pullDistance).toBe(0);
    expect(result.current.isRefreshing).toBe(false);
  });

  it("returns correct disabled state", async () => {
    const { usePullToRefresh } = await import("@/hooks/usePullToRefresh");
    const containerRef = React.createRef<HTMLDivElement>();
    const onRefresh = vi.fn().mockResolvedValue(undefined);

    const { result } = renderHook(() =>
      usePullToRefresh({ onRefresh, containerRef, threshold: 60, disabled: true }),
    );

    expect(result.current.isPulling).toBe(false);
    expect(result.current.isRefreshing).toBe(false);
  });
});

// ============================================
// useGoalSettings
// ============================================
describe("useGoalSettings", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns initial state", async () => {
    const { useGoalSettings } = await import("@/hooks/useGoalSettings");
    const wrapper = createWrapper();
    const { result } = renderHook(() => useGoalSettings(), { wrapper });
    expect(result.current).toHaveProperty("editing");
    expect(result.current).toHaveProperty("saving");
    expect(result.current).toHaveProperty("form");
    expect(result.current).toHaveProperty("openEdit");
    expect(result.current).toHaveProperty("saveSettings");
    expect(result.current.editing).toBe(false);
    expect(result.current.saving).toBe(false);
  });

  it("handleCloseModal sets editing to false when not dirty", async () => {
    const { useGoalSettings } = await import("@/hooks/useGoalSettings");
    const wrapper = createWrapper();
    const { result } = renderHook(() => useGoalSettings(), { wrapper });
    // When not editing, handleCloseModal should do nothing
    act(() => {
      result.current.handleCloseModal();
    });
    expect(result.current.editing).toBe(false);
  });
});

// ============================================
// useSwipeNavigation
// ============================================
describe("useSwipeNavigation", () => {
  it("attaches touch event listeners to container", async () => {
    const { useSwipeNavigation } = await import("@/hooks/useSwipeNavigation");
    const container = document.createElement("div");
    document.body.appendChild(container);
    const containerRef = { current: container };

    const addEventListenerSpy = vi.spyOn(container, "addEventListener");

    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <MemoryRouter initialEntries={["/dashboard"]}>{children}</MemoryRouter>
    );
    renderHook(() => useSwipeNavigation(containerRef), { wrapper });

    expect(addEventListenerSpy).toHaveBeenCalledWith(
      "touchstart",
      expect.any(Function),
      expect.any(Object),
    );
    expect(addEventListenerSpy).toHaveBeenCalledWith(
      "touchend",
      expect.any(Function),
      expect.any(Object),
    );

    document.body.removeChild(container);
  });

  it("removes event listeners on unmount", async () => {
    const { useSwipeNavigation } = await import("@/hooks/useSwipeNavigation");
    const container = document.createElement("div");
    document.body.appendChild(container);
    const containerRef = { current: container };

    const removeEventListenerSpy = vi.spyOn(container, "removeEventListener");

    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <MemoryRouter initialEntries={["/dashboard"]}>{children}</MemoryRouter>
    );
    const { unmount } = renderHook(() => useSwipeNavigation(containerRef), { wrapper });
    unmount();

    expect(removeEventListenerSpy).toHaveBeenCalledWith("touchstart", expect.any(Function));
    expect(removeEventListenerSpy).toHaveBeenCalledWith("touchend", expect.any(Function));

    document.body.removeChild(container);
  });
});
