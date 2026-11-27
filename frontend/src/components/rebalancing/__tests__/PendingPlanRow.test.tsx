import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { RebalancingPlanLegSummary } from "@/api/rebalancingPlan";
import PendingPlanRow from "../PendingPlanRow";

const leg = (over: Partial<RebalancingPlanLegSummary> = {}): RebalancingPlanLegSummary => ({
  plan_id: "p1",
  leg_id: "l1",
  portfolio_id: "pf1",
  portfolio_name: "코어",
  account_id: "a1",
  account_name: "키움",
  side: "BUY",
  status: "PENDING",
  deadline_at: new Date(Date.now() + 3_600_000).toISOString(),
  decided_at: null,
  execution_id: null,
  error_message: null,
  actionable: true,
  partially_executed: false,
  items: [
    {
      ticker: "QQQ",
      name: "Invesco QQQ",
      market: "NASDAQ",
      quantity: 2,
      account_id: "a1",
      order_type: "LIMIT",
      limit_price: 712_300,
      reference_price: 712_300,
    },
  ],
  ...over,
});

const noop = vi.fn();

describe("PendingPlanRow (plans/156 B5)", () => {
  it("항목 가격을 원 단위로 보인다 — 메일 확인 페이지와 같은 표기", () => {
    render(
      <PendingPlanRow
        leg={leg()}
        onCancel={noop}
        onApprove={noop}
        onRetryFx={noop}
        isPending={false}
      />,
    );
    fireEvent.click(screen.getAllByRole("button")[0]!);
    expect(screen.getAllByText("712,300원").length).toBeGreaterThan(0);
  });

  it("환전 대기 달러가 없으면 $0.00 대신 —", () => {
    render(
      <PendingPlanRow
        leg={leg({ status: "WAITING_FX", required_usd: 1234.5, available_usd: null })}
        onCancel={noop}
        onApprove={noop}
        onRetryFx={noop}
        isPending={false}
      />,
    );
    expect(screen.getByText(/필요 \$1,234\.5 · 보유 —/)).toBeDefined();
  });
});
