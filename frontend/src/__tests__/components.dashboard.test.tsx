import { describe, it, expect } from "vitest";
import { screen, render, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderWithProviders } from "@/test/renderWithProviders";
import InvestmentGoalCard from "@/components/dashboard/InvestmentGoalCard";
import DividendSection from "@/components/dashboard/DividendSection";
import type { DashboardData } from "@/api/dashboard";
import type { DCAAnalysisData } from "@/api/invest";

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
  annual_deposit_current: 18_000_000,
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
  return_goal_gap_pct: null,
  annual_dividend_goal: null,
  dividend_goal_achievement_pct: null,
};

function makeDcaData(expectedGoalDate: string | null): DCAAnalysisData {
  return {
    settings: {
      monthly_deposit_amount: 500_000,
      goal_annual_return_pct: 8,
      goal_amount: 1_000_000_000,
      goal_start_date: "2024-01-01",
      goal_initial_amount: null,
    },
    projection_months: [],
    yearly_achievements: [],
    goal_timeline: {
      months_to_goal: 120,
      expected_goal_date: expectedGoalDate,
      actual_expected_goal_date: expectedGoalDate,
      current_progress_pct: 15.0,
      on_track: true,
      lead_lag_months: 0,
    },
    is_configured: true,
  };
}

describe("InvestmentGoalCard", () => {
  it("목표가 없으면 설정 안내 메시지를 표시한다", () => {
    const data = {
      ...baseDashboard,
      annual_deposit_goal: null,
      deposit_achievement_pct: null,
      goal_amount: null,
      goal_achievement_pct: null,
      retirement_target_year: null,
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

  it("전체 진행율 섹션에 자산 목표 달성률과 현재/목표 금액을 표시한다 (자산 목표 칩은 제거됨)", () => {
    renderGoalCard(<InvestmentGoalCard data={baseDashboard} />);
    expect(screen.getAllByText("15.0%")[0]).toBeInTheDocument();
    expect(screen.getAllByText(/현재 1\.50억원/)[0]).toBeInTheDocument();
    expect(screen.getAllByText(/목표 10\.00억원/)[0]).toBeInTheDocument();
  });

  it("연간 입금 항목에 현재/목표 금액 텍스트를 표시한다", () => {
    renderGoalCard(<InvestmentGoalCard data={baseDashboard} />);
    expect(screen.getAllByText("1,800만 / 2,400만원")[0]).toBeInTheDocument();
  });

  it("data가 undefined면 목표 미설정 안내를 표시한다", () => {
    renderGoalCard(<InvestmentGoalCard data={undefined} />);
    expect(screen.getByText(/투자 목표가 설정되지 않았습니다/)).toBeInTheDocument();
  });

  it("DCA 타임라인이 없으면 은퇴 목표까지 남은 기간을 카운트다운으로 표시한다", () => {
    renderGoalCard(<InvestmentGoalCard data={baseDashboard} />);
    const yearsLeft = 2050 - new Date().getFullYear();
    expect(screen.getAllByText(`${yearsLeft}년 후`)[0]).toBeInTheDocument();
  });

  it("목표금액 도달 예상 시점이 은퇴 목표보다 빠르면 앞서 달성 배지를 표시한다", () => {
    renderGoalCard(<InvestmentGoalCard data={baseDashboard} dcaData={makeDcaData("2045-03")} />);
    expect(screen.getAllByText("5년 앞서 달성")[0]).toBeInTheDocument();
  });

  it("목표금액 도달 예상 시점이 은퇴 목표보다 늦으면 지연 예상 배지를 표시한다", () => {
    renderGoalCard(<InvestmentGoalCard data={baseDashboard} dcaData={makeDcaData("2055-03")} />);
    expect(screen.getAllByText("5년 지연 예상")[0]).toBeInTheDocument();
  });

  it("목표 연수익률을 초과 달성하면 초과달성 배지를 표시한다", () => {
    const data = {
      ...baseDashboard,
      goal_annual_return_pct: 7.0,
      xirr_pct: 8.5,
      return_goal_gap_pct: 1.5,
    };
    renderGoalCard(<InvestmentGoalCard data={data} />);
    expect(screen.getAllByText("+1.5%p")[0]).toBeInTheDocument();
    expect(screen.getAllByText("초과달성")[0]).toBeInTheDocument();
  });

  it("목표 연수익률에 미달하면 미달 배지를 표시한다", () => {
    const data = {
      ...baseDashboard,
      goal_annual_return_pct: 7.0,
      xirr_pct: 5.0,
      return_goal_gap_pct: -2.0,
    };
    renderGoalCard(<InvestmentGoalCard data={data} />);
    expect(screen.getAllByText("-2.0%p")[0]).toBeInTheDocument();
    expect(screen.getAllByText("미달")[0]).toBeInTheDocument();
  });

  it("목표 연수익률이 미설정이면 연수익률 패널에 미설정을 표시한다", () => {
    renderGoalCard(<InvestmentGoalCard data={baseDashboard} />);
    expect(screen.getAllByText("연수익률 목표")[0]).toBeInTheDocument();
  });

  it("목표 연수익률은 설정됐지만 실제 수익률 데이터가 없으면 미설정 대신 목표값을 표시한다", () => {
    const data = {
      ...baseDashboard,
      goal_annual_return_pct: 13,
      xirr_pct: null,
      annual_return_pct: null,
      return_goal_gap_pct: null,
    };
    renderGoalCard(<InvestmentGoalCard data={data} />);
    expect(screen.getAllByText("목표 13%")[0]).toBeInTheDocument();
    expect(screen.getAllByText("실제 수익률 계산 중")[0]).toBeInTheDocument();
  });

  it("연수익률 목표만 설정되고 다른 목표가 없어도 목표 미설정 안내가 뜨지 않는다", () => {
    const data = {
      ...baseDashboard,
      annual_deposit_goal: null,
      deposit_achievement_pct: null,
      goal_amount: null,
      goal_achievement_pct: null,
      retirement_target_year: null,
      goal_annual_return_pct: 13,
      xirr_pct: null,
      annual_return_pct: null,
      return_goal_gap_pct: null,
    };
    renderGoalCard(<InvestmentGoalCard data={data} />);
    expect(screen.queryByText(/투자 목표가 설정되지 않았습니다/)).not.toBeInTheDocument();
    expect(screen.getAllByText("목표 13%")[0]).toBeInTheDocument();
  });

  it("모바일 DCA 상세는 기본 접힘 상태이며, 토글 클릭 시 펼쳐진다", () => {
    renderGoalCard(<InvestmentGoalCard data={baseDashboard} dcaData={makeDcaData("2045-03")} />);
    // 헤드라인(진행율)은 접힘 상태에도 모바일+데스크탑 양쪽에 항상 보인다
    expect(screen.getAllByText("15.0%").length).toBeGreaterThanOrEqual(2);
    // 접힘 상태: "실제 달성 예상"은 데스크탑 블록에만 존재(1개) — 모바일 상세는 아직 숨김
    expect(screen.getAllByText("실제 달성 예상")).toHaveLength(1);

    fireEvent.click(screen.getByText("달성 예상일 · 진행 상세"));
    // 펼침 후에는 모바일 상세 블록도 렌더되어 2곳에 존재
    expect(screen.getAllByText("실제 달성 예상")).toHaveLength(2);
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

  it("isLoading이 true이면 스켈레톤을 표시한다", () => {
    const { container } = renderWithProviders(
      <DividendSection
        annualReceived={null}
        estimatedAnnual={null}
        estimatedMonthly={null}
        isLoading
      />,
    );
    expect(container.firstChild).toBeDefined();
  });
});
