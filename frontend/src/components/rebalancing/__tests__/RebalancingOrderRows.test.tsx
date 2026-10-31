import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import type { RebalancingItem } from "@/api/rebalancing";
import {
  AllocationNote,
  BuyHoldingNote,
  PriceErrorBanner,
  QtyInput,
} from "../RebalancingOrderRows";

function makeItem(overrides: Partial<RebalancingItem> = {}): RebalancingItem {
  return {
    ticker: "005930",
    name: "삼성전자",
    market: "KOSPI",
    target_weight_pct: 10,
    current_weight_pct: 5,
    weight_diff_pct: 5,
    current_value_krw: 1000000,
    target_value_krw: 2000000,
    diff_krw: 1000000,
    shares_to_trade: 10,
    current_price_krw: 70000,
    ...overrides,
  };
}

describe("BuyHoldingNote", () => {
  it("목표 수량이 있으면 '보유 → 목표'로 표시한다", () => {
    const { container } = render(
      <BuyHoldingNote item={makeItem({ target_qty: 12 })} currentQty={5} />,
    );
    expect(container.textContent).toBe("5주 → 목표 12주");
  });

  it("목표 수량이 있고 미보유면 '미보유 → 목표'", () => {
    const { container } = render(
      <BuyHoldingNote item={makeItem({ target_qty: 3 })} currentQty={0} />,
    );
    expect(container.textContent).toBe("미보유 → 목표 3주");
  });

  it("목표 수량이 없으면 현재 보유 여부만 표시한다", () => {
    const { container, rerender } = render(<BuyHoldingNote item={makeItem()} currentQty={7} />);
    expect(container.textContent).toBe("현재 7주 보유");
    rerender(<BuyHoldingNote item={makeItem()} currentQty={0} />);
    expect(container.textContent).toBe("현재 미보유");
  });

  it("국내 대체 종목이면 원래 종목을 화면 문구로 밝힌다", () => {
    render(<BuyHoldingNote item={makeItem({ substitute_for: "QQQ" })} currentQty={0} />);
    expect(screen.getByText("국내 대체 (원래 QQQ)")).toBeTruthy();
  });
});

describe("AllocationNote", () => {
  it("다 배분하지 않았으면 주황으로, 대체 기준 종목을 함께 표시한다", () => {
    render(<AllocationNote allocated={2} needed={5} unitTicker="QQQ" />);
    expect(screen.getByText("배분 2 / 5주 (QQQ 기준)").className).toContain("text-amber-600");
  });

  it("다 배분했으면 회색", () => {
    render(<AllocationNote allocated={5} needed={5} />);
    expect(screen.getByText("배분 5 / 5주").className).toContain("text-gray-500");
  });
});

describe("QtyInput", () => {
  it("입력값을 정수로, 빈 값은 0으로 넘긴다", () => {
    const onChange = vi.fn();
    render(<QtyInput value={3} colorClass="" onChange={onChange} />);
    const input = screen.getByRole("spinbutton");
    fireEvent.change(input, { target: { value: "7" } });
    fireEvent.change(input, { target: { value: "" } });
    expect(onChange).toHaveBeenNthCalledWith(1, 7);
    expect(onChange).toHaveBeenNthCalledWith(2, 0);
  });

  it("0이면 빈 칸으로 보여준다", () => {
    render(<QtyInput value={0} colorClass="" onChange={vi.fn()} />);
    expect((screen.getByRole("spinbutton") as HTMLInputElement).value).toBe("");
  });
});

describe("PriceErrorBanner", () => {
  it("재조회 버튼이 onRetry를 부른다", () => {
    const onRetry = vi.fn();
    render(<PriceErrorBanner onRetry={onRetry} />);
    fireEvent.click(screen.getByRole("button", { name: /재조회/ }));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});
