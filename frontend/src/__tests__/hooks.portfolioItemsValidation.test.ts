import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { PortfolioItem } from "@/api/portfolios";
import {
  getPortfolioItemsError,
  submittablePortfolioItems,
  usePortfolioItemsEditor,
} from "@/hooks/usePortfolioItemsEditor";

vi.mock("@/api/assets", () => ({ searchStocks: vi.fn().mockResolvedValue([]) }));

const item = (ticker: string, weight: number): PortfolioItem => ({
  ticker,
  name: ticker,
  market: "KOSPI",
  weight,
});

describe("getPortfolioItemsError", () => {
  it("합계가 100이어도 음수 비중은 거부한다", () => {
    expect(getPortfolioItemsError([item("A", 110), item("B", -10)])).toMatch("0~100");
  });

  it("종목 없는 행에 비중이 있으면 거부한다", () => {
    expect(getPortfolioItemsError([item("A", 60), item("", 40)])).toMatch("종목을 선택하지 않은");
  });

  it("종목 없는 0% 빈 행은 허용하고 저장 대상에서 뺀다", () => {
    const items = [item("A", 100), item("", 0)];
    expect(getPortfolioItemsError(items)).toBeNull();
    expect(submittablePortfolioItems(items).map((i) => i.ticker)).toEqual(["A"]);
  });
});

describe("usePortfolioItemsEditor removeItem", () => {
  it("위 행을 지우면 편집·활성 행 인덱스도 함께 당긴다 (plans/156 B2)", () => {
    const { result } = renderHook(() =>
      usePortfolioItemsEditor([item("A", 30), item("B", 30), item("C", 40)]),
    );
    act(() => result.current.startEditing(2));
    act(() => result.current.setActiveRow(2));
    act(() => result.current.removeItem(0));

    // startEditing은 그 행의 종목을 비운다 — C 자리가 이제 1번
    expect(result.current.items.map((i) => i.weight)).toEqual([30, 40]);
    expect(result.current.items[0]?.ticker).toBe("B");
    expect([...result.current.editingRows]).toEqual([1]);
    expect(result.current.activeRow).toBe(1);
  });

  it("지운 행이 편집·활성 행이면 상태를 비운다", () => {
    const { result } = renderHook(() => usePortfolioItemsEditor([item("A", 50), item("B", 50)]));
    act(() => result.current.startEditing(1));
    act(() => result.current.setActiveRow(1));
    act(() => result.current.removeItem(1));

    expect(result.current.editingRows.size).toBe(0);
    expect(result.current.activeRow).toBeNull();
  });
});
