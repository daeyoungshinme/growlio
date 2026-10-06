import { describe, it, expect, vi, beforeEach } from "vitest";
import type { ReactNode } from "react";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const analyzeCandidateOverlap = vi.fn();
vi.mock("@/api/rebalancing", () => ({
  analyzeCandidateOverlap: (...args: unknown[]) => analyzeCandidateOverlap(...args),
}));

import { useCandidateOverlap } from "@/hooks/useCandidateOverlap";

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const EMPTY = { groups: [], profiles: [], price_data_available: true };

describe("useCandidateOverlap", () => {
  beforeEach(() => {
    analyzeCandidateOverlap.mockReset();
    analyzeCandidateOverlap.mockResolvedValue(EMPTY);
  });

  it("목록을 생략하면 저장된 후보 기준으로 조회한다", async () => {
    const { result } = renderHook(() => useCandidateOverlap(), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(analyzeCandidateOverlap).toHaveBeenCalledWith(undefined);
  });

  it("편집 중 목록이 비어 있으면 조회하지 않는다", () => {
    renderHook(() => useCandidateOverlap([]), { wrapper });
    expect(analyzeCandidateOverlap).not.toHaveBeenCalled();
  });

  it("enabled=false면 조회하지 않는다", () => {
    renderHook(
      () => useCandidateOverlap([{ ticker: "SPY", name: "SPDR", market: "NYSE" }], false),
      { wrapper },
    );
    expect(analyzeCandidateOverlap).not.toHaveBeenCalled();
  });

  it("편집 중 목록을 그대로 넘긴다", async () => {
    const draft = [{ ticker: "SPY", name: "SPDR", market: "NYSE" }];
    const { result } = renderHook(() => useCandidateOverlap(draft), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(analyzeCandidateOverlap).toHaveBeenCalledWith(draft);
  });
});
