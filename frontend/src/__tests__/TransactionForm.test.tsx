import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { TransactionForm } from "../components/assets/TransactionForm";
import { renderWithProviders } from "../test/renderWithProviders";
import type { AssetAccount } from "../api/assets";

vi.mock("../hooks/useExchangeRate", () => ({
  useExchangeRate: () => 1350,
}));

vi.mock("../hooks/useStockSearch", () => ({
  useStockSearch: () => ({
    suggestions: [],
    isSearching: false,
    search: vi.fn(),
    clearSuggestions: vi.fn(),
  }),
}));

vi.mock("../api/transactions", () => ({
  createTransaction: vi.fn().mockResolvedValue({ id: "tx-1" }),
  updateTransaction: vi.fn().mockResolvedValue({ id: "tx-1" }),
}));

vi.mock("../api/client", () => ({
  api: {
    get: vi.fn().mockResolvedValue({ data: { positions: [] } }),
  },
}));

vi.mock("../utils/queryInvalidation", () => ({
  invalidateTransactionData: vi.fn(),
}));

vi.mock("../utils/toast", () => ({
  toast: vi.fn(),
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
    deposit_krw: null,
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
];

const defaultProps = {
  accounts: mockAccounts,
  editingTx: null,
  onSuccess: vi.fn(),
  onCancel: vi.fn(),
};

describe("TransactionForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("폼 초기 상태에서 거래 유형 버튼을 렌더링한다", () => {
    renderWithProviders(<TransactionForm {...defaultProps} />);
    expect(screen.getByText("입금")).toBeInTheDocument();
    expect(screen.getByText("출금")).toBeInTheDocument();
    expect(screen.getByText("배당")).toBeInTheDocument();
  });

  it("계좌 선택 드롭다운에 계좌 목록이 표시된다", () => {
    renderWithProviders(<TransactionForm {...defaultProps} />);
    expect(screen.getByText("국내 증권계좌")).toBeInTheDocument();
  });

  it("취소 버튼 클릭 시 onCancel을 호출한다", () => {
    renderWithProviders(<TransactionForm {...defaultProps} />);
    const cancelBtn = screen.getByRole("button", { name: "취소" });
    fireEvent.click(cancelBtn);
    expect(defaultProps.onCancel).toHaveBeenCalledOnce();
  });

  it("금액이 0이면 submit 버튼이 비활성화된다", () => {
    renderWithProviders(<TransactionForm {...defaultProps} />);
    const submitBtn = screen.getByRole("button", { name: "추가" });
    expect(submitBtn).toBeDisabled();
  });

  it("출금 탭 클릭 시 거래 유형이 변경된다", () => {
    renderWithProviders(<TransactionForm {...defaultProps} />);
    const withdrawalBtn = screen.getByRole("button", { name: "출금" });
    fireEvent.click(withdrawalBtn);
    // 버튼이 선택된 스타일(bg-blue-600)로 변경되어야 함
    expect(withdrawalBtn).toHaveClass("bg-blue-600");
  });

  it("editingTx가 있으면 수정 모드로 렌더링된다", () => {
    const editingTx = {
      id: "tx-existing",
      account_id: "acc-1",
      transaction_type: "DEPOSIT" as const,
      amount: 500000,
      fee: null,
      transaction_date: "2026-01-01",
      ticker: null,
      notes: "테스트 메모",
      created_at: "2026-01-01T00:00:00Z",
    };
    renderWithProviders(<TransactionForm {...defaultProps} editingTx={editingTx} />);
    expect(screen.getByDisplayValue("500000")).toBeInTheDocument();
  });
});
