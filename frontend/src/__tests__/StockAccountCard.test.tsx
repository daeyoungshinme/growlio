import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import StockAccountCard from "@/components/assets/StockAccountCard";
import { renderWithProviders } from "@/test/renderWithProviders";
import type { AssetAccount } from "@/api/assets";

vi.mock("../hooks/useExchangeRate", () => ({
  useExchangeRate: () => 1350,
}));

const mockAccount: AssetAccount = {
  id: "acc-1",
  name: "테스트 증권계좌",
  asset_type: "STOCK_KIS",
  data_source: "KIS_API",
  institution: "한국투자증권",
  kis_account_no: "12345678-01",
  kiwoom_account_no: null,
  is_mock_mode: false,
  manual_amount: null,
  manual_currency: "KRW",
  manual_updated_at: null,
  deposit_krw: 100000,
  deposit_usd: null,
  real_estate_details: null,
  include_in_total: true,
  is_active: true,
  sort_order: 0,
  notes: null,
  created_at: "2026-01-01T00:00:00Z",
  has_own_kis_credentials: false,
  has_own_kiwoom_credentials: false,
};

const defaultProps = {
  account: mockAccount,
  stats: undefined,
  onDelete: vi.fn(),
  onManagePositions: vi.fn(),
  onTransactions: vi.fn(),
  onEdit: vi.fn(),
  onEditName: vi.fn(),
  onSync: vi.fn(),
  isSyncing: false,
  isDeleting: false,
};

describe("StockAccountCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("계좌명과 증권사 이름을 렌더링한다", () => {
    renderWithProviders(<StockAccountCard {...defaultProps} />);
    expect(screen.getByText("테스트 증권계좌")).toBeInTheDocument();
    expect(screen.getByText(/한국투자증권/)).toBeInTheDocument();
  });

  it("계좌번호를 표시한다", () => {
    renderWithProviders(<StockAccountCard {...defaultProps} />);
    expect(screen.getByText(/12345678-01/)).toBeInTheDocument();
  });

  it("KIS 동기화 버튼에 aria-label이 있다", () => {
    renderWithProviders(<StockAccountCard {...defaultProps} />);
    const syncBtn = screen.getByRole("button", { name: "KIS 데이터 동기화" });
    expect(syncBtn).toBeInTheDocument();
  });

  it("종목 관리 버튼에 aria-label이 있다", () => {
    renderWithProviders(<StockAccountCard {...defaultProps} />);
    expect(screen.getByRole("button", { name: "종목 관리" })).toBeInTheDocument();
  });

  it("계좌 삭제 버튼에 aria-label이 있다", () => {
    renderWithProviders(<StockAccountCard {...defaultProps} />);
    expect(screen.getByRole("button", { name: "계좌 삭제" })).toBeInTheDocument();
  });

  it("동기화 버튼 클릭 시 onSync를 계좌 id와 함께 호출한다", () => {
    renderWithProviders(<StockAccountCard {...defaultProps} />);
    fireEvent.click(screen.getByRole("button", { name: "KIS 데이터 동기화" }));
    expect(defaultProps.onSync).toHaveBeenCalledWith("acc-1");
  });

  it("삭제 버튼 클릭 시 onDelete를 계좌 id와 함께 호출한다", () => {
    renderWithProviders(<StockAccountCard {...defaultProps} />);
    fireEvent.click(screen.getByRole("button", { name: "계좌 삭제" }));
    expect(defaultProps.onDelete).toHaveBeenCalledWith("acc-1");
  });

  it("계좌명 수정 버튼 클릭 시 편집 모드로 전환된다", () => {
    renderWithProviders(<StockAccountCard {...defaultProps} />);
    fireEvent.click(screen.getByRole("button", { name: "계좌명 수정" }));
    expect(screen.getByRole("textbox")).toBeInTheDocument();
    expect(screen.getByText("저장")).toBeInTheDocument();
  });

  it("동기화 중에는 sync 버튼이 비활성화된다", () => {
    renderWithProviders(<StockAccountCard {...defaultProps} isSyncing={true} />);
    const syncBtn = screen.getByRole("button", { name: "KIS 데이터 동기화" });
    expect(syncBtn).toBeDisabled();
  });

  it("통계 데이터가 있으면 평가금액을 표시한다", () => {
    const stats = {
      amount_krw: 5000000,
      invested_krw: 4000000,
      unrealized_pnl: 1000000,
      deposit_total: 4000000,
      dividend_total: 100000,
    };
    renderWithProviders(<StockAccountCard {...defaultProps} stats={stats} />);
    expect(screen.getByText("평가금액")).toBeInTheDocument();
  });

  it("예수금 수정 버튼 클릭 시 onEdit을 계좌 정보와 함께 호출한다 (계좌 수정 모달로 위임)", () => {
    const stats = {
      amount_krw: 5000000,
      invested_krw: 4000000,
      unrealized_pnl: 1000000,
      deposit_total: 4000000,
      dividend_total: 100000,
    };
    renderWithProviders(<StockAccountCard {...defaultProps} stats={stats} />);
    fireEvent.click(screen.getByRole("button", { name: "예수금 수정" }));
    expect(defaultProps.onEdit).toHaveBeenCalledWith(mockAccount);
  });
});
