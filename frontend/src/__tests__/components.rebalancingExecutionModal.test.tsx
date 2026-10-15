import { createContext } from "react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";
import type { RebalancingAnalysis } from "@/api/rebalancing";

const execMock = vi.hoisted(() => ({ current: {} as Record<string, unknown> }));

vi.mock("@/hooks/useRebalancingExecution", () => ({
  useRebalancingExecution: () => execMock.current,
  RebalancingExecutionContext: createContext(null),
}));
vi.mock("@/components/rebalancing/RebalancingConfirmStep", () => ({
  RebalancingConfirmStep: () => <div>confirm-step</div>,
}));
vi.mock("@/components/rebalancing/RebalancingResultSection", () => ({
  RebalancingResultSection: () => <div>result-section</div>,
}));

import { RebalancingExecutionModal } from "@/components/rebalancing/RebalancingExecutionModal";

const LIMIT_ORDER = {
  ticker: "AAPL",
  name: "Apple",
  market: "NASDAQ",
  side: "BUY",
  quantity: 1,
  account_id: "acc",
  order_type: "LIMIT",
  limit_price: null,
};

function setExec(over: {
  confirmed?: boolean;
  missing?: string[];
  orders?: unknown[];
  priceState?: string;
}) {
  const dispatch = vi.fn();
  const handleExecute = vi.fn();
  execMock.current = {
    state: {
      phase: "confirm",
      results: [],
      confirmed: over.confirmed ?? false,
      orderType: "LIMIT",
      priceState: over.priceState ?? "done",
      priceLoadProgress: { loaded: 0, total: 0 },
    },
    orders: over.orders ?? [LIMIT_ORDER],
    missingLimitPriceTickers: over.missing ?? [],
    dispatch,
    loadAllPrices: vi.fn(),
    handleExecute,
  };
  return { dispatch, handleExecute };
}

function renderModal() {
  renderWithProviders(
    <RebalancingExecutionModal
      portfolioId="p1"
      analysis={{} as RebalancingAnalysis}
      accounts={[]}
      onClose={vi.fn()}
    />,
  );
}

describe("RebalancingExecutionModal 실행 게이트", () => {
  beforeEach(() => vi.clearAllMocks());

  it("지정가가 빈 주문이 있으면 확인 버튼을 막고 종목을 알려준다", () => {
    setExec({ missing: ["AAPL", "AAPL"] });
    renderModal();

    expect(screen.getByRole("alert")).toHaveTextContent(
      "지정가가 비어 있는 주문이 있습니다: AAPL —",
    );
    expect(screen.getByRole("button", { name: /지정가 주문 확인/ })).toBeDisabled();
  });

  it("시세를 불러오는 중에는 누락 경고 대신 로딩만 보이고 버튼은 막혀 있다", () => {
    setExec({ missing: ["AAPL"], priceState: "loading" });
    renderModal();

    expect(screen.queryByText(/지정가가 비어 있는 주문이 있습니다/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /지정가 주문 확인/ })).toBeDisabled();
  });

  it("최종 실행 단계에서도 지정가 누락이면 실행하지 않는다", () => {
    const { handleExecute } = setExec({ confirmed: true, missing: ["AAPL"] });
    renderModal();

    const execute = screen.getByRole("button", { name: /최종 실행/ });
    expect(execute).toBeDisabled();
    fireEvent.click(execute);
    expect(handleExecute).not.toHaveBeenCalled();
  });

  it("가격이 모두 있으면 확인 버튼이 활성화되고 확인 단계로 넘어간다", () => {
    const { dispatch } = setExec({ orders: [{ ...LIMIT_ORDER, limit_price: 200 }] });
    renderModal();

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /지정가 주문 확인 \(1건\)/ }));
    expect(dispatch).toHaveBeenCalledWith({ type: "CONFIRM_CLICK" });
  });

  it("주문이 없으면 확인 버튼이 비활성화된다", () => {
    setExec({ orders: [] });
    renderModal();

    expect(screen.getByRole("button", { name: /주문 확인 \(0건\)/ })).toBeDisabled();
  });
});
