import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { ExecutionOrderItem } from "@/api/rebalancing";
import { RebalancingFinalConfirmDialog } from "@/components/rebalancing/RebalancingFinalConfirmDialog";
import { limitDeviationPct } from "@/components/rebalancing/rebalancingTradeMath";

function order(over: Partial<ExecutionOrderItem> = {}): ExecutionOrderItem {
  return {
    ticker: "005930",
    name: "삼성전자",
    market: "KOSPI",
    side: "BUY",
    quantity: 3,
    account_id: "acc",
    order_type: "LIMIT",
    limit_price: 70000,
    ...over,
  };
}

function renderDialog(orders: ExecutionOrderItem[], livePricesKrw: Record<string, number> = {}) {
  render(
    <RebalancingFinalConfirmDialog
      orders={orders}
      orderType="LIMIT"
      strategy="FULL"
      hasRealAccount
      livePricesKrw={livePricesKrw}
      livePricesUsd={{}}
      totalSellProceeds={null}
      totalBuyCost={210000}
      onConfirm={vi.fn()}
      onCancel={vi.fn()}
    />,
  );
}

describe("RebalancingFinalConfirmDialog", () => {
  it("6건을 넘는 주문은 '외 N건'으로 줄인다", () => {
    renderDialog(Array.from({ length: 8 }, (_, i) => order({ ticker: `T${i}`, name: `종목${i}` })));
    expect(screen.getByText("종목5")).toBeInTheDocument();
    expect(screen.queryByText("종목6")).not.toBeInTheDocument();
    expect(screen.getByText("외 2건")).toBeInTheDocument();
  });

  it("현재가에서 크게 벗어난 지정가를 강조한다", () => {
    renderDialog([order({ limit_price: 7000 })], { "005930": 70000 });
    expect(screen.getByText(/현재가 -90\.0%/)).toBeInTheDocument();
  });

  it("현재가 근처 지정가는 강조하지 않는다", () => {
    renderDialog([order({ limit_price: 71000 })], { "005930": 70000 });
    expect(screen.queryByText(/현재가 [+-]/)).not.toBeInTheDocument();
  });

  it("limitDeviationPct — 시장가거나 현재가를 모르면 null", () => {
    expect(limitDeviationPct(order({ order_type: "MARKET" }), { "005930": 1 }, {})).toBeNull();
    expect(limitDeviationPct(order(), {}, {})).toBeNull();
    expect(
      limitDeviationPct(
        order({ market: "NASDAQ", ticker: "AAPL", limit_price: 220 }),
        {},
        { AAPL: 200 },
      ),
    ).toBeCloseTo(10);
  });
});
