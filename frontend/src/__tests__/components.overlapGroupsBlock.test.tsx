import { describe, it, expect } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";
import OverlapGroupsBlock from "@/components/rebalancing/OverlapGroupsBlock";
import type { OverlapGroup, OverlapMember } from "@/api/rebalancing";

function member(overrides: Partial<OverlapMember> = {}): OverlapMember {
  return {
    ticker: "360750",
    name: "TIGER 미국S&P500",
    market: "KOSPI",
    held: false,
    candidate: true,
    ter_pct: 0.0068,
    base_index: "S&P 500",
    ...overrides,
  };
}

function group(overrides: Partial<OverlapGroup> = {}): OverlapGroup {
  return {
    reasons: ["SAME_INDEX"],
    max_correlation: null,
    members: [
      member({
        ticker: "360200",
        name: "ACE 미국S&P500",
        held: true,
        candidate: false,
        ter_pct: 0.0047,
      }),
      member(),
    ],
    cheapest_ticker: "360200",
    cheapest_market: "KOSPI",
    ter_gap_pct: 0.0021,
    ...overrides,
  };
}

describe("OverlapGroupsBlock", () => {
  it("그룹이 없으면 렌더하지 않는다", () => {
    const { container } = renderWithProviders(
      <OverlapGroupsBlock groups={[]} weightByKey={new Map()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("기본 접힘 상태에서 묶음 수와 보유 종목 힌트를 보여준다", () => {
    renderWithProviders(<OverlapGroupsBlock groups={[group()]} weightByKey={new Map()} />);
    expect(screen.getByText("중복 투자 점검 · 1개 묶음")).toBeInTheDocument();
    expect(screen.getByText("보유 종목과 겹치는 묶음 1개 포함")).toBeInTheDocument();
    expect(screen.queryByText("ACE 미국S&P500")).toBeNull();
  });

  it("펼치면 멤버·보유 표시·추천 비중·최저 보수·연 비용 차이를 보여준다", () => {
    renderWithProviders(
      <OverlapGroupsBlock groups={[group()]} weightByKey={new Map([["360750:KOSPI", 30]])} />,
    );
    fireEvent.click(screen.getByText("중복 투자 점검 · 1개 묶음"));

    expect(screen.getByText("ACE 미국S&P500")).toBeInTheDocument();
    expect(screen.getByText("· 보유 중")).toBeInTheDocument();
    expect(screen.getByText("· 추천 30.0%")).toBeInTheDocument();
    expect(screen.getByText(/· 최저/)).toBeInTheDocument();
    // 0.0021%p × 1,000만원 = 연 약 210원
    expect(screen.getByText(/1,000만원 보유 시 연 약\s*210원/)).toBeInTheDocument();
  });

  it("보수 정보가 없는 멤버는 확인 불가로 표시한다", () => {
    renderWithProviders(
      <OverlapGroupsBlock
        groups={[
          group({
            members: [member({ ter_pct: null }), member({ ticker: "SPY", market: "NYSE" })],
            cheapest_ticker: null,
            cheapest_market: null,
            ter_gap_pct: null,
          }),
        ]}
        weightByKey={new Map()}
      />,
    );
    fireEvent.click(screen.getByText("중복 투자 점검 · 1개 묶음"));
    expect(screen.getByText("보수 확인 불가")).toBeInTheDocument();
  });
});
