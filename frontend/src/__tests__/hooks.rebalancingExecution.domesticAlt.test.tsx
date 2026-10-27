import { describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { renderHook } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { AssetAccount } from "@/api/assets";
import type { RebalancingAnalysis, RebalancingItem } from "@/api/rebalancing";
import { useRebalancingExecution } from "@/hooks/useRebalancingExecution";

// 마운트 시 잔고·시세를 불러오는 호출은 빈 응답으로 막는다
vi.mock("@/api/assets", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/assets")>()),
  fetchStockPricesBatch: vi.fn().mockResolvedValue({}),
  fetchStockPrice: vi.fn().mockResolvedValue(null),
}));
vi.mock("@/api/rebalancing", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/rebalancing")>()),
  fetchAllBrokerBalances: vi.fn().mockResolvedValue([]),
  fetchBrokerBalance: vi.fn().mockResolvedValue({ positions: [] }),
}));
vi.mock("@/utils/toast", () => ({ toast: vi.fn() }));

const base: RebalancingItem = {
  ticker: "VOO",
  name: "VOO",
  market: "NYSE",
  target_weight_pct: 100,
  current_weight_pct: 0,
  weight_diff_pct: 100,
  current_value_krw: 0,
  target_value_krw: 1_000_000,
  diff_krw: 1_000_000,
  shares_to_trade: null,
  current_price_krw: 500_000,
};

const analysis: RebalancingAnalysis = {
  portfolio_id: "p1",
  portfolio_name: "ISA",
  base_type: "STOCK_ONLY",
  base_value_krw: 1_000_000,
  analyzed_at: "2026-10-27T00:00:00Z",
  current_portfolio_annual_dividend: 0,
  target_portfolio_annual_dividend: 0,
  ticker_account_map: {},
  items: [
    {
      ...base,
      group_key: "US_SP500",
      members: [
        { ...base, group_role: "PRIMARY", current_qty: 0, shares_to_trade: 2 },
        {
          ...base,
          ticker: "360750",
          name: "TIGER 미국S&P500",
          market: "KOSPI",
          group_role: "DOMESTIC_ALT",
          target_value_krw: 0,
          current_qty: 0,
          current_price_krw: 20_000,
          shares_to_trade: 0,
        },
      ],
    },
  ],
};

const account = (taxType: AssetAccount["tax_type"]): AssetAccount =>
  ({
    id: "acc1",
    name: "계좌",
    asset_type: "STOCK_KIS",
    data_source: "KIS",
    institution: null,
    kis_account_no: "12345678-01",
    kiwoom_account_no: null,
    is_mock_mode: true,
    manual_amount: null,
    manual_currency: "KRW",
    manual_updated_at: null,
    tax_type: taxType,
  }) as AssetAccount;

function render(taxType: AssetAccount["tax_type"]) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return renderHook(
    () => useRebalancingExecution({ portfolioId: "p1", analysis, accounts: [account(taxType)] }),
    { wrapper },
  ).result.current;
}

describe("수동 실행 국내 대체 자동 전환 (plans/79 E)", () => {
  it("ISA 계좌는 해외 대표 대신 국내 대체 종목 주문을 만든다", () => {
    const hook = render("ISA");
    expect(hook.getBuyRows("acc1").map((r) => [r.item.ticker, r.suggestedQty])).toEqual([
      ["360750", 50],
    ]);
    expect(hook.orders.map((o) => [o.ticker, o.market, o.quantity])).toEqual([
      ["360750", "KOSPI", 50],
    ]);
  });

  it("일반 계좌는 대표 종목 그대로", () => {
    const hook = render("GENERAL");
    expect(hook.orders.map((o) => [o.ticker, o.quantity])).toEqual([["VOO", 2]]);
  });
});
