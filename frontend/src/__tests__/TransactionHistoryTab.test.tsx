import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor, within } from "@testing-library/react";
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

// 기본 0행(기존 테스트) — 행 렌더가 필요한 테스트만 virtualCount를 올린다
let virtualCount = 0;
vi.mock("@tanstack/react-virtual", () => ({
  useVirtualizer: () => ({
    getVirtualItems: () =>
      Array.from({ length: virtualCount }, (_, i) => ({
        index: i,
        key: i,
        start: i * 48,
        end: (i + 1) * 48,
        size: 48,
      })),
    getTotalSize: () => virtualCount * 48,
    measureElement: () => {},
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
    data_source: "MANUAL",
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
    virtualCount = 0;
  });

  describe("삭제 확인", () => {
    const tx = {
      id: "tx-1",
      account_id: "acc-1",
      transaction_type: "DEPOSIT" as const,
      amount: 500_000,
      fee: null,
      transaction_date: "2026-10-01",
      ticker: null,
      notes: null,
      created_at: "2026-10-01T00:00:00Z",
    };

    it("휴지통을 눌러도 바로 삭제하지 않고 확인 후 삭제한다", async () => {
      const { fetchTransactions, deleteTransaction } = await import("../api/transactions");
      vi.mocked(fetchTransactions).mockResolvedValue([tx]);
      virtualCount = 1;
      renderWithProviders(<TransactionHistoryTab accounts={mockAccounts} />);

      const [trash] = await screen.findAllByRole("button", { name: "삭제" });
      fireEvent.click(trash);
      const dialog = screen.getByRole("dialog");
      expect(
        within(dialog).getByText(/2026-10-01 입금 50만원 기록을 삭제할까요\?/),
      ).toBeInTheDocument();
      expect(vi.mocked(deleteTransaction)).not.toHaveBeenCalled();

      fireEvent.click(within(dialog).getByRole("button", { name: "삭제" }));
      await waitFor(() => expect(vi.mocked(deleteTransaction)).toHaveBeenCalled());
      expect(vi.mocked(deleteTransaction).mock.calls[0][0]).toBe("tx-1");
    });

    it("확인창에서 취소하면 삭제하지 않는다", async () => {
      const { fetchTransactions, deleteTransaction } = await import("../api/transactions");
      vi.mocked(fetchTransactions).mockResolvedValue([tx]);
      virtualCount = 1;
      renderWithProviders(<TransactionHistoryTab accounts={mockAccounts} />);

      const [trash] = await screen.findAllByRole("button", { name: "삭제" });
      fireEvent.click(trash);
      fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "취소" }));
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      expect(vi.mocked(deleteTransaction)).not.toHaveBeenCalled();
    });
  });

  it("조회 실패를 '내역 없음'이 아니라 오류+다시 시도로 보여준다", async () => {
    const { fetchTransactions } = await import("../api/transactions");
    vi.mocked(fetchTransactions).mockRejectedValueOnce(new Error("network"));
    renderWithProviders(<TransactionHistoryTab accounts={mockAccounts} />);

    expect(await screen.findByText("거래 내역을 불러오지 못했습니다.")).toBeInTheDocument();
    expect(screen.queryByText("등록된 내역이 없습니다.")).not.toBeInTheDocument();
    vi.mocked(fetchTransactions).mockResolvedValueOnce([]);
    fireEvent.click(screen.getByRole("button", { name: "다시 시도" }));
    expect(await screen.findByText("등록된 내역이 없습니다.")).toBeInTheDocument();
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

  it("유형 필터는 칩으로 전환된다", () => {
    renderWithProviders(<TransactionHistoryTab accounts={mockAccounts} />);
    const group = screen.getByRole("group", { name: "유형 필터" });
    const dividendChip = within(group).getByRole("button", { name: "배당" });
    expect(within(group).getByRole("button", { name: "전체" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    fireEvent.click(dividendChip);
    expect(dividendChip).toHaveAttribute("aria-pressed", "true");
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
