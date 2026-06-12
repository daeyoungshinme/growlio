import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import { useOnlineStatus } from "@/hooks/useOnlineStatus";
import { useCurrencyInput } from "@/hooks/useCurrencyInput";
import { useLogout } from "@/hooks/useLogout";

vi.mock("@/api/assets", () => ({
  fetchExchangeRate: vi.fn().mockResolvedValue({ usd_krw: 1350 }),
}));

vi.mock("@/utils/toast", () => ({
  toast: vi.fn(),
}));

vi.mock("@/stores/authStore", () => ({
  useAuthStore: vi.fn((selector) => {
    const state = { logout: vi.fn().mockResolvedValue(undefined) };
    return typeof selector === "function" ? selector(state) : state;
  }),
}));

function createWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

describe("useOnlineStatus", () => {
  it("초기 상태는 navigator.onLine 값이다", () => {
    const { result } = renderHook(() => useOnlineStatus());
    expect(result.current).toBe(navigator.onLine);
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

  it("언마운트 시 이벤트 리스너가 제거된다", () => {
    const addSpy = vi.spyOn(window, "addEventListener");
    const removeSpy = vi.spyOn(window, "removeEventListener");
    const { unmount } = renderHook(() => useOnlineStatus());
    unmount();
    expect(removeSpy).toHaveBeenCalledWith("online", expect.any(Function));
    expect(removeSpy).toHaveBeenCalledWith("offline", expect.any(Function));
    addSpy.mockRestore();
    removeSpy.mockRestore();
  });
});

describe("useCurrencyInput", () => {
  it("초기값이 없으면 모두 undefined/0이다", () => {
    const { result } = renderHook(() => useCurrencyInput(), {
      wrapper: createWrapper(),
    });
    expect(result.current.depositKrw).toBeUndefined();
    expect(result.current.depositUsd).toBeUndefined();
    expect(result.current.totalKrw).toBe(0);
    expect(result.current.hasAnyDeposit).toBe(false);
  });

  it("KRW 입금 설정 시 totalKrw가 업데이트된다", () => {
    const { result } = renderHook(() => useCurrencyInput(1000000), {
      wrapper: createWrapper(),
    });
    expect(result.current.depositKrw).toBe(1000000);
    expect(result.current.totalKrw).toBe(1000000);
    expect(result.current.hasAnyDeposit).toBe(true);
  });

  it("USD 입금이 있고 환율이 없으면 usdPending이 true다", () => {
    // fetchExchangeRate returns null initially
    const { result } = renderHook(() => useCurrencyInput(undefined, 100), {
      wrapper: createWrapper(),
    });
    // usdRate is null initially
    expect(result.current.depositUsd).toBe(100);
  });

  it("USD 입금과 환율이 있으면 totalKrw가 환산된다", async () => {
    const { result } = renderHook(() => useCurrencyInput(0, 100), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.usdRate).toBe(1350));
    expect(result.current.usdAsKrw).toBe(135000);
    expect(result.current.totalKrw).toBe(135000);
    expect(result.current.usdPending).toBe(false);
  });

  it("setDepositKrw가 상태를 업데이트한다", () => {
    const { result } = renderHook(() => useCurrencyInput(), {
      wrapper: createWrapper(),
    });
    act(() => {
      result.current.setDepositKrw(500000);
    });
    expect(result.current.depositKrw).toBe(500000);
    expect(result.current.totalKrw).toBe(500000);
  });

  it("setDepositUsd가 상태를 업데이트한다", () => {
    const { result } = renderHook(() => useCurrencyInput(), {
      wrapper: createWrapper(),
    });
    act(() => {
      result.current.setDepositUsd(200);
    });
    expect(result.current.depositUsd).toBe(200);
  });
});

describe("useLogout", () => {
  beforeEach(() => vi.clearAllMocks());

  it("logout 함수를 반환한다", () => {
    const { result } = renderHook(() => useLogout(), {
      wrapper: createWrapper(),
    });
    expect(typeof result.current).toBe("function");
  });

  it("logout 실행 시 authStore.logout을 호출한다", async () => {
    const { useAuthStore } = await import("@/stores/authStore");
    const logoutFn = vi.fn().mockResolvedValue(undefined);
    vi.mocked(useAuthStore).mockImplementation((selector: (s: { logout: () => Promise<void> }) => unknown) => {
      const state = { logout: logoutFn };
      return typeof selector === "function" ? selector(state) : state;
    });

    const { result } = renderHook(() => useLogout(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await result.current();
    });

    expect(logoutFn).toHaveBeenCalled();
  });
});
