import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

// ── mocks ────────────────────────────────────────────────────────────────────

vi.mock("@/api/client", () => {
  const mockApi = { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn(), patch: vi.fn() };
  return {
    api: mockApi,
    apiGet: (url: string, ...args: unknown[]) =>
      mockApi.get(url, ...args).then((r: { data: unknown }) => r.data),
    apiPost: (url: string, ...args: unknown[]) =>
      mockApi.post(url, ...args).then((r: { data: unknown }) => r.data),
    apiPut: (url: string, ...args: unknown[]) =>
      mockApi.put(url, ...args).then((r: { data: unknown }) => r.data),
    apiPatch: (url: string, ...args: unknown[]) =>
      mockApi.patch(url, ...args).then((r: { data: unknown }) => r.data),
    apiDelete: (url: string, ...args: unknown[]) =>
      mockApi.delete(url, ...args).then((r: { data: unknown }) => r.data),
  };
});

vi.mock("@/api/rebalancing", () => ({
  fetchBrokerBalance: vi.fn(),
  fetchAllBrokerBalances: vi.fn(),
  executeRebalancing: vi.fn(),
  analyzePortfolio: vi.fn(),
}));

vi.mock("@/api/assets", () => ({
  fetchStockPrice: vi.fn(),
  fetchAccounts: vi.fn().mockResolvedValue([]),
  fetchExchangeRate: vi.fn().mockResolvedValue({ usd_krw: 1350 }),
}));

vi.mock("@/utils/toast", () => ({ toast: vi.fn() }));

vi.mock("@/utils/queryInvalidation", () => ({
  invalidateSyncData: vi.fn().mockResolvedValue(undefined),
  invalidateAccountData: vi.fn(),
}));

vi.mock("../hooks/useHaptic", () => ({ triggerHaptic: vi.fn().mockResolvedValue(undefined) }));
vi.mock("@/hooks/useHaptic", () => ({ triggerHaptic: vi.fn().mockResolvedValue(undefined) }));

// ── imports ───────────────────────────────────────────────────────────────────

import { useRebalancingBalances } from "@/hooks/useRebalancingBalances";
import { useRebalancingPrices } from "@/hooks/useRebalancingPrices";
import {
  useRebalancingExecution,
  getActionableItems,
  executionReducer,
} from "@/hooks/rebalancingExecution/index";
import type { ExecutionState, ExecutionAction } from "@/hooks/rebalancingExecution/types";
import type { RebalancingAnalysis } from "@/api/rebalancing";
import type { AssetAccount } from "@/api/assets";

// ── helpers ───────────────────────────────────────────────────────────────────

function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
}

const mockAnalysis: RebalancingAnalysis = {
  portfolio_id: "p1",
  portfolio_name: "Test Portfolio",
  base_type: "STOCK",
  base_value_krw: 10000000,
  items: [
    {
      ticker: "005930",
      name: "삼성전자",
      market: "KRX",
      target_weight_pct: 50,
      current_weight_pct: 40,
      weight_diff_pct: 10,
      current_value_krw: 4000000,
      target_value_krw: 5000000,
      diff_krw: 1000000,
      shares_to_trade: 10,
      current_price_krw: 70000,
    },
    {
      ticker: "AAPL",
      name: "Apple Inc.",
      market: "NASDAQ",
      target_weight_pct: 50,
      current_weight_pct: 60,
      weight_diff_pct: -10,
      current_value_krw: 6000000,
      target_value_krw: 5000000,
      diff_krw: -1000000,
      shares_to_trade: -5,
      current_price_krw: 180000,
    },
  ],
  untracked_holdings: [],
  analyzed_at: "2024-01-01T00:00:00Z",
  current_portfolio_annual_dividend: 0,
  target_portfolio_annual_dividend: 0,
  ticker_account_map: {
    "005930": [
      {
        account_id: "acc1",
        account_name: "KIS 계좌",
        asset_type: "STOCK_KIS",
        quantity: 10,
        value_krw: 700000,
        is_mock_mode: false,
      },
    ],
    AAPL: [
      {
        account_id: "acc1",
        account_name: "KIS 계좌",
        asset_type: "STOCK_KIS",
        quantity: 5,
        value_krw: 900000,
        is_mock_mode: false,
      },
    ],
  },
};

 
const mockKisAccounts: AssetAccount[] = [
  {
    id: "acc1",
    name: "KIS 계좌",
    asset_type: "STOCK_KIS",
    balance: 5000000,
    data_source: "KIS_API",
    deposit_krw: 5000000,
    deposit_usd: null,
    is_mock_mode: false,
    target_portfolio_id: null,
  } as unknown as AssetAccount,
];

const baseState: ExecutionState = {
  liveBalances: {},
  balanceState: {},
  depositKrw: {},
  orderableKrw: {},
  priceState: "idle",
  priceLoadProgress: { loaded: 0, total: 0 },
  livePricesKrw: {},
  livePricesUsd: {},
  globalUsdRate: null,
  orderType: "MARKET",
  limitPriceOverrides: {},
  qtyOverrides: {},
  buyAccounts: {},
  selected: new Set(),
  phase: "confirm",
  results: [],
  errorMsg: null,
  confirmed: false,
};

// ── executionReducer ──────────────────────────────────────────────────────────

describe("executionReducer", () => {
  it("BALANCES_START — accountId들의 상태를 loading으로 설정한다", () => {
    const action: ExecutionAction = { type: "BALANCES_START", accountIds: ["acc1", "acc2"] };
    const result = executionReducer(baseState, action);
    expect(result.balanceState["acc1"]).toBe("loading");
    expect(result.balanceState["acc2"]).toBe("loading");
  });

  it("BALANCES_LOADED — 잔고와 입금을 업데이트한다", () => {
    const action: ExecutionAction = {
      type: "BALANCES_LOADED",
      balances: {
        acc1: [
          {
            ticker: "005930",
            quantity: 10,
            value_krw: 700000,
            avg_price: 70000,
            current_price: 70000,
            name: "삼성전자",
            market: "KRX",
          },
        ],
      },
      deposits: { acc1: 1000000 },
      orderables: { acc1: 800000 },
      states: { acc1: "loaded" },
    };
    const result = executionReducer(baseState, action);
    expect(result.liveBalances["acc1"]).toHaveLength(1);
    expect(result.depositKrw["acc1"]).toBe(1000000);
    expect(result.orderableKrw["acc1"]).toBe(800000);
    expect(result.balanceState["acc1"]).toBe("loaded");
  });

  it("BALANCES_ERROR — accountId들의 상태를 error로 설정한다", () => {
    const action: ExecutionAction = { type: "BALANCES_ERROR", accountIds: ["acc1"] };
    const result = executionReducer(baseState, action);
    expect(result.balanceState["acc1"]).toBe("error");
  });

  it("BALANCE_LOADING — 단일 계좌 상태를 loading으로 설정한다", () => {
    const action: ExecutionAction = { type: "BALANCE_LOADING", accountId: "acc1" };
    const result = executionReducer(baseState, action);
    expect(result.balanceState["acc1"]).toBe("loading");
  });

  it("BALANCE_LOADED — 단일 계좌 잔고를 업데이트한다", () => {
    const action: ExecutionAction = {
      type: "BALANCE_LOADED",
      accountId: "acc1",
      positions: [],
      deposit: 2000000,
      orderable: 1500000,
    };
    const result = executionReducer(baseState, action);
    expect(result.depositKrw["acc1"]).toBe(2000000);
    expect(result.orderableKrw["acc1"]).toBe(1500000);
    expect(result.balanceState["acc1"]).toBe("loaded");
  });

  it("BALANCE_ERROR — is404=true이면 not_found로 설정한다", () => {
    const action: ExecutionAction = { type: "BALANCE_ERROR", accountId: "acc1", is404: true };
    const result = executionReducer(baseState, action);
    expect(result.balanceState["acc1"]).toBe("not_found");
  });

  it("BALANCE_ERROR — is404=false이면 error로 설정한다", () => {
    const action: ExecutionAction = { type: "BALANCE_ERROR", accountId: "acc1", is404: false };
    const result = executionReducer(baseState, action);
    expect(result.balanceState["acc1"]).toBe("error");
  });

  it("PRICES_START — priceState를 loading으로 설정한다", () => {
    const action: ExecutionAction = { type: "PRICES_START", total: 5 };
    const result = executionReducer(baseState, action);
    expect(result.priceState).toBe("loading");
    expect(result.priceLoadProgress).toEqual({ loaded: 0, total: 5 });
  });

  it("PRICES_PROGRESS — loaded 카운트를 업데이트한다", () => {
    const state = { ...baseState, priceLoadProgress: { loaded: 0, total: 5 } };
    const action: ExecutionAction = { type: "PRICES_PROGRESS", loaded: 3 };
    const result = executionReducer(state, action);
    expect(result.priceLoadProgress.loaded).toBe(3);
  });

  it("PRICES_DONE — 가격 데이터를 설정하고 priceState를 loaded로 설정한다", () => {
    const action: ExecutionAction = {
      type: "PRICES_DONE",
      krw: { "005930": 70000 },
      usd: { AAPL: 150 },
      usdRate: 1350,
    };
    const result = executionReducer(baseState, action);
    expect(result.livePricesKrw["005930"]).toBe(70000);
    expect(result.livePricesUsd["AAPL"]).toBe(150);
    expect(result.globalUsdRate).toBe(1350);
    expect(result.priceState).toBe("loaded");
  });

  it("PRICES_DONE — krw가 비어있으면 priceState를 error로 설정한다", () => {
    const action: ExecutionAction = { type: "PRICES_DONE", krw: {}, usd: {}, usdRate: null };
    const result = executionReducer(baseState, action);
    expect(result.priceState).toBe("error");
  });

  it("SET_ORDER_TYPE — 주문 유형을 업데이트한다", () => {
    const action: ExecutionAction = { type: "SET_ORDER_TYPE", orderType: "LIMIT" };
    const result = executionReducer(baseState, action);
    expect(result.orderType).toBe("LIMIT");
  });

  it("TOGGLE_SELECTED — 선택되지 않은 키를 추가한다", () => {
    const action: ExecutionAction = { type: "TOGGLE_SELECTED", key: "buy_005930_acc1" };
    const result = executionReducer(baseState, action);
    expect(result.selected.has("buy_005930_acc1")).toBe(true);
  });

  it("TOGGLE_SELECTED — 이미 선택된 키를 제거한다", () => {
    const state = { ...baseState, selected: new Set(["buy_005930_acc1"]) };
    const action: ExecutionAction = { type: "TOGGLE_SELECTED", key: "buy_005930_acc1" };
    const result = executionReducer(state, action);
    expect(result.selected.has("buy_005930_acc1")).toBe(false);
  });

  it("EXECUTE_START — phase를 executing으로 설정한다", () => {
    const action: ExecutionAction = { type: "EXECUTE_START" };
    const result = executionReducer(baseState, action);
    expect(result.phase).toBe("executing");
    expect(result.errorMsg).toBeNull();
  });

  it("EXECUTE_SUCCESS — phase를 result로 설정한다", () => {
    const action: ExecutionAction = { type: "EXECUTE_SUCCESS", results: [] };
    const result = executionReducer(baseState, action);
    expect(result.phase).toBe("result");
  });

  it("EXECUTE_ERROR — phase를 confirm으로 되돌리고 에러 메시지를 설정한다", () => {
    const state = { ...baseState, phase: "executing" as const };
    const action: ExecutionAction = { type: "EXECUTE_ERROR", msg: "오류 발생" };
    const result = executionReducer(state, action);
    expect(result.phase).toBe("confirm");
    expect(result.errorMsg).toBe("오류 발생");
  });

  it("ADD_BUY_ACCOUNT — 매수 계좌를 추가한다", () => {
    const action: ExecutionAction = {
      type: "ADD_BUY_ACCOUNT",
      ticker: "005930",
      accountId: "acc2",
    };
    const result = executionReducer(baseState, action);
    expect(result.buyAccounts["005930"]).toContain("acc2");
  });

  it("REMOVE_BUY_ACCOUNT — 매수 계좌를 제거한다", () => {
    const state = {
      ...baseState,
      buyAccounts: { "005930": ["acc1", "acc2"] },
      selected: new Set(["buy_005930_acc1"]),
    };
    const action: ExecutionAction = {
      type: "REMOVE_BUY_ACCOUNT",
      ticker: "005930",
      accountId: "acc1",
    };
    const result = executionReducer(state, action);
    expect(result.buyAccounts["005930"]).not.toContain("acc1");
    expect(result.selected.has("buy_005930_acc1")).toBe(false);
  });

  it("CONFIRM_CLICK — confirmed를 true로 설정한다", () => {
    const action: ExecutionAction = { type: "CONFIRM_CLICK" };
    const result = executionReducer(baseState, action);
    expect(result.confirmed).toBe(true);
  });

  it("SET_QTY — 수량을 업데이트한다", () => {
    const action: ExecutionAction = { type: "SET_QTY", key: "buy_005930_acc1", qty: 5 };
    const result = executionReducer(baseState, action);
    expect(result.qtyOverrides["buy_005930_acc1"]).toBe(5);
  });

  it("SET_QTY_AND_SELECT — qty > 0이면 selected에 추가한다", () => {
    const action: ExecutionAction = { type: "SET_QTY_AND_SELECT", key: "buy_005930_acc1", qty: 3 };
    const result = executionReducer(baseState, action);
    expect(result.qtyOverrides["buy_005930_acc1"]).toBe(3);
    expect(result.selected.has("buy_005930_acc1")).toBe(true);
  });

  it("SET_QTY_AND_SELECT — qty === 0이면 selected에서 제거한다", () => {
    const state = { ...baseState, selected: new Set(["buy_005930_acc1"]) };
    const action: ExecutionAction = { type: "SET_QTY_AND_SELECT", key: "buy_005930_acc1", qty: 0 };
    const result = executionReducer(state, action);
    expect(result.selected.has("buy_005930_acc1")).toBe(false);
  });
});

// ── getActionableItems ────────────────────────────────────────────────────────

describe("getActionableItems", () => {
  it("shares_to_trade가 null인 아이템을 필터링한다", () => {
    const analysis = {
      ...mockAnalysis,
      items: [
        ...mockAnalysis.items,
        { ...mockAnalysis.items[0], ticker: "CASH", shares_to_trade: null },
      ],
    };
    const result = getActionableItems(analysis);
    expect(result.every((i) => i.shares_to_trade !== null)).toBe(true);
  });

  it("shares_to_trade가 1 미만인 아이템을 필터링한다", () => {
    const analysis = {
      ...mockAnalysis,
      items: [
        { ...mockAnalysis.items[0], shares_to_trade: 0 },
        { ...mockAnalysis.items[1], shares_to_trade: 5 },
      ],
    };
    const result = getActionableItems(analysis);
    expect(result).toHaveLength(1);
    expect(result[0].ticker).toBe("AAPL");
  });

  it("매수·매도 아이템을 모두 반환한다", () => {
    const result = getActionableItems(mockAnalysis);
    expect(result).toHaveLength(2);
  });
});

// ── useRebalancingBalances ────────────────────────────────────────────────────

describe("useRebalancingBalances", () => {
  beforeEach(() => vi.clearAllMocks());

  it("loadLiveBalance — 성공 시 BALANCE_LOADED를 dispatch한다", async () => {
    const { fetchBrokerBalance } = await import("@/api/rebalancing");
    vi.mocked(fetchBrokerBalance).mockResolvedValue({
      account_id: "acc1",
      account_name: "KIS 계좌",
      is_mock: false,
      positions: [
        {
          ticker: "005930",
          quantity: 10,
          value_krw: 700000,
          avg_price: 70000,
          current_price: 70000,
          name: "삼성전자",
          market: "KRX",
        },
      ],
      deposit_krw: 1000000,
      orderable_krw: 800000,
      error: null,
    });

    const dispatch = vi.fn();
    const { result } = renderHook(() => useRebalancingBalances(dispatch, mockKisAccounts), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await result.current.loadLiveBalance("acc1");
    });

    expect(dispatch).toHaveBeenCalledWith({ type: "BALANCE_LOADING", accountId: "acc1" });
    expect(dispatch).toHaveBeenCalledWith(
      expect.objectContaining({ type: "BALANCE_LOADED", accountId: "acc1" }),
    );
  });

  it("loadLiveBalance — 에러 시 BALANCE_ERROR를 dispatch한다", async () => {
    const { fetchBrokerBalance } = await import("@/api/rebalancing");
    vi.mocked(fetchBrokerBalance).mockRejectedValue(new Error("네트워크 오류"));

    const dispatch = vi.fn();
    const { result } = renderHook(() => useRebalancingBalances(dispatch, mockKisAccounts), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await result.current.loadLiveBalance("acc1");
    });

    expect(dispatch).toHaveBeenCalledWith({ type: "BALANCE_LOADING", accountId: "acc1" });
    expect(dispatch).toHaveBeenCalledWith(
      expect.objectContaining({ type: "BALANCE_ERROR", accountId: "acc1" }),
    );
  });

  it("loadAllLiveBalances — kisAccounts가 비어있으면 아무 것도 하지 않는다", async () => {
    const dispatch = vi.fn();
    const { result } = renderHook(() => useRebalancingBalances(dispatch, []), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await result.current.loadAllLiveBalances();
    });

    expect(dispatch).not.toHaveBeenCalled();
  });

  it("loadAllLiveBalances — 성공 시 BALANCES_LOADED를 dispatch한다", async () => {
    const { fetchAllBrokerBalances } = await import("@/api/rebalancing");
    vi.mocked(fetchAllBrokerBalances).mockResolvedValue([
      {
        account_id: "acc1",
        account_name: "KIS 계좌",
        is_mock: false,
        positions: [],
        deposit_krw: 1000000,
        orderable_krw: 800000,
        error: null,
      },
    ]);

    const dispatch = vi.fn();
    const { result } = renderHook(() => useRebalancingBalances(dispatch, mockKisAccounts), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await result.current.loadAllLiveBalances();
    });

    expect(dispatch).toHaveBeenCalledWith(expect.objectContaining({ type: "BALANCES_START" }));
    expect(dispatch).toHaveBeenCalledWith(expect.objectContaining({ type: "BALANCES_LOADED" }));
  });

  it("loadAllLiveBalances — 에러 응답 시 states에 error를 설정한다", async () => {
    const { fetchAllBrokerBalances } = await import("@/api/rebalancing");
    vi.mocked(fetchAllBrokerBalances).mockResolvedValue([
      {
        account_id: "acc1",
        account_name: "KIS 계좌",
        is_mock: false,
        positions: [],
        deposit_krw: 0,
        orderable_krw: null,
        error: "Failed",
      },
    ]);

    const dispatch = vi.fn();
    const { result } = renderHook(() => useRebalancingBalances(dispatch, mockKisAccounts), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await result.current.loadAllLiveBalances();
    });

    const loadedCall = dispatch.mock.calls.find((c) => c[0].type === "BALANCES_LOADED");
    expect(loadedCall).toBeDefined();
    expect(loadedCall![0].states["acc1"]).toBe("error");
  });
});

// ── useRebalancingPrices ──────────────────────────────────────────────────────

describe("useRebalancingPrices", () => {
  beforeEach(() => vi.clearAllMocks());

  it("loadAllPrices — 아이템이 없으면 아무 것도 하지 않는다", async () => {
    const emptyAnalysis = { ...mockAnalysis, items: [], untracked_holdings: [] };
    const dispatch = vi.fn();
    const { result } = renderHook(() => useRebalancingPrices(dispatch, emptyAnalysis));

    await act(async () => {
      await result.current.loadAllPrices();
    });

    expect(dispatch).not.toHaveBeenCalled();
  });

  it("loadAllPrices — 성공 시 PRICES_DONE을 dispatch한다", async () => {
    const { fetchStockPrice } = await import("@/api/assets");
    vi.mocked(fetchStockPrice).mockResolvedValue({
      price_krw: 70000,
      price_usd: null,
      usd_rate: null,
    });

    const dispatch = vi.fn();
    const { result } = renderHook(() => useRebalancingPrices(dispatch, mockAnalysis));

    await act(async () => {
      await result.current.loadAllPrices();
    });

    expect(dispatch).toHaveBeenCalledWith(expect.objectContaining({ type: "PRICES_DONE" }));
  });

  it("loadAllPrices — PRICES_DONE 또는 PRICES_START를 dispatch한다", async () => {
    const { fetchStockPrice } = await import("@/api/assets");
    vi.mocked(fetchStockPrice).mockResolvedValue({
      price_krw: 80000,
      price_usd: null,
      usd_rate: null,
    });

    const dispatch = vi.fn();
    // Use a fresh analysis with unique tickers to avoid price cache
    const freshAnalysis: RebalancingAnalysis = {
      ...mockAnalysis,
      items: [{ ...mockAnalysis.items[0], ticker: "FRESH1" }],
      untracked_holdings: [],
      ticker_account_map: {},
    };
    const { result } = renderHook(() => useRebalancingPrices(dispatch, freshAnalysis));

    await act(async () => {
      await result.current.loadAllPrices();
    });

    const types = dispatch.mock.calls.map((c) => c[0].type);
    // At least PRICES_DONE should have been called
    expect(types).toContain("PRICES_DONE");
  });
});

// ── useRebalancingExecution ───────────────────────────────────────────────────

describe("useRebalancingExecution", () => {
  beforeEach(() => vi.clearAllMocks());

  it("초기 상태가 올바르게 설정된다", async () => {
    const { fetchAllBrokerBalances } = await import("@/api/rebalancing");
    const { fetchStockPrice } = await import("@/api/assets");
    vi.mocked(fetchAllBrokerBalances).mockResolvedValue([]);
    vi.mocked(fetchStockPrice).mockResolvedValue({
      price_krw: 70000,
      price_usd: null,
      usd_rate: null,
    });

    const { result } = renderHook(
      () =>
        useRebalancingExecution({
          portfolioId: "p1",
          analysis: mockAnalysis,
          accounts: mockKisAccounts,
        }),
      { wrapper: createWrapper() },
    );

    expect(result.current.state.phase).toBe("confirm");
    expect(result.current.state.orderType).toBe("MARKET");
    expect(result.current.kisAccounts).toHaveLength(1);
  });

  it("actionableItems에서 거래 가능한 아이템만 반환한다", async () => {
    const { fetchAllBrokerBalances } = await import("@/api/rebalancing");
    vi.mocked(fetchAllBrokerBalances).mockResolvedValue([]);

    const { result } = renderHook(
      () =>
        useRebalancingExecution({
          portfolioId: "p1",
          analysis: mockAnalysis,
          accounts: mockKisAccounts,
        }),
      { wrapper: createWrapper() },
    );

    expect(result.current.actionableItems).toHaveLength(2);
  });

  it("dispatch를 통해 orderType을 변경할 수 있다", async () => {
    const { fetchAllBrokerBalances } = await import("@/api/rebalancing");
    vi.mocked(fetchAllBrokerBalances).mockResolvedValue([]);

    const { result } = renderHook(
      () =>
        useRebalancingExecution({
          portfolioId: "p1",
          analysis: mockAnalysis,
          accounts: mockKisAccounts,
        }),
      { wrapper: createWrapper() },
    );

    act(() => {
      result.current.dispatch({ type: "SET_ORDER_TYPE", orderType: "LIMIT" });
    });

    expect(result.current.state.orderType).toBe("LIMIT");
  });
});
