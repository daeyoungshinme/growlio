import { act, renderHook } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { numberFieldPayload } from "@/hooks/useEditableSettingsForm";

vi.mock("@/api/settings", () => ({
  fetchSettings: vi.fn(),
  updateGoalSettings: vi.fn().mockResolvedValue(undefined),
}));

vi.mock("@/utils/toast", () => ({ toast: vi.fn() }));

vi.mock("@/utils/queryInvalidation", () => ({
  invalidateDcaData: vi.fn().mockResolvedValue(undefined),
  invalidateGoalRecommendationData: vi.fn().mockResolvedValue(undefined),
}));

function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

describe("numberFieldPayload", () => {
  it("값이 있으면 숫자", () => {
    expect(numberFieldPayload("1200", "")).toBe(1200);
  });

  it("원래 있던 값을 지우면 null(백엔드가 비움)", () => {
    expect(numberFieldPayload("", "1200")).toBeNull();
  });

  it("처음부터 비어 있었으면 undefined(키 생략 → 기존 값 유지)", () => {
    expect(numberFieldPayload("", "")).toBeUndefined();
    expect(numberFieldPayload("", undefined)).toBeUndefined();
  });
});

describe("useDividendPlanSettings 저장", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("배당 목표를 지우고 저장하면 null을 보내고, 목표 카드·추천까지 무효화한다", async () => {
    const { fetchSettings, updateGoalSettings } = await import("@/api/settings");
    const { invalidateDcaData, invalidateGoalRecommendationData } =
      await import("@/utils/queryInvalidation");
    vi.mocked(fetchSettings).mockResolvedValueOnce({ annual_dividend_goal: 12000000 } as never);
    const { useDividendPlanSettings } = await import("@/hooks/useDividendPlanSettings");
    const { result } = renderHook(() => useDividendPlanSettings(), { wrapper: createWrapper() });

    await act(async () => {
      await result.current.openEdit();
    });
    act(() => {
      result.current.setForm({ annual_dividend_goal: "" });
    });
    await act(async () => {
      await result.current.saveSettings();
    });

    expect(updateGoalSettings).toHaveBeenCalledWith({ annual_dividend_goal: null });
    expect(invalidateDcaData).toHaveBeenCalled();
    expect(invalidateGoalRecommendationData).toHaveBeenCalled();
  });

  it("처음부터 비어 있던 배당 목표는 키를 보내지 않는다", async () => {
    const { fetchSettings, updateGoalSettings } = await import("@/api/settings");
    vi.mocked(fetchSettings).mockResolvedValueOnce({ annual_dividend_goal: null } as never);
    const { useDividendPlanSettings } = await import("@/hooks/useDividendPlanSettings");
    const { result } = renderHook(() => useDividendPlanSettings(), { wrapper: createWrapper() });

    await act(async () => {
      await result.current.openEdit();
    });
    await act(async () => {
      await result.current.saveSettings();
    });

    expect(updateGoalSettings).toHaveBeenCalledWith({ annual_dividend_goal: undefined });
  });
});
