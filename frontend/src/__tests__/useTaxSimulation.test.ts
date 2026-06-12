import { describe, it, expect } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useTaxSimulation, TAX_DEDUCTION, TAX_RATE, posKey } from "@/hooks/useTaxSimulation";
import type { OverseasPositionDetail } from "@/api/tax";

function makePos(overrides: Partial<OverseasPositionDetail> = {}): OverseasPositionDetail {
  return {
    ticker: "AAPL",
    name: "Apple",
    market: "NASDAQ",
    currency: "USD",
    account_id: "acc-1",
    account_name: "테스트 계좌",
    qty: 10,
    avg_price_krw: 150000,
    current_price_krw: 200000,
    avg_price_usd: null,
    value_krw: 2000000,
    invested_krw: 1500000,
    unrealized_pnl_krw: 500000,
    unrealized_pnl_pct: 33.33,
    ...overrides,
  };
}

describe("posKey", () => {
  it("account_id와 ticker를 결합한 키를 반환한다", () => {
    const pos = makePos({ account_id: "acc-1", ticker: "AAPL" });
    expect(posKey(pos)).toBe("acc-1-AAPL");
  });
});

describe("useTaxSimulation", () => {
  it("초기 상태가 올바르다", () => {
    const { result } = renderHook(() => useTaxSimulation([]));
    expect(result.current.alreadyRealizedInput).toBe("");
    expect(result.current.alreadyRealized).toBe(0);
    expect(result.current.profitPositions).toEqual([]);
    expect(result.current.lossPositions).toEqual([]);
    expect(result.current.totalLoss).toBe(0);
    expect(result.current.currentTax).toBe(0);
    expect(result.current.simTax).toBe(0);
  });

  it("수익 포지션과 손실 포지션을 올바르게 분류한다", () => {
    const profitPos = makePos({ unrealized_pnl_krw: 500000, ticker: "AAPL" });
    const lossPos = makePos({ unrealized_pnl_krw: -200000, ticker: "MSFT" });
    const { result } = renderHook(() => useTaxSimulation([profitPos, lossPos]));

    expect(result.current.profitPositions).toHaveLength(1);
    expect(result.current.lossPositions).toHaveLength(1);
    expect(result.current.profitPositions[0].ticker).toBe("AAPL");
    expect(result.current.lossPositions[0].ticker).toBe("MSFT");
  });

  it("손실 합계가 올바르게 계산된다", () => {
    const positions = [
      makePos({ unrealized_pnl_krw: -200000, ticker: "MSFT" }),
      makePos({ unrealized_pnl_krw: -300000, ticker: "GOOG" }),
    ];
    const { result } = renderHook(() => useTaxSimulation(positions));
    expect(result.current.totalLoss).toBe(-500000);
  });

  it("alreadyRealizedInput 변경이 alreadyRealized를 업데이트한다", () => {
    const { result } = renderHook(() => useTaxSimulation([]));
    act(() => {
      result.current.setAlreadyRealizedInput("1,000,000");
    });
    expect(result.current.alreadyRealized).toBe(1000000);
  });

  it("잘못된 alreadyRealizedInput은 0으로 처리된다", () => {
    const { result } = renderHook(() => useTaxSimulation([]));
    act(() => {
      result.current.setAlreadyRealizedInput("abc");
    });
    expect(result.current.alreadyRealized).toBe(0);
  });

  it("기공제 금액이 TAX_DEDUCTION 미만이면 remainingDeduction이 양수다", () => {
    const { result } = renderHook(() => useTaxSimulation([]));
    act(() => {
      result.current.setAlreadyRealizedInput("1000000");
    });
    expect(result.current.remainingDeduction).toBe(TAX_DEDUCTION - 1000000);
  });

  it("currentTax는 기본공제 초과분의 TAX_RATE 세금이다", () => {
    const { result } = renderHook(() => useTaxSimulation([]));
    act(() => {
      result.current.setAlreadyRealizedInput("5000000"); // 공제 한도 초과
    });
    const expectedTax = Math.round((5000000 - TAX_DEDUCTION) * TAX_RATE);
    expect(result.current.currentTax).toBe(expectedTax);
  });

  it("공제한도 미달 시 currentTax는 0이다", () => {
    const { result } = renderHook(() => useTaxSimulation([]));
    act(() => {
      result.current.setAlreadyRealizedInput("1000000");
    });
    expect(result.current.currentTax).toBe(0);
  });

  it("handleQtyChange가 sellQtyMap을 업데이트한다", () => {
    const pos = makePos({ qty: 100, ticker: "AAPL" });
    const { result } = renderHook(() => useTaxSimulation([pos]));
    act(() => {
      result.current.handleQtyChange(pos, "50");
    });
    expect(result.current.sellQtyMap[posKey(pos)]).toBe(50);
  });

  it("handleQtyChange는 최대값을 pos.qty로 제한한다", () => {
    const pos = makePos({ qty: 100, ticker: "AAPL" });
    const { result } = renderHook(() => useTaxSimulation([pos]));
    act(() => {
      result.current.handleQtyChange(pos, "200");
    });
    expect(result.current.sellQtyMap[posKey(pos)]).toBe(100);
  });

  it("handleQtyChange는 최솟값을 0으로 제한한다", () => {
    const pos = makePos({ qty: 100, ticker: "AAPL" });
    const { result } = renderHook(() => useTaxSimulation([pos]));
    act(() => {
      result.current.handleQtyChange(pos, "-10");
    });
    expect(result.current.sellQtyMap[posKey(pos)]).toBe(0);
  });

  it("deductionUsedPct가 올바르게 계산된다", () => {
    const { result } = renderHook(() => useTaxSimulation([]));
    act(() => {
      result.current.setAlreadyRealizedInput(String(TAX_DEDUCTION / 2));
    });
    expect(result.current.deductionUsedPct).toBeCloseTo(50, 1);
  });

  it("기공제가 없을 때 수익 포지션에 대한 recommendations를 생성한다", () => {
    const profitPos = makePos({ unrealized_pnl_krw: 1000000, qty: 10, ticker: "AAPL" });
    const { result } = renderHook(() => useTaxSimulation([profitPos]));
    // 기공제 없음 → maxTaxFreeProfit = TAX_DEDUCTION + 0 = 2,500,000
    // profitPos.pnl (1,000,000) < 2,500,000 → 전량 매도 권장
    expect(result.current.recommendations).toHaveLength(1);
    expect(result.current.recommendations[0].label).toContain("전량");
  });

  it("sellQtyMap에 입력이 있으면 recommendations가 비어있다", () => {
    const profitPos = makePos({ unrealized_pnl_krw: 1000000, qty: 10, ticker: "AAPL" });
    const { result } = renderHook(() => useTaxSimulation([profitPos]));
    act(() => {
      result.current.handleQtyChange(profitPos, "5");
    });
    expect(result.current.recommendations).toEqual([]);
  });

  it("simTax와 simTaxDiff가 올바르게 계산된다", () => {
    const profitPos = makePos({ unrealized_pnl_krw: 5000000, qty: 10, ticker: "AAPL" });
    const { result } = renderHook(() => useTaxSimulation([profitPos]));
    act(() => {
      result.current.handleQtyChange(profitPos, "10");
    });
    // totalSimPnl = 5000000
    // simTotalRealized = 0 + 5000000 = 5000000
    // simTax = round(max(0, 5000000 - 2500000) * 0.22) = round(2500000 * 0.22) = 550000
    expect(result.current.simTax).toBe(550000);
    expect(result.current.simTaxDiff).toBe(550000 - 0);
  });
});
