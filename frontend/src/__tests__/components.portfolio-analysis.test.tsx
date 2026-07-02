import { describe, it, expect, vi } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";
import type { AssetAccount } from "@/api/assets";

import PortfolioWeightChart from "@/components/portfolio-analysis/PortfolioWeightChart";
import PortfolioAccountSelector from "@/components/portfolio-analysis/PortfolioAccountSelector";

// ------- PortfolioWeightChart -------
describe("PortfolioWeightChart", () => {
  it("renders null when no valid items", () => {
    const { container } = renderWithProviders(<PortfolioWeightChart items={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders with valid items", () => {
    const items = [
      { ticker: "AAPL", name: "Apple", market: "NASDAQ", weight: 40 },
      { ticker: "005930", name: "삼성전자", market: "KOSPI", weight: 30 },
    ];
    renderWithProviders(<PortfolioWeightChart items={items} />);
    expect(document.body).toBeDefined();
  });

  it("shows concentration warning when weight > 50", () => {
    const items = [{ ticker: "AAPL", name: "Apple", market: "NASDAQ", weight: 60 }];
    renderWithProviders(<PortfolioWeightChart items={items} />);
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
      />,
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
      />,
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
      />,
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
      />,
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
      />,
    );
    expect(screen.getByText(/1개 계좌만 분석에 포함됩니다/)).toBeDefined();
  });
});

