import { describe, it, expect, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { renderWithProviders } from "@/test/renderWithProviders";
import type { Portfolio } from "@/api/portfolios";
import type { RebalancingAlert } from "@/api/alerts";

vi.mock("@/api/portfolios", () => ({
  fetchPortfolios: vi.fn(),
}));
vi.mock("@/api/alerts", () => ({
  fetchRebalancingAlerts: vi.fn(),
}));

import { fetchPortfolios } from "@/api/portfolios";
import { fetchRebalancingAlerts } from "@/api/alerts";
import AutoInvestStatusBanner from "@/components/invest/AutoInvestStatusBanner";

const portfolio: Portfolio = {
  id: "port-1",
  name: "성장 포트폴리오",
  items: [],
  base_type: "STOCK_ONLY",
  sort_order: 0,
  created_at: "2024-01-01T00:00:00Z",
  updated_at: "2024-01-01T00:00:00Z",
};

const dcaAlert: RebalancingAlert = {
  id: "alert-1",
  portfolio_id: "port-1",
  threshold_pct: 0.5,
  schedule_type: "MONTHLY",
  schedule_day_of_week: null,
  schedule_day_of_month: 25,
  trigger_condition: "SCHEDULE_ONLY",
  mode: "AUTO",
  strategy: "BUY_ONLY",
  account_id: "acc-1",
  order_type: "MARKET",
  market_condition_mode: "DISABLED",
  auto_execution_time: "09:05",
  notify_time: "08:30",
  buy_wait_minutes: 10,
  tax_impact_gate_mode: "DISABLED",
  max_tax_impact_krw: null,
  is_active: true,
  last_triggered_at: null,
  created_at: "2024-01-01T00:00:00Z",
  updated_at: "2024-01-01T00:00:00Z",
};

describe("AutoInvestStatusBanner", () => {
  it("포트폴리오가 없으면 아무것도 렌더링하지 않는다", async () => {
    vi.mocked(fetchPortfolios).mockResolvedValue([]);
    vi.mocked(fetchRebalancingAlerts).mockResolvedValue([]);

    const { container } = renderWithProviders(
      <MemoryRouter>
        <AutoInvestStatusBanner />
      </MemoryRouter>,
    );

    await waitFor(() => expect(container.textContent).toBe(""));
  });

  it("DCA 프리셋 알림이 없으면 설정 유도 문구를 보여준다", async () => {
    vi.mocked(fetchPortfolios).mockResolvedValue([portfolio]);
    vi.mocked(fetchRebalancingAlerts).mockResolvedValue([]);

    renderWithProviders(
      <MemoryRouter>
        <AutoInvestStatusBanner />
      </MemoryRouter>,
    );

    expect(await screen.findByText("정기 적립식 자동매수를 설정해보세요")).toBeInTheDocument();
    // 포트폴리오가 1개뿐이면 알림 설정 모달까지 바로 연다
    expect(screen.getByText("설정하기").closest("a")?.getAttribute("href")).toContain(
      "openAlert=1",
    );
  });

  it("DCA 프리셋 알림이 있으면 매월 며칠인지와 포트폴리오 이름을 보여준다", async () => {
    vi.mocked(fetchPortfolios).mockResolvedValue([portfolio]);
    vi.mocked(fetchRebalancingAlerts).mockResolvedValue([dcaAlert]);

    renderWithProviders(
      <MemoryRouter>
        <AutoInvestStatusBanner />
      </MemoryRouter>,
    );

    expect(await screen.findByText("정기 적립식 매월 25일 자동매수 중")).toBeInTheDocument();
    expect(screen.getByText("성장 포트폴리오")).toBeInTheDocument();
    expect(screen.getByText("설정 관리").closest("a")?.getAttribute("href")).toContain(
      `portfolioId=${portfolio.id}&openAlert=1`,
    );
  });
});
