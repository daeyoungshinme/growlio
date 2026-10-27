import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

vi.mock("@/api/alerts", () => ({ fetchRebalancingAlerts: vi.fn() }));

import { fetchRebalancingAlerts } from "@/api/alerts";
import { useAutoExecutionNotice } from "@/hooks/useAutoExecutionNotice";

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("useAutoExecutionNotice (plans/63 P4-4)", () => {
  beforeEach(() => vi.clearAllMocks());

  it("켜진 AUTO 알림이 있으면 다음 자동 실행 시각과 함께 안내한다", async () => {
    vi.mocked(fetchRebalancingAlerts).mockResolvedValue([
      {
        portfolio_id: "p1",
        is_active: true,
        mode: "AUTO",
        threshold_pct: 5,
        auto_execution_time: "09:05",
      },
    ] as never);
    const { result } = renderHook(() => useAutoExecutionNotice("p1"), { wrapper });
    await waitFor(() => expect(result.current).toContain("(09:05)"));
  });

  it("계좌별 알림 중 첫 행이 NOTIFY여도 AUTO 행의 실행 시각을 쓴다 (plans/80)", async () => {
    vi.mocked(fetchRebalancingAlerts).mockResolvedValue([
      {
        portfolio_id: "p1",
        is_active: true,
        mode: "NOTIFY",
        threshold_pct: 5,
        auto_execution_time: null,
      },
      {
        portfolio_id: "p1",
        is_active: true,
        mode: "AUTO",
        threshold_pct: 5,
        auto_execution_time: "10:30",
      },
    ] as never);
    const { result } = renderHook(() => useAutoExecutionNotice("p1"), { wrapper });
    await waitFor(() => expect(result.current).toContain("(10:30)"));
  });

  it("꺼진 AUTO·NOTIFY 알림이면 안내하지 않는다", async () => {
    vi.mocked(fetchRebalancingAlerts).mockResolvedValue([
      { portfolio_id: "p1", is_active: false, mode: "AUTO", threshold_pct: 5 },
      { portfolio_id: "p2", is_active: true, mode: "NOTIFY", threshold_pct: 5 },
    ] as never);
    const { result: r1 } = renderHook(() => useAutoExecutionNotice("p1"), { wrapper });
    const { result: r2 } = renderHook(() => useAutoExecutionNotice("p2"), { wrapper });
    await waitFor(() => expect(fetchRebalancingAlerts).toHaveBeenCalled());
    expect(r1.current).toBeNull();
    expect(r2.current).toBeNull();
  });
});
