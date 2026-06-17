import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import TransactionHistoryTab from "@/components/assets/TransactionHistoryTab";
import { renderWithProviders } from "@/test/renderWithProviders";
import type { AssetAccount } from "@/api/assets";

vi.mock("../api/transactions", () => ({
  fetchTransactions: vi.fn().mockResolvedValue([]),
  deleteTransaction: vi.fn().mockResolvedValue({}),
}));

vi.mock("../api/assets", () => ({
  updateAccount: vi.fn().mockResolvedValue({}),
}));

vi.mock("../utils/queryInvalidation", () => ({
  invalidateTransactionData: vi.fn(),
  invalidateAccountData: vi.fn(),
}));

vi.mock("../utils/toast", () => ({
  toast: vi.fn(),
}));

vi.mock("@tanstack/react-virtual", () => ({
  useVirtualizer: () => ({
    getVirtualItems: () => [],
    getTotalSize: () => 0,
  }),
}));

// TransactionForm은 별도 테스트 — 여기서는 mock
vi.mock("../components/assets/TransactionForm", () => ({
  TransactionForm: () => <div data-testid="mock-transaction-form" />,
}));

const mockAccounts: AssetAccount[] = [
  {
    id: "acc-1",
    name: "국내 증권계좌",
    asset_type: "STOCK_KIS",
    data_source: "KIS_API",
    institution: "한국투자증권",
    kis_account_no: null,
    kiwoom_account_no: null,
    is_mock_mode: false,
    manual_amount: null,
    manual_currency: "KRW",
    manual_updated_at: null,
    deposit_krw: 1_000_000,
    deposit_usd: null,
    real_estate_details: null,
    include_in_total: true,
    is_active: true,
    sort_order: 0,
    notes: null,
    created_at: "2026-01-01T00:00:00Z",
    has_own_kis_credentials: false,
    has_own_kiwoom_credentials: false,
  },
  {
    id: "acc-2",
    name: "은행 계좌",
    asset_type: "BANK_ACCOUNT",
    data_source: "OPEN_BANKING",
    institution: "국민은행",
    kis_account_no: null,
    kiwoom_account_no: null,
    is_mock_mode: false,
    manual_amount: null,
    manual_currency: "KRW",
    manual_updated_at: null,
    deposit_krw: null,
    deposit_usd: null,
    real_estate_details: null,
    include_in_total: true,
    is_active: true,
    sort_order: 1,
    notes: null,
    created_at: "2026-01-01T00:00:00Z",
    has_own_kis_credentials: false,
    has_own_kiwoom_credentials: false,
  },
];

describe("TransactionHistoryTab", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("연도 선택 드롭다운이 현재 연도로 초기화된다", () => {
    const currentYear = new Date().getFullYear();
    renderWithProviders(<TransactionHistoryTab accounts={mockAccounts} />);
    const yearSelect = screen.getByDisplayValue(`${currentYear}년`);
    expect(yearSelect).toBeInTheDocument();
  });

  it("계좌 필터 드롭다운에 '전체 계좌' 옵션이 있다", () => {
    renderWithProviders(<TransactionHistoryTab accounts={mockAccounts} />);
    expect(screen.getByText("전체 계좌")).toBeInTheDocument();
  });

  it("계좌 필터 드롭다운에 계좌 목록이 표시된다", () => {
    renderWithProviders(<TransactionHistoryTab accounts={mockAccounts} />);
    expect(screen.getByText("국내 증권계좌")).toBeInTheDocument();
    expect(screen.getByText("은행 계좌")).toBeInTheDocument();
  });

  it("거래 유형 필터 드롭다운에 입금/출금/배당 옵션이 있다", () => {
    renderWithProviders(<TransactionHistoryTab accounts={mockAccounts} />);
    expect(screen.getByText("입금")).toBeInTheDocument();
    expect(screen.getByText("출금")).toBeInTheDocument();
    expect(screen.getByText("배당")).toBeInTheDocument();
  });

  it("'내역 추가' 버튼 클릭 시 TransactionForm이 표시된다", async () => {
    renderWithProviders(<TransactionHistoryTab accounts={mockAccounts} />);
    const addBtn = screen.getByRole("button", { name: /내역 추가/ });
    fireEvent.click(addBtn);
    await waitFor(() => expect(screen.getByTestId("mock-transaction-form")).toBeInTheDocument());
  });

  it("'내역 추가' 버튼을 두 번 클릭하면 폼이 숨겨진다", async () => {
    renderWithProviders(<TransactionHistoryTab accounts={mockAccounts} />);
    const addBtn = screen.getByRole("button", { name: /내역 추가/ });
    fireEvent.click(addBtn);
    await waitFor(() => expect(screen.getByTestId("mock-transaction-form")).toBeInTheDocument());
    fireEvent.click(addBtn);
    await waitFor(() =>
      expect(screen.queryByTestId("mock-transaction-form")).not.toBeInTheDocument(),
    );
  });

  it("입금 합계와 배당 합계 카드가 렌더링된다", () => {
    const currentYear = new Date().getFullYear();
    renderWithProviders(<TransactionHistoryTab accounts={mockAccounts} />);
    expect(screen.getByText(`${currentYear}년 입금 합계`)).toBeInTheDocument();
    expect(screen.getByText(`${currentYear}년 배당 합계`)).toBeInTheDocument();
  });

  it("거래 데이터가 없으면 합계가 0원이다", async () => {
    renderWithProviders(<TransactionHistoryTab accounts={mockAccounts} />);
    await waitFor(() => {
      const zeros = screen.getAllByText("0원");
      expect(zeros.length).toBeGreaterThanOrEqual(2);
    });
  });

  it("연도를 변경하면 해당 연도로 필터가 변경된다", async () => {
    const { fetchTransactions } = await import("../api/transactions");
    renderWithProviders(<TransactionHistoryTab accounts={mockAccounts} />);
    const yearSelects = screen.getAllByRole("combobox");
    const yearSelect =
      yearSelects.find((el) => el.querySelector(`option[value="${new Date().getFullYear()}"]`)) ??
      yearSelects[yearSelects.length - 1];

    const prevYear = new Date().getFullYear() - 1;
    fireEvent.change(yearSelect, { target: { value: String(prevYear) } });

    await waitFor(() => {
      expect(vi.mocked(fetchTransactions)).toHaveBeenCalledWith(
        expect.objectContaining({ year: prevYear }),
      );
    });
  });
});
