import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import type { AccountRow, PortfolioOverview } from "@/types";

// 차트는 테마 스토어(matchMedia)를 읽는다 — 이 테스트는 실패 표시만 본다
vi.mock("@/stores/themeStore", () => ({
  useThemeStore: (sel?: (s: { isDark: boolean }) => unknown) =>
    sel ? sel({ isDark: false }) : { isDark: false },
}));

const refetch = vi.fn();
vi.mock("@/hooks/useAllocationHistory", () => ({
  useAllocationHistory: () => ({
    isLoading: false,
    isError: true,
    refetch,
    chartData: [],
    allTypes: [],
    labelMap: {},
    reversedMonthly: [],
  }),
}));

import HorizonSummaryCard from "@/components/portfolio/HorizonSummaryCard";
import AllocationHistoryChart from "@/components/dashboard/AllocationHistoryChart";

function excludedTaggedAccount(): AccountRow {
  return {
    id: "a1",
    name: "연금 계좌",
    asset_type: "STOCK_KIS",
    asset_type_label: "KIS",
    data_source: "KIS_API",
    institution: null,
    amount_krw: 10_000_000,
    invested_krw: 9_000_000,
    unrealized_pnl: 1_000_000,
    position_count: 1,
    positions: [],
    investment_horizon: "LONG_TERM",
    include_in_total: false,
  };
}

describe("HorizonSummaryCard (plans/146 C3)", () => {
  const overview = { accounts: [excludedTaggedAccount()] } as unknown as PortfolioOverview;

  it("전체 보기에선 합산 제외 계좌를 뺀다", () => {
    const { container } = render(<HorizonSummaryCard overview={overview} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("계좌를 직접 고르면 합산 제외여도 보인다", () => {
    const { container } = render(<HorizonSummaryCard overview={overview} accountSelected />);
    expect(container).not.toBeEmptyDOMElement();
  });
});

describe("AllocationHistoryChart (plans/146 C4)", () => {
  it("조회 실패를 빈 상태가 아니라 실패 + 다시 시도로 보인다", () => {
    render(<AllocationHistoryChart onCollapse={vi.fn()} title="자산 추이" />);
    expect(screen.getByText("자산 추이를 불러오지 못했습니다.")).toBeInTheDocument();
    expect(screen.queryByText("아직 자산 추이 데이터가 없습니다")).toBeNull();
    fireEvent.click(screen.getByText("다시 시도"));
    expect(refetch).toHaveBeenCalled();
  });
});
