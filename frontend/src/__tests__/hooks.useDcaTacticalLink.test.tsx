import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { RebalancingAlert } from "@/api/alerts";
import { fetchRebalancingAlerts } from "@/api/alerts";
import { useDcaTacticalLink } from "@/hooks/useDcaTacticalLink";

vi.mock("@/api/alerts", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/alerts")>()),
  fetchRebalancingAlerts: vi.fn(),
}));

const alert = (over: Partial<RebalancingAlert>): RebalancingAlert =>
  ({
    id: "a1",
    portfolio_id: "p1",
    is_active: true,
    mode: "AUTO",
    strategy: "BUY_ONLY",
    account_id: null,
    market_condition_mode: "OFF",
    threshold_pct: 5,
    ...over,
  }) as RebalancingAlert;

function render(alerts: RebalancingAlert[], portfolioId: string | undefined = "p1") {
  vi.mocked(fetchRebalancingAlerts).mockResolvedValue(alerts);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return renderHook(() => useDcaTacticalLink(portfolioId), { wrapper }).result;
}

describe("useDcaTacticalLink (plans/71)", () => {
  beforeEach(() => vi.mocked(fetchRebalancingAlerts).mockReset());

  it("포트폴리오가 없으면 적립식 아님", () => {
    const result = render([alert({ market_condition_mode: "TACTICAL" })], undefined);
    expect(result.current).toEqual({ dcaAuto: false, linked: false });
  });

  it("활성 AUTO 매수만 + TACTICAL이면 연동됨", async () => {
    const result = render([alert({ market_condition_mode: "TACTICAL" })]);
    await waitFor(() => expect(result.current).toEqual({ dcaAuto: true, linked: true }));
  });

  it("전술 연동이 아니면 dcaAuto만", async () => {
    const result = render([alert({})]);
    await waitFor(() => expect(result.current).toEqual({ dcaAuto: true, linked: false }));
  });

  it("NOTIFY·FULL·비활성·다른 포트폴리오는 적립식이 아니다", async () => {
    const result = render([
      alert({ mode: "NOTIFY" }),
      alert({ strategy: "FULL" }),
      alert({ is_active: false }),
      alert({ portfolio_id: "p2" }),
    ]);
    await waitFor(() => expect(fetchRebalancingAlerts).toHaveBeenCalled());
    expect(result.current).toEqual({ dcaAuto: false, linked: false });
  });

  it("계좌별 알림 중 첫 행이 NOTIFY여도 다른 계좌의 적립식 자동매수를 찾는다 (plans/80)", async () => {
    const result = render([
      alert({ id: "a1", account_id: "acc1", mode: "NOTIFY", strategy: "FULL" }),
      alert({ id: "a2", account_id: "acc2", market_condition_mode: "TACTICAL" }),
    ]);
    await waitFor(() => expect(result.current).toEqual({ dcaAuto: true, linked: true }));
  });

  it("적립식 자동매수 중 하나라도 전술 연동이 아니면 연동 안내를 유지한다", async () => {
    const result = render([
      alert({ id: "a1", account_id: "acc1", market_condition_mode: "TACTICAL" }),
      alert({ id: "a2", account_id: "acc2" }),
    ]);
    await waitFor(() => expect(result.current).toEqual({ dcaAuto: true, linked: false }));
  });
});
