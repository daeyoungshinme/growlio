import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import type { SuggestedGoalCandidate } from "@/api/rebalancing";
import SuggestedCandidatesBlock from "@/components/rebalancing/SuggestedCandidatesBlock";

function makeCandidate(overrides: Partial<SuggestedGoalCandidate> = {}): SuggestedGoalCandidate {
  return {
    ticker: "JEPQ",
    name: "JPMorgan Nasdaq Equity Premium Income ETF",
    market: "NASDAQ",
    asset_class: "EQUITY",
    dividend_yield_pct: 9.95,
    ...overrides,
  };
}

describe("SuggestedCandidatesBlock", () => {
  it("후보 목록이 비어 있으면 아무것도 렌더링하지 않는다", () => {
    const { container } = render(
      <SuggestedCandidatesBlock candidates={[]} onAdd={vi.fn()} isPending={false} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("후보 배지와 배당수익률, '후보에 추가' 버튼을 렌더링한다", () => {
    render(
      <SuggestedCandidatesBlock candidates={[makeCandidate()]} onAdd={vi.fn()} isPending={false} />,
    );
    expect(screen.getByText(/Nasdaq Equity Premium/)).toBeDefined();
    expect(screen.getByText(/연 9\.9%/)).toBeDefined();
    expect(screen.getByText("후보에 추가")).toBeDefined();
  });

  it("배당수익률 데이터가 없으면 괄호 표시를 생략한다", () => {
    render(
      <SuggestedCandidatesBlock
        candidates={[makeCandidate({ dividend_yield_pct: null })]}
        onAdd={vi.fn()}
        isPending={false}
      />,
    );
    expect(screen.queryByText(/연 /)).toBeNull();
  });

  it("버튼 클릭 시 onAdd를 호출한다", () => {
    const onAdd = vi.fn();
    render(
      <SuggestedCandidatesBlock candidates={[makeCandidate()]} onAdd={onAdd} isPending={false} />,
    );

    fireEvent.click(screen.getByText("후보에 추가"));

    expect(onAdd).toHaveBeenCalledTimes(1);
  });

  it("isPending일 때 버튼이 비활성화된다", () => {
    render(
      <SuggestedCandidatesBlock candidates={[makeCandidate()]} onAdd={vi.fn()} isPending={true} />,
    );

    expect(screen.getByText("후보에 추가").closest("button")).toHaveProperty("disabled", true);
  });
});
