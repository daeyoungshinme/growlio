import { describe, it, vi } from "vitest";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

// ── mocks ────────────────────────────────────────────────────────────────────

vi.mock("@/api/marketSignals", () => ({
  fetchMarketSignal: vi.fn().mockResolvedValue(null),
  fetchMacroDiagnosis: vi.fn().mockResolvedValue(null),
}));

vi.mock("@/components/dashboard/RebalancingStatusCard", () => ({
  default: () => React.createElement("div", { "data-testid": "rebalancing-status-card" }),
}));

vi.mock("@/components/portfolio-analysis/PortfolioManageTab", () => ({
  default: () => React.createElement("div", { "data-testid": "portfolio-manage-tab" }),
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
});
