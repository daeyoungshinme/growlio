import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RebalancingConfirmStep } from "../RebalancingConfirmStep";

// 실주문 직전 화면 — 지금까지 0% 커버리지였다(plans/156 D). 표·현금 바는 각자 테스트가 있어 자리만 남긴다.
vi.mock("../RebalancingOrderTable", () => ({
  RebalancingOrderTable: ({ accId }: { accId: string }) => <div>order-table:{accId}</div>,
}));
vi.mock("../CashSummaryBar", () => ({ CashSummaryBar: () => null }));

const ctx = vi.hoisted(() => ({ value: {} as Record<string, unknown> }));
vi.mock("@/hooks/useRebalancingExecution", () => ({
  useRebalancingExecutionContext: () => ctx.value,
}));

const account = (over: Record<string, unknown> = {}) => ({
  id: "acc-1",
  name: "키움 종합",
  kis_account_no: null,
  is_mock_mode: false,
  is_active: true,
  ...over,
});

function makeContext(over: Record<string, unknown> = {}, stateOver: Record<string, unknown> = {}) {
  return {
    tradableAccounts: [account()],
    actionableItems: [],
    dispatch: vi.fn(),
    getSellRows: () => [{ ticker: "AAA" }],
    getBuyRows: () => [],
    getBuyTotalInfo: vi.fn(),
    getAddableBuyItems: () => [],
    addBuyAccount: vi.fn(),
    getAccountSummary: () => ({ sells: 1, buys: 0 }),
    getLimitPriceNative: vi.fn(),
    getEstimateKrw: vi.fn(),
    loadLiveBalance: vi.fn(),
    retryPrice: vi.fn(),
    loadAllPrices: vi.fn(),
    hasRealAccount: true,
    globalCashSummary: { balancesLoaded: false },
    autoAdjustForCash: vi.fn(),
    getCashAnalysis: () => ({ krwOverseasOrder: false }),
    state: {
      strategy: "FULL",
      balanceState: {},
      depositKrw: {},
      depositUsd: {},
      orderableKrw: {},
      priceState: {},
      priceRetrying: {},
      livePricesKrw: {},
      livePricesUsd: {},
      globalUsdRate: 1400,
      orderType: "MARKET",
      qtyOverrides: {},
      selected: {},
      buyAccounts: {},
      errorMsg: null,
      ...stateOver,
    },
    ...over,
  };
}

describe("RebalancingConfirmStep", () => {
  beforeEach(() => {
    ctx.value = makeContext();
  });

  it("실계좌가 섞이면 실제 자금 경고와 실계좌 배지를 보인다", () => {
    render(<RebalancingConfirmStep ordersCount={1} />);
    expect(screen.getByText("실계좌 주문입니다. 실제 자금이 사용됩니다.")).toBeDefined();
    expect(screen.getByText("실계좌")).toBeDefined();
    expect(screen.getByText("order-table:acc-1")).toBeDefined();
  });

  it("모의 계좌만이면 실계좌 경고를 띄우지 않는다", () => {
    ctx.value = makeContext({
      hasRealAccount: false,
      tradableAccounts: [account({ is_mock_mode: true })],
    });
    render(<RebalancingConfirmStep ordersCount={1} />);
    expect(screen.queryByText("실계좌 주문입니다. 실제 자금이 사용됩니다.")).toBeNull();
    expect(screen.getByText("모의")).toBeDefined();
  });

  it("주문 방식을 고르면 SET_STRATEGY를 보내고, 매수만이면 건너뛰는 매도 수를 알린다", () => {
    const dispatch = vi.fn();
    ctx.value = makeContext(
      {
        dispatch,
        actionableItems: [{ shares_to_trade: -3 }, { shares_to_trade: -1 }, { shares_to_trade: 2 }],
      },
      { strategy: "BUY_ONLY" },
    );
    render(<RebalancingConfirmStep ordersCount={1} />);

    expect(screen.getByText(/과비중 2개 종목은 매도하지 않고/)).toBeDefined();
    fireEvent.click(screen.getByText("매도+매수"));
    expect(dispatch).toHaveBeenCalledWith({ type: "SET_STRATEGY", strategy: "FULL" });
  });

  it("예수금이 부족하면 부족액과 자동 조정 버튼을 보인다", () => {
    const autoAdjustForCash = vi.fn();
    ctx.value = makeContext({
      autoAdjustForCash,
      globalCashSummary: {
        balancesLoaded: true,
        isInsufficient: true,
        totalDeposit: 1_000_000,
        totalSellProceeds: 0,
        totalAvailable: 1_000_000,
        totalBuyCost: 1_500_000,
        surplus: -500_000,
      },
    });
    render(<RebalancingConfirmStep ordersCount={1} />);

    expect(screen.getByText("부족 50만원")).toBeDefined();
    fireEvent.click(screen.getByText("예수금에 맞춰 자동 조정"));
    expect(autoAdjustForCash).toHaveBeenCalled();
  });

  it("잔고 조회 버튼은 그 계좌의 실시간 잔고를 불러온다", () => {
    const loadLiveBalance = vi.fn();
    ctx.value = makeContext({ loadLiveBalance });
    render(<RebalancingConfirmStep ordersCount={1} />);
    fireEvent.click(screen.getByText("잔고 조회"));
    expect(loadLiveBalance).toHaveBeenCalledWith("acc-1");
  });

  it("주문 가능 계좌가 없거나 주문이 0건이면 안내한다", () => {
    ctx.value = makeContext({ tradableAccounts: [] });
    const { unmount } = render(<RebalancingConfirmStep ordersCount={0} />);
    expect(screen.getByText("연결된 KIS/키움 계좌가 없습니다.")).toBeDefined();
    unmount();

    ctx.value = makeContext();
    render(<RebalancingConfirmStep ordersCount={0} />);
    expect(screen.getByText(/실행할 주문이 없습니다/)).toBeDefined();
  });

  it("미배정 매수 종목을 이 계좌에 추가한다", () => {
    const addBuyAccount = vi.fn();
    ctx.value = makeContext({
      addBuyAccount,
      getAddableBuyItems: () => [{ ticker: "QQQ", name: "나스닥100", shares_to_trade: 3 }],
    });
    render(<RebalancingConfirmStep ordersCount={1} />);
    fireEvent.change(screen.getByLabelText("이 계좌로 매수할 종목 추가"), {
      target: { value: "QQQ" },
    });
    expect(addBuyAccount).toHaveBeenCalledWith("QQQ", "acc-1");
  });
});
