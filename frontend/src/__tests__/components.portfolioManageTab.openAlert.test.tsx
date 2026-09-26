import { describe, expect, it, vi } from "vitest";
import { act, screen } from "@testing-library/react";
import { MemoryRouter, useSearchParams } from "react-router-dom";
import React from "react";
import { renderWithProviders } from "@/test/renderWithProviders";

vi.mock("@/api/portfolios", () => ({
  fetchPortfolios: vi
    .fn()
    .mockResolvedValue([
      { id: "p1", name: "성장", items: [], account_ids: null, alert_scope: "AGGREGATE" },
    ]),
  createPortfolio: vi.fn(),
  deletePortfolio: vi.fn(),
  reorderPortfolios: vi.fn(),
  updatePortfolio: vi.fn(),
}));
vi.mock("@/api/rebalancing", () => ({ fetchDriftSummary: vi.fn().mockResolvedValue([]) }));
vi.mock("@/api/assets", () => ({
  fetchAccounts: vi.fn().mockResolvedValue([]),
  batchSetTargetPortfolio: vi.fn(),
}));
vi.mock("@/api/alerts", () => ({ fetchRebalancingAlerts: vi.fn().mockResolvedValue([]) }));
vi.mock("@/components/portfolio-analysis/PortfolioListSection", () => ({
  default: () => React.createElement("div", { "data-testid": "portfolio-list" }),
}));
vi.mock("@/components/rebalancing/RebalancingAlertModalRouter", () => ({
  default: ({ portfolioId, onClose }: { portfolioId: string; onClose: () => void }) =>
    React.createElement(
      "div",
      { "data-testid": "alert-modal", "data-portfolio-id": portfolioId },
      React.createElement("button", { onClick: onClose }, "close-modal"),
    ),
}));

import PortfolioManageTab from "@/components/portfolio-analysis/PortfolioManageTab";

function Harness() {
  const [params, setParams] = useSearchParams();
  // 분석/실행 패널(PortfolioExecutionTab)이 하는 것과 같은 요청 — portfolioId + openAlert=1
  const requestOpenAlert = () =>
    setParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set("portfolioId", "p1");
      next.set("openAlert", "1");
      return next;
    });
  return (
    <>
      <button onClick={requestOpenAlert}>request-open-alert</button>
      <PortfolioManageTab
        selectedPortfolioId={params.get("portfolioId") ?? undefined}
        onAnalyze={vi.fn()}
      />
    </>
  );
}

function requestOpenAlert() {
  act(() => screen.getByText("request-open-alert").click());
}

describe("PortfolioManageTab — 자동화 설정 모달 단일 호스트(openAlert 파라미터)", () => {
  it("마운트 시 openAlert=1이면 선택 포트폴리오의 모달을 연다", async () => {
    renderWithProviders(
      <MemoryRouter initialEntries={["/rebalancing?portfolioId=p1&openAlert=1"]}>
        <Harness />
      </MemoryRouter>,
    );
    expect(await screen.findByTestId("alert-modal")).toHaveAttribute("data-portfolio-id", "p1");
  });

  it("마운트 이후 들어온 요청(분석 패널)도 열고, 닫은 뒤 같은 포트폴리오로 재요청해도 다시 연다", async () => {
    renderWithProviders(
      <MemoryRouter initialEntries={["/rebalancing"]}>
        <Harness />
      </MemoryRouter>,
    );
    await screen.findByTestId("portfolio-list");
    expect(screen.queryByTestId("alert-modal")).not.toBeInTheDocument();

    requestOpenAlert();
    expect(await screen.findByTestId("alert-modal")).toHaveAttribute("data-portfolio-id", "p1");

    act(() => screen.getByText("close-modal").click());
    expect(screen.queryByTestId("alert-modal")).not.toBeInTheDocument();

    requestOpenAlert();
    expect(await screen.findByTestId("alert-modal")).toBeInTheDocument();
  });
});
