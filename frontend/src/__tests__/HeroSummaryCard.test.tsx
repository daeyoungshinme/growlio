import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import HeroSummaryCard from "@/components/dashboard/HeroSummaryCard";
import { renderWithProviders } from "@/test/renderWithProviders";
import type { DashboardData } from "@/api/dashboard";

vi.mock("../components/dashboard/AssetAllocationChart", () => ({
  default: () => <div data-testid="mock-allocation-chart" />,
}));

const baseDashboard: DashboardData = {
  total_assets_krw: 150_000_000,
  cumulative_return_pct: 12.5,
  asset_allocation: [
    { type: "STOCK_KIS", amount_krw: 100_000_000, pct: 66.7 },
    { type: "BANK_ACCOUNT", amount_krw: 50_000_000, pct: 33.3 },
  ],
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

describe("HeroSummaryCard", () => {
  it("전체 자산이 억원 단위로 포맷되어 표시된다", () => {
    renderWithProviders(<HeroSummaryCard data={baseDashboard} exchangeRate={1350} />);
    expect(screen.getByText("1.50억원")).toBeInTheDocument();
  });

  it("exchangeRate가 null이면 환율 셀에 '—'가 표시된다", () => {
    renderWithProviders(<HeroSummaryCard data={baseDashboard} exchangeRate={null} />);
    // 여러 "—"가 있을 수 있으므로 getAllByText 사용
    const dashes = screen.getAllByText("—");
    expect(dashes.length).toBeGreaterThanOrEqual(1);
  });

  it("cumulative_return_pct가 null이면 fmtPct가 '—'를 반환한다", () => {
    const data = { ...baseDashboard, cumulative_return_pct: null };
    renderWithProviders(<HeroSummaryCard data={data} exchangeRate={1350} />);
    const dashes = screen.getAllByText("—");
    expect(dashes.length).toBeGreaterThanOrEqual(1);
  });

  it("수익률이 양수이면 text-red-500 (한국 주식 관례) 클래스를 가진다", () => {
    renderWithProviders(<HeroSummaryCard data={baseDashboard} exchangeRate={1350} />);
    const pnlEls = screen.getAllByText("+12.50%");
    expect(pnlEls.length).toBeGreaterThanOrEqual(1);
    pnlEls.forEach((el) => expect(el).toHaveClass("text-red-500"));
  });

  it("수익률이 음수이면 text-blue-500 (한국 주식 관례) 클래스를 가진다", () => {
    const data = { ...baseDashboard, cumulative_return_pct: -5.3 };
    renderWithProviders(<HeroSummaryCard data={data} exchangeRate={1350} />);
    const pnlEls = screen.getAllByText("-5.30%");
    expect(pnlEls.length).toBeGreaterThanOrEqual(1);
    pnlEls.forEach((el) => expect(el).toHaveClass("text-blue-500"));
  });

  it("asset_allocation이 비어 있으면 '자산 데이터 없음'이 표시된다", () => {
    const data = { ...baseDashboard, asset_allocation: [] };
    renderWithProviders(<HeroSummaryCard data={data} exchangeRate={1350} />);
    expect(screen.getByText("자산 데이터 없음")).toBeInTheDocument();
  });

  it("환율이 있으면 1,350원 형식으로 표시된다", () => {
    renderWithProviders(<HeroSummaryCard data={baseDashboard} exchangeRate={1350} />);
    expect(screen.getByText("1,350원")).toBeInTheDocument();
  });
});
