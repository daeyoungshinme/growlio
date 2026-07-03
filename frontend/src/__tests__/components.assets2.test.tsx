import { describe, it, expect, vi } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { render } from "@testing-library/react";

vi.mock("@/utils/format", () => ({
  fmtKrwShort: vi.fn((n: number) => `${n}만`),
  fmtKrw: vi.fn((n: number) => `${n}원`),
}));

vi.mock("@/utils/colors", () => ({
  pnlColor: vi.fn((val: number) => (val >= 0 ? "text-red-500" : "text-blue-500")),
}));

vi.mock("@/constants/markets", () => ({
  POSITION_MARKETS: ["KOSPI", "KOSDAQ", "NASDAQ", "NYSE"],
  isOverseasMarket: vi.fn((market: string) => ["NASDAQ", "NYSE", "AMEX"].includes(market)),
}));

vi.mock("@/hooks/useRebalancingExecution", () => ({
  isOverseasMarket: vi.fn((market: string) => ["NASDAQ", "NYSE", "AMEX"].includes(market)),
}));

vi.mock("@/components/rebalancing/RebalancingBadges", () => ({
  SideBadge: ({ isBuy }: { isBuy: boolean }) => <span>{isBuy ? "매수" : "매도"}</span>,
}));

vi.mock("@/components/rebalancing/RebalancingPriceCell", () => ({
  PriceCell: () => <span data-testid="price-cell">가격</span>,
}));

import { PnlCell, MarketSelect } from "@/components/assets/PositionHelpers";
import { RebalancingMobileCard } from "@/components/rebalancing/RebalancingMobileCard";
import { RebalancingPriceInput } from "@/components/rebalancing/RebalancingPriceInput";
import type { RebalancingItem } from "@/api/rebalancing";

// ------- PnlCell -------
describe("PnlCell", () => {
  it("양수 수익일 때 + 접두사를 표시한다", () => {
    render(<PnlCell val={100000} pct={5.5} />);
    expect(screen.getByText(/\+5\.50%/)).toBeDefined();
    expect(screen.getAllByText(/\+/).length).toBeGreaterThan(0);
  });

  it("음수 손실일 때 + 접두사 없이 표시한다", () => {
    render(<PnlCell val={-50000} pct={-3.2} />);
    expect(screen.getByText(/-3\.20%/)).toBeDefined();
  });
});

// ------- MarketSelect -------
describe("MarketSelect", () => {
  it("현재 선택된 시장을 표시한다", () => {
    const onChange = vi.fn();
    render(<MarketSelect value="KOSPI" disabled={false} onChange={onChange} />);
    const select = screen.getByRole("combobox") as HTMLSelectElement;
    expect(select.value).toBe("KOSPI");
  });

  it("onChange가 선택 변경 시 호출된다", () => {
    const onChange = vi.fn();
    render(<MarketSelect value="KOSPI" disabled={false} onChange={onChange} />);
    const select = screen.getByRole("combobox");
    fireEvent.change(select, { target: { value: "NASDAQ" } });
    expect(onChange).toHaveBeenCalledWith("NASDAQ");
  });

  it("disabled=true일 때 select가 비활성화된다", () => {
    const onChange = vi.fn();
    render(<MarketSelect value="KOSPI" disabled={true} onChange={onChange} />);
    const select = screen.getByRole("combobox") as HTMLSelectElement;
    expect(select.disabled).toBe(true);
  });
});

// ------- RebalancingMobileCard -------
describe("RebalancingMobileCard", () => {
  const mockItem: RebalancingItem = {
    ticker: "005930",
    name: "삼성전자",
    market: "KOSPI",
    target_weight_pct: 20,
    current_weight_pct: 15,
    weight_diff_pct: 5,
    current_value_krw: 1500000,
    target_value_krw: 2000000,
    diff_krw: 500000,
    shares_to_trade: 10,
    current_price_krw: 70000,
  };

  const baseProps = {
    orderKey: "005930-KOSPI",
    item: mockItem,
    qty: 10,
    isBuy: true,
    selected: new Set<string>(),
    orderType: "MARKET" as const,
    priceState: "loaded" as const,
    livePricesKrw: { "005930": 70000 },
    livePricesUsd: {},
    globalUsdRate: null,
    nativeLimitPrice: 0,
    currentNativePrice: 70000,
    estKrw: 700000,
    marketOrderEst: 700000,
    dispatch: vi.fn(),
  };

  it("종목명과 티커를 표시한다", () => {
    render(<RebalancingMobileCard {...baseProps} />);
    expect(screen.getByText("삼성전자")).toBeDefined();
    expect(screen.getByText("005930")).toBeDefined();
  });

  it("MARKET 주문 타입일 때 시장가 예상금액을 표시한다", () => {
    render(<RebalancingMobileCard {...baseProps} />);
    expect(screen.getByText(/700000원/)).toBeDefined();
  });

  it("LIMIT 주문 타입일 때 지정가 입력 UI를 표시한다", () => {
    render(<RebalancingMobileCard {...baseProps} orderType="LIMIT" nativeLimitPrice={68000} />);
    expect(screen.getByText("지정가")).toBeDefined();
    expect(screen.getByText("현재가로")).toBeDefined();
  });

  it("체크박스 클릭 시 TOGGLE_SELECTED 액션을 dispatch한다", () => {
    const dispatch = vi.fn();
    render(<RebalancingMobileCard {...baseProps} dispatch={dispatch} />);
    const checkbox = screen.getByRole("checkbox");
    fireEvent.click(checkbox);
    expect(dispatch).toHaveBeenCalledWith({ type: "TOGGLE_SELECTED", key: "005930-KOSPI" });
  });

  it("선택된 상태일 때 배경 클래스가 적용된다", () => {
    const { container } = render(
      <RebalancingMobileCard {...baseProps} selected={new Set(["005930-KOSPI"])} />,
    );
    expect((container.firstChild as HTMLElement)?.className).toContain("bg-indigo-950/20");
  });

  it("해외 종목일 때 USD 표시를 보여준다", () => {
    render(
      <RebalancingMobileCard
        {...baseProps}
        item={{ ...mockItem, market: "NASDAQ" }}
        orderType="LIMIT"
        nativeLimitPrice={100}
      />,
    );
    expect(screen.getByText("USD")).toBeDefined();
  });
});

// ------- RebalancingPriceInput -------
describe("RebalancingPriceInput", () => {
  const baseProps = {
    orderKey: "005930-KOSPI",
    market: "KOSPI",
    qty: 5,
    orderType: "LIMIT" as const,
    priceState: "idle" as const,
    nativeVal: 0,
    currentNativePrice: undefined,
    globalUsdRate: null,
    dispatch: vi.fn(),
  };

  it("MARKET 주문 타입이면 빈 td를 반환한다", () => {
    const { container } = render(
      <table>
        <tbody>
          <tr>
            <RebalancingPriceInput {...baseProps} orderType="MARKET" />
          </tr>
        </tbody>
      </table>,
    );
    const td = container.querySelector("td");
    expect(td).toBeDefined();
    expect(td?.children.length).toBe(0);
  });

  it("국내 종목 LIMIT 주문은 원 단위를 표시한다", () => {
    render(
      <table>
        <tbody>
          <tr>
            <RebalancingPriceInput {...baseProps} />
          </tr>
        </tbody>
      </table>,
    );
    expect(screen.getByText("원")).toBeDefined();
  });

  it("해외 종목은 USD 단위를 표시한다", () => {
    render(
      <table>
        <tbody>
          <tr>
            <RebalancingPriceInput {...baseProps} market="NASDAQ" />
          </tr>
        </tbody>
      </table>,
    );
    expect(screen.getByText("USD")).toBeDefined();
  });

  it("priceState=loaded이고 currentNativePrice가 있으면 '현재가로' 버튼을 표시한다", () => {
    const dispatch = vi.fn();
    render(
      <table>
        <tbody>
          <tr>
            <RebalancingPriceInput
              {...baseProps}
              priceState="loaded"
              currentNativePrice={70000}
              dispatch={dispatch}
            />
          </tr>
        </tbody>
      </table>,
    );
    const btn = screen.getByText("현재가로");
    expect(btn).toBeDefined();
    fireEvent.click(btn);
    expect(dispatch).toHaveBeenCalledWith({
      type: "SET_LIMIT_PRICE",
      key: "005930-KOSPI",
      price: 70000,
    });
  });

  it("nativeVal > 0이면 예상 금액 계산을 표시한다", () => {
    render(
      <table>
        <tbody>
          <tr>
            <RebalancingPriceInput {...baseProps} nativeVal={70000} />
          </tr>
        </tbody>
      </table>,
    );
    expect(screen.getByText(/5주/)).toBeDefined();
  });

  it("해외 종목에서 nativeVal > 0이면 환율 변환 계산을 표시한다", () => {
    render(
      <table>
        <tbody>
          <tr>
            <RebalancingPriceInput
              {...baseProps}
              market="NASDAQ"
              nativeVal={100}
              globalUsdRate={1350}
              qty={3}
            />
          </tr>
        </tbody>
      </table>,
    );
    expect(screen.getByText(/3주/)).toBeDefined();
  });
});
