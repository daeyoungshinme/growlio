import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import type { RebalancingAlert } from "@/api/alerts";
import AutomationStatusBar from "@/components/rebalancing/AutomationStatusBar";

const alert = (over: Partial<RebalancingAlert>) =>
  ({
    mode: "NOTIFY",
    is_active: true,
    threshold_pct: 5,
    relative_threshold_pct: null,
    schedule_type: "DAILY",
    trigger_condition: "DRIFT_ONLY",
    strategy: "BUY_ONLY",
    schedule_day_of_month: null,
    ...over,
  }) as RebalancingAlert;

describe("AutomationStatusBar compact (포트폴리오 카드 칩)", () => {
  it("알림 없음 → 자동화 설정", () => {
    render(<AutomationStatusBar onOpenAlertModal={vi.fn()} compact />);
    expect(screen.getByText("자동화 설정")).toBeInTheDocument();
  });

  it("꺼진 알림 → 꺼짐 (plans/145 A2 — 예전엔 is_active를 안 넘겨 표시되지 않았다)", () => {
    render(
      <AutomationStatusBar
        existingAlert={alert({ mode: "AUTO", is_active: false })}
        onOpenAlertModal={vi.fn()}
        compact
      />,
    );
    expect(screen.getByText("꺼짐")).toBeInTheDocument();
    expect(screen.queryByText("자동")).not.toBeInTheDocument();
  });

  it("켜진 AUTO → 자동, NOTIFY → 알림", () => {
    const { rerender } = render(
      <AutomationStatusBar
        existingAlert={alert({ mode: "AUTO" })}
        onOpenAlertModal={vi.fn()}
        compact
      />,
    );
    expect(screen.getByText("자동")).toBeInTheDocument();
    rerender(<AutomationStatusBar existingAlert={alert({})} onOpenAlertModal={vi.fn()} compact />);
    expect(screen.getByText("알림")).toBeInTheDocument();
  });

  it("적립식 자동매수 프리셋 → 적립매수", () => {
    render(
      <AutomationStatusBar
        existingAlert={alert({
          mode: "AUTO",
          schedule_type: "MONTHLY",
          trigger_condition: "SCHEDULE_ONLY",
          schedule_day_of_month: 10,
        })}
        onOpenAlertModal={vi.fn()}
        compact
      />,
    );
    expect(screen.getByText("적립매수")).toBeInTheDocument();
  });

  it("탭하면 모달 열기 — 카드 선택으로 전파하지 않는다", () => {
    const onOpen = vi.fn();
    const onCard = vi.fn();
    render(
      <div onClick={onCard}>
        <AutomationStatusBar onOpenAlertModal={onOpen} compact />
      </div>,
    );
    fireEvent.click(screen.getByRole("button"));
    expect(onOpen).toHaveBeenCalledOnce();
    expect(onCard).not.toHaveBeenCalled();
  });
});
