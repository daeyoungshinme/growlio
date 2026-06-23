import { describe, it, expect } from "vitest";
import { screen, render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderWithProviders } from "@/test/renderWithProviders";
import InvestmentGoalCard from "@/components/dashboard/InvestmentGoalCard";
import DividendSection from "@/components/dashboard/DividendSection";
import type { DashboardData } from "@/api/dashboard";

function renderGoalCard(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
    </MemoryRouter>,
  );
}

const baseDashboard: DashboardData = {
  total_assets_krw: 150_000_000,
  cumulative_return_pct: 12.5,
  asset_allocation: [],
  deposit_achievement_pct: 75.0,
  annual_deposit_goal: 24_000_000,
  retirement_target_year: 2050,
  goal_amount: 1_000_000_000,
  goal_achievement_pct: 15.0,
  stock_return_pct: 8.0,
  annual_return_pct: null,
  monthly_trend: [],
  annual_dividends_received: 0,
  estimated_annual_dividends: 0,
  dividend_monthly_breakdown: [],
  xirr_pct: null,
  xirr_is_estimated: false,
  benchmark_sp500_pct: null,
  goal_annual_return_pct: null,
};

describe("InvestmentGoalCard", () => {
  it("목표가 없으면 설정 안내 메시지를 표시한다", () => {
    const data = {
      ...baseDashboard,
      annual_deposit_goal: null,
      deposit_achievement_pct: null,
      goal_amount: null,
      goal_achievement_pct: null,
    };
    renderGoalCard(<InvestmentGoalCard data={data} />);
    expect(screen.getByText(/투자 목표가 설정되지 않았습니다/)).toBeInTheDocument();
  });

  it("연간 입금 목표가 있으면 달성률을 표시한다", () => {
    renderGoalCard(<InvestmentGoalCard data={baseDashboard} />);
    // 모바일+데스크탑 두 곳에 렌더링되므로 getAllByText 사용
    expect(screen.getAllByText("75.0%")[0]).toBeInTheDocument();
  });

  it("달성률이 100% 초과 시 100%로 클램핑된다", () => {
    const data = { ...baseDashboard, deposit_achievement_pct: 120 };
    renderGoalCard(<InvestmentGoalCard data={data} />);
    expect(screen.getAllByText("100.0%")[0]).toBeInTheDocument();
  });

  it("자산 목표 달성률을 표시한다", () => {
    renderGoalCard(<InvestmentGoalCard data={baseDashboard} />);
    expect(screen.getAllByText("15.0%")[0]).toBeInTheDocument();
  });

  it("data가 undefined면 목표 미설정 안내를 표시한다", () => {
    renderGoalCard(<InvestmentGoalCard data={undefined} />);
    expect(screen.getByText(/투자 목표가 설정되지 않았습니다/)).toBeInTheDocument();
  });

  it("은퇴 목표 연도를 현재 자산 섹션에 표시한다", () => {
    renderGoalCard(<InvestmentGoalCard data={baseDashboard} />);
    expect(screen.getByText(/2050년 목표/)).toBeInTheDocument();
  });
});

describe("DividendSection", () => {
  it("모든 배당 항목을 표시한다", () => {
    renderWithProviders(
      <DividendSection
        annualReceived={500000}
        estimatedAnnual={600000}
        estimatedMonthly={50000}
        overallDividendYield={2.5}
      />,
    );
    expect(screen.getByText("연간 배당금")).toBeInTheDocument();
    expect(screen.getByText("실제 배당금")).toBeInTheDocument();
    expect(screen.getByText("월별 배당금")).toBeInTheDocument();
  });

  it("estimatedAnnual이 null이면 연간 배당금을 '—'로 표시한다", () => {
    renderWithProviders(
      <DividendSection annualReceived={null} estimatedAnnual={null} estimatedMonthly={null} />,
    );
    const dashes = screen.getAllByText("—");
    expect(dashes.length).toBeGreaterThanOrEqual(3);
  });

  it("estimatedAnnual > 0이면 수익률도 함께 표시한다", () => {
    renderWithProviders(
      <DividendSection
        annualReceived={500000}
        estimatedAnnual={600000}
        estimatedMonthly={50000}
        overallDividendYield={2.5}
      />,
    );
    expect(screen.getByText("(2.50%)")).toBeInTheDocument();
  });

  it("overallDividendYield가 없으면 수익률을 표시하지 않는다", () => {
    renderWithProviders(
      <DividendSection
        annualReceived={500000}
        estimatedAnnual={600000}
        estimatedMonthly={50000}
        overallDividendYield={null}
      />,
    );
    expect(screen.queryByText(/%\)/)).toBeNull();
  });

  it("estimatedAnnual이 0이면 연간 배당금을 '—'로 표시한다", () => {
    renderWithProviders(
      <DividendSection annualReceived={0} estimatedAnnual={0} estimatedMonthly={0} />,
    );
    const dashes = screen.getAllByText("—");
    expect(dashes.length).toBeGreaterThanOrEqual(3);
  });
});
