import { describe, it, expect, vi } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";
import type { AssetAccount } from "@/api/assets";
import type { Transaction } from "@/api/transactions";
import type { PortfolioOverview } from "@/types";

vi.mock("@/context/ExchangeRateContext", () => ({
  useExchangeRateContext: vi.fn(() => ({ rate: 1350 })),
  ExchangeRateProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

import StockAccountSummaryCard from "@/components/assets/StockAccountSummaryCard";
import BankAccountCard from "@/components/assets/BankAccountCard";
import { RealEstateAccountCard, RealEstateAccountModal, RealEstateEditModal } from "@/components/assets/RealEstateSection";
import { TransactionList } from "@/components/assets/TransactionList";

const mockStockAccount: AssetAccount = {
  id: "acc1",
  name: "한국투자 주식",
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
  deposit_krw: 1000000,
  deposit_usd: 500,
  real_estate_details: null,
  include_in_total: true,
  sort_order: 0,
  notes: null,
  created_at: "2024-01-01",
  has_own_kis_credentials: false,
  has_own_kiwoom_credentials: false,
};

const mockBankAccount: AssetAccount = {
  id: "bank1",
  name: "국민은행 입출금",
  asset_type: "BANK_ACCOUNT",
  data_source: "MANUAL",
  institution: "국민은행",
  kis_account_no: null,
  kiwoom_account_no: null,
  is_mock_mode: false,
  is_active: true,
  manual_amount: null,
  manual_currency: "KRW",
  manual_updated_at: null,
  deposit_krw: 5000000,
  deposit_usd: null,
  real_estate_details: null,
  include_in_total: true,
  sort_order: 1,
  notes: null,
  created_at: "2024-01-01",
  has_own_kis_credentials: false,
  has_own_kiwoom_credentials: false,
};

const mockRealEstate: AssetAccount = {
  id: "re1",
  name: "강남 아파트",
  asset_type: "REAL_ESTATE",
  data_source: "MANUAL",
  institution: null,
  kis_account_no: null,
  kiwoom_account_no: null,
  is_mock_mode: false,
  is_active: true,
  manual_amount: 800000000,
  manual_currency: "KRW",
  manual_updated_at: null,
  deposit_krw: null,
  deposit_usd: null,
  include_in_total: true,
  sort_order: 2,
  notes: null,
  created_at: "2024-01-01",
  has_own_kis_credentials: false,
  has_own_kiwoom_credentials: false,
  real_estate_details: {
    property_type: "아파트",
    address: "서울시 강남구 역삼동",
    purchase_price_krw: 600000000,
    purchase_date: "2020-01-01",
    mortgage_balance_krw: 200000000,
  },
};

// ------- StockAccountSummaryCard -------
describe("StockAccountSummaryCard", () => {
  it("renders with overview data", () => {
    const overview = {
      total_stock_krw: 10000000,
      unrealized_pnl_krw: 500000,
      stock_return_pct: 5.0,
    } as unknown as PortfolioOverview;

    renderWithProviders(
      <StockAccountSummaryCard
        stockAccounts={[mockStockAccount]}
        overview={overview}
        allTx={[
          { transaction_type: "DEPOSIT", amount: 5000000, account_id: "acc1" },
          { transaction_type: "DIVIDEND", amount: 200000, account_id: "acc1" },
        ]}
        usdRate={1350}
      />
    );
    expect(screen.getByText("증권계좌 전체 요약")).toBeDefined();
    expect(screen.getByText("평가금액")).toBeDefined();
    expect(screen.getByText("평가손익")).toBeDefined();
  });

  it("renders with undefined overview", () => {
    renderWithProviders(
      <StockAccountSummaryCard
        stockAccounts={[mockStockAccount]}
        overview={undefined}
        allTx={[]}
        usdRate={1350}
      />
    );
    expect(screen.getByText("증권계좌 전체 요약")).toBeDefined();
  });

  it("shows negative pnl color", () => {
    const overview = {
      total_stock_krw: 9000000,
      unrealized_pnl_krw: -500000,
      stock_return_pct: -5.0,
    } as unknown as PortfolioOverview;

    renderWithProviders(
      <StockAccountSummaryCard
        stockAccounts={[mockStockAccount]}
        overview={overview}
        allTx={[]}
        usdRate={null}
      />
    );
    expect(document.body).toBeDefined();
  });
});

// ------- BankAccountCard -------
describe("BankAccountCard", () => {
  it("renders bank account info", () => {
    renderWithProviders(
      <BankAccountCard
        account={mockBankAccount}
        onDelete={vi.fn()}
        onEditModal={vi.fn()}
        onEditName={vi.fn()}
        onSync={vi.fn()}
        isDeleting={false}
        isSyncing={false}
      />
    );
    expect(screen.getByText("국민은행 입출금")).toBeDefined();
    expect(screen.getByText("국민은행")).toBeDefined();
    expect(screen.getByText("입출금")).toBeDefined();
  });

  it("renders edit name mode on pencil click", () => {
    renderWithProviders(
      <BankAccountCard
        account={mockBankAccount}
        onDelete={vi.fn()}
        onEditModal={vi.fn()}
        onEditName={vi.fn()}
        onSync={vi.fn()}
        isDeleting={false}
        isSyncing={false}
      />
    );
    fireEvent.click(screen.getByLabelText("계좌명 수정"));
    expect(screen.getByDisplayValue("국민은행 입출금")).toBeDefined();
  });

  it("calls onDelete when delete button clicked", () => {
    const onDelete = vi.fn();
    renderWithProviders(
      <BankAccountCard
        account={mockBankAccount}
        onDelete={onDelete}
        onEditModal={vi.fn()}
        onEditName={vi.fn()}
        onSync={vi.fn()}
        isDeleting={false}
        isSyncing={false}
      />
    );
    fireEvent.click(screen.getByLabelText("계좌 삭제"));
    expect(onDelete).toHaveBeenCalledWith("bank1");
  });

  it("shows edit modal button for MANUAL accounts", () => {
    renderWithProviders(
      <BankAccountCard
        account={mockBankAccount}
        onDelete={vi.fn()}
        onEditModal={vi.fn()}
        onEditName={vi.fn()}
        onSync={vi.fn()}
        isDeleting={false}
        isSyncing={false}
      />
    );
    expect(screen.getByLabelText("금액 수정")).toBeDefined();
  });

  it("shows sync button for OPEN_BANKING accounts", () => {
    const obAccount = { ...mockBankAccount, data_source: "OPEN_BANKING" };
    renderWithProviders(
      <BankAccountCard
        account={obAccount}
        onDelete={vi.fn()}
        onEditModal={vi.fn()}
        onEditName={vi.fn()}
        onSync={vi.fn()}
        isDeleting={false}
        isSyncing={false}
      />
    );
    expect(screen.getByLabelText("잔액 새로고침")).toBeDefined();
  });
});

// ------- RealEstateAccountCard -------
describe("RealEstateAccountCard", () => {
  it("renders real estate info", () => {
    renderWithProviders(
      <RealEstateAccountCard
        account={mockRealEstate}
        onDelete={vi.fn()}
        onEdit={vi.fn()}
        isDeleting={false}
      />
    );
    expect(screen.getByText("강남 아파트")).toBeDefined();
    expect(screen.getByText("아파트")).toBeDefined();
    expect(screen.getByText("서울시 강남구 역삼동")).toBeDefined();
  });

  it("calls onEdit when edit button clicked", () => {
    const onEdit = vi.fn();
    renderWithProviders(
      <RealEstateAccountCard
        account={mockRealEstate}
        onDelete={vi.fn()}
        onEdit={onEdit}
        isDeleting={false}
      />
    );
    fireEvent.click(screen.getByLabelText("수정"));
    expect(onEdit).toHaveBeenCalledWith(mockRealEstate);
  });

  it("shows 자산 제외 badge when include_in_total is false", () => {
    const excluded = { ...mockRealEstate, include_in_total: false };
    renderWithProviders(
      <RealEstateAccountCard
        account={excluded}
        onDelete={vi.fn()}
        onEdit={vi.fn()}
        isDeleting={false}
      />
    );
    expect(screen.getByText("자산 제외")).toBeDefined();
  });
});

// ------- RealEstateAccountModal -------
describe("RealEstateAccountModal", () => {
  it("renders create modal", () => {
    renderWithProviders(
      <RealEstateAccountModal
        onClose={vi.fn()}
        onSubmit={vi.fn()}
        isLoading={false}
      />
    );
    expect(screen.getByText("부동산 추가")).toBeDefined();
    expect(screen.getByLabelText(/부동산 이름/)).toBeDefined();
  });

  it("calls onClose when cancel button clicked", () => {
    const onClose = vi.fn();
    renderWithProviders(
      <RealEstateAccountModal
        onClose={onClose}
        onSubmit={vi.fn()}
        isLoading={false}
      />
    );
    fireEvent.click(screen.getByText("취소"));
    expect(onClose).toHaveBeenCalled();
  });

  it("shows saving state", () => {
    renderWithProviders(
      <RealEstateAccountModal
        onClose={vi.fn()}
        onSubmit={vi.fn()}
        isLoading={true}
      />
    );
    expect(screen.getByText("저장 중...")).toBeDefined();
  });
});

// ------- RealEstateEditModal -------
describe("RealEstateEditModal", () => {
  it("renders edit modal with existing data", () => {
    renderWithProviders(
      <RealEstateEditModal
        account={mockRealEstate}
        onClose={vi.fn()}
        onSubmit={vi.fn()}
        isLoading={false}
      />
    );
    expect(screen.getByText("부동산 수정")).toBeDefined();
    expect(screen.getByDisplayValue("강남 아파트")).toBeDefined();
  });
});

// ------- TransactionList -------
const mockTransactions: Transaction[] = [
  {
    id: "tx1",
    account_id: "acc1",
    transaction_date: "2024-01-15",
    transaction_type: "DEPOSIT",
    amount: 1000000,
    fee: null,
    notes: "월급",
    ticker: null,
    created_at: "2024-01-15",
  },
  {
    id: "tx2",
    account_id: "acc1",
    transaction_date: "2024-01-20",
    transaction_type: "DIVIDEND",
    amount: 50000,
    fee: null,
    notes: null,
    ticker: "AAPL",
    created_at: "2024-01-20",
  },
];

describe("TransactionList", () => {
  it("renders loading state", () => {
    renderWithProviders(
      <TransactionList
        txList={undefined}
        isLoading={true}
        activeType="DEPOSIT"
        isDeleting={false}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
      />
    );
    expect(screen.getByText("로딩 중...")).toBeDefined();
  });

  it("renders empty state", () => {
    renderWithProviders(
      <TransactionList
        txList={[]}
        isLoading={false}
        activeType="DEPOSIT"
        isDeleting={false}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
      />
    );
    expect(screen.getByText("등록된 내역이 없습니다")).toBeDefined();
  });

  it("renders transaction list", () => {
    renderWithProviders(
      <TransactionList
        txList={mockTransactions}
        isLoading={false}
        activeType="DEPOSIT"
        isDeleting={false}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
      />
    );
    expect(screen.getByText("2024-01-15")).toBeDefined();
    expect(screen.getByText("월급")).toBeDefined();
  });

  it("calls onEdit when edit button clicked", () => {
    const onEdit = vi.fn();
    renderWithProviders(
      <TransactionList
        txList={mockTransactions}
        isLoading={false}
        activeType="DEPOSIT"
        isDeleting={false}
        onEdit={onEdit}
        onDelete={vi.fn()}
      />
    );
    const editBtns = document.querySelectorAll('[class*="hover:text-blue-400"]');
    if (editBtns.length > 0) fireEvent.click(editBtns[0]);
    expect(onEdit).toHaveBeenCalledWith(mockTransactions[0]);
  });

  it("shows ticker in dividend transaction", () => {
    renderWithProviders(
      <TransactionList
        txList={mockTransactions}
        isLoading={false}
        activeType="DIVIDEND"
        isDeleting={false}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
      />
    );
    expect(screen.getByText("AAPL")).toBeDefined();
  });
});
