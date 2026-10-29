import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor, within } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";

const cancelExecutionOrder = vi.fn();
vi.mock("@/api/rebalancing", async (orig) => ({
  ...(await orig<typeof import("@/api/rebalancing")>()),
  cancelExecutionOrder: (id: string) => cancelExecutionOrder(id),
}));

const toast = vi.fn();
vi.mock("@/utils/toast", () => ({ toast: (...args: unknown[]) => toast(...args) }));

import { OrderResultList } from "@/components/rebalancing/OrderResultList";
import type { ExecutionResult, OrderResult } from "@/api/rebalancing";

function order(extra: Partial<OrderResult> = {}): OrderResult {
  return {
    ticker: "069500",
    name: "KODEX 200",
    market: "KOSPI",
    side: "BUY",
    quantity: 3,
    status: "SUCCESS",
    order_no: "0001",
    error_msg: null,
    order_type: "LIMIT",
    price: 35000,
    ...extra,
  };
}

function results(orders: OrderResult[]): ExecutionResult[] {
  return [
    {
      account_id: "acc",
      account_name: "KIS 계좌",
      is_mock: true,
      orders,
      success_count: orders.length,
      fail_count: 0,
      executed_at: "",
    },
  ];
}

// 모바일 카드(sm:hidden)와 데스크탑 표가 함께 렌더링되므로 첫 번째 것만 조작한다
const firstCancelButton = () => screen.getAllByRole("button", { name: "미체결 취소" })[0];

describe("OrderResultList — 미체결 취소", () => {
  beforeEach(() => {
    cancelExecutionOrder.mockReset();
    toast.mockReset();
  });

  it("cancelable이 아닌 주문(과거 결과·실패 주문)에는 취소 버튼이 없다", () => {
    renderWithProviders(
      <OrderResultList
        results={results([order(), order({ result_id: "r2", cancelable: false })])}
      />,
    );
    expect(screen.queryByRole("button", { name: "미체결 취소" })).toBeNull();
  });

  it("확인 후 취소 API를 부르고 '미체결 취소됨'을 표시한다", async () => {
    cancelExecutionOrder.mockResolvedValue({
      result_id: "r1",
      cancel_status: "CANCELED",
      cancel_message: null,
      message: "미체결 수량이 취소되었습니다.",
    });
    renderWithProviders(
      <OrderResultList results={results([order({ result_id: "r1", cancelable: true })])} />,
    );

    fireEvent.click(firstCancelButton());
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/이미 체결된 수량은 취소되지 않습니다/)).toBeDefined();
    fireEvent.click(within(dialog).getByRole("button", { name: "미체결 취소" }));

    // 모바일 카드·데스크탑 표 두 벌이 같은 취소 상태를 보여 준다 — 화면 폭을 바꿔도 버튼이 되살아나지 않게(plans/90 A6)
    await waitFor(() => expect(screen.getAllByText("미체결 취소됨")).toHaveLength(2));
    expect(screen.queryByRole("button", { name: "미체결 취소" })).toBeNull();
    expect(cancelExecutionOrder).toHaveBeenCalledWith("r1");
    expect(toast).toHaveBeenCalledWith("미체결 수량이 취소되었습니다.", "success");
  });

  it("증권사 거부(이미 체결)는 실패 사유를 보여 주고 다시 시도할 수 있다", async () => {
    cancelExecutionOrder.mockResolvedValue({
      result_id: "r1",
      cancel_status: "CANCEL_FAILED",
      cancel_message: "취소가능수량이 없습니다",
      message: "취소하지 못했습니다: 취소가능수량이 없습니다",
    });
    renderWithProviders(
      <OrderResultList results={results([order({ result_id: "r1", cancelable: true })])} />,
    );

    fireEvent.click(firstCancelButton());
    fireEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "미체결 취소" }),
    );

    // 원 사유만 붙는다 — "취소 실패: 취소하지 못했습니다: …" 이중 접두가 아니다(plans/90 B6)
    await waitFor(() =>
      expect(screen.getAllByText("취소 실패: 취소가능수량이 없습니다")).toHaveLength(2),
    );
    expect(toast).toHaveBeenCalledWith(expect.stringContaining("취소가능수량"), "error");
    expect(firstCancelButton()).toBeDefined();
  });

  it("이력에서 이미 취소된 주문은 버튼 없이 상태만 표시한다", () => {
    renderWithProviders(
      <OrderResultList
        results={results([
          order({ result_id: "r1", cancelable: false, cancel_status: "CANCELED" }),
        ])}
      />,
    );
    expect(screen.getAllByText("미체결 취소됨").length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: "미체결 취소" })).toBeNull();
  });

  it("확인창은 body로 portal된다 — 하단 네비를 피하는 실행 모달 안에서 네비 아래로 깔리지 않게 (plans/90 A1)", () => {
    const { container } = renderWithProviders(
      <OrderResultList results={results([order({ result_id: "r1", cancelable: true })])} />,
    );
    fireEvent.click(firstCancelButton());
    const dialog = screen.getByRole("dialog");
    expect(container.contains(dialog)).toBe(false);
    expect(document.body.contains(dialog)).toBe(true);
  });
});
