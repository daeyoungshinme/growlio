import { describe, it, expect, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

const update = vi.fn().mockResolvedValue(undefined);
vi.mock("@/utils/platform", () => ({ isNativePlatform: () => true, getApiBaseUrl: () => "" }));
vi.mock("@/plugins/WidgetPlugin", () => ({ WidgetPlugin: { update } }));

import { useWidget } from "@/hooks/useWidget";
import { QUERY_KEYS } from "@/constants/queryKeys";

describe("useWidget", () => {
  it("대시보드 쿼리 observer를 만들지 않고 캐시 갱신만 위젯에 반영한다", async () => {
    const qc = new QueryClient();
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );
    renderHook(() => useWidget(), { wrapper });

    // observer가 없으니 쿼리를 만들지도, 조회하지도 않는다
    expect(qc.getQueryCache().find({ queryKey: QUERY_KEYS.dashboard })).toBeUndefined();

    qc.setQueryData(QUERY_KEYS.dashboard, { total_assets_krw: 1_000_000, stock_return_pct: 5 });
    await waitFor(() => expect(update).toHaveBeenCalledTimes(1));
    expect(qc.getQueryCache().find({ queryKey: QUERY_KEYS.dashboard })?.getObserversCount()).toBe(
      0,
    );
  });
});
