import { describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { act, renderHook } from "@testing-library/react";
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

const account = (taxType: AssetAccount["tax_type"], id = "acc1"): AssetAccount =>
  ({
    id,
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

function renderWith(accounts: AssetAccount[], a: RebalancingAnalysis = analysis) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return renderHook(() => useRebalancingExecution({ portfolioId: "p1", analysis: a, accounts }), {
    wrapper,
  }).result;
}

function render(taxType: AssetAccount["tax_type"]) {
  return renderWith([account(taxType)]).current;
}

// 대체 종목이 없는 그룹 — ISA는 VOO를 살 방법이 없다
const analysisNoAlt: RebalancingAnalysis = {
  ...analysis,
  items: [{ ...analysis.items[0]!, members: [analysis.items[0]!.members![0]!] }],
};

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

describe("여러 계좌로 나눠 살 때도 절세 계좌는 국내 대체 (plans/80 A)", () => {
  const isa = account("ISA", "isa");
  const general = account("GENERAL", "gen");

  it("ISA 행에 일반 계좌를 더해도 ISA 행은 대체 종목 그대로·선택 유지", () => {
    const result = renderWith([isa, general]);
    act(() => result.current.addBuyAccount("VOO", "gen"));
    const hook = result.current;
    expect(hook.getBuyRows("isa").map((r) => r.item.ticker)).toEqual(["360750"]);
    expect(hook.getBuyRows("gen").map((r) => r.item.ticker)).toEqual(["VOO"]);
    // ISA 대체 주문은 계속 나가고, 새로 더한 일반 계좌는 0주로 시작해 주문에 없다
    expect(hook.orders.map((o) => [o.ticker, o.account_id, o.quantity])).toEqual([
      ["360750", "isa", 50],
    ]);
    // 배분 합계는 VOO 주수로 환산: 360750 50주 × 2만 원 ÷ VOO 50만 원 = 2주
    expect(hook.getBuyTotalInfo("VOO")).toEqual({ allocated: 2, needed: 2 });
  });

  it("더했던 계좌를 빼면 원래 대체 행만 남는다", () => {
    const result = renderWith([isa, general]);
    act(() => result.current.addBuyAccount("VOO", "gen"));
    act(() =>
      result.current.dispatch({
        type: "REMOVE_BUY_ACCOUNT",
        ticker: "VOO",
        accountId: "gen",
        rowTicker: "VOO",
      }),
    );
    expect(result.current.orders.map((o) => [o.ticker, o.account_id])).toEqual([["360750", "isa"]]);
  });

  it("대체 종목이 없으면 ISA에는 해외 종목을 추가 후보로 보여주지 않는다", () => {
    const result = renderWith([general, isa], analysisNoAlt);
    expect(result.current.getAddableBuyItems("isa")).toEqual([]);
  });

  it("기본 매수 계좌가 ISA여도 살 수 없는 해외 종목은 일반 계좌로 잡는다", () => {
    const result = renderWith([isa, general], analysisNoAlt);
    expect(result.current.state.buyAccounts).toEqual({ VOO: ["gen"] });
    expect(result.current.orders.map((o) => [o.ticker, o.account_id])).toEqual([["VOO", "gen"]]);
  });
});
