import { describe, it, expect, vi } from "vitest";
import { render, within, fireEvent } from "@testing-library/react";
import { RebalancingOrderTable, type RebalancingOrderTableProps } from "../RebalancingOrderTable";
import type { RebalancingItem } from "@/api/rebalancing";

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

function makeProps(
  overrides: Partial<RebalancingOrderTableProps> = {},
): RebalancingOrderTableProps {
  return {
    accId: "acc-1",
    sellRows: [
      { item: makeItem({ ticker: "000660", name: "SK하이닉스" }), currentQty: 5, suggestedQty: 2 },
    ],
    buyRows: [{ item: makeItem(), suggestedQty: 3, currentQty: 0 }],
    orderType: "MARKET",
    priceState: "loaded",
    livePricesKrw: {},
    livePricesUsd: {},
    priceRetrying: new Set(),
    onRetryPrice: vi.fn(),
    onRetryAllPrices: vi.fn(),
    globalUsdRate: null,
    selected: new Set(),
    qtyOverrides: {},
    buyAccounts: {},
    dispatch: vi.fn(),
    getLimitPriceNative: () => 0,
    getEstimateKrw: () => null,
    getBuyTotalInfo: () => ({ allocated: 3, needed: 3 }),
    ...overrides,
  };
}

describe("RebalancingOrderTable", () => {
  it.each(["MARKET", "LIMIT"] as const)(
    "%s 주문에서 데스크톱 데이터 행의 칸 수가 헤더와 같다(plans/62 B1)",
    (orderType) => {
      const { container } = render(<RebalancingOrderTable {...makeProps({ orderType })} />);
      const headerCount = container.querySelectorAll("thead th").length;
      const dataRows = [...container.querySelectorAll("tbody tr")].filter(
        (tr) => tr.querySelectorAll("td").length > 1,
      );
      expect(dataRows).toHaveLength(2);
      for (const row of dataRows) {
        expect(row.querySelectorAll("td")).toHaveLength(headerCount);
      }
    },
  );

  it("분할 매수 시 모바일 카드에서도 이 계좌 몫을 뺄 수 있다(plans/62 B6)", () => {
    const dispatch = vi.fn();
    const { container } = render(
      <RebalancingOrderTable
        {...makeProps({ dispatch, buyAccounts: { "005930": ["acc-1", "acc-2"] } })}
      />,
    );
    const mobile = within(container.querySelector<HTMLElement>(".md\\:hidden")!);
    fireEvent.click(mobile.getByRole("button", { name: "이 계좌에서 제거" }));
    expect(dispatch).toHaveBeenCalledWith({
      type: "REMOVE_BUY_ACCOUNT",
      ticker: "005930",
      accountId: "acc-1",
      rowTicker: "005930",
    });
  });

  it("단일 계좌 매수면 모바일 제거 버튼을 보이지 않는다", () => {
    const { container } = render(
      <RebalancingOrderTable {...makeProps({ buyAccounts: { "005930": ["acc-1"] } })} />,
    );
    const mobile = within(container.querySelector<HTMLElement>(".md\\:hidden")!);
    expect(mobile.queryByRole("button", { name: "이 계좌에서 제거" })).toBeNull();
  });
});
