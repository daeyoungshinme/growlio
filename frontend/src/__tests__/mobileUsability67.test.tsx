import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { marketLabel } from "@/constants/markets";
import ChallengeMonthGrid from "@/components/invest/ChallengeMonthGrid";
import RebalancingWeightTable from "@/components/rebalancing/RebalancingWeightTable";
import type { ChallengeMonth } from "@/api/challenges";
import type { RebalancingItem } from "@/api/rebalancing";

const toastSpy = vi.fn();
vi.mock("@/utils/toast", () => ({ toast: (...args: unknown[]) => toastSpy(...args) }));

// docs/plans/67 — 모바일 사용성 정리에서 바뀐 표시 규칙
describe("marketLabel", () => {
  it("내부 변형 코드는 사람이 읽는 라벨로, 익숙한 거래소명은 그대로", () => {
    expect(marketLabel("NASDAQ_US")).toBe("NASDAQ");
    expect(marketLabel("US")).toBe("미국");
    expect(marketLabel("krx")).toBe("국내");
    expect(marketLabel("CASH")).toBe("현금");
    expect(marketLabel("KOSPI")).toBe("KOSPI");
    expect(marketLabel(null)).toBe("");
  });
});

function month(m: string, satisfied = true): ChallengeMonth {
  return { month: m, net_krw: 300_000, satisfied, target_met: satisfied };
}

describe("ChallengeMonthGrid", () => {
  it("최근 12개월만 먼저 보이고 이전 달은 더 보기로 펼친다", () => {
    const months = Array.from({ length: 14 }, (_, i) => {
      const y = 2025 + Math.floor(i / 12);
      const mm = String((i % 12) + 1).padStart(2, "0");
      return month(`${y}-${mm}`);
    });
    render(<ChallengeMonthGrid months={months} hasTarget={false} />);

    // 첫 칸에 연도 표시 — 2025-03부터 12개
    expect(screen.getByText("'25.3")).toBeInTheDocument();
    expect(screen.queryByText("'25.1")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "이전 2개월 보기" }));
    expect(screen.getByText("'25.1")).toBeInTheDocument();
  });

  it("칸을 누르면 그 달 입금액을 토스트로 알려준다 (hover 전용 title 대체)", () => {
    render(<ChallengeMonthGrid months={[month("2026-05")]} hasTarget={false} />);
    fireEvent.click(screen.getByRole("button", { name: /2026/ }));
    expect(toastSpy).toHaveBeenCalledWith(expect.stringContaining("30만원"), "info");
  });
});

const baseItem: RebalancingItem = {
  ticker: "005930",
  name: "삼성전자",
  market: "KOSPI",
  target_weight_pct: 30,
  current_weight_pct: 25,
  weight_diff_pct: 5,
  current_value_krw: 2_500_000,
  target_value_krw: 3_000_000,
  diff_krw: 500_000,
  shares_to_trade: 7,
  current_price_krw: 70_000,
  current_qty: 35,
  target_qty: 42,
};

describe("RebalancingWeightTable 모바일 카드", () => {
  it("첫 줄에 할 일(매수 N주 · 금액), 가격·수수료는 탭해서 펼친다", () => {
    render(<RebalancingWeightTable items={[baseItem]} />);
    expect(screen.getByText(/매수 7주/)).toBeInTheDocument();
    expect(screen.getByText("25.0% → 목표 30.0%")).toBeInTheDocument();
    expect(screen.queryByText("보유 35주 → 42주")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /삼성전자/ }));
    expect(screen.getByText("보유 35주 → 42주")).toBeInTheDocument();
  });

  it("거래할 게 없으면 유지로 표시하고 펼칠 수 없다", () => {
    render(
      <RebalancingWeightTable
        items={[{ ...baseItem, diff_krw: 0, shares_to_trade: 0, weight_diff_pct: 0 }]}
      />,
    );
    expect(screen.getByText("유지")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /삼성전자/ })).toBeDisabled();
  });
});
