import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

vi.mock("@/api/rebalancingPlan", () => ({
  fetchPlanPreview: vi.fn(),
  cancelBuyPlanByToken: vi.fn(),
  decideSellPlanByToken: vi.fn(),
}));

import RebalancingPlanConfirmPage from "@/pages/RebalancingPlanConfirmPage";
import {
  cancelBuyPlanByToken,
  decideSellPlanByToken,
  fetchPlanPreview,
  type PlanTokenPreview,
  type RebalancingPlanLegSummary,
} from "@/api/rebalancingPlan";
import { QUERY_KEYS } from "@/constants/queryKeys";

function makePreview(leg: Partial<RebalancingPlanLegSummary>): PlanTokenPreview {
  return {
    valid: true,
    reason: null,
    actionable: true,
    leg: {
      plan_id: "p1",
      leg_id: "l1",
      portfolio_id: "pf1",
      portfolio_name: "코어",
      account_id: "a1",
      account_name: "KIS 계좌",
      side: "SELL",
      status: "PENDING",
      deadline_at: "2026-09-25T06:00:00Z",
      decided_at: null,
      execution_id: null,
      error_message: null,
      actionable: true,
      items: [
        {
          ticker: "005930",
          name: "삼성전자",
          market: "KOSPI",
          quantity: 3,
          account_id: "a1",
          order_type: "MARKET",
          limit_price: null,
          reference_price: 70000,
        },
      ],
      ...leg,
    },
  };
}

function renderPage(token = "tok") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/rebalancing/plan-confirm?token=${token}`]}>
        <RebalancingPlanConfirmPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { invalidateSpy };
}

describe("RebalancingPlanConfirmPage", () => {
  beforeEach(() => vi.clearAllMocks());

  it("토큰이 없으면 유효하지 않은 링크 안내", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter initialEntries={["/rebalancing/plan-confirm"]}>
          <RebalancingPlanConfirmPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(screen.getByText("유효하지 않은 링크입니다.")).toBeInTheDocument();
    expect(fetchPlanPreview).not.toHaveBeenCalled();
  });

  it("만료된 토큰은 사유를 보여준다", async () => {
    vi.mocked(fetchPlanPreview).mockResolvedValue({
      valid: false,
      reason: "EXPIRED",
      actionable: false,
      leg: null,
    });
    renderPage();
    expect(await screen.findByText("만료된 계획입니다.")).toBeInTheDocument();
  });

  it("매도 승인 → 결정 API 호출 + 대기 플랜/이력 캐시 무효화", async () => {
    vi.mocked(fetchPlanPreview).mockResolvedValue(makePreview({ side: "SELL" }));
    vi.mocked(decideSellPlanByToken).mockResolvedValue({ status: "OK", message: "승인되었습니다" });
    const { invalidateSpy } = renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "승인 (매도 실행)" }));

    expect(await screen.findByText("승인되었습니다")).toBeInTheDocument();
    expect(decideSellPlanByToken).toHaveBeenCalledWith("tok", "APPROVE");
    await waitFor(() =>
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: QUERY_KEYS.rebalancingPlans }),
    );
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: QUERY_KEYS.rebalancingHistory });
  });

  it("매도 거부는 REJECT로 호출", async () => {
    vi.mocked(fetchPlanPreview).mockResolvedValue(makePreview({ side: "SELL" }));
    vi.mocked(decideSellPlanByToken).mockResolvedValue({ status: "OK", message: "거부되었습니다" });
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "거부" }));
    expect(await screen.findByText("거부되었습니다")).toBeInTheDocument();
    expect(decideSellPlanByToken).toHaveBeenCalledWith("tok", "REJECT");
  });

  it("매수 계획은 취소 버튼만 노출하고 취소 API를 호출", async () => {
    vi.mocked(fetchPlanPreview).mockResolvedValue(makePreview({ side: "BUY" }));
    vi.mocked(cancelBuyPlanByToken).mockResolvedValue({ status: "OK", message: "취소되었습니다" });
    const { invalidateSpy } = renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "매수 취소하기" }));
    expect(await screen.findByText("취소되었습니다")).toBeInTheDocument();
    expect(cancelBuyPlanByToken).toHaveBeenCalledWith("tok");
    expect(screen.queryByRole("button", { name: "승인 (매도 실행)" })).not.toBeInTheDocument();
    await waitFor(() =>
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: QUERY_KEYS.rebalancingPlans }),
    );
  });
});
