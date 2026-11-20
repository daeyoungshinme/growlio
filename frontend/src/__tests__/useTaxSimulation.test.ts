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
    expect(result.current.profitPositions[0]!.ticker).toBe("AAPL");
    expect(result.current.lossPositions[0]!.ticker).toBe("MSFT");
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
    expect(result.current.recommendations[0]!.label).toContain("전량");
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

describe("useTaxSimulation — 증권사 자동 집계 실현손익(E6)", () => {
  it("입력 전에는 자동값을 쓰고 공제 잔여를 계산한다", () => {
    const { result } = renderHook(() => useTaxSimulation([], 2_000_000));
    expect(result.current.isManualRealized).toBe(false);
    expect(result.current.alreadyRealized).toBe(2_000_000);
    expect(result.current.remainingDeduction).toBe(TAX_DEDUCTION - 2_000_000);
  });

  it("직접 입력하면 자동값 대신 입력값을 쓴다", () => {
    const { result } = renderHook(() => useTaxSimulation([], 2_000_000));
    act(() => result.current.setAlreadyRealizedInput("3,000,000"));
    expect(result.current.isManualRealized).toBe(true);
    expect(result.current.alreadyRealized).toBe(3_000_000);
    expect(result.current.currentTax).toBe(Math.round(500_000 * TAX_RATE));
  });

  it("입력을 지우면 다시 자동값으로 돌아간다", () => {
    const { result } = renderHook(() => useTaxSimulation([], -1_000_000));
    act(() => result.current.setAlreadyRealizedInput("5"));
    act(() => result.current.setAlreadyRealizedInput(""));
    expect(result.current.alreadyRealized).toBe(-1_000_000);
    expect(result.current.remainingDeduction).toBe(TAX_DEDUCTION + 1_000_000);
  });
});

describe("useTaxSimulation — 백엔드 세금 요약의 공제·세율 사용 (plans/39 N4)", () => {
  it("넘겨받은 공제·세율로 계산한다", () => {
    const rule = { deduction: 5_000_000, rate: 0.2 };
    const { result } = renderHook(() => useTaxSimulation([], 6_000_000, rule));
    expect(result.current.taxDeduction).toBe(5_000_000);
    expect(result.current.remainingDeduction).toBe(0);
    expect(result.current.currentTax).toBe(200_000); // (600만 − 500만) × 20%
  });
});

describe("useTaxSimulation — 절세 추천이 올해 실현손익을 반영 (plans/139)", () => {
  // 주당 수익 5만원 × 10주 = 50만원
  const profit = makePos({ ticker: "AAPL", qty: 10, unrealized_pnl_krw: 500_000 });

  it("공제 잔여 15만원이면 3주만 추천하고 실현액도 3주 기준이다", () => {
    const { result } = renderHook(() => useTaxSimulation([profit], 2_350_000));
    const recs = result.current.recommendations;
    expect(recs).toHaveLength(1);
    expect(recs[0]!.kind).toBe("PROFIT");
    expect(recs[0]!.shares).toBe(3);
    expect(recs[0]!.realizedKrw).toBe(150_000);
    expect(recs[0]!.label).toBe("3주 매도");
    expect(result.current.lossHarvestRecommendations).toEqual([]);
  });

  it("손실 종목이 있어도 손실 매도 없는 수익 매도 추천을 따로 준다", () => {
    // 주당 손실 10만원 × 10주
    const loss = makePos({ ticker: "MSFT", qty: 10, unrealized_pnl_krw: -1_000_000 });
    const { result } = renderHook(() => useTaxSimulation([profit, loss], 2_350_000));
    const profitOnly = result.current.recommendations;
    expect(profitOnly.every((r) => r.kind === "PROFIT")).toBe(true);
    expect(profitOnly[0]!.shares).toBe(3);
    expect(profitOnly[0]!.realizedKrw).toBe(150_000);
  });

  it("손실 통산 추천은 필요한 손실 매도를 함께 넣고, 수익 실현은 잔여+손실 매도분 이내다", () => {
    const loss = makePos({ ticker: "MSFT", qty: 10, unrealized_pnl_krw: -1_000_000 });
    const { result } = renderHook(() => useTaxSimulation([profit, loss], 2_350_000));
    const recs = result.current.lossHarvestRecommendations;
    const profitSum = recs
      .filter((r) => r.kind === "PROFIT")
      .reduce((s, r) => s + r.realizedKrw, 0);
    const lossRec = recs.find((r) => r.kind === "LOSS");
    expect(lossRec).toBeDefined();
    // 50만 전량 실현에 35만 부족 → 손실 4주(40만) 매도
    expect(lossRec!.shares).toBe(4);
    expect(profitSum).toBe(500_000);
    expect(profitSum).toBeLessThanOrEqual(150_000 + Math.abs(lossRec!.realizedKrw));
  });

  it("공제 잔여로 이미 전량 무세 실현이 되면 손실 통산 추천은 비어 있다(같은 목록 중복 방지)", () => {
    const loss = makePos({ ticker: "MSFT", qty: 10, unrealized_pnl_krw: -1_000_000 });
    const { result } = renderHook(() => useTaxSimulation([profit, loss], 0));
    expect(result.current.recommendations[0]!.label).toContain("전량");
    expect(result.current.lossHarvestRecommendations).toEqual([]);
  });

  it("공제를 넘겨 실현했고 손실 종목이 없으면 추천이 없다", () => {
    const { result } = renderHook(() => useTaxSimulation([profit], 3_000_000));
    expect(result.current.recommendations).toEqual([]);
  });

  it("손실이 미실현 손실 전체를 무조건 예산에 더하지 않는다 — 수익이 없으면 손실 매도도 추천하지 않는다", () => {
    const loss = makePos({ ticker: "MSFT", qty: 10, unrealized_pnl_krw: -1_000_000 });
    const { result } = renderHook(() => useTaxSimulation([loss], 3_000_000));
    expect(result.current.recommendations).toEqual([]);
    expect(result.current.lossHarvestRecommendations).toEqual([]);
  });

  it("올해 실현 손실은 공제 잔여를 늘린다", () => {
    const big = makePos({ ticker: "NVDA", qty: 10, unrealized_pnl_krw: 3_000_000 });
    const { result } = renderHook(() => useTaxSimulation([big], -500_000));
    expect(result.current.remainingDeduction).toBe(TAX_DEDUCTION + 500_000);
    expect(result.current.recommendations[0]!.label).toContain("전량");
  });

  it("주당 수익이 잔여보다 큰 종목은 건너뛰고 주당 수익이 작은 종목을 추천한다", () => {
    // 총수익은 작지만 1주 수익 10만원
    const pricey = makePos({ ticker: "AAA", qty: 1, unrealized_pnl_krw: 100_000 });
    // 총수익은 크지만 1주 수익 1만원
    const cheap = makePos({ ticker: "BBB", qty: 100, unrealized_pnl_krw: 1_000_000 });
    const { result } = renderHook(() => useTaxSimulation([pricey, cheap], 2_450_000));
    const recs = result.current.recommendations;
    expect(recs.map((r) => r.pos.ticker)).toEqual(["BBB"]);
    expect(recs[0]!.shares).toBe(5);
  });

  it("건너뛴 수익 종목 몫으로 끌어온 손실은 추천에서 덜어낸다(plans/141 A2)", () => {
    // 공제 잔여 0: A(2주·주당 +20,000)는 손실 4주로 덮이고, B(1주 +100,000)는 남은 손실 1주로 못 덮어 건너뛴다
    const a = makePos({ ticker: "AAA", qty: 2, unrealized_pnl_krw: 40_000 });
    const b = makePos({ ticker: "BBB", qty: 1, unrealized_pnl_krw: 100_000 });
    const loss = makePos({ ticker: "LLL", qty: 5, unrealized_pnl_krw: -50_000 });
    const { result } = renderHook(() =>
      useTaxSimulation([a, b, loss], 0, { deduction: 0, rate: TAX_RATE }),
    );
    const recs = result.current.lossHarvestRecommendations;
    expect(recs.filter((r) => r.kind === "PROFIT").map((r) => r.pos.ticker)).toEqual(["AAA"]);
    const lossRec = recs.find((r) => r.kind === "LOSS");
    expect(lossRec!.shares).toBe(4);
    // 무세 불변식: 손실 통산 + 공제 잔여 ≥ 수익 실현
    const profitSum = recs
      .filter((r) => r.kind === "PROFIT")
      .reduce((s, r) => s + r.realizedKrw, 0);
    expect(Math.abs(lossRec!.realizedKrw)).toBeGreaterThanOrEqual(profitSum);
  });

  it("손실이 모자라 일부만 무세로 팔면 끌어온 손실 중 남는 몫을 덜어낸다", () => {
    // 공제 잔여 0, A(3주·주당 +30,000=90,000), 손실 5주·주당 −10,000 → 5주 끌어와 예산 50,000 → A 1주(30,000)만 → 손실 3주면 충분
    const a = makePos({ ticker: "AAA", qty: 3, unrealized_pnl_krw: 90_000 });
    const loss = makePos({ ticker: "LLL", qty: 5, unrealized_pnl_krw: -50_000 });
    const { result } = renderHook(() =>
      useTaxSimulation([a, loss], 0, { deduction: 0, rate: TAX_RATE }),
    );
    const recs = result.current.lossHarvestRecommendations;
    expect(recs.find((r) => r.kind === "PROFIT")!.shares).toBe(1);
    expect(recs.find((r) => r.kind === "LOSS")!.shares).toBe(3);
  });
});
