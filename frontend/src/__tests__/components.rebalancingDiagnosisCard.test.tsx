import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import RebalancingDiagnosisCard from "@/components/rebalancing/RebalancingDiagnosisCard";
import type { RebalancingAnalysis, RebalancingItem } from "@/api/rebalancing";

const item = (ticker: string, diff: number): RebalancingItem =>
  ({
    ticker,
    name: ticker,
    market: ticker === "CASH" ? "KRW" : "NASDAQ",
    weight_diff_pct: diff,
  }) as RebalancingItem;

const analysis = (items: RebalancingItem[]) =>
  ({ portfolio_id: "p1", portfolio_name: "테스트", items }) as unknown as RebalancingAnalysis;

describe("RebalancingDiagnosisCard — 서버 알림과 같은 이탈 기준 (plans/63 P1-3)", () => {
  it("예수금 항목도 세고, 임계치와 같은 이탈은 세지 않는다", () => {
    render(
      <RebalancingDiagnosisCard
        analysis={analysis([item("CASH", -12), item("AAPL", 5), item("MSFT", -3)])}
        alertThreshold={5}
      />,
    );
    expect(screen.getByText("리밸런싱 필요")).toBeDefined();
    expect(
      screen.getAllByText(/1개 항목이 목표 비중에서 ±5%를 넘게 벗어났습니다/).length,
    ).toBeGreaterThan(0);
  });

  it("최대 이탈이 임계치와 같으면 리밸런싱 필요가 아니다", () => {
    render(<RebalancingDiagnosisCard analysis={analysis([item("AAPL", 5)])} alertThreshold={5} />);
    expect(screen.queryByText("리밸런싱 필요")).toBeNull();
    expect(screen.getByText("주의")).toBeDefined();
  });
});
