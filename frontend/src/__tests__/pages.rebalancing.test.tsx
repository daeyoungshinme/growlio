import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

// ── mocks ────────────────────────────────────────────────────────────────────

vi.mock("@/api/marketSignals", () => ({
  fetchMarketSignal: vi.fn().mockResolvedValue(null),
}));

vi.mock("@/components/dashboard/RebalancingStatusCard", () => ({
  default: () => React.createElement("div", { "data-testid": "rebalancing-status-card" }),
}));

vi.mock("@/components/portfolio-analysis/PortfolioManageTab", () => ({
  default: () => React.createElement("div", { "data-testid": "portfolio-manage-tab" }),
}));

vi.mock("@/components/rebalancing/RecommendationCard", () => ({
  default: ({ initialOptionsOpen }: { initialOptionsOpen?: boolean }) =>
    React.createElement("div", {
      "data-testid": "recommendation-card",
      "data-options-open": String(Boolean(initialOptionsOpen)),
    }),
}));

vi.mock("@/components/portfolio-analysis/PortfolioExecutionTab", () => ({
  default: () => React.createElement("div", { "data-testid": "portfolio-execution-tab" }),
}));

// ── imports ───────────────────────────────────────────────────────────────────

import RebalancingPage from "@/pages/RebalancingPage";

// ── helpers ───────────────────────────────────────────────────────────────────

function renderPage(search = "") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(
    <MemoryRouter initialEntries={[`/rebalancing${search}`]}>
      <QueryClientProvider client={qc}>
        <RebalancingPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

// ── tests ─────────────────────────────────────────────────────────────────────

describe("RebalancingPage", () => {
  it("기본 렌더링이 정상적으로 동작한다", () => {
    renderPage();
  });

  it("portfolioId 쿼리 파라미터를 처리한다", () => {
    renderPage("?portfolioId=123");
  });

  it("추천은 독립 서브탭 — 포트폴리오 탭에는 추천 카드가 없다", async () => {
    renderPage("?rtab=포트폴리오");
    expect(await screen.findByTestId("portfolio-manage-tab")).toBeInTheDocument();
    expect(screen.queryByTestId("recommendation-card")).not.toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "추천" })).toBeInTheDocument();
  });

  it("rtab=추천&openRecOptions=1 이면 추천 카드가 옵션 모달을 연 상태로 마운트된다", async () => {
    renderPage("?rtab=추천&openRecOptions=1");
    const card = await screen.findByTestId("recommendation-card");
    expect(card).toHaveAttribute("data-options-open", "true");
  });
});
