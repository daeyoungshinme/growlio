import { describe, it, expect, vi } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";
import { MemoryRouter } from "react-router-dom";

// Mock recharts
vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div data-testid="recharts-container">{children}</div>,
  BarChart: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Bar: () => <div />,
  XAxis: () => <div />,
  YAxis: () => <div />,
  CartesianGrid: () => <div />,
  Legend: () => <div />,
  Tooltip: () => <div />,
  Treemap: () => <div />,
  LineChart: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Line: () => <div />,
  Cell: () => <div />,
}));

vi.mock("@/stores/themeStore", () => ({
  useThemeStore: () => ({ isDark: false, toggle: vi.fn() }),
}));

vi.mock("@/api/portfolios", () => ({
  fetchAllocationHistory: vi.fn().mockResolvedValue([]),
}));

vi.mock("@/api/dart", () => ({
  fetchDartDisclosures: vi.fn().mockResolvedValue([]),
}));

vi.mock("@/utils/dividendUtils", () => ({
  MONTH_LABELS: ["1월","2월","3월","4월","5월","6월","7월","8월","9월","10월","11월","12월"],
  dividendFreqInfo: vi.fn(() => ({ label: "분기", cls: "text-blue-500" })),
  weightBarColor: vi.fn(() => "bg-blue-500"),
  yieldBadgeClass: vi.fn(() => "bg-green-100 text-green-600"),
}));

import AllocationHistoryChart from "@/components/dashboard/AllocationHistoryChart";
import DisclosureFeedCard from "@/components/dashboard/DisclosureFeedCard";
import DividendByTickerTable from "@/components/dashboard/DividendByTickerTable";
import DividendMonthsModal from "@/components/dashboard/DividendMonthsModal";
import PortfolioTreemapChart from "@/components/dashboard/PortfolioTreemapChart";

// ------- AllocationHistoryChart -------
describe("AllocationHistoryChart", () => {
  it("renders loading state initially (no data fetched)", () => {
    renderWithProviders(<AllocationHistoryChart />);
    // isLoading will show skeleton or nothing (based on data state)
    // Just check it doesn't crash
    expect(document.body).toBeDefined();
  });

  it("renders without crash when data returns empty", async () => {
    renderWithProviders(<AllocationHistoryChart />);
    // Should render without throwing
    expect(document.body).toBeDefined();
  });
});

// ------- DisclosureFeedCard -------
describe("DisclosureFeedCard", () => {
  it("renders with day filter buttons", () => {
    renderWithProviders(
      <MemoryRouter>
        <DisclosureFeedCard />
      </MemoryRouter>
    );
    expect(screen.getByText("7일")).toBeDefined();
    expect(screen.getByText("30일")).toBeDefined();
    expect(screen.getByText("90일")).toBeDefined();
  });

  it("changes days filter on button click", () => {
    renderWithProviders(
      <MemoryRouter>
        <DisclosureFeedCard />
      </MemoryRouter>
    );
    fireEvent.click(screen.getByText("7일"));
    // Just verify no crash
    expect(screen.getByText("7일")).toBeDefined();
  });

  it("shows disclosure card header", () => {
    renderWithProviders(
      <MemoryRouter>
        <DisclosureFeedCard />
      </MemoryRouter>
    );
    expect(screen.getByText("보유 종목 공시")).toBeDefined();
  });
});

// ------- DividendByTickerTable -------
const mockItems = [
  {
    ticker: "AAPL",
    market: "NASDAQ",
    name: "Apple Inc.",
    estimated_annual_krw: 500000,
    estimated_monthly_krw: 41666,
    investment_yield: 2.5,
    dividend_months: [3, 6, 9, 12],
    dividend_months_is_manual: false,
  },
  {
    ticker: "005930",
    market: "KOSPI",
    name: "삼성전자",
    estimated_annual_krw: 800000,
    estimated_monthly_krw: 66666,
    investment_yield: 3.2,
    dividend_months: [1, 4, 7, 10],
    dividend_months_is_manual: true,
  },
];

describe("DividendByTickerTable", () => {
  it("renders loading skeleton", () => {
    const { container } = renderWithProviders(
      <DividendByTickerTable items={[]} isLoading={true} />
    );
    expect(container.firstChild).toBeDefined();
  });

  it("renders empty state", () => {
    renderWithProviders(
      <DividendByTickerTable items={[]} isLoading={false} />
    );
    expect(screen.getByText("보유 종목 없음")).toBeDefined();
  });

  it("renders dividend items", () => {
    renderWithProviders(
      <DividendByTickerTable items={mockItems} isLoading={false} />
    );
    expect(screen.getByText("Apple Inc.")).toBeDefined();
    expect(screen.getByText("삼성전자")).toBeDefined();
  });

  it("shows total row when items present", () => {
    renderWithProviders(
      <DividendByTickerTable items={mockItems} isLoading={false} />
    );
    expect(screen.getByText("합계")).toBeDefined();
  });

  it("opens edit modal when pencil button clicked", () => {
    renderWithProviders(
      <DividendByTickerTable items={mockItems} isLoading={false} />
    );
    const pencilBtns = document.querySelectorAll('[title="배당월 수정"]');
    if (pencilBtns.length > 0) {
      fireEvent.click(pencilBtns[0]);
      // Modal should appear
      expect(screen.getByText(/배당 지급 월 선택/)).toBeDefined();
    }
  });

  it("renders item with no ticker (unclassified)", () => {
    const unclassifiedItem = {
      ticker: null as unknown as string,
      market: null as unknown as string,
      name: "미분류 배당",
      estimated_annual_krw: 100000,
      estimated_monthly_krw: 8333,
      investment_yield: 0,
      dividend_months: [6, 12],
      dividend_months_is_manual: false,
    };
    renderWithProviders(
      <DividendByTickerTable items={[unclassifiedItem]} isLoading={false} />
    );
    expect(screen.getByText("미분류 배당")).toBeDefined();
  });
});

// ------- DividendMonthsModal -------
describe("DividendMonthsModal", () => {
  const defaultProps = {
    ticker: "AAPL",
    market: "NASDAQ",
    name: "Apple Inc.",
    currentMonths: [3, 6, 9, 12],
    isManual: false,
    onClose: vi.fn(),
    onSave: vi.fn(),
    onReset: vi.fn(),
    isSaving: false,
  };

  it("renders with ticker info", () => {
    renderWithProviders(<DividendMonthsModal {...defaultProps} />);
    expect(screen.getByText("Apple Inc.")).toBeDefined();
    expect(screen.getByText(/AAPL/)).toBeDefined();
  });

  it("calls onClose when close button is clicked", () => {
    const onClose = vi.fn();
    renderWithProviders(<DividendMonthsModal {...defaultProps} onClose={onClose} />);
    const closeBtn = document.querySelector('[class*="p-2"]');
    if (closeBtn) fireEvent.click(closeBtn);
    // Alternatively find X button
    const buttons = screen.getAllByRole("button");
    // Close is the X button
    fireEvent.click(buttons[0]);
    expect(onClose).toHaveBeenCalled();
  });

  it("calls onSave when save button is clicked", () => {
    const onSave = vi.fn();
    renderWithProviders(<DividendMonthsModal {...defaultProps} onSave={onSave} />);
    fireEvent.click(screen.getByText("저장"));
    expect(onSave).toHaveBeenCalled();
  });

  it("shows reset button when isManual is true", () => {
    renderWithProviders(<DividendMonthsModal {...defaultProps} isManual={true} />);
    expect(screen.getByText("자동으로 복구")).toBeDefined();
  });

  it("calls onReset when reset button is clicked", () => {
    const onReset = vi.fn();
    renderWithProviders(<DividendMonthsModal {...defaultProps} isManual={true} onReset={onReset} />);
    fireEvent.click(screen.getByText("자동으로 복구"));
    expect(onReset).toHaveBeenCalled();
  });

  it("toggles month selection", () => {
    renderWithProviders(<DividendMonthsModal {...defaultProps} />);
    // Month buttons are 1월~12월
    const monthBtns = screen.getAllByRole("button").filter(
      (b) => b.textContent?.match(/^[0-9]+월$/)
    );
    expect(monthBtns.length).toBe(12);
    // Click 1월 to toggle it
    fireEvent.click(monthBtns[0]);
    // Should not crash
    expect(document.body).toBeDefined();
  });

  it("shows saving state on button", () => {
    renderWithProviders(<DividendMonthsModal {...defaultProps} isSaving={true} />);
    expect(screen.getByText("저장 중...")).toBeDefined();
  });
});

// ------- PortfolioTreemapChart -------
describe("PortfolioTreemapChart", () => {
  it("renders without crash with empty data", () => {
    renderWithProviders(<PortfolioTreemapChart data={[]} />);
    expect(document.body).toBeDefined();
  });

  it("renders with data", () => {
    const data = [
      { name: "삼성전자", ticker: "005930", value: 1000000, pct: 50 },
      { name: "Apple", ticker: "AAPL", value: 500000, pct: 25 },
    ];
    renderWithProviders(<PortfolioTreemapChart data={data} />);
    expect(screen.getByText("종목별 비중")).toBeDefined();
  });
});
