import { describe, it, expect, vi } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { render } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";
import type { AssetAccount } from "@/api/assets";
import StatCard from "@/components/common/StatCard";
import PriceCell from "@/components/common/PriceCell";
import BankAccountCard from "@/components/assets/BankAccountCard";
import AmountUnitButtons from "@/components/common/AmountUnitButtons";

vi.mock("@/context/ExchangeRateContext", () => ({
  useExchangeRateContext: vi.fn(() => ({ rate: 1350, isLoading: false, error: null })),
}));

describe("StatCard", () => {
  it("레이블과 값을 표시한다", () => {
    renderWithProviders(<StatCard label="총 자산" value="1억 2,345만원" />);
    expect(screen.getByText("총 자산")).toBeInTheDocument();
    expect(screen.getByText("1억 2,345만원")).toBeInTheDocument();
  });

  it("sub 텍스트가 있으면 함께 표시한다", () => {
    renderWithProviders(<StatCard label="수익률" value="+12.3%" sub="연초 대비" />);
    expect(screen.getByText("연초 대비")).toBeInTheDocument();
  });

  it("sub 텍스트가 없으면 표시하지 않는다", () => {
    renderWithProviders(<StatCard label="수익률" value="+12.3%" />);
    expect(screen.queryByText(/연초/)).toBeNull();
  });

  it("color=red이면 적절한 색상 클래스가 적용된다", () => {
    renderWithProviders(<StatCard label="손실" value="-5.0%" color="red" />);
    const valueEl = screen.getByText("-5.0%");
    expect(valueEl.className).toContain("text-red-500");
  });

  it("size=sm이면 sm 클래스가 적용된다", () => {
    renderWithProviders(<StatCard label="소형" value="100" size="sm" />);
    const valueEl = screen.getByText("100");
    expect(valueEl.className).toContain("text-sm");
  });
});

describe("PriceCell", () => {
  it("국내 종목이면 원 단위로 표시한다", () => {
    renderWithProviders(<PriceCell krw={75000} />);
    expect(screen.getByText("75,000원")).toBeInTheDocument();
  });

  it("krw가 null이면 0원으로 표시한다", () => {
    renderWithProviders(<PriceCell krw={null} />);
    expect(screen.getByText("0원")).toBeInTheDocument();
  });

  it("해외 종목에 usd 값이 있으면 USD 주표시 + KRW 보조 표시한다", () => {
    renderWithProviders(<PriceCell krw={135000} usd={100} isOverseas />);
    expect(screen.getByText("$100.00")).toBeInTheDocument();
    expect(screen.getByText("₩135,000")).toBeInTheDocument();
  });

  it("해외 종목이어도 usd가 없으면 원 단위로 표시한다", () => {
    renderWithProviders(<PriceCell krw={135000} usd={null} isOverseas />);
    expect(screen.getByText("135,000원")).toBeInTheDocument();
  });

  it("해외 종목이고 krw가 0이면 KRW 보조 표시를 안 한다", () => {
    renderWithProviders(<PriceCell krw={0} usd={100} isOverseas />);
    expect(screen.getByText("$100.00")).toBeInTheDocument();
    expect(screen.queryByText(/₩/)).toBeNull();
  });
});

const makeAccount = (overrides = {}) => ({
  id: "acc-1",
  name: "국민은행 입출금",
  institution: "국민은행",
  asset_type: "BANK_ACCOUNT",
  data_source: "MANUAL",
  deposit_krw: null,
  deposit_usd: null,
  manual_amount: 1000000,
  notes: "비상금 통장",
  is_active: true,
  ...overrides,
});

describe("BankAccountCard", () => {
  const defaultProps = {
    onDelete: vi.fn(),
    onEditModal: vi.fn(),
    onEditName: vi.fn(),
    onSync: vi.fn(),
    isDeleting: false,
    isSyncing: false,
  };

  it("계좌명과 기관명을 표시한다", () => {
    renderWithProviders(
      <BankAccountCard account={makeAccount() as unknown as AssetAccount} {...defaultProps} />,
    );
    expect(screen.getByText("국민은행 입출금")).toBeInTheDocument();
    expect(screen.getByText("국민은행")).toBeInTheDocument();
  });

  it("asset_type 레이블을 올바르게 표시한다", () => {
    renderWithProviders(
      <BankAccountCard account={makeAccount() as unknown as AssetAccount} {...defaultProps} />,
    );
    expect(screen.getByText("입출금")).toBeInTheDocument();
  });

  it("DEPOSIT 타입이면 예·적금 레이블을 표시한다", () => {
    renderWithProviders(
      <BankAccountCard
        account={makeAccount({ asset_type: "DEPOSIT" }) as unknown as AssetAccount}
        {...defaultProps}
      />,
    );
    expect(screen.getByText("예·적금")).toBeInTheDocument();
  });

  it("notes가 있으면 표시한다", () => {
    renderWithProviders(
      <BankAccountCard account={makeAccount() as unknown as AssetAccount} {...defaultProps} />,
    );
    expect(screen.getByText("비상금 통장")).toBeInTheDocument();
  });

  it("삭제 버튼 클릭 시 onDelete를 호출한다", () => {
    const onDelete = vi.fn();
    renderWithProviders(
      <BankAccountCard
        account={makeAccount() as unknown as AssetAccount}
        {...defaultProps}
        onDelete={onDelete}
      />,
    );
    fireEvent.click(screen.getByLabelText("계좌 삭제"));
    expect(onDelete).toHaveBeenCalledWith("acc-1");
  });

  it("MANUAL 데이터소스이면 금액 수정 버튼이 나온다", () => {
    renderWithProviders(
      <BankAccountCard account={makeAccount() as unknown as AssetAccount} {...defaultProps} />,
    );
    expect(screen.getByLabelText("금액 수정")).toBeInTheDocument();
  });

  it("OPEN_BANKING 데이터소스이면 새로고침 버튼이 나온다", () => {
    renderWithProviders(
      <BankAccountCard
        account={makeAccount({ data_source: "OPEN_BANKING" }) as never}
        {...defaultProps}
      />,
    );
    expect(screen.getByLabelText("잔액 새로고침")).toBeInTheDocument();
  });

  it("계좌명 수정 버튼 클릭 시 편집 모드로 전환된다", () => {
    renderWithProviders(
      <BankAccountCard account={makeAccount() as unknown as AssetAccount} {...defaultProps} />,
    );
    fireEvent.click(screen.getByLabelText("계좌명 수정"));
    expect(screen.getByRole("textbox")).toBeInTheDocument();
    expect(screen.getByText("저장")).toBeInTheDocument();
    expect(screen.getByText("취소")).toBeInTheDocument();
  });

  it("계좌명 저장 시 onEditName을 호출한다", () => {
    const onEditName = vi.fn();
    renderWithProviders(
      <BankAccountCard
        account={makeAccount() as unknown as AssetAccount}
        {...defaultProps}
        onEditName={onEditName}
      />,
    );
    fireEvent.click(screen.getByLabelText("계좌명 수정"));
    const input = screen.getByRole("textbox");
    fireEvent.change(input, { target: { value: "새 계좌명" } });
    fireEvent.click(screen.getByText("저장"));
    expect(onEditName).toHaveBeenCalledWith("acc-1", "새 계좌명");
  });

  it("취소 버튼 클릭 시 편집 모드를 벗어난다", () => {
    renderWithProviders(
      <BankAccountCard account={makeAccount() as unknown as AssetAccount} {...defaultProps} />,
    );
    fireEvent.click(screen.getByLabelText("계좌명 수정"));
    fireEvent.click(screen.getByText("취소"));
    expect(screen.queryByRole("textbox")).toBeNull();
  });
});

// ------- AmountUnitButtons -------
describe("AmountUnitButtons", () => {
  it("4개 단위 버튼을 렌더링한다", () => {
    render(<AmountUnitButtons onAdd={vi.fn()} />);
    expect(screen.getByText("+1만")).toBeInTheDocument();
    expect(screen.getByText("+10만")).toBeInTheDocument();
    expect(screen.getByText("+100만")).toBeInTheDocument();
    expect(screen.getByText("+1억")).toBeInTheDocument();
  });

  it("버튼 클릭 시 해당 금액으로 onAdd를 호출한다", () => {
    const onAdd = vi.fn();
    render(<AmountUnitButtons onAdd={onAdd} />);
    fireEvent.click(screen.getByText("+1만"));
    expect(onAdd).toHaveBeenCalledWith(10_000);
    fireEvent.click(screen.getByText("+1억"));
    expect(onAdd).toHaveBeenCalledWith(100_000_000);
  });

  it("className prop이 컨테이너에 적용된다", () => {
    const { container } = render(<AmountUnitButtons onAdd={vi.fn()} className="custom-class" />);
    expect(container.firstChild).toHaveClass("custom-class");
  });
});
