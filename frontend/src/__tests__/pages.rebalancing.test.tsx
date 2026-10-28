import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

// ── mocks ────────────────────────────────────────────────────────────────────

vi.mock("@/api/marketSignals", () => ({
  fetchMarketSignal: vi.fn().mockResolvedValue(null),
}));

vi.mock("@/api/economicIndicators", () => ({
  fetchInflationSummary: vi.fn().mockResolvedValue([]),
}));

vi.mock("@/api/tactical", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/tactical")>()),
  fetchTacticalStrategies: vi.fn().mockResolvedValue([]),
  fetchTacticalMarket: vi.fn().mockResolvedValue({
    macro_level: "GREEN",
    macro_freshness: "LIVE",
    technicals: {},
  }),
}));

vi.mock("@/api/portfolios", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/portfolios")>()),
  fetchPortfolios: vi.fn().mockResolvedValue([]),
}));

vi.mock("@/api/assets", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/assets")>()),
  fetchAccounts: vi.fn().mockResolvedValue([]),
}));

vi.mock("@/components/dashboard/RebalancingStatusCard", () => ({
  default: () => React.createElement("div", { "data-testid": "rebalancing-status-card" }),
}));

vi.mock("@/components/portfolio-analysis/PortfolioManageTab", () => ({
  default: ({
    prefillName,
    onPrefillConsumed,
    selectedPortfolioId,
  }: {
    prefillName?: string;
    onPrefillConsumed?: () => void;
    selectedPortfolioId?: string;
  }) =>
    React.createElement(
      "div",
      {
        "data-testid": "portfolio-manage-tab",
        "data-prefill-name": prefillName ?? "",
        "data-selected": selectedPortfolioId ?? "",
      },
      React.createElement("button", { onClick: onPrefillConsumed }, "consume-prefill"),
    ),
}));

vi.mock("@/components/rebalancing/RecommendationCard", () => ({
  default: ({
    initialOptionsOpen,
    onCreatePortfolio,
  }: {
    initialOptionsOpen?: boolean;
    onCreatePortfolio?: (items: unknown[], name: string, accountIds?: string[]) => void;
  }) =>
    React.createElement(
      "div",
      {
        "data-testid": "recommendation-card",
        "data-options-open": String(Boolean(initialOptionsOpen)),
      },
      React.createElement(
        "button",
        { onClick: () => onCreatePortfolio?.([], "추천 포트폴리오") },
        "create-from-recommendation",
      ),
    ),
}));

vi.mock("@/components/rebalancing/TacticalAllocationTab", () => ({
  default: () => React.createElement("div", { "data-testid": "tactical-tab" }),
}));

vi.mock("@/components/rebalancing/RebalancingHistoryTab", () => ({
  default: () => React.createElement("div", { "data-testid": "history-tab" }),
}));

vi.mock("@/components/portfolio-analysis/PortfolioExecutionTab", () => ({
  default: () => React.createElement("div", { "data-testid": "portfolio-execution-tab" }),
}));

// ── imports ───────────────────────────────────────────────────────────────────

import RebalancingPage from "@/pages/RebalancingPage";
import { fetchMarketSignal } from "@/api/marketSignals";
import { fetchInflationSummary } from "@/api/economicIndicators";
import { fetchPortfolios } from "@/api/portfolios";
import { fetchAccounts } from "@/api/assets";
import { fetchTacticalStrategies } from "@/api/tactical";

// ── helpers ───────────────────────────────────────────────────────────────────

function NavigateButton({ to }: { to: string }) {
  const navigate = useNavigate();
  return <button onClick={() => void navigate(to)}>navigate</button>;
}

function renderPage(search = "", navigateTo?: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(
    <MemoryRouter initialEntries={[`/rebalancing${search}`]}>
      <QueryClientProvider client={qc}>
        {navigateTo && <NavigateButton to={navigateTo} />}
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

  it("탭은 진단·포트폴리오·목표 조정·이력 4개 — 추천·전술은 목표 조정 안의 모드 (plans/64)", async () => {
    renderPage("?rtab=포트폴리오");
    expect(await screen.findByTestId("portfolio-manage-tab")).toBeInTheDocument();
    expect(screen.queryByTestId("recommendation-card")).not.toBeInTheDocument();
    expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual([
      "진단",
      "포트폴리오",
      "목표 조정",
      "이력",
    ]);
  });

  it("예전 링크 rtab=추천은 목표 조정 탭의 추천 모드로 연다", async () => {
    renderPage("?rtab=추천");
    expect(await screen.findByTestId("recommendation-card")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "목표 조정" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "추천" })).toHaveAttribute("aria-selected", "true");
  });

  it("예전 링크 rtab=전술은 목표 조정 탭의 전술 모드로 연다", async () => {
    renderPage("?rtab=전술");
    expect(await screen.findByTestId("tactical-tab")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "전술" })).toHaveAttribute("aria-selected", "true");
  });

  it("URL 선택 없이 전술에서 포트폴리오 탭으로 가면 전술이 고른 포트폴리오가 유지된다 (plans/83 A)", async () => {
    // p1=기준 포트폴리오(계좌 목표), p2=전술 켜짐 — 전술은 p2, 다른 탭 기본값은 p1
    vi.mocked(fetchPortfolios).mockResolvedValue([
      { id: "p1", name: "국내 배당", account_ids: [] },
      { id: "p2", name: "미국 전술", account_ids: [] },
    ] as unknown as Awaited<ReturnType<typeof fetchPortfolios>>);
    vi.mocked(fetchAccounts).mockResolvedValue([
      { id: "a1", is_active: true, asset_type: "STOCK_KIS", target_portfolio_id: "p1" },
    ] as unknown as Awaited<ReturnType<typeof fetchAccounts>>);
    vi.mocked(fetchTacticalStrategies).mockResolvedValue([
      { portfolio_id: "p2", confirmed_regime: null, notify_enabled: true },
    ]);
    try {
      renderPage("?rtab=전술");
      expect(
        await screen.findByRole("option", { name: "미국 전술 (전술 켜짐)" }),
      ).toBeInTheDocument();
      await waitFor(() => expect(screen.getByRole("combobox")).toHaveValue("p2"));
      fireEvent.click(screen.getByRole("tab", { name: "포트폴리오" }));
      expect(await screen.findByTestId("portfolio-manage-tab")).toHaveAttribute(
        "data-selected",
        "p2",
      );
    } finally {
      vi.mocked(fetchPortfolios).mockResolvedValue([]);
      vi.mocked(fetchAccounts).mockResolvedValue([]);
      vi.mocked(fetchTacticalStrategies).mockResolvedValue([]);
    }
  });

  it("전술을 거치지 않으면 포트폴리오 탭 기본값은 기준 포트폴리오다 (plans/64 S3)", async () => {
    vi.mocked(fetchPortfolios).mockResolvedValue([
      { id: "p1", name: "국내 배당", account_ids: [] },
      { id: "p2", name: "미국 전술", account_ids: [] },
    ] as unknown as Awaited<ReturnType<typeof fetchPortfolios>>);
    vi.mocked(fetchAccounts).mockResolvedValue([
      { id: "a1", is_active: true, asset_type: "STOCK_KIS", target_portfolio_id: "p1" },
    ] as unknown as Awaited<ReturnType<typeof fetchAccounts>>);
    try {
      renderPage("?rtab=포트폴리오");
      await waitFor(() =>
        expect(screen.getByTestId("portfolio-manage-tab")).toHaveAttribute("data-selected", "p1"),
      );
    } finally {
      vi.mocked(fetchPortfolios).mockResolvedValue([]);
      vi.mocked(fetchAccounts).mockResolvedValue([]);
    }
  });

  it("목표 조정 탭에서 전술 모드로 바꾸면 전술 화면이 보인다", async () => {
    renderPage("?rtab=목표 조정");
    expect(await screen.findByTestId("recommendation-card")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "전술" }));
    expect(await screen.findByTestId("tactical-tab")).toBeInTheDocument();
  });

  it("rtab=추천&openRecOptions=1 이면 추천 카드가 옵션 모달을 연 상태로 마운트된다", async () => {
    renderPage("?rtab=추천&openRecOptions=1");
    const card = await screen.findByTestId("recommendation-card");
    expect(card).toHaveAttribute("data-options-open", "true");
  });

  it("페이지가 열린 채 rtab만 바뀌어도(푸시 딥링크) 탭이 따라간다 (plans/62 B4)", async () => {
    renderPage("?rtab=진단", "/rebalancing?rtab=이력");
    fireEvent.click(screen.getByRole("button", { name: "navigate" }));
    expect(await screen.findByTestId("history-tab")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "이력" })).toHaveAttribute("aria-selected", "true");
  });

  it("추천 prefill을 소비하면 이름까지 비운다 (plans/62 B3)", async () => {
    renderPage("?rtab=추천");
    fireEvent.click(await screen.findByRole("button", { name: "create-from-recommendation" }));
    const manage = await screen.findByTestId("portfolio-manage-tab");
    expect(manage).toHaveAttribute("data-prefill-name", "추천 포트폴리오");

    fireEvent.click(screen.getByRole("button", { name: "consume-prefill" }));
    expect(screen.getByTestId("portfolio-manage-tab")).toHaveAttribute("data-prefill-name", "");
  });

  it("시장신호 조회가 실패해도 물가 지표는 단독으로 보여준다 (plans/39 N7)", async () => {
    vi.mocked(fetchMarketSignal).mockRejectedValueOnce(new Error("signal down"));
    vi.mocked(fetchInflationSummary).mockResolvedValueOnce([
      {
        code: "CPI_US",
        name: "CPI",
        latest_value: 320.1,
        latest_date: "2026-08-01",
        mom_change_pct: 0.2,
        yoy_change_pct: 2.9,
        next_release_date: null,
      },
    ]);
    renderPage("?rtab=진단");
    expect(await screen.findByText("물가 지표 (미국)")).toBeInTheDocument();
  });
});
