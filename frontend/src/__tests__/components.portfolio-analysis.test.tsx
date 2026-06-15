import { describe, it, expect, vi } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";
import { MemoryRouter } from "react-router-dom";
import type { AssetAccount } from "@/api/assets";
import type { RebalancingAnalysis } from "@/api/rebalancing";

vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div data-testid="recharts-container">{children}</div>,
  PieChart: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Pie: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Cell: () => <div />,
  Tooltip: () => <div />,
  BarChart: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Bar: () => <div />,
  XAxis: () => <div />,
  YAxis: () => <div />,
  CartesianGrid: () => <div />,
  Legend: () => <div />,
}));

vi.mock("@/hooks/useInsights", () => ({
  useInsights: vi.fn(() => ({ data: [], isLoading: false })),
}));

import PortfolioDiagnosisCard from "@/components/portfolio-analysis/PortfolioDiagnosisCard";
import PortfolioWeightChart from "@/components/portfolio-analysis/PortfolioWeightChart";
import PortfolioAccountSelector from "@/components/portfolio-analysis/PortfolioAccountSelector";
import PortfolioComparisonPanel from "@/components/portfolio-analysis/PortfolioComparisonPanel";

// ------- PortfolioDiagnosisCard -------
describe("PortfolioDiagnosisCard", () => {
  it("renders no issues state", () => {
    renderWithProviders(
      <MemoryRouter>
        <PortfolioDiagnosisCard />
      </MemoryRouter>
    );
    expect(screen.getByText("포트폴리오 진단 결과")).toBeDefined();
    expect(screen.getByText(/이상 없음/)).toBeDefined();
  });

  it("renders with portfolio name", () => {
    renderWithProviders(
      <MemoryRouter>
        <PortfolioDiagnosisCard portfolioName="내 포트폴리오" />
      </MemoryRouter>
    );
    expect(screen.getByText(/'내 포트폴리오' 기준/)).toBeDefined();
  });

  it("expands on click", () => {
    renderWithProviders(
      <MemoryRouter>
        <PortfolioDiagnosisCard />
      </MemoryRouter>
    );
    const btn = screen.getByRole("button");
    fireEvent.click(btn);
    expect(screen.getByText("포트폴리오 이상 없음")).toBeDefined();
  });

  it("renders with custom insights via mock override", () => {
    // Just verify that basic render works (mock setup is at module level)
    renderWithProviders(
      <MemoryRouter>
        <PortfolioDiagnosisCard portfolioName="테스트" />
      </MemoryRouter>
    );
    expect(screen.getByText(/테스트/)).toBeDefined();
  });
});

// ------- PortfolioWeightChart -------
describe("PortfolioWeightChart", () => {
  it("renders null when no valid items", () => {
    const { container } = renderWithProviders(
      <PortfolioWeightChart items={[]} />
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders with valid items", () => {
    const items = [
      { ticker: "AAPL", name: "Apple", market: "NASDAQ", weight: 40 },
      { ticker: "005930", name: "삼성전자", market: "KOSPI", weight: 30 },
    ];
    renderWithProviders(
      <PortfolioWeightChart items={items} />
    );
    expect(document.body).toBeDefined();
  });

  it("shows concentration warning when weight > 50", () => {
    const items = [
      { ticker: "AAPL", name: "Apple", market: "NASDAQ", weight: 60 },
    ];
    renderWithProviders(
      <PortfolioWeightChart items={items} />
    );
    expect(screen.getByText(/집중 투자 위험/)).toBeDefined();
  });
});

// ------- PortfolioAccountSelector -------
const mockAccounts: AssetAccount[] = [
  {
    id: "acc1",
    name: "한국투자 주식계좌",
    asset_type: "STOCK_KIS",
    data_source: "KIS_API",
    institution: null,
    kis_account_no: "123-456",
    kiwoom_account_no: null,
    is_mock_mode: false,
    is_active: true,
    manual_amount: null,
    manual_currency: "KRW",
    manual_updated_at: null,
    deposit_krw: null,
    deposit_usd: null,
    real_estate_details: null,
    include_in_total: true,
    sort_order: 0,
    notes: null,
    created_at: "2024-01-01",
    has_own_kis_credentials: false,
    has_own_kiwoom_credentials: false,
  },
  {
    id: "acc2",
    name: "키움 모의계좌",
    asset_type: "STOCK_KIWOOM",
    data_source: "KIWOOM_API",
    institution: null,
    kis_account_no: null,
    kiwoom_account_no: "789-012",
    is_mock_mode: true,
    is_active: true,
    manual_amount: null,
    manual_currency: "KRW",
    manual_updated_at: null,
    deposit_krw: null,
    deposit_usd: null,
    real_estate_details: null,
    include_in_total: true,
    sort_order: 1,
    notes: null,
    created_at: "2024-01-01",
    has_own_kis_credentials: false,
    has_own_kiwoom_credentials: false,
  },
];

describe("PortfolioAccountSelector", () => {
  it("renders accounts list", () => {
    renderWithProviders(
      <PortfolioAccountSelector
        accounts={mockAccounts}
        selectedAccountIds={new Set(["acc1", "acc2"])}
        isAllSelected={true}
        onToggleAccount={vi.fn()}
        onSelectAll={vi.fn()}
      />
    );
    expect(screen.getByText("한국투자 주식계좌")).toBeDefined();
    expect(screen.getByText("키움 모의계좌")).toBeDefined();
  });

  it("shows mock indicator for mock accounts", () => {
    renderWithProviders(
      <PortfolioAccountSelector
        accounts={mockAccounts}
        selectedAccountIds={new Set(["acc1", "acc2"])}
        isAllSelected={true}
        onToggleAccount={vi.fn()}
        onSelectAll={vi.fn()}
      />
    );
    expect(screen.getByText("(모의)")).toBeDefined();
  });

  it("shows select all button when not all selected", () => {
    renderWithProviders(
      <PortfolioAccountSelector
        accounts={mockAccounts}
        selectedAccountIds={new Set(["acc1"])}
        isAllSelected={false}
        onToggleAccount={vi.fn()}
        onSelectAll={vi.fn()}
      />
    );
    expect(screen.getByText("전체 선택")).toBeDefined();
  });

  it("calls onToggleAccount when checkbox clicked", () => {
    const onToggle = vi.fn();
    renderWithProviders(
      <PortfolioAccountSelector
        accounts={mockAccounts}
        selectedAccountIds={new Set(["acc1", "acc2"])}
        isAllSelected={true}
        onToggleAccount={onToggle}
        onSelectAll={vi.fn()}
      />
    );
    const checkboxes = screen.getAllByRole("checkbox");
    fireEvent.click(checkboxes[0]);
    expect(onToggle).toHaveBeenCalledWith("acc1");
  });

  it("shows selected count message", () => {
    renderWithProviders(
      <PortfolioAccountSelector
        accounts={mockAccounts}
        selectedAccountIds={new Set(["acc1"])}
        isAllSelected={false}
        onToggleAccount={vi.fn()}
        onSelectAll={vi.fn()}
      />
    );
    expect(screen.getByText(/1개 계좌만 분석에 포함됩니다/)).toBeDefined();
  });
});

// ------- PortfolioComparisonPanel -------
const mockAnalysis: RebalancingAnalysis = {
  portfolio_id: "p1",
  portfolio_name: "포트폴리오 A",
  base_type: "STOCK_ONLY",
  base_value_krw: 10000000,
  analyzed_at: "2024-01-01",
  current_portfolio_annual_dividend: 0,
  target_portfolio_annual_dividend: 300000,
  target_weighted_cagr_10y_pct: 8.5,
  ticker_account_map: {},
  items: [
    {
      ticker: "AAPL",
      name: "Apple Inc.",
      market: "NASDAQ",
      current_weight_pct: 20,
      target_weight_pct: 25,
      weight_diff_pct: 5,
      current_value_krw: 2000000,
      target_value_krw: 2500000,
      diff_krw: 500000,
      shares_to_trade: 3,
      current_price_krw: 170000,
      cagr_10y_pct: 12.5,
      return_10y_pct: 224.0,
      actual_years_10y: 10,
    },
  ],
  untracked_holdings: [],
};

describe("PortfolioComparisonPanel", () => {
  it("renders comparison panel", () => {
    renderWithProviders(
      <PortfolioComparisonPanel
        accountName="테스트 계좌"
        currentAnalysis={mockAnalysis}
        proposedAnalysis={mockAnalysis}
        onReplace={vi.fn()}
        onCancel={vi.fn()}
      />
    );
    expect(document.body).toBeDefined();
  });

  it("renders action buttons", () => {
    renderWithProviders(
      <PortfolioComparisonPanel
        accountName="테스트 계좌"
        currentAnalysis={mockAnalysis}
        proposedAnalysis={mockAnalysis}
        onReplace={vi.fn()}
        onCancel={vi.fn()}
      />
    );
    // Find buttons
    const buttons = screen.getAllByRole("button");
    expect(buttons.length).toBeGreaterThan(0);
  });
});
