import { describe, expect, it, vi, beforeEach } from "vitest";
import { act, renderHook, screen, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { renderWithProviders } from "@/test/renderWithProviders";
import ErrorBoundary from "@/components/ErrorBoundary";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { invalidateTransactionData } from "@/utils/queryInvalidation";
import { useSyncStore } from "@/stores/syncStore";

vi.mock("@/api/alerts", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/alerts")>()),
  fetchRebalancingAlert: vi.fn(),
}));

vi.mock("@/api/rebalancingPlan", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/rebalancingPlan")>()),
  fetchRecentPlanLegs: vi.fn(),
}));

vi.mock("@/api/rebalancing", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/rebalancing")>()),
  fetchRebalancingHistory: vi.fn(),
}));

import { fetchRebalancingAlert } from "@/api/alerts";
import { fetchRecentPlanLegs } from "@/api/rebalancingPlan";
import { fetchRebalancingHistory } from "@/api/rebalancing";
import { useRebalancingAlertQueries } from "@/hooks/useRebalancingAlertForm";
import RebalancingHistoryTab from "@/components/rebalancing/RebalancingHistoryTab";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return createElement(QueryClientProvider, { client }, children);
}

describe("조회 실패를 '없음'으로 보이지 않는다 (plans/109 D)", () => {
  beforeEach(() => vi.clearAllMocks());

  describe("알림 설정 조회", () => {
    const render = () =>
      renderHook(() => useRebalancingAlertQueries({ portfolioId: "p1", accountIds: [] }), {
        wrapper,
      });

    // 훅이 5xx를 2회 재시도(백오프 1s·2s)하므로 판정까지 약 3초 걸린다
    it("조회 실패면 기본 폼으로 넘어가지 않도록 loadFailed를 알린다", async () => {
      vi.mocked(fetchRebalancingAlert).mockRejectedValue(new Error("500"));
      const { result } = render();
      await waitFor(() => expect(result.current.loadFailed).toBe(true), { timeout: 6000 });
    }, 8000);

    it("알림이 없는 것(null)은 실패가 아니다", async () => {
      vi.mocked(fetchRebalancingAlert).mockResolvedValue(null);
      const { result } = render();
      await waitFor(() => expect(result.current.isLoading).toBe(false));
      expect(result.current.loadFailed).toBe(false);
      expect(result.current.alert).toBeNull();
    });
  });

  describe("실행 이력 탭", () => {
    it("조회 실패면 '이력 없음' 대신 재시도를 보여준다", async () => {
      vi.mocked(fetchRebalancingHistory).mockRejectedValue(new Error("down"));
      vi.mocked(fetchRecentPlanLegs).mockRejectedValue(new Error("down"));
      renderWithProviders(
        <MemoryRouter>
          <RebalancingHistoryTab />
        </MemoryRouter>,
      );

      expect(await screen.findByText("실행 이력을 일부 불러오지 못했습니다.")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "다시 시도" })).toBeInTheDocument();
      expect(screen.queryByText("아직 실행 이력이 없습니다.")).toBeNull();
    });

    it("둘 다 성공하고 비어 있으면 빈 상태를 보여준다", async () => {
      vi.mocked(fetchRebalancingHistory).mockResolvedValue([]);
      vi.mocked(fetchRecentPlanLegs).mockResolvedValue([]);
      renderWithProviders(
        <MemoryRouter>
          <RebalancingHistoryTab />
        </MemoryRouter>,
      );

      expect(await screen.findByText("아직 실행 이력이 없습니다.")).toBeInTheDocument();
    });
  });
});

describe("거래 변경 후 무효화", () => {
  it("종목별 배당 캐시도 함께 무효화한다", async () => {
    const client = new QueryClient();
    const spy = vi.spyOn(client, "invalidateQueries");
    await invalidateTransactionData(client);
    expect(spy).toHaveBeenCalledWith({ queryKey: QUERY_KEYS.dividendByTickerBase });
  });
});

describe("syncStore 초기화", () => {
  it("reset은 이전 계정의 실패 계좌를 지운다", () => {
    act(() =>
      useSyncStore.getState().finishSyncAll(1, [{ account_id: "a", name: "옛 계좌" }] as never),
    );
    expect(useSyncStore.getState().failedAccounts).toHaveLength(1);
    act(() => useSyncStore.getState().reset());
    expect(useSyncStore.getState().failedAccounts).toHaveLength(0);
  });
});

describe("ErrorBoundary resetKey", () => {
  function Boom({ fail }: { fail: boolean }) {
    if (fail) throw new Error("secret detail");
    return <div>정상 화면</div>;
  }

  it("라우트가 바뀌면 오류 화면을 해제한다", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    const { rerender } = renderWithProviders(
      <ErrorBoundary resetKey="/a">
        <Boom fail />
      </ErrorBoundary>,
    );
    expect(screen.queryByText("정상 화면")).toBeNull();

    rerender(
      <ErrorBoundary resetKey="/b">
        <Boom fail={false} />
      </ErrorBoundary>,
    );
    expect(screen.getByText("정상 화면")).toBeInTheDocument();
    spy.mockRestore();
  });
});

describe("실행 이력 페이지네이션 (plans/110 D7)", () => {
  beforeEach(() => vi.clearAllMocks());

  const rows = (from: number, count: number) =>
    Array.from({ length: count }, (_, i) => ({
      id: `exec-${from + i}`,
      triggered_by: "MANUAL",
      strategy: "FULL",
      total_success: 1,
      total_fail: 0,
      total_skipped: 0,
      executed_at: "2026-11-01T00:00:00Z",
    }));

  it("받아 둔 50건을 다 보여주면 다음 묶음을 skip으로 받는다", async () => {
    vi.mocked(fetchRecentPlanLegs).mockResolvedValue([]);
    vi.mocked(fetchRebalancingHistory).mockImplementation((_limit, skip = 0) =>
      Promise.resolve((skip === 0 ? rows(0, 50) : rows(50, 3)) as never),
    );
    renderWithProviders(
      <MemoryRouter>
        <RebalancingHistoryTab />
      </MemoryRouter>,
    );

    const more = await screen.findByText("실행 이력 더 보기");
    expect(fetchRebalancingHistory).toHaveBeenCalledTimes(1);
    for (let i = 0; i < 4; i++) act(() => more.click());

    await waitFor(() => expect(fetchRebalancingHistory).toHaveBeenCalledWith(50, 50));
  });
});
