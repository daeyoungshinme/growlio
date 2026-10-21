import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { AlertModeSection } from "@/components/rebalancing/alertModal/AlertModeSection";
import type { RebalancingAlertFormState } from "@/hooks/useRebalancingAlertForm";

const form = (mode: "AUTO" | "NOTIFY") =>
  ({
    mode,
    setMode: vi.fn(),
    notifyTime: "08:30",
    setNotifyTime: vi.fn(),
  }) as unknown as RebalancingAlertFormState;

describe("AlertModeSection — 리포트 시각 노출 (plans/63 P4-1)", () => {
  it("AUTO 모드에서도 이탈 리포트 시각을 보여 준다", () => {
    render(
      <AlertModeSection
        form={form("AUTO")}
        targetAccountIsAutoEligible
        autoExecutionAccounts={[]}
      />,
    );
    expect(screen.getByText("이탈 리포트 시각 (KST)")).toBeDefined();
  });

  it("NOTIFY 모드는 종전처럼 알림 시각으로 표시한다", () => {
    render(
      <AlertModeSection
        form={form("NOTIFY")}
        targetAccountIsAutoEligible
        autoExecutionAccounts={[]}
      />,
    );
    expect(screen.getByText("알림 시각 (KST)")).toBeDefined();
  });
});
