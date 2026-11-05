import { describe, it, expect } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import HeroSummaryCard from "@/components/dashboard/HeroSummaryCard";
import { renderWithProviders } from "@/test/renderWithProviders";
import type { DashboardData } from "@/api/dashboard";
import { MemoryRouter } from "react-router-dom";
import type { PortfolioOverview } from "@/types";
import { portfolioUrl } from "@/utils/tabUrl";

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
  estimated_annual_dividends: 0,
  xirr_pct: null,
  goal_annual_return_pct: null,
  return_goal_gap_pct: null,
  annual_dividend_goal: null,
  dividend_goal_achievement_pct: null,
};

describe("HeroSummaryCard", () => {
  it("전체 자산 금액은 기본 숨김이고 title·범례 금액도 노출하지 않는다", () => {
    renderWithProviders(<HeroSummaryCard data={baseDashboard} exchangeRate={1350} />);
    const toggle = screen.getByRole("button", { name: "전체 자산 금액 보기" });
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    expect(toggle).not.toHaveAttribute("title");
    expect(screen.queryByText("1.50억원")).toBeNull();
    expect(screen.queryByText(/· 1.0억/)).toBeNull();
  });

  describe("주식 평가손익", () => {
    const overview = {
      total_stock_krw: 80_000_000,
      unrealized_pnl_krw: 10_000_000,
      stock_return_pct: 14.3,
    } as PortfolioOverview;

    function renderHero(value: PortfolioOverview) {
      renderWithProviders(
        <MemoryRouter>
          <HeroSummaryCard data={baseDashboard} overview={value} exchangeRate={1350} />
        </MemoryRouter>,
      );
    }

    it("금액은 전체 자산과 함께 기본 숨김이고 수익률만 보인다", () => {
      renderHero(overview);
      expect(screen.getByText(/••••••.*\+14\.3%/)).toBeInTheDocument();
      expect(screen.queryByText(/\+1,000만/)).toBeNull();
    });

    it("금액을 펼치면 손익 금액도 표시하고 자산 탭으로 연결된다", () => {
      renderHero(overview);
      fireEvent.click(screen.getByRole("button", { name: "전체 자산 금액 보기" }));
      expect(screen.getByText(/\+1,000만.*\+14\.3%/)).toBeInTheDocument();
      expect(screen.getByRole("link", { name: /주식 평가손익/ })).toHaveAttribute(
        "href",
        portfolioUrl(),
      );
    });

    it("보유 주식이 없으면 표시하지 않는다", () => {
      renderHero({ ...overview, total_stock_krw: 0 });
      expect(screen.queryByText(/주식 평가손익/)).toBeNull();
    });
  });

  it("누르면 전체 자산이 억원 단위로 표시되고 다시 누르면 숨긴다", () => {
    renderWithProviders(<HeroSummaryCard data={baseDashboard} exchangeRate={1350} />);
    fireEvent.click(screen.getByRole("button", { name: "전체 자산 금액 보기" }));
    expect(screen.getByText("1.50억원")).toBeInTheDocument();
    const toggle = screen.getByRole("button", { name: "전체 자산 금액 숨기기" });
    expect(toggle).toHaveAttribute("title", "150,000,000원");
    expect(screen.getByText(/· 1.0억/)).toBeInTheDocument();

    fireEvent.click(toggle);
    expect(screen.queryByText("1.50억원")).toBeNull();
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

  it("dataUpdatedAt이 있으면 업데이트 시각과 범례를 함께 표시한다", () => {
    renderWithProviders(
      <HeroSummaryCard data={baseDashboard} exchangeRate={1350} dataUpdatedAt={Date.now()} />,
    );
    expect(screen.getByText("방금 업데이트")).toBeInTheDocument();
    expect(screen.getByText(/주식 67%/)).toBeInTheDocument();
  });

  it("환율이 있으면 1,350원 형식으로 표시된다", () => {
    renderWithProviders(<HeroSummaryCard data={baseDashboard} exchangeRate={1350} />);
    expect(screen.getByText("1,350원")).toBeInTheDocument();
  });
});
