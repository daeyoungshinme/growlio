import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import PortfolioSummaryCard from "../components/dashboard/PortfolioSummaryCard";
import { renderWithProviders } from "../test/renderWithProviders";

vi.mock("../components/dashboard/PortfolioTreemapChart", () => ({
  default: () => <div data-testid="mock-treemap" />,
}));

vi.mock("../components/common/Tooltip", () => ({
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

const mockOverview = {
  total_stock_krw: 110_000_000,
  total_invested_krw: 100_000_000,
  unrealized_pnl_krw: 10_000_000,
  stock_return_pct: 10.0,
};

describe("PortfolioSummaryCard", () => {
  it("isLoading=true이면 스켈레톤 UI를 렌더링한다", () => {
    const { container } = renderWithProviders(
      <PortfolioSummaryCard overview={undefined} isLoading={true} />,
    );
    // SkeletonStatBox와 SkeletonCard가 포함된 div가 있어야 함
    expect(container.firstChild).toBeTruthy();
  });

  it("overview=undefined이고 isLoading=false이면 '데이터를 불러올 수 없습니다'를 표시한다", () => {
    renderWithProviders(
      <PortfolioSummaryCard overview={undefined} isLoading={false} />,
    );
    expect(screen.getByText("데이터를 불러올 수 없습니다")).toBeInTheDocument();
  });

  it("overview가 있으면 주식 수익률을 표시한다", () => {
    renderWithProviders(
      <PortfolioSummaryCard overview={mockOverview} isLoading={false} />,
    );
    expect(screen.getByText("+10.00%")).toBeInTheDocument();
  });

  it("수익(양수 unrealized_pnl_krw)이면 text-red-500 클래스 (한국 주식 관례)", () => {
    renderWithProviders(
      <PortfolioSummaryCard overview={mockOverview} isLoading={false} />,
    );
    // 10_000_000 → fmtKrw = "1,000만원", 부호 "+" 추가 → "+1,000만원"
    const pnlEl = screen.getByText("+1,000만원");
    expect(pnlEl).toHaveClass("text-red-500");
  });

  it("손실(음수 unrealized_pnl_krw)이면 text-blue-500 클래스 (한국 주식 관례)", () => {
    const lossOverview = { ...mockOverview, unrealized_pnl_krw: -5_000_000, stock_return_pct: -5.0 };
    renderWithProviders(
      <PortfolioSummaryCard overview={lossOverview} isLoading={false} />,
    );
    // -5_000_000 → fmtKrw = "-500만원"
    const pnlEl = screen.getByText("-500만원");
    expect(pnlEl).toHaveClass("text-blue-500");
  });

  it("stockAllocation이 있으면 트리맵 차트를 렌더링한다 (Suspense 해소 대기)", async () => {
    const allocation = [
      { name: "삼성전자", ticker: "005930", value_krw: 60_000_000, pct: 60 },
      { name: "SK하이닉스", ticker: "000660", value_krw: 40_000_000, pct: 40 },
    ];
    renderWithProviders(
      <PortfolioSummaryCard overview={mockOverview} isLoading={false} stockAllocation={allocation} />,
    );
    // lazy import가 resolve될 때까지 대기
    const chart = await screen.findByTestId("mock-treemap");
    expect(chart).toBeInTheDocument();
  });

  it("stockAllocation이 없으면 트리맵 차트를 렌더링하지 않는다", () => {
    renderWithProviders(
      <PortfolioSummaryCard overview={mockOverview} isLoading={false} />,
    );
    expect(screen.queryByTestId("mock-treemap")).not.toBeInTheDocument();
  });
});
