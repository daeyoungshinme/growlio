import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import RebalancingDiagnosisCard from "@/components/rebalancing/RebalancingDiagnosisCard";
import type { RebalancingAnalysis, RebalancingItem } from "@/api/rebalancing";
import { renderWithProviders } from "@/test/renderWithProviders";

vi.mock("@/api/rebalancing", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/rebalancing")>()),
  fetchDriftSummary: vi.fn(),
}));

import { fetchDriftSummary } from "@/api/rebalancing";

const item = (ticker: string, diff: number, target = 30): RebalancingItem =>
  ({
    ticker,
    name: ticker,
    market: ticker === "CASH" ? "KRW" : "NASDAQ",
    target_weight_pct: target,
    weight_diff_pct: diff,
  }) as RebalancingItem;

const analysis = (items: RebalancingItem[]) =>
  ({ portfolio_id: "p1", portfolio_name: "테스트", items }) as unknown as RebalancingAnalysis;

beforeEach(() => {
  vi.mocked(fetchDriftSummary).mockResolvedValue([]);
});

describe("RebalancingDiagnosisCard — 서버 알림과 같은 이탈 기준 (plans/63 P1-3)", () => {
  it("예수금 항목도 세고, 임계치와 같은 이탈은 세지 않는다", () => {
    renderWithProviders(
      <RebalancingDiagnosisCard
        analysis={analysis([item("CASH", -12, 0), item("AAPL", 5), item("MSFT", -3)])}
        alertThreshold={5}
      />,
    );
    expect(screen.getByText("리밸런싱 필요")).toBeDefined();
    expect(
      screen.getAllByText(/1개 항목이 목표 비중에서 ±5%를 넘게 벗어났습니다/).length,
    ).toBeGreaterThan(0);
  });

  it("최대 이탈이 임계치와 같으면 리밸런싱 필요가 아니다", () => {
    renderWithProviders(
      <RebalancingDiagnosisCard analysis={analysis([item("AAPL", 5)])} alertThreshold={5} />,
    );
    expect(screen.queryByText("리밸런싱 필요")).toBeNull();
    expect(screen.getByText("주의")).toBeDefined();
  });

  it("drift-summary 행의 상대 이탈 기준·시점 판정을 따른다 (plans/136)", async () => {
    vi.mocked(fetchDriftSummary).mockResolvedValue([
      {
        portfolio_id: "p1",
        portfolio_name: "테스트",
        needs_rebalancing: true,
        threshold_pct: 5,
        relative_threshold_pct: 25,
        max_drift_pct: 3,
        drifted_items_count: 1,
        timing: "HOLD",
        timing_reason: "자동 실행 시장 조건에 걸려 보류 중이에요.",
        has_alert_configured: true,
      },
    ]);
    // 목표 5% 종목이 3%p 이탈 — 절대 ±5%론 안 잡히지만 상대 25%(1.25%p)는 넘는다
    renderWithProviders(
      <RebalancingDiagnosisCard analysis={analysis([item("SMALL", 3, 5)])} alertThreshold={5} />,
    );
    expect(await screen.findByText(/^보류 · 1개 항목/)).toBeDefined();
    expect(screen.getByText("리밸런싱 필요")).toBeDefined();
  });
});
