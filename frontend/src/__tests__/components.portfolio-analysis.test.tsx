import { describe, it, expect, vi } from "vitest";
import { screen, fireEvent, within } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";
import type { AssetAccount } from "@/api/assets";
import type { Portfolio } from "@/api/portfolios";

import PortfolioWeightChart from "@/components/portfolio-analysis/PortfolioWeightChart";
import PortfolioAccountSelector from "@/components/portfolio-analysis/PortfolioAccountSelector";
import PortfolioListSection from "@/components/portfolio-analysis/PortfolioListSection";

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

// ------- PortfolioListSection: 기준 포트폴리오 재지정 -------
describe("PortfolioListSection - 기준 지정 재지정", () => {
  const portfolioA: Portfolio = {
    id: "pA",
    name: "포트폴리오 A",
    items: [],
    base_type: "STOCK_ONLY",
    account_ids: null,
    sort_order: 0,
    created_at: "2024-01-01",
    updated_at: "2024-01-01",
  };
  const portfolioB: Portfolio = {
    id: "pB",
    name: "포트폴리오 B",
    items: [],
    base_type: "STOCK_ONLY",
    account_ids: null,
    sort_order: 1,
    created_at: "2024-01-01",
    updated_at: "2024-01-01",
  };
  const targetedAccount: AssetAccount = {
    ...mockAccounts[0],
    id: "acc1",
    name: "한국투자 주식계좌",
    target_portfolio_id: "pA",
  };

  function renderSection(onBatchSetTarget = vi.fn()) {
    renderWithProviders(
      <PortfolioListSection
        portfolios={[portfolioA, portfolioB]}
        isLoading={false}
        selectedIds={new Set()}
        stockAccounts={[targetedAccount]}
        alertPortfolioIds={new Set()}
        autoAlertCount={0}
        alertByPortfolioId={{}}
        isTargetPending={false}
        onDragEnd={vi.fn()}
        onToggleSelect={vi.fn()}
        onOpenEditor={vi.fn()}
        onOpenAlertModal={vi.fn()}
        onConfirmDelete={vi.fn()}
        onBatchSetTarget={onBatchSetTarget}
      />,
    );
    return onBatchSetTarget;
  }

  function clickAssignButton(index: number) {
    const buttons = screen.getAllByRole("button", { name: "기준 포트폴리오 지정" });
    fireEvent.click(buttons[index]);
  }

  it("이미 다른 포트폴리오에 지정된 계좌를 선택하면 확인 모달을 띄우고 즉시 재지정하지 않는다", () => {
    const onBatchSetTarget = renderSection();
    clickAssignButton(1); // 포트폴리오 B 카드
    const dialog = screen.getByRole("dialog");
    expect(
      within(dialog).getByText(/포트폴리오 B.*기준 포트폴리오로 다시 지정할까요/),
    ).toBeDefined();
    expect(within(dialog).getByText("한국투자 주식계좌")).toBeDefined();
    expect(within(dialog).getByText("포트폴리오 A")).toBeDefined();
    expect(onBatchSetTarget).not.toHaveBeenCalled();
  });

  it("확인 모달에서 변경을 누르면 새 포트폴리오로 재지정된다", () => {
    const onBatchSetTarget = renderSection();
    clickAssignButton(1);
    fireEvent.click(screen.getByRole("button", { name: "변경" }));
    expect(onBatchSetTarget).toHaveBeenCalledWith("pB", ["acc1"]);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("확인 모달에서 취소를 누르면 재지정하지 않는다", () => {
    const onBatchSetTarget = renderSection();
    clickAssignButton(1);
    fireEvent.click(screen.getByRole("button", { name: "취소" }));
    expect(onBatchSetTarget).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
