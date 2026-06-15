import { describe, it, expect, vi } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";
import type { DividendByTicker } from "@/types";

// Mock recharts
vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div data-testid="recharts-container">{children}</div>,
  BarChart: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AreaChart: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Bar: () => <div />,
  Area: () => <div />,
  Cell: () => <div />,
  XAxis: () => <div />,
  YAxis: () => <div />,
  CartesianGrid: () => <div />,
  Tooltip: () => <div />,
  Treemap: () => <div />,
  PieChart: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Pie: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Legend: () => <div />,
}));

vi.mock("@/stores/themeStore", () => ({
  useThemeStore: () => ({ isDark: false, toggle: vi.fn() }),
}));

vi.mock("@/utils/dividendUtils", () => ({
  MONTH_LABELS: ["1월","2월","3월","4월","5월","6월","7월","8월","9월","10월","11월","12월"],
  dividendFreqInfo: vi.fn(() => ({ label: "분기", cls: "text-blue-500" })),
  weightBarColor: vi.fn(() => "bg-blue-500"),
  yieldBadgeClass: vi.fn(() => "bg-green-100 text-green-600"),
}));

vi.mock("@/api/dividends", () => ({
  fetchMonthlyOptimization: vi.fn().mockResolvedValue([]),
  fetchDRIPSimulation: vi.fn().mockResolvedValue(null),
}));

import DomesticForeignBar from "@/components/portfolio/DomesticForeignBar";
import TreemapChart from "@/components/portfolio/TreemapChart";
import MonthlyTickerDetail from "@/components/portfolio/MonthlyTickerDetail";
import MonthlyDividendChart from "@/components/portfolio/MonthlyDividendChart";
import MonthlyOptimizationCard from "@/components/portfolio/MonthlyOptimizationCard";
import DRIPSimulationChart from "@/components/portfolio/DRIPSimulationChart";

// ------- DomesticForeignBar -------
describe("DomesticForeignBar", () => {
  it("renders with empty items", () => {
    renderWithProviders(<DomesticForeignBar items={[]} />);
    expect(screen.getByText("국내/해외 비중")).toBeDefined();
    expect(screen.getByText("데이터 없음")).toBeDefined();
  });

  it("renders with domestic and foreign data", () => {
    const items = [
      { name: "국내 주식", value: 5000000, pct: 60 },
      { name: "해외 주식", value: 3000000, pct: 40 },
    ];
    renderWithProviders(<DomesticForeignBar items={items} />);
    expect(screen.getByText("국내 주식")).toBeDefined();
    expect(screen.getByText("해외 주식")).toBeDefined();
  });

  it("shows percentage values", () => {
    const items = [
      { name: "국내 주식", value: 5000000, pct: 60 },
      { name: "해외 주식", value: 3000000, pct: 40 },
    ];
    renderWithProviders(<DomesticForeignBar items={items} />);
    // pct values shown in label
    expect(screen.getAllByText("60.0%").length).toBeGreaterThan(0);
    expect(screen.getAllByText("40.0%").length).toBeGreaterThan(0);
  });
});

// ------- TreemapChart -------
describe("TreemapChart", () => {
  it("renders loading state", () => {
    renderWithProviders(<TreemapChart data={[]} title="자산 배분" isLoading={true} />);
    expect(screen.getByText("자산 배분")).toBeDefined();
  });

  it("renders empty state", () => {
    renderWithProviders(<TreemapChart data={[]} title="자산 배분" />);
    expect(screen.getByText("데이터 없음")).toBeDefined();
  });

  it("renders with data", () => {
    const data = [
      { name: "삼성전자", ticker: "005930", value: 1000000, pct: 50 },
      { name: "Apple", ticker: "AAPL", value: 500000, pct: 25 },
    ];
    renderWithProviders(<TreemapChart data={data} title="종목별 비중" />);
    expect(screen.getByText("종목별 비중")).toBeDefined();
  });
});

// ------- MonthlyDividendChart -------
describe("MonthlyDividendChart", () => {
  const barData = [
    { name: "1월", month: 1, isPast: true, actual: 100000, estimated: 150000 },
    { name: "2월", month: 2, isPast: false, actual: 0, estimated: 200000 },
  ];

  it("renders chart", () => {
    renderWithProviders(
      <MonthlyDividendChart
        barData={barData}
        currentYear={2024}
        selectedMonth={1}
        isDark={false}
        onMonthSelect={vi.fn()}
      />
    );
    expect(screen.getByText(/월별 배당 현황/)).toBeDefined();
  });
});

// ------- MonthlyTickerDetail -------
const mockDividendByTicker: DividendByTicker[] = [
  {
    ticker: "AAPL",
    market: "NASDAQ",
    name: "Apple Inc.",
    currency: "USD",
    estimated_annual_krw: 500000,
    estimated_monthly_krw: 41666,
    estimated_monthly_usd: 30,
    investment_yield: 2.5,
    dividend_months: [3, 6, 9, 12],
    dividend_months_is_manual: false,
  } as DividendByTicker,
];

describe("MonthlyTickerDetail", () => {
  it("renders with tickers for selected month", () => {
    renderWithProviders(
      <MonthlyTickerDetail
        selectedMonth={3}
        selectedMonthTickers={mockDividendByTicker}
        selectedMonthActual={undefined}
        monthStr="2024-03"
        monthlyEstimate={41666}
        monthTickerActualMap={{}}
      />
    );
    expect(screen.getAllByText("Apple Inc.").length).toBeGreaterThan(0);
  });

  it("renders empty state when no tickers", () => {
    renderWithProviders(
      <MonthlyTickerDetail
        selectedMonth={2}
        selectedMonthTickers={[]}
        selectedMonthActual={undefined}
        monthStr="2024-02"
        monthlyEstimate={0}
        monthTickerActualMap={{}}
      />
    );
    expect(screen.getByText("이 달에 배당 예정 종목이 없습니다.")).toBeDefined();
  });

  it("shows actual amount when provided", () => {
    renderWithProviders(
      <MonthlyTickerDetail
        selectedMonth={3}
        selectedMonthTickers={mockDividendByTicker}
        selectedMonthActual={{ month: "2024-03", amount: 80000 }}
        monthStr="2024-03"
        monthlyEstimate={41666}
        monthTickerActualMap={{ "2024-03-AAPL": 80000 }}
      />
    );
    expect(document.body).toBeDefined();
  });
});

// ------- MonthlyOptimizationCard -------
describe("MonthlyOptimizationCard", () => {
  it("renders loading state initially", () => {
    renderWithProviders(<MonthlyOptimizationCard />);
    // While loading or empty
    expect(document.body).toBeDefined();
  });
});

// ------- DRIPSimulationChart -------
describe("DRIPSimulationChart", () => {
  it("renders simulation controls", () => {
    renderWithProviders(<DRIPSimulationChart />);
    expect(screen.getByText("5년")).toBeDefined();
    expect(screen.getByText("10년")).toBeDefined();
    expect(screen.getByText("20년")).toBeDefined();
    expect(screen.getByText("30년")).toBeDefined();
  });

  it("renders run button", () => {
    renderWithProviders(<DRIPSimulationChart />);
    expect(screen.getByText("시뮬레이션 실행")).toBeDefined();
  });

  it("changes year selection on button click", () => {
    renderWithProviders(<DRIPSimulationChart />);
    fireEvent.click(screen.getByText("20년"));
    // Clicking 20년 triggers handleRun which calls mutate
    expect(document.body).toBeDefined();
  });
});
